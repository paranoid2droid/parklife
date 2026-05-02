"""Collect multiple licensed iNaturalist observation photos per species.

The existing `species.photo_url` stores one representative image. This script
adds a small gallery to `species_photo`, prioritising common demo species so
the modal can show a carousel without bloating the export too much.

Idempotent and cached:
  - API responses: data/cache/inat_photos/<taxon_id>.json
  - DB rows: UNIQUE(species_id, url)
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
API = "https://api.inaturalist.org/v1/observations"
CACHE = ROOT / "data" / "cache" / "inat_photos"
REQUEST_DELAY_SECONDS = 1.0

PHOTO_SCHEMA = """
CREATE TABLE IF NOT EXISTS species_photo (
    id              INTEGER PRIMARY KEY,
    species_id      INTEGER NOT NULL REFERENCES species(id) ON DELETE CASCADE,
    url             TEXT NOT NULL,
    thumb_url       TEXT,
    attribution     TEXT,
    source          TEXT NOT NULL DEFAULT 'iNaturalist',
    sort_order      INTEGER NOT NULL DEFAULT 0,
    UNIQUE(species_id, url)
);

CREATE INDEX IF NOT EXISTS idx_species_photo_species ON species_photo(species_id);
"""


def fetch_photos(taxon_id: int, *, per_page: int = 40) -> tuple[dict | None, bool]:
    cp = CACHE / f"{taxon_id}.json"
    cp.parent.mkdir(parents=True, exist_ok=True)
    if cp.exists():
        try:
            return json.loads(cp.read_text(encoding="utf-8")), False
        except Exception:
            pass
    params = {
        "taxon_id": taxon_id,
        "quality_grade": "research",
        "photos": "true",
        "captive": "false",
        "per_page": per_page,
        "order_by": "observed_on",
        "order": "desc",
        "locale": "ja",
    }
    r = requests.get(
        API,
        params=params,
        headers={"User-Agent": UA, "Accept-Language": "ja"},
        impersonate="chrome",
        timeout=30,
    )
    if r.status_code != 200:
        print(f"  taxon {taxon_id}: HTTP {r.status_code}", file=sys.stderr, flush=True)
        return None, True
    data = r.json()
    cp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data, True


def _photo_urls(photo: dict) -> tuple[str | None, str | None]:
    medium = photo.get("medium_url")
    square = photo.get("square_url")
    url = photo.get("url")
    if not medium and url:
        medium = url.replace("/square.", "/medium.")
    return medium or url, square or url


def extract_photos(payload: dict, max_photos: int) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for obs in payload.get("results") or []:
        for photo in obs.get("photos") or []:
            url, thumb = _photo_urls(photo)
            if not url or url in seen:
                continue
            seen.add(url)
            out.append({
                "url": url,
                "thumb_url": thumb,
                "attribution": photo.get("attribution") or "",
            })
            if len(out) >= max_photos:
                return out
    return out


def main(limit: int | None = 500, max_photos: int = 5) -> int:
    db_path = ROOT / "data" / "parklife.db"
    db.init(db_path)
    with db.connect(db_path) as conn:
        conn.executescript(PHOTO_SCHEMA)
        rows = list(conn.execute("""
            SELECT s.id, s.inat_taxon_id, s.common_name_ja, s.scientific_name,
                   COUNT(DISTINCT ps.park_id) AS park_count,
                   COUNT(sp.id) AS existing_photos
            FROM species s
            JOIN park_species ps ON ps.species_id = s.id
            LEFT JOIN species_photo sp ON sp.species_id = s.id
            WHERE s.inat_taxon_id IS NOT NULL
              AND COALESCE(s.kingdom, '') NOT IN ('archaea', 'bacteria', 'chromista', 'protozoa')
            GROUP BY s.id
            HAVING existing_photos < ?
            ORDER BY park_count DESC, s.id
        """, (max_photos,)))
    if limit:
        rows = rows[:limit]
    print(f"species needing gallery photos: {len(rows)}", flush=True)

    fetched = cache_hits = inserted = with_photos = 0
    with db.connect(db_path) as conn:
        conn.executescript(PHOTO_SCHEMA)
        for i, r in enumerate(rows, 1):
            payload, did_fetch = fetch_photos(r["inat_taxon_id"])
            fetched += int(did_fetch)
            cache_hits += int(not did_fetch)
            if did_fetch:
                time.sleep(REQUEST_DELAY_SECONDS)
            photos = extract_photos(payload or {}, max_photos)
            if photos:
                with_photos += 1
            for order, photo in enumerate(photos):
                cur = conn.execute(
                    """INSERT OR IGNORE INTO species_photo
                       (species_id, url, thumb_url, attribution, source, sort_order)
                       VALUES (?, ?, ?, ?, 'iNaturalist', ?)""",
                    (r["id"], photo["url"], photo["thumb_url"], photo["attribution"], order),
                )
                inserted += cur.rowcount
            if i % 25 == 0 or photos:
                conn.commit()
                name = r["common_name_ja"] or r["scientific_name"] or r["id"]
                print(f"  [{i:>4}/{len(rows)}] {str(name)[:28]:<28} photos={len(photos)} "
                      f"inserted={inserted} fetched={fetched} cache={cache_hits}", flush=True)
        conn.commit()

    print("\n=== collect_species_photos done ===", flush=True)
    print(f"  species tried: {len(rows)}", flush=True)
    print(f"  species with photos: {with_photos}", flush=True)
    print(f"  fetched: {fetched}  cache: {cache_hits}", flush=True)
    print(f"  new photo rows: {inserted}", flush=True)
    return 0


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a]
    limit = int(args[0]) if args else 500
    max_photos = int(args[1]) if len(args) > 1 else 5
    sys.exit(main(limit=limit, max_photos=max_photos))
