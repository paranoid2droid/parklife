"""Add species_photo.license and backfill it from each row's attribution.

Idempotent: adds the column if missing, then (re)parses attribution into a
normalized license family via parklife.licenses.parse_license. Prints a
breakdown plus the commercial-reuse coverage that the productization probe
cares about — how many species keep >=1 commercially-licensable photo.
"""

from __future__ import annotations

from pathlib import Path

from parklife import db
from parklife.licenses import allows_commercial, parse_license

ROOT = Path(__file__).resolve().parent.parent


def ensure_column(conn) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(species_photo)")}
    if "license" not in cols:
        conn.execute("ALTER TABLE species_photo ADD COLUMN license TEXT")


def main() -> None:
    db_path = ROOT / "data" / "parklife.db"
    with db.connect(db_path) as conn:
        ensure_column(conn)

        rows = list(conn.execute("SELECT id, attribution FROM species_photo"))
        updates = [(parse_license(a), pid) for pid, a in rows]
        conn.executemany(
            "UPDATE species_photo SET license = ? WHERE id = ?", updates
        )
        conn.commit()

        total = len(rows)
        filled = sum(1 for lic, _ in updates if lic)
        print(f"backfilled license on {filled}/{total} photo rows")
        print("--- by license family ---")
        for code, n in conn.execute(
            "SELECT COALESCE(license,'<unparsed>') AS lic, COUNT(*) AS n "
            "FROM species_photo GROUP BY lic ORDER BY n DESC"
        ):
            tag = "  [commercial OK]" if allows_commercial(code) else ""
            print(f"  {code:<14} {n}{tag}")

        species_with_photo = conn.execute(
            "SELECT COUNT(DISTINCT species_id) FROM species_photo"
        ).fetchone()[0]
        ok_families = ",".join(f"'{c}'" for c in sorted(
            {"CC0", "PD", "CC BY", "CC BY-SA", "CC BY-ND"}))
        species_commercial = conn.execute(
            f"SELECT COUNT(DISTINCT species_id) FROM species_photo "
            f"WHERE license IN ({ok_families})"
        ).fetchone()[0]
        pct = 100 * species_commercial / species_with_photo if species_with_photo else 0
        print("--- commercial-reuse coverage ---")
        print(f"  species with >=1 photo:            {species_with_photo}")
        print(f"  species with >=1 commercial photo: {species_commercial} ({pct:.1f}%)")


if __name__ == "__main__":
    main()
