"""Add monthly seasonality to iNaturalist observations.

For each park × taxon, loop over months 1..12 and query
species_counts?month=N to learn which species are observed in that month.
We then UPDATE existing observation rows by OR-ing the month bit into
months_bitmap, and INSERT new species that only show up in month-filtered
results (rare but possible).

Default: only birds (Aves, taxon_id=3) since they're the main use case
for `bloom <month>` queries. Pass alternate taxa as args.

Cache: data/cache/inat_monthly/<prefecture>__<slug>__<taxon>__<month>.json
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from curl_cffi import requests

from parklife import db

ROOT = Path(__file__).resolve().parent.parent
UA = "parklife-bot/0.1 (research; contact: paranoid2droid@gmail.com)"
API = "https://api.inaturalist.org/v1/observations/species_counts"
RADIUS_KM = 1.5
PER_PAGE = 100

# (taxon_id, label, our taxon_group). Extend as needed; keep our internal
# taxon_group strings consistent with parklife.normalize.wikipedia.
TAXA = {
    "bird":      ("3",     "Aves"),
    "mammal":    ("40151", "Mammalia"),
    "reptile":   ("26036", "Reptilia"),
    "amphibian": ("20978", "Amphibia"),
    "insect":    ("47158", "Insecta"),
    "arachnid":  ("47119", "Arachnida"),
    "mollusk":   ("47115", "Mollusca"),
    "fish":      ("47178", "Actinopterygii"),
}


def cache_path(prefecture: str, slug: str, taxon: str, month: int) -> Path:
    return ROOT / "data" / "cache" / "inat_monthly" / f"{prefecture}__{slug}__{taxon}__{month:02d}.json"


def fetch_month(prefecture: str, slug: str, lat: float, lon: float,
                taxon_id: str, month: int) -> tuple[str, dict]:
    cp = cache_path(prefecture, slug, taxon_id, month)
    cp.parent.mkdir(parents=True, exist_ok=True)
    if cp.exists():
        return ("cache", json.loads(cp.read_text(encoding="utf-8")))
    params = {
        "lat": lat, "lng": lon, "radius": RADIUS_KM,
        "taxon_id": taxon_id, "month": month,
        "quality_grade": "research", "captive": "false",
        "per_page": PER_PAGE, "locale": "ja",
    }
    r = requests.get(
        API, params=params, headers={"User-Agent": UA, "Accept-Language": "ja"},
        impersonate="chrome", timeout=30,
    )
    if r.status_code != 200:
        return (f"http{r.status_code}", {"results": [], "total_results": 0})
    data = r.json()
    cp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return ("network", data)


def main(taxon_keys: list[str], pref_filter: str | None = None,
         max_parks: int | None = None) -> int:
    db_path = ROOT / "data" / "parklife.db"

    # Pre-resolve taxa
    taxa = []
    for k in taxon_keys:
        if k not in TAXA:
            print(f"unknown taxon key: {k} (allowed: {list(TAXA)})")
            return 2
        tid, label = TAXA[k]
        taxa.append((tid, label, k))

    with db.connect(db_path) as conn:
        sql = ("SELECT id, slug, prefecture, lat, lon, name_ja FROM park "
               "WHERE lat IS NOT NULL AND lon IS NOT NULL")
        params: list = []
        if pref_filter:
            sql += " AND prefecture=?"; params.append(pref_filter)
        sql += " ORDER BY prefecture, name_ja"
        parks = list(conn.execute(sql, params))
    if max_parks:
        parks = parks[:max_parks]
    total_calls = 12 * len(taxa) * len(parks)
    print(f"parks: {len(parks)}; taxa: {[t[2] for t in taxa]}; "
          f"total calls: {total_calls}; eta: ~{total_calls * 0.8 / 60:.0f} min")

    updates = 0
    inserts = 0
    cache_hits = 0
    api_calls = 0

    with db.connect(db_path) as conn:
        for i, p in enumerate(parks, 1):
            for taxon_id, taxon_label, group in taxa:
                for month in range(1, 13):
                    src, data = fetch_month(p["prefecture"], p["slug"],
                                             p["lat"], p["lon"], taxon_id, month)
                    api_calls += 1
                    if src == "cache":
                        cache_hits += 1
                    else:
                        time.sleep(0.7)
                    bit = 1 << (month - 1)
                    for r in (data.get("results") or []):
                        t = r.get("taxon") or {}
                        sci = t.get("name")
                        ja = t.get("preferred_common_name")
                        if ja and not any(0x3040 <= ord(c) <= 0x30FF or 0x4E00 <= ord(c) <= 0x9FFF for c in ja):
                            ja = None
                        # find existing species
                        sp = None
                        if sci:
                            sp = conn.execute("SELECT id FROM species WHERE scientific_name=?", (sci,)).fetchone()
                        if not sp and ja:
                            sp = conn.execute("SELECT id FROM species WHERE common_name_ja=?", (ja,)).fetchone()
                        if not sp:
                            # rare: new species — insert
                            cur = conn.execute(
                                """INSERT INTO species (scientific_name, common_name_ja, kingdom, taxon_group)
                                   VALUES (?, ?, ?, ?)""",
                                (sci, ja, "animalia", group),
                            )
                            sp_id = cur.lastrowid
                            inserts += 1
                        else:
                            sp_id = sp["id"]
                        # find existing observation for (park, species, iNat source)
                        existing = conn.execute(
                            """SELECT id, months_bitmap FROM observation
                               WHERE park_id=? AND species_id=?
                               AND location_hint = 'iNaturalist (research grade)'""",
                            (p["id"], sp_id),
                        ).fetchone()
                        if existing:
                            cur_bits = existing["months_bitmap"] or 0
                            new_bits = cur_bits | bit
                            if new_bits != cur_bits:
                                conn.execute(
                                    "UPDATE observation SET months_bitmap=? WHERE id=?",
                                    (new_bits, existing["id"]),
                                )
                                updates += 1
                        else:
                            # no existing iNat obs row — create one with this month's bit
                            raw = ja or sci
                            conn.execute(
                                """INSERT INTO observation
                                   (park_id, species_id, raw_name, months_bitmap,
                                    location_hint, characteristics, source_id)
                                   VALUES (?, ?, ?, ?, 'iNaturalist (research grade)', NULL, NULL)""",
                                (p["id"], sp_id, raw, bit),
                            )
                            inserts += 1
            conn.commit()
            if i % 5 == 0 or i == len(parks):
                print(f"  [{i:>3}/{len(parks)}] {p['slug']:<25} "
                      f"updates={updates} inserts={inserts} "
                      f"calls={api_calls} cache={cache_hits}")
    print(f"\n=== monthly enrichment done ===")
    print(f"  api calls: {api_calls}  cache hits: {cache_hits}")
    print(f"  observations updated (months bit OR'd): {updates}")
    print(f"  observations inserted: {inserts}")
    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    keys = ["bird"]
    pref = None
    cap = None
    if args and args[0] in TAXA:
        keys = [args.pop(0)]
        # allow comma-separated
    elif args and "," in args[0]:
        keys = args.pop(0).split(",")
    if args and args[0] in {"tokyo","kanagawa","chiba","saitama"}:
        pref = args.pop(0)
    if args:
        cap = int(args[0])
    sys.exit(main(keys, pref_filter=pref, max_parks=cap))
