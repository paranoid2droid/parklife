"""One-off: add + backfill observation.obs_count and park_species.abundance.

The per-source sighting count each ingestion already fetched was only stored in
free-text `characteristics` ('observations: N' / 'GBIF occurrences: N' /
'count: N'). This promotes it to a numeric column so ranking can reflect real
abundance (perception) instead of our source-row count. Idempotent; batched
commits so it interleaves with a concurrently-running ingest.

After this, scripts.dedupe recomputes park_species.abundance itself; the in-place
UPDATE here is just so the value is available before the next full dedupe.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "parklife.db"

# 'observations: 5' (iNat) | 'GBIF occurrences: 3' | 'count: 12' (eBird)
_PAT = re.compile(r"(?:observations|GBIF occurrences|count):\s*(\d+)")


def parse_count(characteristics: str | None) -> int | None:
    if not characteristics:
        return None
    m = _PAT.search(characteristics)
    return int(m.group(1)) if m else None


def main() -> None:
    conn = sqlite3.connect(DB, timeout=120)
    conn.execute("PRAGMA busy_timeout = 120000")
    cols = lambda t: {r[1] for r in conn.execute(f"PRAGMA table_info({t})")}
    if "obs_count" not in cols("observation"):
        conn.execute("ALTER TABLE observation ADD COLUMN obs_count INTEGER")
        print("added observation.obs_count")
    if "abundance" not in cols("park_species"):
        conn.execute("ALTER TABLE park_species ADD COLUMN abundance INTEGER")
        print("added park_species.abundance")
    conn.commit()

    # 1. backfill observation.obs_count from characteristics (batched)
    rows = conn.execute(
        "SELECT id, characteristics FROM observation "
        "WHERE obs_count IS NULL AND characteristics IS NOT NULL"
    ).fetchall()
    updates = [(c, rid) for rid, ch in rows if (c := parse_count(ch)) is not None]
    print(f"observation rows to backfill: {len(updates)} (of {len(rows)} scanned)")
    for i in range(0, len(updates), 10000):
        conn.executemany("UPDATE observation SET obs_count=? WHERE id=?",
                         updates[i:i + 10000])
        conn.commit()
    print("obs_count backfill done")

    # 2. park_species.abundance = MAX onsite obs_count per pair (batched UPDATE;
    #    dedupe will recompute this identically on its next run)
    pairs = conn.execute(
        "SELECT park_id, species_id, MAX(obs_count) FROM observation "
        "WHERE evidence_tier='onsite' AND obs_count IS NOT NULL "
        "GROUP BY park_id, species_id"
    ).fetchall()
    print(f"park_species pairs to set abundance: {len(pairs)}")
    ups = [(mx, pid, sid) for pid, sid, mx in pairs]
    for i in range(0, len(ups), 10000):
        conn.executemany(
            "UPDATE park_species SET abundance=? WHERE park_id=? AND species_id=?",
            ups[i:i + 10000])
        conn.commit()
    print("abundance UPDATE done")
    conn.close()


if __name__ == "__main__":
    main()
