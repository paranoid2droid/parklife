from parklife import db
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
with db.connect(ROOT / "data" / "parklife.db") as conn:
    n = conn.execute("""
      SELECT COUNT(*) FROM species
      WHERE taxon_group IN ('plant','tree','herb','shrub','vine','fern','moss')
        AND inat_taxon_id IS NULL
        AND scientific_name IS NOT NULL
    """).fetchone()[0]
    print(f"plants without inat_taxon_id but with sci_name: {n}")
    # those represent ~one taxa-lookup call each
    n2 = conn.execute("""
      SELECT COUNT(*) FROM species
      WHERE taxon_group IN ('plant','tree','herb','shrub','vine','fern','moss')
        AND inat_taxon_id IS NOT NULL
    """).fetchone()[0]
    print(f"plants WITH inat_taxon_id: {n2}")
    n3 = conn.execute("""
      SELECT COUNT(*) FROM species
      WHERE taxon_group IN ('plant','tree','herb','shrub','vine','fern','moss')
    """).fetchone()[0]
    print(f"all plant-ish species: {n3}")
