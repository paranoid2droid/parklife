"""Load data/seeds/*.json into the `park` table.

Idempotent: re-running upserts on (prefecture, slug). Reset `data/parklife.db`
first if you want a clean state.
"""

from __future__ import annotations

from pathlib import Path

from parklife import db, seeds

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    db_path = ROOT / "data" / "parklife.db"
    db.init(db_path)
    parks = seeds.load(ROOT / "data" / "seeds")
    inserted = updated = 0
    with db.connect(db_path) as conn:
        for p in parks:
            existing = conn.execute(
                "SELECT id FROM park WHERE prefecture = ? AND slug = ?",
                (p.prefecture, p.slug),
            ).fetchone()
            if existing:
                conn.execute(
                    """UPDATE park SET name_ja=?, name_en=?, municipality=?,
                                       operator=?, official_url=?, lat=?, lon=?
                       WHERE id=?""",
                    (p.name_ja, p.name_en, p.municipality, p.operator,
                     p.official_url, p.lat, p.lon, existing["id"]),
                )
                updated += 1
            else:
                conn.execute(
                    """INSERT INTO park (slug, name_ja, name_en, prefecture,
                                         municipality, operator, official_url,
                                         lat, lon)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (p.slug, p.name_ja, p.name_en, p.prefecture, p.municipality,
                     p.operator, p.official_url, p.lat, p.lon),
                )
                inserted += 1
    print(f"inserted={inserted} updated={updated} total_in_db={inserted+updated}")


if __name__ == "__main__":
    main()
