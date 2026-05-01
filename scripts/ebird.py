"""eBird recent-observation enrichment for park birds.

For each park with coordinates, query eBird's recent nearby observations API
and ingest bird species observed near the park. This complements iNaturalist
and GBIF with bird-specialist citizen-science data.

Requires:
  EBIRD_API_KEY=<token> .venv/bin/python -m scripts.ebird

Cache: data/cache/ebird/<prefecture>__<slug>.json
Endpoint: https://api.ebird.org/v2/data/obs/geo/recent

Politeness: 1 request/sec. eBird recent nearby observations cover up to
30 days back and up to 50 km radius; we intentionally use a small radius so
records are more relevant to each park.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

from curl_cffi import requests

from parklife import db

ROOT = Path(__file__).resolve().parent.parent
UA = "parklife-bot/0.1 (research; contact: paranoid2droid@gmail.com)"
API = "https://api.ebird.org/v2/data/obs/geo/recent"

RADIUS_KM = 2.0
BACK_DAYS = 30
MAX_RESULTS = 10000


def cache_path(slug: str, prefecture: str) -> Path:
    return ROOT / "data" / "cache" / "ebird" / f"{prefecture}__{slug}.json"


def fetch_park(slug: str, prefecture: str, lat: float, lon: float, key: str) -> tuple[str, list[dict]]:
    cp = cache_path(slug, prefecture)
    cp.parent.mkdir(parents=True, exist_ok=True)
    if cp.exists():
        return ("cache", json.loads(cp.read_text(encoding="utf-8")))

    params = {
        "lat": lat,
        "lng": lon,
        "dist": RADIUS_KM,
        "back": BACK_DAYS,
        "maxResults": MAX_RESULTS,
        "sppLocale": "ja",
        "sort": "species",
    }
    try:
        r = requests.get(
            API,
            params=params,
            headers={
                "User-Agent": UA,
                "x-ebirdapitoken": key,
                "Accept": "application/json",
            },
            timeout=60,
            impersonate="chrome",
        )
    except Exception as e:
        print(f"    network error on {slug}: {type(e).__name__}: {e}")
        return ("error", [])
    if r.status_code != 200:
        print(f"    HTTP {r.status_code} on {slug}: {r.text[:160]}")
        return ("error", [])
    data = r.json()
    cp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return ("network", data)


def api_url(lat: float, lon: float) -> str:
    params = {
        "lat": lat,
        "lng": lon,
        "dist": RADIUS_KM,
        "back": BACK_DAYS,
        "maxResults": MAX_RESULTS,
        "sppLocale": "ja",
        "sort": "species",
    }
    return f"{API}?{urlencode(params)}"


def insert_source(conn, park_id: int, prefecture: str, slug: str, url: str) -> int:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rel = f"data/cache/ebird/{prefecture}__{slug}.json"
    cur = conn.execute(
        """INSERT OR IGNORE INTO source (park_id, url, fetched_at, http_status,
                                         content_sha256, raw_path)
           VALUES (?, ?, ?, 200, NULL, ?)""",
        (park_id, url, now, rel),
    )
    if cur.lastrowid:
        return cur.lastrowid
    row = conn.execute(
        "SELECT id FROM source WHERE park_id=? AND url=? ORDER BY id DESC LIMIT 1",
        (park_id, url),
    ).fetchone()
    return row["id"] if row else 0


def upsert_species(conn, sci_name: str, ja_name: str | None, en_name: str | None) -> int | None:
    if not sci_name:
        return None
    row = conn.execute("SELECT id FROM species WHERE scientific_name=?", (sci_name,)).fetchone()
    if row:
        sid = row["id"]
        conn.execute(
            """UPDATE species SET common_name_ja = COALESCE(common_name_ja, ?),
                                  common_name_en = COALESCE(common_name_en, ?),
                                  kingdom = COALESCE(kingdom, 'animalia'),
                                  taxon_group = COALESCE(taxon_group, 'bird')
               WHERE id=?""",
            (ja_name, en_name, sid),
        )
        return sid
    cur = conn.execute(
        """INSERT INTO species
           (scientific_name, common_name_ja, common_name_en, kingdom, taxon_group)
           VALUES (?, ?, ?, 'animalia', 'bird')""",
        (sci_name, ja_name, en_name),
    )
    return cur.lastrowid


def main(prefecture_filter: str | None = None, max_parks: int | None = None) -> int:
    key = os.environ.get("EBIRD_API_KEY", "").strip()
    if not key:
        print("error: EBIRD_API_KEY is required", file=sys.stderr)
        return 2

    db_path = ROOT / "data" / "parklife.db"
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
    print(f"parks to enrich via eBird: {len(parks)}")

    total_inserted = cache_hits = network_calls = errors = 0
    with db.connect(db_path) as conn:
        for i, p in enumerate(parks, 1):
            src, records = fetch_park(p["slug"], p["prefecture"], p["lat"], p["lon"], key)
            if src == "cache":
                cache_hits += 1
            elif src == "network":
                network_calls += 1
                time.sleep(1.0)
            else:
                errors += 1
                time.sleep(1.0)
                continue

            src_id = insert_source(conn, p["id"], p["prefecture"], p["slug"], api_url(p["lat"], p["lon"]))
            park_inserted = 0
            for rec in records:
                sci = (rec.get("sciName") or "").strip()
                ja = (rec.get("comName") or "").strip() or None
                species_code = (rec.get("speciesCode") or "").strip()
                if not sci:
                    continue
                sid = upsert_species(conn, sci, ja, None)
                if not sid:
                    continue
                raw_name = ja or sci
                conn.execute(
                    """INSERT OR IGNORE INTO species_alias
                       (species_id, raw_name, lang, status)
                       VALUES (?, ?, ?, 'resolved')""",
                    (sid, raw_name, "ja" if ja else "sci"),
                )
                conn.execute(
                    """INSERT OR IGNORE INTO species_alias
                       (species_id, raw_name, lang, status)
                       VALUES (?, ?, 'sci', 'resolved')""",
                    (sid, sci),
                )
                if species_code:
                    conn.execute(
                        """INSERT OR IGNORE INTO species_alias
                           (species_id, raw_name, lang, status)
                           VALUES (?, ?, 'ebird', 'resolved')""",
                        (sid, species_code),
                    )
                existing = conn.execute(
                    """SELECT id FROM observation
                       WHERE park_id=? AND species_id=? AND location_hint='eBird'""",
                    (p["id"], sid),
                ).fetchone()
                if existing:
                    continue
                detail = []
                if rec.get("obsDt"):
                    detail.append(f"latest: {rec['obsDt']}")
                if rec.get("howMany") is not None:
                    detail.append(f"count: {rec['howMany']}")
                if rec.get("locName"):
                    detail.append(f"near: {rec['locName']}")
                if species_code:
                    detail.append(f"eBird code: {species_code}")
                conn.execute(
                    """INSERT INTO observation
                       (park_id, species_id, raw_name, months_bitmap,
                        location_hint, characteristics, source_id)
                       VALUES (?, ?, ?, NULL, 'eBird', ?, ?)""",
                    (p["id"], sid, raw_name, "; ".join(detail), src_id),
                )
                park_inserted += 1
                total_inserted += 1
            conn.commit()
            if i % 10 == 0 or park_inserted:
                print(f"  [{i:>3}/{len(parks)}] {p['slug']:<25} +{park_inserted} "
                      f"(total ins={total_inserted} cache={cache_hits} net={network_calls} err={errors})")

    print("\n=== eBird enrichment done ===")
    print(f"  parks processed: {len(parks)}")
    print(f"  cache hits: {cache_hits}  network calls: {network_calls}  errors: {errors}")
    print(f"  observations inserted: {total_inserted}")
    return 0


if __name__ == "__main__":
    pref = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] in {"tokyo", "kanagawa", "chiba", "saitama"} else None
    cap = int(sys.argv[2]) if len(sys.argv) > 2 else None
    raise SystemExit(main(prefecture_filter=pref, max_parks=cap))
