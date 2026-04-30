"""Gap #2: enrich parks with cultivated/horticultural plants from iNat.

Same shape as scripts.inaturalist (species_counts per park) but with:
  - taxon_id = 47126 (Plantae) only
  - captive = true   (the wild=false set; covers garden ornamentals)
  - characteristics = 'cultivated'

Cache: data/cache/inat_captive/<prefecture>__<slug>.json
Source URL distinguishes from the wild iNat run by including captive=true.

Idempotent: re-running uses the cache for parks already done.
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

PLANTAE_TAXON = "47126"
RADIUS_KM = 1.5
PER_PAGE = 100


def cache_path(prefecture: str, slug: str) -> Path:
    return ROOT / "data" / "cache" / "inat_captive" / f"{prefecture}__{slug}.json"


def fetch(prefecture: str, slug: str, lat: float, lon: float) -> tuple[str, dict]:
    cp = cache_path(prefecture, slug)
    cp.parent.mkdir(parents=True, exist_ok=True)
    if cp.exists():
        return ("cache", json.loads(cp.read_text(encoding="utf-8")))
    params = {
        "lat": lat, "lng": lon, "radius": RADIUS_KM,
        "taxon_id": PLANTAE_TAXON,
        "captive": "true",
        "quality_grade": "research,needs_id",
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


def upsert_species(conn, sci: str | None, ja: str | None,
                    en: str | None, taxon_id: int | None, photo: str | None) -> int | None:
    if not (sci or ja):
        return None
    row = None
    if sci:
        row = conn.execute("SELECT id FROM species WHERE scientific_name=?", (sci,)).fetchone()
    if not row and ja:
        row = conn.execute("SELECT id FROM species WHERE common_name_ja=?", (ja,)).fetchone()
    if row:
        sid = row["id"]
        conn.execute(
            """UPDATE species SET scientific_name = COALESCE(scientific_name, ?),
                                  common_name_ja = COALESCE(common_name_ja, ?),
                                  common_name_en = COALESCE(common_name_en, ?),
                                  kingdom = COALESCE(kingdom, 'plantae'),
                                  taxon_group = COALESCE(taxon_group, 'plant'),
                                  inat_taxon_id = COALESCE(inat_taxon_id, ?),
                                  photo_url = COALESCE(photo_url, ?)
               WHERE id=?""",
            (sci, ja, en, taxon_id, photo, sid),
        )
        return sid
    cur = conn.execute(
        """INSERT INTO species (scientific_name, common_name_ja, common_name_en,
                                 kingdom, taxon_group, inat_taxon_id, photo_url)
           VALUES (?, ?, ?, 'plantae', 'plant', ?, ?)""",
        (sci, ja, en, taxon_id, photo),
    )
    return cur.lastrowid


def main() -> int:
    db_path = ROOT / "data" / "parklife.db"
    with db.connect(db_path) as conn:
        parks = list(conn.execute(
            "SELECT id, slug, prefecture, lat, lon, name_ja FROM park "
            "WHERE lat IS NOT NULL AND lon IS NOT NULL "
            "ORDER BY prefecture, name_ja"
        ))
    print(f"parks: {len(parks)}")
    inserts = updates = api_calls = cache_hits = 0
    with db.connect(db_path) as conn:
        for i, p in enumerate(parks, 1):
            src, data = fetch(p["prefecture"], p["slug"], p["lat"], p["lon"])
            api_calls += 1
            if src == "cache":
                cache_hits += 1
            else:
                time.sleep(0.7)
            results = data.get("results") or []
            if not results:
                continue
            url = (f"{API}?lat={p['lat']}&lng={p['lon']}&radius={RADIUS_KM}"
                    f"&taxon_id={PLANTAE_TAXON}&captive=true&locale=ja")
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            cur = conn.execute(
                """INSERT OR IGNORE INTO source (park_id, url, fetched_at, http_status,
                                                 content_sha256, raw_path)
                   VALUES (?, ?, ?, 200, NULL, ?)""",
                (p["id"], url, now, f"data/cache/inat_captive/{p['prefecture']}__{p['slug']}.json"),
            )
            src_id = cur.lastrowid
            if not src_id:
                row = conn.execute(
                    "SELECT id FROM source WHERE park_id=? AND url=? ORDER BY id DESC LIMIT 1",
                    (p["id"], url),
                ).fetchone()
                src_id = row["id"] if row else None

            for r in results:
                t = r.get("taxon") or {}
                sci = t.get("name")
                ja = t.get("preferred_common_name")
                if ja and not any(0x3040 <= ord(c) <= 0x30FF or 0x4E00 <= ord(c) <= 0x9FFF for c in ja):
                    en, ja = ja, None
                else:
                    en = None
                photo = (t.get("default_photo") or {}).get("medium_url") if t.get("default_photo") else None
                sid = upsert_species(conn, sci, ja, en, t.get("id"), photo)
                if not sid:
                    continue
                raw = ja or sci
                if not raw:
                    continue
                # alias
                conn.execute(
                    """INSERT OR IGNORE INTO species_alias (species_id, raw_name, lang, status)
                       VALUES (?, ?, ?, 'resolved')""",
                    (sid, raw, "ja-kana" if ja else "sci"),
                )
                # observation: dedup on (park, species, source)
                exists = conn.execute(
                    "SELECT id FROM observation WHERE park_id=? AND species_id=? AND source_id=?",
                    (p["id"], sid, src_id),
                ).fetchone()
                if exists:
                    continue
                count = r.get("count") or 0
                conn.execute(
                    """INSERT INTO observation
                       (park_id, species_id, raw_name, months_bitmap,
                        location_hint, characteristics, source_id)
                       VALUES (?, ?, ?, NULL, 'iNaturalist (captive/cultivated)',
                               ?, ?)""",
                    (p["id"], sid, raw, f"observations: {count}", src_id),
                )
                inserts += 1
            conn.commit()
            if i % 20 == 0 or inserts:
                print(f"  [{i:>3}/{len(parks)}] {p['slug']:<25} ins={inserts} api={api_calls} cache={cache_hits}")
    print(f"\n=== captive enrichment done ===")
    print(f"  api calls: {api_calls}  cache hits: {cache_hits}")
    print(f"  observations inserted: {inserts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
