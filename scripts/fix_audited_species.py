"""Fix specific species rows whose taxon assignment is wrong (caught
during audit). Idempotent — re-running is harmless.
"""
from __future__ import annotations

from pathlib import Path

from parklife import db

ROOT = Path(__file__).resolve().parent.parent

# (common_name_ja or scientific_name match) -> updates
FIXES: list[dict] = [
    # クジラ generic was tagged mollusk; correct kingdom + group
    {"match": ("common_name_ja", "クジラ"),
     "set": {"taxon_group": "mammal", "scientific_name": "Cetacea"}},
    # ハイビスカス got no group; it's a shrub
    {"match": ("common_name_ja", "ハイビスカス"),
     "set": {"taxon_group": "shrub", "kingdom": "plantae"}},
    # コウモリ generic was wrongly mapped to a Townsend's big-eared bat (NA species)
    {"match": ("common_name_ja", "コウモリ"),
     "set": {"scientific_name": None, "taxon_group": "mammal"}},
    # イルカ has no sci — leave as-is but ensure mammal
    {"match": ("common_name_ja", "イルカ"),
     "set": {"taxon_group": "mammal"}},
    # ニホンザル taxon
    {"match": ("scientific_name", "Macaca fuscata"),
     "set": {"taxon_group": "mammal"}},
]


def main() -> None:
    db_path = ROOT / "data" / "parklife.db"
    fixed = 0
    with db.connect(db_path) as conn:
        for f in FIXES:
            field, value = f["match"]
            row = conn.execute(f"SELECT id FROM species WHERE {field}=?", (value,)).fetchone()
            if not row:
                continue
            sid = row["id"]
            sets = ", ".join(f"{k}=?" for k in f["set"])
            params = list(f["set"].values()) + [sid]
            conn.execute(f"UPDATE species SET {sets} WHERE id=?", params)
            fixed += 1
        conn.commit()
    print(f"fixed {fixed} species rows")


if __name__ == "__main__":
    main()
