"""Gap #5: Refine plant flowering months using iNaturalist phenology
histograms.

For each plant species (taxon_group in {plant, tree, shrub, herb, vine,
fern, moss}) with an inat_taxon_id, query the histogram endpoint:
  /v1/observations/histogram?taxon_id=X&place_id=6803&interval=month_of_year
                            &term_id=12&term_value_id=13&verifiable=true

Annotation 12 = 'Plant Phenology', value 13 = 'Flowering'.
Place 6803 = Japan.

Strategy:
  1. Try flowering-only counts.
  2. If total ≤ 30 (annotation sparse), fall back to all-observations.
  3. Pick months where count >= 0.4 * max as 'primary'.
  4. Insert one observation row per (park, species) where the species is
     already known to be at that park, with our derived months_bitmap and
     location_hint = 'iNat phenology'. Existing rows are preserved.

After ingestion, run dedupe + exports — the per-pair months_bitmap will
OR with TMG/iNat data, narrowing the bloom window where applicable.

Cache: data/cache/inat_phenology/<taxon_id>.json
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from curl_cffi import requests

from parklife import db

ROOT = Path(__file__).resolve().parent.parent
UA = "parklife-bot/0.1 (research; contact: paranoid2droid@gmail.com)"
API = "https://api.inaturalist.org/v1/observations/histogram"
JAPAN_PLACE = 6737  # iNat place_id for Japan (verified via /places/autocomplete)

CACHE = ROOT / "data" / "cache" / "inat_phenology"
PLANT_GROUPS = ("plant", "tree", "shrub", "herb", "vine", "fern", "moss")

PEAK_RATIO_THRESHOLD = 0.4   # months ≥ 40% of max are 'in bloom'
FLOWERING_TOTAL_FLOOR = 30   # below this, annotations are too sparse


def _cache(taxon_id: int, kind: str) -> Path:
    return CACHE / f"{taxon_id}__{kind}.json"


def fetch(taxon_id: int, with_flowering: bool) -> dict:
    kind = "flower" if with_flowering else "all"
    cp = _cache(taxon_id, kind)
    cp.parent.mkdir(parents=True, exist_ok=True)
    if cp.exists():
        try:
            return json.loads(cp.read_text(encoding="utf-8"))
        except Exception:
            pass
    params = {
        "taxon_id": taxon_id, "place_id": JAPAN_PLACE,
        "interval": "month_of_year", "verifiable": "true",
    }
    if with_flowering:
        params["term_id"] = 12
        params["term_value_id"] = 13
    r = requests.get(API, params=params, headers={"User-Agent": UA},
                     impersonate="chrome", timeout=20)
    if r.status_code != 200:
        return {}
    data = r.json()
    cp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def months_bitmap_from_histogram(counts: dict) -> tuple[int, int]:
    """Return (bitmap, total). bitmap=0 if no signal."""
    months: dict[int, int] = {}
    for k, v in counts.items():
        try:
            months[int(k)] = int(v)
        except Exception:
            continue
    if not months:
        return (0, 0)
    total = sum(months.values())
    if total == 0:
        return (0, 0)
    peak = max(months.values())
    threshold = peak * PEAK_RATIO_THRESHOLD
    bits = 0
    for m, count in months.items():
        if count >= threshold and 1 <= m <= 12:
            bits |= 1 << (m - 1)
    return (bits, total)


def main(limit: int | None = None) -> int:
    db_path = ROOT / "data" / "parklife.db"
    placeholders = ",".join("?" * len(PLANT_GROUPS))
    with db.connect(db_path) as conn:
        species_rows = list(conn.execute(f"""
            SELECT id, scientific_name, common_name_ja, inat_taxon_id, taxon_group
            FROM species
            WHERE inat_taxon_id IS NOT NULL
              AND taxon_group IN ({placeholders})
            ORDER BY id
        """, PLANT_GROUPS))
    if limit:
        species_rows = species_rows[:limit]
    print(f"plant species with inat_taxon_id: {len(species_rows)}")

    inserted = updated_existing = api_calls = cache_hits = 0
    skipped_no_signal = skipped_year_round = 0

    with db.connect(db_path) as conn:
        for i, sp in enumerate(species_rows, 1):
            tid = sp["inat_taxon_id"]
            # try flowering filter first
            data_f = fetch(tid, with_flowering=True)
            api_calls += 1
            if _cache(tid, "flower").exists() and data_f:
                cache_hits += 1
            else:
                time.sleep(0.6)

            counts = (data_f.get("results") or {}).get("month_of_year", {})
            bits, total = months_bitmap_from_histogram(counts)

            # fallback to all-observations if too few flowering annotations
            used_fallback = False
            if total < FLOWERING_TOTAL_FLOOR:
                data_a = fetch(tid, with_flowering=False)
                api_calls += 1
                if _cache(tid, "all").exists() and data_a:
                    cache_hits += 1
                else:
                    time.sleep(0.6)
                counts = (data_a.get("results") or {}).get("month_of_year", {})
                bits, total = months_bitmap_from_histogram(counts)
                used_fallback = True

            if bits == 0:
                skipped_no_signal += 1
                continue
            # year-round signal isn't useful for bloom narrowing
            if bits == (1 << 12) - 1:
                skipped_year_round += 1
                continue

            # find parks where this species is already known
            parks = list(conn.execute(
                "SELECT DISTINCT park_id FROM observation WHERE species_id=?",
                (sp["id"],),
            ))
            if not parks:
                continue

            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            url = (f"{API}?taxon_id={tid}&place_id={JAPAN_PLACE}"
                    f"&interval=month_of_year"
                    f"&term_id=12&term_value_id=13"
                    f"&fallback={'all' if used_fallback else 'flowering'}")
            cur = conn.execute(
                """INSERT OR IGNORE INTO source (park_id, url, fetched_at, http_status,
                                                 content_sha256, raw_path)
                   VALUES (NULL, ?, ?, 200, NULL, ?)""",
                (url, now, f"data/cache/inat_phenology/{tid}__{'all' if used_fallback else 'flower'}.json"),
            )
            src_id = cur.lastrowid
            if not src_id:
                row = conn.execute(
                    "SELECT id FROM source WHERE url=? ORDER BY id DESC LIMIT 1", (url,),
                ).fetchone()
                src_id = row["id"] if row else None

            for p in parks:
                exists = conn.execute(
                    """SELECT id FROM observation
                       WHERE park_id=? AND species_id=? AND source_id=?""",
                    (p["park_id"], sp["id"], src_id),
                ).fetchone()
                if exists:
                    continue
                raw = sp["common_name_ja"] or sp["scientific_name"]
                conn.execute(
                    """INSERT INTO observation
                       (park_id, species_id, raw_name, months_bitmap,
                        location_hint, characteristics, source_id)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (p["park_id"], sp["id"], raw, bits,
                     "iNat phenology", f"total={total} fallback={used_fallback}", src_id),
                )
                inserted += 1
            conn.commit()
            if i % 50 == 0:
                print(f"  [{i:>4}/{len(species_rows)}] inserted={inserted} "
                      f"no_signal={skipped_no_signal} year_round={skipped_year_round} "
                      f"api={api_calls} cache={cache_hits}")

    print(f"\n=== plant_phenology done ===")
    print(f"  species processed: {len(species_rows)}")
    print(f"  observations inserted: {inserted}")
    print(f"  skipped (no signal): {skipped_no_signal}")
    print(f"  skipped (year-round signal): {skipped_year_round}")
    print(f"  api calls: {api_calls}  cache hits: {cache_hits}")
    return 0


if __name__ == "__main__":
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    sys.exit(main(limit))
