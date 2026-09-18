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
import math
import sys
import time
from pathlib import Path

from curl_cffi import requests

from parklife import db
from parklife.parking import classify_osm

ROOT = Path(__file__).resolve().parent.parent
UA = "parklife-bot/0.1 (research; contact: paranoid2droid@gmail.com)"
# overpass-api.de only (rate limit: 2 slots/IP; over-quota answers are 429 or a
# fast 504 — both mean "wait and retry", not "broken"). The kumi.systems mirror
# was dropped 2026-09-19: it hung the full 60 s timeout on every call, so each
# throttled park cost ~90 s and the nationwide pass could not finish in 4 h.
ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
]
RETRIES = 5          # per park, on 429 / 5xx / network error
BACKOFF_S = (8, 15, 30, 60, 90)
CACHE = ROOT / "data" / "cache" / "osm_parking"
RADIUS_M = 300
SLEEP_S = 3.0  # ~2 slots/IP with cooldown; 1.5 s tripped 504s


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
    endpoint = ENDPOINTS[0]
    for attempt in range(RETRIES):
        try:
            r = requests.post(endpoint, data={"data": q},
                              headers={"User-Agent": UA},
                              timeout=45, impersonate="chrome")
        except Exception as e:
            print(f"  net err {endpoint}: {type(e).__name__}: {e}; retry in {BACKOFF_S[attempt]}s",
                  file=sys.stderr, flush=True)
            time.sleep(BACKOFF_S[attempt])
            continue
        if r.status_code == 429 or r.status_code >= 500:
            print(f"  {r.status_code} from overpass; backing off {BACKOFF_S[attempt]}s", flush=True)
            time.sleep(BACKOFF_S[attempt])
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


BATCH = 25  # parks per Overpass request (one union query, `out center`)


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def overpass_batch_query(points: list[tuple[float, float]], radius: int) -> str:
    parts = "\n".join(
        f'  nwr["amenity"="parking"](around:{radius},{lat},{lon});' for lat, lon in points)
    return f"""
[out:json][timeout:60];
(
{parts}
);
out center;
"""


def _post(q: str) -> dict | None:
    """One Overpass POST with 429/5xx/network backoff. None = gave up."""
    endpoint = ENDPOINTS[0]
    for attempt in range(RETRIES):
        try:
            r = requests.post(endpoint, data={"data": q},
                              headers={"User-Agent": UA},
                              timeout=90, impersonate="chrome")
        except Exception as e:
            print(f"  net err {endpoint}: {type(e).__name__}: {e}; retry in {BACKOFF_S[attempt]}s",
                  file=sys.stderr, flush=True)
            time.sleep(BACKOFF_S[attempt])
            continue
        if r.status_code == 429 or r.status_code >= 500:
            print(f"  {r.status_code} from overpass; backing off {BACKOFF_S[attempt]}s", flush=True)
            time.sleep(BACKOFF_S[attempt])
            continue
        if r.status_code != 200:
            print(f"  {r.status_code} from {endpoint}; giving up this query", flush=True)
            return None
        try:
            return r.json()
        except Exception:
            return None
    return None


def fetch_batch(points: list[tuple[float, float]], radius: int) -> int:
    """Query many parks at once and write each park's per-point cache file.

    Elements come back with `center` (ways/relations) or lat/lon (nodes); each
    is attributed to every park within `radius` m, so the per-park cache is the
    same `{"elements": [...]}` shape `fetch()` produces. Returns the number of
    cache files written (0 = the request failed; nothing is cached, so a
    re-run retries these parks).
    """
    CACHE.mkdir(parents=True, exist_ok=True)
    data = _post(overpass_batch_query(points, radius))
    if data is None:
        return 0
    elems = []
    for e in data.get("elements") or []:
        c = e.get("center") or {}
        lat, lon = e.get("lat", c.get("lat")), e.get("lon", c.get("lon"))
        if lat is None or lon is None:
            continue
        elems.append((float(lat), float(lon), e))
    written = 0
    for plat, plon in points:
        mine = [e for lat, lon, e in elems if _haversine_m(plat, plon, lat, lon) <= radius]
        cache_path(plat, plon, radius).write_text(
            json.dumps({"elements": mine}, ensure_ascii=False), encoding="utf-8")
        written += 1
    return written


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

    # Batched pre-fetch: one Overpass request per BATCH uncached parks (the
    # per-park path below then reads the cache). 3,600 single queries tripped
    # overpass-api.de's 2-slot/IP throttle at ~24 s/park; batching is ~150 calls.
    todo = [(p["lat"], p["lon"]) for p in rows
            if not cache_path(p["lat"], p["lon"], RADIUS_M).exists()]
    if todo:
        print(f"  batched pre-fetch: {len(todo)} uncached parks in {-(-len(todo) // BATCH)} requests",
              flush=True)
        for b in range(0, len(todo), BATCH):
            chunk = todo[b:b + BATCH]
            n = fetch_batch(chunk, RADIUS_M)
            print(f"  batch {b // BATCH + 1}: cached {n}/{len(chunk)}", flush=True)
            time.sleep(SLEEP_S)

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
