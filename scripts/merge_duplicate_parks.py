"""Fold duplicate park rows (data/park_merges.json) into their canonical row.

Background: P13 (国土数値情報 都市公園) seeding deduplicated only against
other P13 entries, never against the original website-seeded 209 parks, so
~18 parks ended up with two markers (e.g. 神代植物公園 ×3). The original row
keeps the official URL and scraped data, so it is always the destination.

Per pair (src → dst):
  * observation / source / park_species_photo rows are repointed to dst
    (photo PK collisions are dropped on the src side);
  * dst.lat/lon/area_m2/municipality are filled from src where dst is NULL
    (six originals never geocoded and therefore never got radius data);
  * both sides' park_species rows are deleted (scripts.dedupe rebuilds);
  * the src park row is copied to park_merged_log, then deleted.

RE-RUN scripts.dedupe afterwards. Idempotent (a src that no longer exists is
skipped). --dry-run prints the plan.

Usage:
    .venv/bin/python -m scripts.merge_duplicate_parks [--dry-run]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from parklife import db

ROOT = Path(__file__).resolve().parent.parent
PAIRS = ROOT / "data" / "park_merges.json"

LOG_DDL = """CREATE TABLE IF NOT EXISTS park_merged_log (
    id INTEGER PRIMARY KEY, orig_park_id INTEGER, slug TEXT, name_ja TEXT,
    prefecture TEXT, municipality TEXT, official_url TEXT, lat REAL, lon REAL,
    area_m2 REAL, merged_into INTEGER, merged_at TEXT, note TEXT)"""


def merge_park(conn, src_id: int, dst_id: int, note: str) -> dict | None:
    src = conn.execute("SELECT * FROM park WHERE id=?", (src_id,)).fetchone()
    dst = conn.execute("SELECT * FROM park WHERE id=?", (dst_id,)).fetchone()
    if not src or not dst:
        return None
    conn.execute(LOG_DDL)
    conn.execute("""INSERT INTO park_merged_log
        (orig_park_id, slug, name_ja, prefecture, municipality, official_url, lat, lon,
         area_m2, merged_into, merged_at, note) VALUES (?,?,?,?,?,?,?,?,?,?,datetime('now'),?)""",
        (src["id"], src["slug"], src["name_ja"], src["prefecture"], src["municipality"],
         src["official_url"], src["lat"], src["lon"], src["area_m2"], dst["id"], note))
    n_obs = conn.execute("UPDATE observation SET park_id=? WHERE park_id=?",
                         (dst_id, src_id)).rowcount
    n_src = conn.execute("UPDATE source SET park_id=? WHERE park_id=?",
                         (dst_id, src_id)).rowcount
    conn.execute("""INSERT OR IGNORE INTO park_species_photo
        (park_id, species_id, url, thumb_url, attribution, source, source_url, sort_order, tier)
        SELECT ?, species_id, url, thumb_url, attribution, source, source_url, sort_order, tier
        FROM park_species_photo WHERE park_id=?""", (dst_id, src_id))
    conn.execute("DELETE FROM park_species_photo WHERE park_id=?", (src_id,))
    for col in ("lat", "lon", "area_m2", "municipality"):
        if dst[col] is None and src[col] is not None:
            conn.execute(f"UPDATE park SET {col}=? WHERE id=? AND {col} IS NULL",
                         (src[col], dst_id))
    conn.execute("DELETE FROM park_species WHERE park_id IN (?, ?)", (src_id, dst_id))
    conn.execute("DELETE FROM park WHERE id=?", (src_id,))
    return {"obs": n_obs, "sources": n_src}


def main(dry_run: bool) -> int:
    pairs = json.loads(PAIRS.read_text())["pairs"]
    with db.connect(ROOT / "data" / "parklife.db") as conn:
        done = skipped = 0
        for p in pairs:
            src = conn.execute("SELECT id, name_ja, lat FROM park WHERE id=?", (p["src"],)).fetchone()
            dst = conn.execute("SELECT id, name_ja, lat FROM park WHERE id=?", (p["dst"],)).fetchone()
            if not src or not dst:
                print(f"  skip {p['src']}→{p['dst']} (already merged / missing)")
                skipped += 1
                continue
            n = conn.execute("SELECT COUNT(*) FROM observation WHERE park_id=?", (src["id"],)).fetchone()[0]
            print(f"  {src['id']} {src['name_ja']} → {dst['id']} {dst['name_ja']}"
                  f"  ({n} obs; dst coords {'NULL→copied' if dst['lat'] is None else 'kept'})")
            if not dry_run:
                merge_park(conn, src["id"], dst["id"], p.get("why", ""))
            done += 1
        if dry_run:
            print(f"(dry-run) would merge {done}, skip {skipped}")
            return 0
        conn.commit()
        print(f"merged {done} park rows, skipped {skipped} — now run scripts.dedupe")
    return 0


if __name__ == "__main__":
    sys.exit(main(dry_run="--dry-run" in sys.argv[1:]))
