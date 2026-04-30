"""Investigate the Acanthus phenology mismatch."""
import json
from parklife import db
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent

with db.connect(ROOT / "data" / "parklife.db") as conn:
    r = conn.execute("SELECT id, scientific_name, common_name_ja, inat_taxon_id, photo_url FROM species WHERE common_name_ja='アカンサス'").fetchone()
    print("species row:", dict(r))
    tid = r["inat_taxon_id"]

cache = ROOT / "data" / "cache" / "inat_phenology" / f"{tid}__flower.json"
if cache.exists():
    data = json.loads(cache.read_text(encoding="utf-8"))
    print("\nflowering histogram:")
    for k, v in (data.get("results") or {}).get("month_of_year", {}).items():
        print(f"  month {k}: {v}")

# Also check what taxon_id 1234567 actually represents
from curl_cffi import requests
UA = "parklife-bot/0.1"
r = requests.get(f"https://api.inaturalist.org/v1/taxa/{tid}",
                  headers={"User-Agent": UA}, impersonate="chrome", timeout=15)
if r.status_code == 200:
    t = r.json()["results"][0]
    print(f"\niNat taxon {tid}:")
    print(f"  name: {t.get('name')}")
    print(f"  preferred_common_name: {t.get('preferred_common_name')}")
    print(f"  rank: {t.get('rank')}")
    print(f"  observations_count: {t.get('observations_count')}")
