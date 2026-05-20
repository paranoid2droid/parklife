"""Fill park.official_url for P13-only parks via OpenStreetMap Overpass.

For each park with empty official_url and known coordinates, query Overpass
for nearby OSM features tagged `leisure=park`, `leisure=garden`, or
`leisure=nature_reserve` within RADIUS_M of the park centre. From the
matching features, pick the best `website` / `contact:website` / `url` tag.

Preference order when multiple features match:
  1. Feature whose `name` / `name:ja` / `name:en` matches park.name_ja (substring either way)
  2. Feature with non-empty `website` tag, otherwise `contact:website`, otherwise `url`
  3. Largest feature (way > node; relation > way) — proxy for "main park"

Polite: 1 batched query per request, 1.5 s sleep between requests.
Per-park cache under data/cache/osm_park_url/.
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
ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
CACHE = ROOT / "data" / "cache" / "osm_park_url"
RADIUS_M = 400
SLEEP_S = 1.5


def cache_path(lat: float, lon: float, radius: int) -> Path:
    key = f"{round(lat, 5)}_{round(lon, 5)}_r{radius}.json"
    return CACHE / key


def overpass_query(lat: float, lon: float, radius: int) -> str:
    return f"""
[out:json][timeout:25];
(
  node["leisure"~"park|garden|nature_reserve"](around:{radius},{lat},{lon});
  way["leisure"~"park|garden|nature_reserve"](around:{radius},{lat},{lon});
  relation["leisure"~"park|garden|nature_reserve"](around:{radius},{lat},{lon});
);
out tags 80;
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


def name_matches(tags: dict, want: str) -> bool:
    """True if any OSM name tag overlaps with the park name."""
    if not want:
        return False
    candidates = [tags.get(k, "") for k in
                  ("name", "name:ja", "name:ja-Hira", "alt_name", "official_name")]
    for n in candidates:
        if not n:
            continue
        if want in n or n in want:
            return True
    return False


def best_url(tags: dict) -> str | None:
    for k in ("website", "contact:website", "url"):
        v = tags.get(k, "").strip()
        if v:
            if not v.startswith(("http://", "https://")):
                v = "https://" + v
            return v
    return None


def element_rank(e: dict) -> int:
    # relation > way > node
    return {"relation": 3, "way": 2, "node": 1}.get(e.get("type"), 0)


def pick_url(data: dict, park_name: str) -> tuple[str | None, str]:
    """Return (url, reason) for the best match in the Overpass response."""
    elements = data.get("elements") or []
    if not elements:
        return None, "no leisure features within radius"
    candidates = []
    for e in elements:
        tags = e.get("tags") or {}
        url = best_url(tags)
        if not url:
            continue
        candidates.append((e, tags, url))
    if not candidates:
        return None, f"{len(elements)} features but none had website tag"
    # First: name-matching feature
    named = [c for c in candidates if name_matches(c[1], park_name)]
    if named:
        named.sort(key=lambda c: -element_rank(c[0]))
        e, tags, url = named[0]
        return url, f"name-matched OSM {e['type']} id={e.get('id')} name={tags.get('name','?')}"
    # Otherwise: largest feature with a URL
    candidates.sort(key=lambda c: -element_rank(c[0]))
    e, tags, url = candidates[0]
    return url, f"nearest OSM {e['type']} id={e.get('id')} name={tags.get('name','?')}"


def main(limit: int | None = None) -> int:
    db_path = ROOT / "data" / "parklife.db"
    with db.connect(db_path) as conn:
        rows = list(conn.execute("""
            SELECT id, slug, prefecture, name_ja, lat, lon
            FROM park
            WHERE slug LIKE 'p13-%'
              AND (official_url IS NULL OR official_url = '')
              AND lat IS NOT NULL AND lon IS NOT NULL
            ORDER BY id
        """))
    if limit:
        rows = rows[:limit]
    print(f"P13 parks needing URL: {len(rows)}", flush=True)

    filled = 0
    none_found = 0
    failed = 0
    cache_hits = net_calls = 0
    with db.connect(db_path) as conn:
        for i, p in enumerate(rows, 1):
            cp = cache_path(p["lat"], p["lon"], RADIUS_M)
            cached = cp.exists()
            try:
                data = fetch(p["lat"], p["lon"], RADIUS_M)
            except Exception as e:
                print(f"  [{i}] {p['slug']} fetch failed: {e}", flush=True)
                failed += 1
                continue
            if cached:
                cache_hits += 1
            else:
                net_calls += 1
                time.sleep(SLEEP_S)
            if data is None:
                failed += 1
                continue
            url, reason = pick_url(data, p["name_ja"] or "")
            if url:
                conn.execute("UPDATE park SET official_url=? WHERE id=?",
                             (url, p["id"]))
                filled += 1
                print(f"  [{i:>3}] {p['name_ja']}: {url}  ({reason})",
                      flush=True)
            else:
                none_found += 1
            if i % 25 == 0:
                conn.commit()
                print(f"  [{i:>3}/{len(rows)}] filled={filled} "
                      f"none={none_found} failed={failed} "
                      f"cache={cache_hits} net={net_calls}", flush=True)
        conn.commit()

    print(f"\n=== osm_park_url done ===")
    print(f"  parks probed:  {len(rows)}")
    print(f"  URL filled:    {filled}")
    print(f"  none found:    {none_found}")
    print(f"  failed:        {failed}")
    print(f"  cache hits:    {cache_hits}  network calls: {net_calls}")
    return 0


if __name__ == "__main__":
    cap = int(sys.argv[1]) if len(sys.argv) > 1 else None
    sys.exit(main(limit=cap))
