"""For each species, add aliases for common name variants and scientific
name so that free-text searches over `species_alias` find the species
regardless of how the user typed the name.

Adds (idempotent):
  - common_name_ja  -> lang='ja'
  - scientific_name -> lang='sci'
  - common_name_en  -> lang='en' (when available)

Existing pending or rejected aliases are left as-is.
"""
from __future__ import annotations

from pathlib import Path

from parklife import db

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    db_path = ROOT / "data" / "parklife.db"
    added = 0
    with db.connect(db_path) as conn:
        rows = list(conn.execute(
            "SELECT id, scientific_name, common_name_ja, common_name_en FROM species"
        ))
        for r in rows:
            for value, lang in [
                (r["common_name_ja"], "ja"),
                (r["scientific_name"], "sci"),
                (r["common_name_en"], "en"),
            ]:
                if not value:
                    continue
                cur = conn.execute(
                    """INSERT OR IGNORE INTO species_alias (species_id, raw_name, lang, status)
                       VALUES (?, ?, ?, 'resolved')""",
                    (r["id"], value, lang),
                )
                if cur.rowcount:
                    added += 1
        conn.commit()
    print(f"added {added} alias rows")


if __name__ == "__main__":
    main()
