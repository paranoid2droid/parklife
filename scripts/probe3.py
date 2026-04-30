from parklife import db
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
with db.connect(ROOT / "data" / "parklife.db") as conn:
    n_total = conn.execute("SELECT COUNT(*) FROM species").fetchone()[0]
    n_inat = conn.execute("SELECT COUNT(*) FROM species WHERE inat_taxon_id IS NOT NULL").fetchone()[0]
    n_photo = conn.execute("SELECT COUNT(*) FROM species WHERE photo_url IS NOT NULL").fetchone()[0]
    print(f"species total: {n_total}; with inat_taxon_id: {n_inat}; with photo_url: {n_photo}")
    print("\nsample with inat_taxon_id:")
    for r in conn.execute("SELECT common_name_ja, scientific_name, inat_taxon_id FROM species WHERE inat_taxon_id IS NOT NULL LIMIT 5"):
        print(f"  {r[0]}  {r[1]}  taxon={r[2]}")
    print("\nsample plants without inat_taxon_id:")
    for r in conn.execute("SELECT common_name_ja, scientific_name, photo_url FROM species WHERE taxon_group IN ('plant','tree','herb','shrub','vine') AND inat_taxon_id IS NULL LIMIT 5"):
        print(f"  {r[0]}  {r[1]}  photo={r[2] is not None}")
