"""See what plant_phenology inserted as months_bitmap."""
from parklife import db
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent

with db.connect(ROOT / "data" / "parklife.db") as conn:
    rows = list(conn.execute("""
      SELECT s.common_name_ja, s.scientific_name, o.months_bitmap, o.characteristics, p.name_ja AS park
      FROM observation o JOIN species s ON s.id=o.species_id
                          JOIN park p    ON p.id=o.park_id
      WHERE o.location_hint='iNat phenology'
      ORDER BY s.common_name_ja, p.name_ja LIMIT 20
    """))
    print(f"phenology rows: {len(rows)}")
    for r in rows:
        bits = r["months_bitmap"] or 0
        months = [m+1 for m in range(12) if bits & (1<<m)]
        print(f"  {(r['common_name_ja'] or '?'):<14} bits={bits:>4}  months={months}  @{r['park'][:18]}  ({r['characteristics']})")
