"""Apply manually-set coordinates from data/manual_coords.json. Useful
for parks Nominatim couldn't resolve (often the most biodiversity-rich
ones — Mount Takao, Bonin, Hachijo, Okutama)."""
from __future__ import annotations

import json
from pathlib import Path

from parklife import db

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    data = json.loads((ROOT / "data" / "manual_coords.json").read_text(encoding="utf-8"))
    db_path = ROOT / "data" / "parklife.db"
    fixed = 0
    with db.connect(db_path) as conn:
        for key, coords in data.items():
            if key.startswith("_"):
                continue
            pref, slug = key.split("/", 1)
            r = conn.execute("SELECT id FROM park WHERE prefecture=? AND slug=?",
                              (pref, slug)).fetchone()
            if not r:
                print(f"  not found: {key}")
                continue
            lat, lon = coords
            conn.execute("UPDATE park SET lat=?, lon=? WHERE id=?",
                          (lat, lon, r["id"]))
            fixed += 1
        conn.commit()
    print(f"applied {fixed} manual coordinate fixes")


if __name__ == "__main__":
    main()
