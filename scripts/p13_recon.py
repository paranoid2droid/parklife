"""Reconnaissance for nationwide P13 expansion.

Download (cache) the P13 都市公園 GML zip for ALL 47 prefectures, apply the
same biodiversity-type + >=5ha filter used by p13_seed, dedupe against parks
already in the DB, and print a per-prefecture table of how many NEW parks each
would add. Read-only: writes nothing to the DB or seed files.
"""
from __future__ import annotations

import sys
import time
import urllib.request
from pathlib import Path

from parklife import db
from scripts.p13_seed import (
    BIODIV_KDP,
    MIN_AREA_M2,
    DEDUP_RADIUS_M,
    RAW_DIR,
    UA,
    URL_FMT,
    haversine_m,
    parse_xml,
)

ROOT = Path(__file__).resolve().parent.parent

# JIS X 0401 prefecture codes 01-47, with the 4 already-done flagged.
PREF_CODES = [f"{i:02d}" for i in range(1, 48)]
DONE = {"11", "12", "13", "14"}  # saitama, chiba, tokyo, kanagawa


def download_zip(code: str) -> Path | None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    target = RAW_DIR / f"P13-11_{code}_GML.zip"
    if target.exists():
        return target
    url = URL_FMT.format(code=code)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=180) as r, open(target, "wb") as f:
            f.write(r.read())
        time.sleep(1)
        return target
    except Exception as e:  # noqa: BLE001
        print(f"  [{code}] download FAILED: {e}")
        return None


def existing_coords(db_path: Path) -> list[tuple[float, float]]:
    with db.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT lat, lon FROM park WHERE lat IS NOT NULL AND lon IS NOT NULL"
        ).fetchall()
    return [(r["lat"], r["lon"]) for r in rows]


def main() -> int:
    db_path = ROOT / "data" / "parklife.db"
    existing = existing_coords(db_path)
    print(f"existing parks with coords: {len(existing)}\n")
    print(f"{'code':>4} {'total':>6} {'filtered':>9} {'overlap':>8} {'NEW':>6}  done")
    grand_new = grand_filtered = 0
    for code in PREF_CODES:
        zip_path = download_zip(code)
        if zip_path is None:
            continue
        parks = parse_xml(zip_path)
        filtered = [p for p in parks
                    if p["kdp"] in BIODIV_KDP
                    and p["area"] >= MIN_AREA_M2
                    and p["lat"] is not None]
        overlap = 0
        new = 0
        for p in filtered:
            if any(haversine_m(p["lat"], p["lon"], la, lo) < DEDUP_RADIUS_M
                   for la, lo in existing):
                overlap += 1
            else:
                new += 1
        flag = "DONE" if code in DONE else ""
        print(f"{code:>4} {len(parks):>6} {len(filtered):>9} {overlap:>8} {new:>6}  {flag}")
        if code not in DONE:
            grand_new += new
            grand_filtered += len(filtered)
    print(f"\nNEW parks (excluding 4 done prefectures): {grand_new}")
    print(f"  (filtered total in those 43: {grand_filtered})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
