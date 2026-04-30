"""Phase C: geocode all parks via OSM Nominatim.

Nominatim usage policy:
  - 1 req/sec maximum
  - User-Agent must identify the application
  - Cache: per-park, written under data/cache/geocode/
  - Idempotent: skip parks that already have lat/lon

Lookup strategy: query 'name_ja, municipality, prefecture, Japan' first,
fall back to 'name_ja, prefecture, Japan'. Take the first result whose
class/type suggests a park or natural feature.
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
NOMINATIM = "https://nominatim.openstreetmap.org/search"

PREF_NAMES_JA = {
    "tokyo": "東京都",
    "kanagawa": "神奈川県",
    "chiba": "千葉県",
    "saitama": "埼玉県",
}

PARK_TYPES = {"park", "garden", "nature_reserve", "protected_area",
              "wood", "forest", "beach", "national_park", "playground"}


def cache_path(slug: str, prefecture: str) -> Path:
    return ROOT / "data" / "cache" / "geocode" / f"{prefecture}__{slug}.json"


def query(name: str) -> list[dict]:
    r = requests.get(
        NOMINATIM,
        params={"q": name, "format": "json", "countrycodes": "jp",
                "addressdetails": 1, "limit": 5},
        headers={"User-Agent": UA, "Accept-Language": "ja,en"},
        impersonate="chrome",
        timeout=20,
    )
    if r.status_code != 200:
        return []
    try:
        return r.json()
    except Exception:
        return []


def pick(results: list[dict]) -> dict | None:
    if not results:
        return None
    for r in results:
        if (r.get("class") in {"leisure", "natural", "boundary"} or
                r.get("type") in PARK_TYPES):
            return r
    return results[0]  # fallback to top hit


def main(limit: int | None = None) -> int:
    db_path = ROOT / "data" / "parklife.db"
    parks: list[dict] = []
    with db.connect(db_path) as conn:
        rows = list(conn.execute(
            "SELECT id, slug, prefecture, name_ja, municipality, lat, lon FROM park "
            "WHERE lat IS NULL OR lon IS NULL ORDER BY prefecture, slug"
        ))
    if limit:
        rows = rows[:limit]
    print(f"to geocode: {len(rows)}")

    geo_dir = ROOT / "data" / "cache" / "geocode"
    geo_dir.mkdir(parents=True, exist_ok=True)

    hits = misses = errors = cached_hits = 0
    with db.connect(db_path) as conn:
        for i, r in enumerate(rows, 1):
            cp = cache_path(r["slug"], r["prefecture"])
            data = None
            if cp.exists():
                try:
                    data = json.loads(cp.read_text(encoding="utf-8"))
                    cached_hits += 1
                except Exception:
                    data = None
            if data is None:
                queries = [
                    f"{r['name_ja']} {r['municipality'] or ''} {PREF_NAMES_JA.get(r['prefecture'],'')}".strip(),
                    f"{r['name_ja']} {PREF_NAMES_JA.get(r['prefecture'],'')}",
                    r['name_ja'],
                ]
                results = []
                for q in queries:
                    if not q.strip():
                        continue
                    try:
                        time.sleep(1.1)  # nominatim politeness
                        results = query(q)
                    except Exception as e:
                        errors += 1
                        results = []
                    if results:
                        break
                data = {"q_used": q if results else queries[0], "results": results}
                cp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

            picked = pick(data.get("results", []))
            if not picked:
                misses += 1
                if i % 25 == 0:
                    print(f"[{i:>3}/{len(rows)}] hits={hits} misses={misses}")
                continue
            try:
                lat = float(picked["lat"]); lon = float(picked["lon"])
            except (KeyError, ValueError, TypeError):
                misses += 1
                continue
            conn.execute("UPDATE park SET lat=?, lon=? WHERE id=?",
                          (lat, lon, r["id"]))
            hits += 1
            if i % 25 == 0:
                conn.commit()
                print(f"[{i:>3}/{len(rows)}] hits={hits} misses={misses} "
                      f"cached_hits={cached_hits} errors={errors}")
        conn.commit()

    print(f"\n=== geocode done ===")
    print(f"  total processed: {len(rows)}")
    print(f"  hits: {hits}  misses: {misses}  cached: {cached_hits}  errors: {errors}")
    return 0


if __name__ == "__main__":
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    sys.exit(main(limit))
