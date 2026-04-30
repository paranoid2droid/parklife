"""Revert loose-match parking entries (those with `(loose) ` prefix)
back to has_parking=NULL because the loose match conflates group-only /
reservation-only parking with general public parking."""
from parklife import db
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
with db.connect(ROOT / "data" / "parklife.db") as conn:
    cur = conn.execute(
        "UPDATE park SET has_parking=NULL, parking_info=NULL "
        "WHERE parking_info LIKE '(loose)%'"
    )
    conn.commit()
    print(f"reverted {cur.rowcount} loose-match parking rows")
