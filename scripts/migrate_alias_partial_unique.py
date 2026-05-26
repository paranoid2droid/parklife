"""One-shot migration: drop table-level UNIQUE(raw_name, lang) on species_alias,
replace with a partial unique index covering only resolver languages.

Idempotent: detects whether the new partial index already exists and exits.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "parklife.db"

RESOLVER_LANGS = ("ja", "ja-kana", "sci", "en")


def already_migrated(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='index' AND name='uniq_alias_resolver'"
    ).fetchone()
    if not row:
        return False
    # Confirm table no longer has the inline UNIQUE
    tbl = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='species_alias'"
    ).fetchone()
    return tbl is not None and "UNIQUE(raw_name, lang)" not in (tbl[0] or "")


def main() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = OFF")  # we recreate the table
        if already_migrated(conn):
            print("Already migrated — nothing to do.")
            return

        before = conn.execute("SELECT COUNT(*) FROM species_alias").fetchone()[0]
        print(f"species_alias rows before: {before}")

        conn.execute("BEGIN")
        try:
            conn.execute("""
                CREATE TABLE species_alias_new (
                    id              INTEGER PRIMARY KEY,
                    species_id      INTEGER REFERENCES species(id) ON DELETE CASCADE,
                    raw_name        TEXT NOT NULL,
                    lang            TEXT,
                    status          TEXT NOT NULL DEFAULT 'resolved'
                )
            """)
            conn.execute("""
                INSERT INTO species_alias_new (id, species_id, raw_name, lang, status)
                SELECT id, species_id, raw_name, lang, status FROM species_alias
            """)
            conn.execute("DROP TABLE species_alias")
            conn.execute("ALTER TABLE species_alias_new RENAME TO species_alias")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_alias_raw_name ON species_alias(raw_name)"
            )
            conn.execute(f"""
                CREATE UNIQUE INDEX uniq_alias_resolver
                    ON species_alias(raw_name, lang)
                    WHERE lang IN {RESOLVER_LANGS!r}
            """)
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

        after = conn.execute("SELECT COUNT(*) FROM species_alias").fetchone()[0]
        print(f"species_alias rows after:  {after}")
        assert before == after, f"row count drift: {before} -> {after}"

        # Sanity: resolver-lang dupes should be zero
        dupes = conn.execute(f"""
            SELECT raw_name, lang, COUNT(*) c FROM species_alias
            WHERE lang IN {RESOLVER_LANGS!r}
            GROUP BY raw_name, lang HAVING c > 1
        """).fetchall()
        if dupes:
            print(f"WARNING: {len(dupes)} resolver-lang dupes detected — index would have failed")
            for r in dupes[:10]:
                print(" ", r)
        else:
            print("Resolver-lang uniqueness preserved.")

        print("Migration complete.")


if __name__ == "__main__":
    main()
