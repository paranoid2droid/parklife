"""Drop the bad phenology data from the misplaced (NZ instead of Japan) run.

Removes:
  - all observation rows with location_hint='iNat phenology'
  - all source rows whose URL mentions place_id=6803
  - the cache dir data/cache/inat_phenology/
"""
from __future__ import annotations
import shutil
from pathlib import Path
from parklife import db

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    db_path = ROOT / "data" / "parklife.db"
    cache = ROOT / "data" / "cache" / "inat_phenology"
    if cache.exists():
        n = sum(1 for _ in cache.glob("*.json"))
        shutil.rmtree(cache)
        print(f"removed cache dir ({n} files)")

    with db.connect(db_path) as conn:
        n_obs = conn.execute(
            "SELECT COUNT(*) FROM observation WHERE location_hint='iNat phenology'"
        ).fetchone()[0]
        conn.execute("DELETE FROM observation WHERE location_hint='iNat phenology'")
        n_src = conn.execute(
            "SELECT COUNT(*) FROM source WHERE url LIKE '%place_id=6803%'"
        ).fetchone()[0]
        conn.execute("DELETE FROM source WHERE url LIKE '%place_id=6803%'")
        conn.commit()
    print(f"removed {n_obs} bad phenology observation rows")
    print(f"removed {n_src} stale source rows (place_id=6803)")


if __name__ == "__main__":
    main()
