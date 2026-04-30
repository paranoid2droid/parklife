"""Show what bird species we already have for the parks with PDFs."""
from parklife import db
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent

with db.connect(ROOT / "data" / "parklife.db") as conn:
    for slug in ("kasairinkai", "kyu-shiba-rikyu", "zenpukuji"):
        print(f"\n=== {slug} ===")
        rows = list(conn.execute("""
            SELECT s.common_name_ja, s.scientific_name FROM park_species ps
            JOIN park p ON p.id=ps.park_id
            JOIN species s ON s.id=ps.species_id
            WHERE p.slug=? AND s.taxon_group='bird'
            ORDER BY s.common_name_ja
        """, (slug,)))
        print(f"  birds known: {len(rows)}")
        for r in rows[:30]:
            print(f"    {r['common_name_ja']:<14} {r['scientific_name'] or ''}")
        if len(rows) > 30:
            print(f"    ... +{len(rows)-30} more")
