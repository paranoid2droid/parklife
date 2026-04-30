"""Link observation rows to species via species_alias.

Run after normalize.py + apply_manual_species.py. Idempotent.
"""

from __future__ import annotations

from pathlib import Path

from parklife import db

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    db_path = ROOT / "data" / "parklife.db"
    with db.connect(db_path) as conn:
        result = conn.execute("""
            UPDATE observation SET species_id = (
                SELECT species_id FROM species_alias
                 WHERE species_alias.raw_name = observation.raw_name
                   AND species_alias.species_id IS NOT NULL
                 LIMIT 1
            )
            WHERE species_id IS NULL
              AND raw_name IN (
                SELECT raw_name FROM species_alias
                 WHERE species_id IS NOT NULL
              )
        """)
        conn.commit()
        linked = result.rowcount
        total = conn.execute("SELECT COUNT(*) FROM observation").fetchone()[0]
        with_sp = conn.execute("SELECT COUNT(*) FROM observation WHERE species_id IS NOT NULL").fetchone()[0]
        print(f"backfilled {linked} observation rows")
        print(f"observation rows with species_id: {with_sp}/{total}")


if __name__ == "__main__":
    main()
