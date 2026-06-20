"""Fill park.has_parking for NULL rows using OpenStreetMap Overpass.

For every park with NULL has_parking and known coordinates, query Overpass
for `amenity=parking` (node|way|relation) within RADIUS_M of the park
centre point. If any are found, mark the park has_parking=1; if the query
succeeded but returned nothing, mark has_parking=0. Failed queries leave
the row as NULL.

Polite: 1 batched query per request, 1.5 s sleep between requests.
Per-park cache under data/cache/osm_parking/.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from curl_cffi import requests

from parklife import db
from parklife.parking import classify_osm

ROOT = Path(__file__).resolve().parent.parent
UA = "parklife-bot/0.1 (research; contact: paranoid2droid@gmail.com)"
ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
CACHE = ROOT / "data" / "cache" / "osm_parking"
RADIUS_M = 300
SLEEP_S = 1.5


def cache_path(lat: float, lon: float, radius: int) -> Path:
    key = f"{round(lat, 5)}_{round(lon, 5)}_r{radius}.json"
    return CACHE / key


def overpass_query(lat: float, lon: float, radius: int) -> str:
    return f"""
[out:json][timeout:25];
(
  node["amenity"="parking"](around:{radius},{lat},{lon});
  way["amenity"="parking"](around:{radius},{lat},{lon});
  relation["amenity"="parking"](around:{radius},{lat},{lon});
);
out tags 50;
"""


def fetch(lat: float, lon: float, radius: int) -> dict | None:
    cp = cache_path(lat, lon, radius)
    if cp.exists():
        try:
            return json.loads(cp.read_text(encoding="utf-8"))
        except Exception:
            pass
    CACHE.mkdir(parents=True, exist_ok=True)
    q = overpass_query(lat, lon, radius)
    for endpoint in ENDPOINTS:
        try:
            r = requests.post(endpoint, data={"data": q},
                              headers={"User-Agent": UA},
                              timeout=60, impersonate="chrome")
        except Exception as e:
            print(f"  net err {endpoint}: {type(e).__name__}: {e}",
                  file=sys.stderr, flush=True)
            continue
        if r.status_code == 429:
            print(f"  429 from {endpoint}; backing off 30s", flush=True)
            time.sleep(30)
            continue
        if r.status_code >= 500:
            print(f"  {r.status_code} from {endpoint}; trying next", flush=True)
            continue
        if r.status_code != 200:
            print(f"  {r.status_code} from {endpoint}; giving up this query",
                  flush=True)
            return None
        try:
            data = r.json()
        except Exception:
            return None
        cp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return data
    return None


def parking_signal(data: dict) -> tuple[bool, int]:
    elements = data.get("elements") or []
    # Reject elements that are private / disused / abandoned.
    usable = []
    for e in elements:
        tags = e.get("tags") or {}
        if tags.get("access") in ("private", "no", "permit", "customers"):
            continue
        if tags.get("disused:amenity") or tags.get("abandoned:amenity"):
            continue
        usable.append(e)
    return (len(usable) > 0, len(usable))


def main(limit: int | None = None) -> int:
    db_path = ROOT / "data" / "parklife.db"
    with db.connect(db_path) as conn:
        rows = list(conn.execute("""
            SELECT id, slug, prefecture, name_ja, lat, lon
            FROM park
            WHERE has_parking IS NULL
              AND lat IS NOT NULL AND lon IS NOT NULL
            ORDER BY id
        """))
    if limit:
        rows = rows[:limit]
    print(f"NULL parks with coords to probe: {len(rows)}", flush=True)

    yes = no = unknown = 0
    cache_hits = net_calls = 0
    with db.connect(db_path) as conn:
        for i, p in enumerate(rows, 1):
            cp = cache_path(p["lat"], p["lon"], RADIUS_M)
            cached = cp.exists()
            try:
                data = fetch(p["lat"], p["lon"], RADIUS_M)
            except Exception as e:
                print(f"  [{i}] {p['slug']} fetch failed: {e}", flush=True)
                unknown += 1
                continue
            if cached:
                cache_hits += 1
            else:
                net_calls += 1
                time.sleep(SLEEP_S)
            if data is None:
                unknown += 1
                continue
            _has, count = parking_signal(data)
            verdict, source, info = classify_osm(count, RADIUS_M)
            if verdict == 1:
                conn.execute(
                    "UPDATE park SET has_parking=1, parking_info=?, parking_source=? WHERE id=?",
                    (info, source, p["id"]))
                yes += 1
            else:
                # OSM absence is UNKNOWN, not "no parking" — record the source so
                # the row stays a re-checkable NULL, never a confident negative.
                conn.execute(
                    "UPDATE park SET has_parking=NULL, parking_info=?, parking_source=? WHERE id=?",
                    (info, source, p["id"]))
                unknown += 1
            if i % 25 == 0:
                conn.commit()
                print(f"  [{i:>4}/{len(rows)}] yes={yes} no={no} unknown={unknown} "
                      f"cache={cache_hits} net={net_calls}", flush=True)
        conn.commit()

    print(f"\n=== osm_parking done ===")
    print(f"  parks probed: {len(rows)}")
    print(f"  has_parking=1 set (osm:present): {yes}")
    print(f"  left NULL (osm:absent = unknown): {unknown}")
    print(f"  cache hits: {cache_hits}  network calls: {net_calls}")
    return 0


if __name__ == "__main__":
    cap = int(sys.argv[1]) if len(sys.argv) > 1 else None
    sys.exit(main(limit=cap))
