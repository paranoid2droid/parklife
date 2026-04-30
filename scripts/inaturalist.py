"""Phase D: enrich parks with iNaturalist research-grade species observations.

For each park with lat/lon, query iNaturalist's species_counts endpoint for
each iconic taxon. Insert observations linked to species_alias entries
keyed on `preferred_common_name` (Japanese vernacular name when locale=ja).

Why species_counts instead of /observations: it aggregates per-species so
we get a clean "is X seen near this park" answer in one call. Each result
includes scientific name, common name, and total observation count.

Rate limits: iNaturalist asks for ≤60 req/min — we use 0.6 s sleep
between calls (≈100 req/min cap, but with parallel taxa we may dip lower).
Cached per (park_slug, taxon_id) under data/cache/inat/.

Idempotency: source URL encodes the query, so repeated runs append a new
source row but observation upsert ((park_id, raw_name, season=NULL)) skips
duplicates.
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
API = "https://api.inaturalist.org/v1/observations/species_counts"

# (taxon_id, label, our taxon_group)
ICONIC = [
    ("3",     "Aves",      "bird"),
    ("40151", "Mammalia",  "mammal"),
    ("26036", "Reptilia",  "reptile"),
    ("20978", "Amphibia",  "amphibian"),
    ("47158", "Insecta",   "insect"),
    ("47119", "Arachnida", "arachnid"),
    ("47115", "Mollusca",  "mollusk"),
    ("47178", "Actinopterygii", "fish"),
]

# 'Plantae' covers an enormous number; cap top N
PLANTAE = ("47126", "Plantae", "plant")

PER_PAGE = 100
RADIUS_KM = 1.5  # most TMG/県立 parks fit


def cache_path(slug: str, prefecture: str, taxon: str) -> Path:
    return ROOT / "data" / "cache" / "inat" / f"{prefecture}__{slug}__{taxon}.json"


def fetch(park_slug: str, prefecture: str, lat: float, lon: float, taxon_id: str,
          *, radius_km: float = RADIUS_KM, per_page: int = PER_PAGE) -> tuple[str, dict]:
    cp = cache_path(park_slug, prefecture, taxon_id)
    cp.parent.mkdir(parents=True, exist_ok=True)
    if cp.exists():
        return ("cache", json.loads(cp.read_text(encoding="utf-8")))
    params = {
        "lat": lat, "lng": lon, "radius": radius_km,
        "taxon_id": taxon_id, "quality_grade": "research",
        "captive": "false", "per_page": per_page, "locale": "ja",
    }
    r = requests.get(
        API, params=params, headers={"User-Agent": UA, "Accept-Language": "ja"},
        timeout=30, impersonate="chrome",
    )
    if r.status_code != 200:
        return (f"http{r.status_code}", {"results": [], "total_results": 0})
    data = r.json()
    cp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return ("network", data)


def upsert_species(conn, sci_name: str | None, ja_name: str | None,
                    en_name: str | None, kingdom: str | None, taxon_group: str | None) -> int | None:
    """Find or create a species. Match priority: scientific_name → common_name_ja."""
    if not (sci_name or ja_name):
        return None
    row = None
    if sci_name:
        row = conn.execute("SELECT id FROM species WHERE scientific_name=?", (sci_name,)).fetchone()
    if not row and ja_name:
        row = conn.execute("SELECT id FROM species WHERE common_name_ja=?", (ja_name,)).fetchone()
    if row:
        sid = row["id"]
        conn.execute(
            """UPDATE species SET scientific_name = COALESCE(scientific_name, ?),
                                  common_name_ja = COALESCE(common_name_ja, ?),
                                  common_name_en = COALESCE(common_name_en, ?),
                                  kingdom = COALESCE(kingdom, ?),
                                  taxon_group = COALESCE(taxon_group, ?)
               WHERE id=?""",
            (sci_name, ja_name, en_name, kingdom, taxon_group, sid),
        )
        return sid
    cur = conn.execute(
        """INSERT INTO species (scientific_name, common_name_ja, common_name_en, kingdom, taxon_group)
           VALUES (?, ?, ?, ?, ?)""",
        (sci_name, ja_name, en_name, kingdom, taxon_group),
    )
    return cur.lastrowid


def insert_source(conn, park_id: int, prefecture: str, slug: str, taxon_label: str,
                   url: str) -> int:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rel = f"data/cache/inat/{prefecture}__{slug}__{taxon_label}.json"
    cur = conn.execute(
        """INSERT OR IGNORE INTO source (park_id, url, fetched_at, http_status,
                                         content_sha256, raw_path)
           VALUES (?, ?, ?, 200, NULL, ?)""",
        (park_id, url, now, rel),
    )
    if cur.lastrowid:
        return cur.lastrowid
    # if same (url, fetched_at) collided, just look it up
    row = conn.execute(
        "SELECT id FROM source WHERE park_id=? AND url=? ORDER BY id DESC LIMIT 1",
        (park_id, url),
    ).fetchone()
    return row["id"] if row else 0


def main(prefecture_filter: str | None = None,
         taxa: list[tuple[str, str, str]] | None = None,
         max_parks: int | None = None) -> int:
    db_path = ROOT / "data" / "parklife.db"
    taxa = taxa or ICONIC

    with db.connect(db_path) as conn:
        sql = ("SELECT id, slug, prefecture, lat, lon, name_ja FROM park "
               "WHERE lat IS NOT NULL AND lon IS NOT NULL")
        params: list = []
        if prefecture_filter:
            sql += " AND prefecture=?"
            params.append(prefecture_filter)
        sql += " ORDER BY prefecture, name_ja"
        parks = list(conn.execute(sql, params))
    if max_parks:
        parks = parks[:max_parks]
    print(f"parks to enrich: {len(parks)}; taxa: {[t[1] for t in taxa]}")

    total_inserted = 0
    total_calls = 0
    cache_hits = 0

    with db.connect(db_path) as conn:
        for i, p in enumerate(parks, 1):
            park_inserted = 0
            for taxon_id, taxon_label, taxon_group in taxa:
                kingdom = "animalia" if taxon_label != "Plantae" else "plantae"
                src, data = fetch(p["slug"], p["prefecture"], p["lat"], p["lon"], taxon_id)
                total_calls += 1
                if src == "cache":
                    cache_hits += 1
                else:
                    time.sleep(0.7)  # politeness
                results = data.get("results", []) or []
                if not results:
                    continue
                api_url = (f"{API}?lat={p['lat']}&lng={p['lon']}&radius={RADIUS_KM}"
                            f"&taxon_id={taxon_id}&quality_grade=research&locale=ja")
                src_id = insert_source(conn, p["id"], p["prefecture"], p["slug"], taxon_label, api_url)
                for r in results:
                    t = r.get("taxon") or {}
                    sci = t.get("name")
                    ja = t.get("preferred_common_name") or None
                    # iNat sometimes returns English in pcn for poorly localised taxa
                    if ja and not any(0x3040 <= ord(c) <= 0x30FF or 0x4E00 <= ord(c) <= 0x9FFF for c in ja):
                        en_name, ja_name = ja, None
                    else:
                        en_name, ja_name = None, ja
                    sid = upsert_species(conn, sci, ja_name, en_name, kingdom, taxon_group)
                    if not sid:
                        continue
                    raw_name = ja_name or sci
                    if not raw_name:
                        continue
                    # link alias if not already
                    conn.execute(
                        """INSERT OR IGNORE INTO species_alias (species_id, raw_name, lang, status)
                           VALUES (?, ?, ?, 'resolved')""",
                        (sid, raw_name, "ja-kana" if ja_name else "sci"),
                    )
                    # observation: dedup on (park_id, species_id, source_id is iNat)
                    existing = conn.execute(
                        """SELECT id FROM observation
                           WHERE park_id=? AND species_id=? AND source_id=?""",
                        (p["id"], sid, src_id),
                    ).fetchone()
                    if existing:
                        continue
                    count = r.get("count") or 0
                    conn.execute(
                        """INSERT INTO observation
                           (park_id, species_id, raw_name, months_bitmap,
                            location_hint, characteristics, source_id)
                           VALUES (?, ?, ?, NULL, ?, ?, ?)""",
                        (p["id"], sid, raw_name, "iNaturalist (research grade)",
                         f"observations: {count}", src_id),
                    )
                    park_inserted += 1; total_inserted += 1
            conn.commit()
            if i % 10 == 0 or park_inserted:
                print(f"  [{i:>3}/{len(parks)}] {p['slug']:<25} +{park_inserted} "
                      f"(total ins={total_inserted} cache_hits={cache_hits}/{total_calls})")
    print(f"\n=== Phase D done ===")
    print(f"  parks processed: {len(parks)}")
    print(f"  api calls: {total_calls}  cache hits: {cache_hits}")
    print(f"  observations inserted: {total_inserted}")
    return 0


if __name__ == "__main__":
    pref = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] in {"tokyo","kanagawa","chiba","saitama"} else None
    cap = int(sys.argv[2]) if len(sys.argv) > 2 else None
    sys.exit(main(prefecture_filter=pref, max_parks=cap))
