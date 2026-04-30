"""Rebuild the `park_species` derived table.

Aggregates every `observation` row by (park_id, species_id):
  - months_bitmap = bitwise OR of source bitmaps (NULL counted as 0)
  - observation_count = number of source rows
  - source_count = number of distinct source_id values
  - raw_names = pipe-joined unique raw_name strings
  - location_hints / characteristics = '; '-joined unique non-empty values

Run after any ingestion change. Idempotent: drops and refills the table.
Skips observation rows where species_id IS NULL (we can't dedup unresolved
names — they stay only in the observation table for traceability).
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from parklife import db

ROOT = Path(__file__).resolve().parent.parent


def _join_unique(values, sep="; ") -> str | None:
    seen: list[str] = []
    for v in values:
        if v is None:
            continue
        v = str(v).strip()
        if not v or v in seen:
            continue
        seen.append(v)
    return sep.join(seen) if seen else None


def main() -> None:
    db_path = ROOT / "data" / "parklife.db"
    db.init(db_path)  # ensure park_species table exists
    with db.connect(db_path) as conn:
        rows = conn.execute("""
            SELECT park_id, species_id, months_bitmap, raw_name,
                   location_hint, characteristics, source_id
            FROM observation
            WHERE species_id IS NOT NULL
        """).fetchall()

        # aggregate in Python (BIT_OR isn't available in this SQLite build)
        agg: dict[tuple[int, int], dict] = defaultdict(lambda: {
            "months": 0, "count": 0, "sources": set(),
            "raw_names": [], "loc": [], "chars": [],
        })
        for r in rows:
            key = (r["park_id"], r["species_id"])
            a = agg[key]
            a["months"] |= (r["months_bitmap"] or 0)
            a["count"] += 1
            if r["source_id"] is not None:
                a["sources"].add(r["source_id"])
            a["raw_names"].append(r["raw_name"])
            a["loc"].append(r["location_hint"])
            a["chars"].append(r["characteristics"])

        conn.execute("DELETE FROM park_species")
        inserted = 0
        for (pid, sid), a in agg.items():
            conn.execute(
                """INSERT INTO park_species
                   (park_id, species_id, months_bitmap, observation_count,
                    source_count, raw_names, location_hints, characteristics)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    pid, sid,
                    a["months"] or None,  # 0 → NULL (truly unknown vs known-no-month)
                    a["count"],
                    len(a["sources"]),
                    _join_unique(a["raw_names"], sep="|"),
                    _join_unique(a["loc"]),
                    _join_unique(a["chars"]),
                ),
            )
            inserted += 1
        conn.commit()
    print(f"rebuilt park_species: {inserted} rows from {len(rows)} observations")
    print(f"  dedup ratio: {inserted/max(1,len(rows)):.1%}")


if __name__ == "__main__":
    main()
