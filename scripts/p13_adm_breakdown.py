"""Break down the nationwide P13 new-park candidates by 管理者 (adm) level."""
from __future__ import annotations

import sys
from pathlib import Path

from parklife import db
from scripts.p13_seed import (
    BIODIV_KDP, MIN_AREA_M2, DEDUP_RADIUS_M, RAW_DIR, haversine_m, parse_xml,
)

ROOT = Path(__file__).resolve().parent.parent
DONE = {"11", "12", "13", "14"}
PREF_CODES = [f"{i:02d}" for i in range(1, 48)]


def classify_adm(adm: str) -> str:
    if not adm:
        return "unknown"
    if adm.endswith(("都", "道", "府", "県")):
        return "prefecture"
    if adm.endswith(("市", "区", "町", "村")):
        return "municipal"
    if "国" in adm:
        return "national"
    return "other"


def main() -> int:
    db_path = ROOT / "data" / "parklife.db"
    with db.connect(db_path) as conn:
        existing = [(r["lat"], r["lon"]) for r in conn.execute(
            "SELECT lat, lon FROM park WHERE lat IS NOT NULL AND lon IS NOT NULL")]
    counts: dict[str, int] = {}
    samples: dict[str, list[str]] = {}
    for code in PREF_CODES:
        if code in DONE:
            continue
        zip_path = RAW_DIR / f"P13-11_{code}_GML.zip"
        if not zip_path.exists():
            continue
        for p in parse_xml(zip_path):
            if (p["kdp"] in BIODIV_KDP and p["area"] >= MIN_AREA_M2
                    and p["lat"] is not None):
                if any(haversine_m(p["lat"], p["lon"], la, lo) < DEDUP_RADIUS_M
                       for la, lo in existing):
                    continue
                k = classify_adm(p["adm"])
                counts[k] = counts.get(k, 0) + 1
                samples.setdefault(p["adm"] or "(blank)", [])
                if len(samples[p["adm"] or "(blank)"]) < 1:
                    samples[p["adm"] or "(blank)"].append(p["name"])
    print("new-park candidates by 管理者 level:")
    for k, v in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {k:>11}: {v}")
    print("\ndistinct adm strings (sample park):")
    for adm, names in sorted(samples.items()):
        print(f"  {adm!r:>20} -> {names[0]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
