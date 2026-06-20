"""One-off migration: backfill `park.parking_source` and fix the OSM-absence bug.

Before this, OSM "no parking node within 300m" was written as a CONFIDENT
has_parking=0 — but OSM under-mapping is indistinguishable from a genuine lack
of parking, so >half the negatives were really just "unmapped". This:

  1. adds the `parking_source` evidence-tier column,
  2. re-derives a source tier for every already-classified row from its stored
     `parking_info` snippet (via the canonical patterns in parklife.parking),
  3. **demotes OSM-absent negatives (has_parking=0, parking_info 'OSM: no…') to
     NULL** so they read as honest "unknown" and stay re-checkable.

Idempotent. Safe to re-run.
"""
from __future__ import annotations

import re
from pathlib import Path

from parklife import db
from parklife.parking import (
    NEGATIVE_PATTERNS,
    POSITIVE_PATTERNS,
    RESTRICTED_PATTERNS,
    SOURCE_MANUAL,
    SOURCE_OSM_ABSENT,
    SOURCE_OSM_PRESENT,
    SOURCE_TEXT_MENTION,
    SOURCE_TEXT_NEGATIVE,
    SOURCE_TEXT_POSITIVE,
    SOURCE_TEXT_RESTRICTED,
    SOURCE_TMG_NO_FACILITY,
    SOURCE_UNKNOWN,
)

ROOT = Path(__file__).resolve().parent.parent


def infer_source(has, info: str | None) -> str:
    """Best-effort evidence tier from the stored verdict + snippet."""
    info = info or ""
    if info.startswith("manual:"):
        return SOURCE_MANUAL
    if info.startswith("OSM:"):
        return SOURCE_OSM_PRESENT if has == 1 else SOURCE_OSM_ABSENT
    if info.startswith("(TMG"):
        return SOURCE_TMG_NO_FACILITY
    # text / scraped snippet — match the canonical patterns against it.
    snippet = info
    if snippet.startswith("scraped("):
        snippet = snippet.split("):", 1)[-1]
    if any(p.search(snippet) for p in NEGATIVE_PATTERNS):
        return SOURCE_TEXT_NEGATIVE
    for m in re.finditer(r"駐車", snippet):
        window = snippet[max(0, m.start() - 80): m.end() + 200]
        if any(p.search(window) for p in RESTRICTED_PATTERNS):
            return SOURCE_TEXT_RESTRICTED
    if any(p.search(snippet) for p in POSITIVE_PATTERNS):
        return SOURCE_TEXT_POSITIVE
    if "駐車" in snippet or "パーキング" in snippet:
        return SOURCE_TEXT_MENTION
    return SOURCE_UNKNOWN


def main() -> None:
    db_path = ROOT / "data" / "parklife.db"
    with db.connect(db_path) as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(park)")}
        if "parking_source" not in cols:
            conn.execute("ALTER TABLE park ADD COLUMN parking_source TEXT")
            print("added column park.parking_source")

        rows = list(conn.execute(
            "SELECT id, has_parking, parking_info FROM park"
        ))
        backfilled = demoted = 0
        for r in rows:
            src = infer_source(r["has_parking"], r["parking_info"])
            if src == SOURCE_OSM_ABSENT and r["has_parking"] == 0:
                # The bug fix: OSM absence is unknown, not "no parking".
                conn.execute(
                    "UPDATE park SET has_parking=NULL, parking_source=? WHERE id=?",
                    (src, r["id"]))
                demoted += 1
            else:
                conn.execute(
                    "UPDATE park SET parking_source=? WHERE id=?",
                    (src, r["id"]))
            backfilled += 1
        conn.commit()

        print(f"backfilled parking_source for {backfilled} parks")
        print(f"demoted OSM-absent negatives 0 -> NULL: {demoted}")
        print()
        print("=== has_parking distribution after migration ===")
        for hp, n in conn.execute(
            "SELECT has_parking, COUNT(*) FROM park GROUP BY has_parking ORDER BY has_parking IS NULL, has_parking"
        ):
            print(f"  has_parking={hp if hp is not None else 'NULL':>4}: {n}")
        print()
        print("=== parking_source distribution ===")
        for src, n in conn.execute(
            "SELECT parking_source, COUNT(*) FROM park GROUP BY parking_source ORDER BY COUNT(*) DESC"
        ):
            print(f"  {src or '(none)':<18}: {n}")


if __name__ == "__main__":
    main()
