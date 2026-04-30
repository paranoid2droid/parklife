"""Find cached files that originated from a PDF URL by querying the
`source` table. Cached files are saved with a .html extension regardless
of content, so we identify PDFs by URL.
"""
from parklife import db
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

with db.connect(ROOT / "data" / "parklife.db") as conn:
    rows = list(conn.execute("""
        SELECT s.url, s.raw_path, p.slug, p.name_ja
        FROM source s LEFT JOIN park p ON p.id=s.park_id
        WHERE LOWER(s.url) LIKE '%.pdf%'
        ORDER BY s.id
    """))
    print(f"PDF source rows: {len(rows)}")
    for r in rows:
        path = ROOT / r["raw_path"] if r["raw_path"] else None
        size = path.stat().st_size if path and path.exists() else 0
        print(f"  {size//1024:>5} KB  {r['slug']:<22} {r['url'][:80]}")
