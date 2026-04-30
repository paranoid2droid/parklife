"""Fix existing species rows whose kingdom is NULL but taxon_group is a
known animal/plant group. Also rewrites cached Wikipedia JSON files so
subsequent runs see corrected kingdoms.
"""
from __future__ import annotations

import json
from pathlib import Path

from parklife import db
from parklife.normalize.wikipedia import GROUP_TO_KINGDOM

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    db_path = ROOT / "data" / "parklife.db"
    fixed_db = 0
    fixed_cache = 0

    # 1) DB-side: derive kingdom from taxon_group
    with db.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT id, taxon_group FROM species WHERE kingdom IS NULL AND taxon_group IS NOT NULL"
        ).fetchall()
        for r in rows:
            kingdom = GROUP_TO_KINGDOM.get(r["taxon_group"])
            if not kingdom:
                continue
            conn.execute("UPDATE species SET kingdom=? WHERE id=?", (kingdom, r["id"]))
            fixed_db += 1
        conn.commit()

    # 2) cache-side: same correction in the JSON files
    cache_dir = ROOT / "data" / "cache" / "wikipedia"
    if cache_dir.is_dir():
        for f in cache_dir.glob("*.json"):
            data = json.loads(f.read_text(encoding="utf-8"))
            if data.get("kingdom"):
                continue
            grp = data.get("taxon_group")
            kingdom = GROUP_TO_KINGDOM.get(grp) if grp else None
            if not kingdom:
                continue
            data["kingdom"] = kingdom
            f.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            fixed_cache += 1

    # 3) also fix the per-token resolution cache used by Phase A
    a_cache = ROOT / "data" / "cache" / "tokyo_animal_resolution.json"
    if a_cache.exists():
        cache = json.loads(a_cache.read_text(encoding="utf-8"))
        fixed_a = 0
        for name, info in cache.items():
            if info.get("kingdom"):
                continue
            grp = info.get("taxon_group")
            kingdom = GROUP_TO_KINGDOM.get(grp) if grp else None
            if not kingdom:
                continue
            info["kingdom"] = kingdom
            fixed_a += 1
        if fixed_a:
            a_cache.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"  tokyo_animal_resolution cache: {fixed_a} fixed")

    print(f"DB rows fixed:    {fixed_db}")
    print(f"cache files fixed: {fixed_cache}")


if __name__ == "__main__":
    main()
