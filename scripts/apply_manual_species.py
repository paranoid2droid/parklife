"""Apply manually curated species mappings from data/manual_species.json
to remaining 'pending' aliases.
"""

from __future__ import annotations

import json
from pathlib import Path

from parklife import db

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    db_path = ROOT / "data" / "parklife.db"
    mapping = json.loads((ROOT / "data" / "manual_species.json").read_text(encoding="utf-8"))
    skipped = resolved = unmapped = 0
    with db.connect(db_path) as conn:
        pending = [
            r["raw_name"] for r in conn.execute(
                "SELECT raw_name FROM species_alias WHERE status='pending'"
            )
        ]
        for raw in pending:
            entry = mapping.get(raw)
            if entry is None:
                unmapped += 1
                continue
            if entry.get("skip"):
                conn.execute(
                    "UPDATE species_alias SET status='rejected' WHERE raw_name=?",
                    (raw,),
                )
                skipped += 1
                continue
            sci = entry.get("scientific_name")
            kingdom = entry.get("kingdom")
            taxon = entry.get("taxon_group")
            row = conn.execute(
                "SELECT id FROM species WHERE common_name_ja=?", (raw,)
            ).fetchone()
            if not row and sci:
                row = conn.execute(
                    "SELECT id FROM species WHERE scientific_name=?", (sci,)
                ).fetchone()
            if row:
                sid = row["id"]
                conn.execute(
                    """UPDATE species SET scientific_name = COALESCE(scientific_name, ?),
                                          kingdom = COALESCE(kingdom, ?),
                                          taxon_group = COALESCE(taxon_group, ?)
                       WHERE id=?""",
                    (sci, kingdom, taxon, sid),
                )
            else:
                cur = conn.execute(
                    """INSERT INTO species (scientific_name, common_name_ja, kingdom, taxon_group)
                       VALUES (?, ?, ?, ?)""",
                    (sci, raw, kingdom, taxon),
                )
                sid = cur.lastrowid
            conn.execute(
                "UPDATE species_alias SET species_id=?, status='resolved' WHERE raw_name=?",
                (sid, raw),
            )
            resolved += 1
        conn.commit()
    print(f"resolved (manual): {resolved}")
    print(f"skipped (non-species): {skipped}")
    print(f"unmapped (still pending): {unmapped}")


if __name__ == "__main__":
    main()
