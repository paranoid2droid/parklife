"""Resolve all pending species_alias rows via Japanese Wikipedia.

For each unique raw_name with status='pending':
  1. Look it up (cached on disk under data/cache/wikipedia/).
  2. If found and not a disambig: upsert a `species` row keyed on title
     (canonical Japanese name) and link the alias to it (status='resolved').
  3. If disambig or not found: leave alias status='pending'.

Politeness: ~5 lookups/sec, cached so re-runs are free.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from parklife import db
from parklife.normalize import wikipedia

ROOT = Path(__file__).resolve().parent.parent


def upsert_species(conn, res: wikipedia.Resolved) -> int:
    """Find or create a species row.

    Match priority: (1) common_name_ja == title, (2) scientific_name match if
    a binomial is present. Two distinct Japanese names that resolve to the
    same Latin name share a row (usually they are synonyms or vernacular variants)."""
    row = conn.execute(
        "SELECT id FROM species WHERE common_name_ja = ?", (res.title,)
    ).fetchone()
    if not row and res.scientific_name:
        row = conn.execute(
            "SELECT id FROM species WHERE scientific_name = ?", (res.scientific_name,)
        ).fetchone()
    if row:
        sid = row["id"]
        conn.execute(
            """UPDATE species SET scientific_name = COALESCE(scientific_name, ?),
                                  kingdom = COALESCE(kingdom, ?),
                                  taxon_group = COALESCE(taxon_group, ?)
               WHERE id = ?""",
            (res.scientific_name, res.kingdom, res.taxon_group, sid),
        )
        return sid
    cur = conn.execute(
        """INSERT INTO species (scientific_name, common_name_ja, kingdom, taxon_group)
           VALUES (?, ?, ?, ?)""",
        (res.scientific_name, res.title, res.kingdom, res.taxon_group),
    )
    return cur.lastrowid


def main(limit: int | None = None) -> None:
    db_path = ROOT / "data" / "parklife.db"
    with db.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT DISTINCT raw_name, lang FROM species_alias WHERE status='pending' "
            "ORDER BY raw_name"
        ).fetchall()
        if limit:
            rows = rows[:limit]
        total = len(rows)
        resolved = disambig = notfound = errors = 0
        t0 = time.time()
        for i, r in enumerate(rows, 1):
            name = r["raw_name"]
            res = wikipedia.lookup_with_cache(name, ROOT)
            if res.error:
                errors += 1
                continue
            if not res.found:
                notfound += 1
                continue
            if res.is_disambig:
                disambig += 1
                continue
            sid = upsert_species(conn, res)
            conn.execute(
                "UPDATE species_alias SET species_id=?, status='resolved' "
                "WHERE raw_name=? AND lang=?",
                (sid, name, r["lang"]),
            )
            resolved += 1
            if i % 25 == 0:
                conn.commit()
                rate = i / max(0.1, time.time() - t0)
                eta_s = (total - i) / max(0.1, rate)
                print(f"[{i:>4}/{total}] resolved={resolved} disambig={disambig} "
                      f"notfound={notfound} errors={errors}  rate={rate:.1f}/s  eta={eta_s:.0f}s")
        conn.commit()
        print(f"\n=== done: {total} names ===")
        print(f"  resolved : {resolved}")
        print(f"  disambig : {disambig}")
        print(f"  notfound : {notfound}")
        print(f"  errors   : {errors}")


if __name__ == "__main__":
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    main(limit)
