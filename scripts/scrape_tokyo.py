"""Scrape all Tokyo parks from the seed list — fetch each park's main page,
extract `花の見ごろ` observations, and write them to the DB.

Idempotent: existing (park_id, raw_name, months_bitmap) rows are skipped.
Politeness: 1 req/sec via fetch_cached_or_new (uses cache when fresh).
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from parklife import db, fetch
from parklife.scrapers import tokyo

ROOT = Path(__file__).resolve().parent.parent


def upsert_observation(conn, park_id: int, source_id: int, ob: tokyo.RawObservation) -> bool:
    """Return True if a new row was inserted."""
    existing = conn.execute(
        """SELECT id FROM observation
           WHERE park_id=? AND raw_name=? AND months_bitmap IS ?""",
        (park_id, ob.raw_name, ob.months_bitmap),
    ).fetchone()
    if existing:
        return False
    conn.execute(
        """INSERT INTO observation
           (park_id, species_id, raw_name, months_bitmap,
            location_hint, characteristics, source_id)
           VALUES (?, NULL, ?, ?, ?, ?, ?)""",
        (park_id, ob.raw_name, ob.months_bitmap, ob.location_hint,
         ob.characteristics, source_id),
    )
    # Add a pending alias for later normalization, idempotent on (raw_name, lang).
    conn.execute(
        """INSERT OR IGNORE INTO species_alias (species_id, raw_name, lang, status)
           VALUES (NULL, ?, 'ja-kana', 'pending')""",
        (ob.raw_name,),
    )
    return True


def main(limit: int | None = None) -> None:
    db_path = ROOT / "data" / "parklife.db"
    with db.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT id, slug, prefecture, official_url, name_ja FROM park "
            "WHERE prefecture='tokyo' AND official_url IS NOT NULL "
            "ORDER BY id"
        ).fetchall()
        if limit:
            rows = rows[:limit]
        total_parks = len(rows)
        ok = empty = errors = inserted = 0
        for i, row in enumerate(rows, 1):
            try:
                src_id, path = fetch.fetch_cached_or_new(
                    conn, ROOT, row["id"], row["prefecture"], row["slug"], row["official_url"],
                )
                obs = tokyo.extract(path.read_bytes())
                new_rows = sum(upsert_observation(conn, row["id"], src_id, ob) for ob in obs)
                conn.commit()
                inserted += new_rows
                if obs:
                    ok += 1
                else:
                    empty += 1
                print(f"[{i:>3}/{total_parks}] {row['slug']:<35} "
                      f"obs={len(obs):>3}  new={new_rows:>3}  {row['name_ja']}")
            except Exception as e:
                errors += 1
                print(f"[{i:>3}/{total_parks}] {row['slug']:<35} ERROR  {e!r}")
        print(f"\n=== summary ===")
        print(f"  parks processed: {total_parks}")
        print(f"  with observations: {ok}")
        print(f"  empty (no 花の見ごろ): {empty}")
        print(f"  errors: {errors}")
        print(f"  observations inserted: {inserted}")


if __name__ == "__main__":
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    main(limit)
