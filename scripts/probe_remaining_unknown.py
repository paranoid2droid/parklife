"""List all remaining 'unknown parking' parks with metadata to decide
the best next move."""
from parklife import db
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent

with db.connect(ROOT / "data" / "parklife.db") as conn:
    for pref in ("tokyo", "saitama", "chiba", "kanagawa"):
        rows = list(conn.execute(
            "SELECT slug, name_ja, municipality, official_url FROM park "
            "WHERE has_parking IS NULL AND prefecture=? ORDER BY slug", (pref,)
        ))
        if not rows: continue
        print(f"\n=== {pref}: {len(rows)} ===")
        for r in rows:
            print(f"  {r['slug']:<26} {r['name_ja']:<24} ({r['municipality'] or ''})")
