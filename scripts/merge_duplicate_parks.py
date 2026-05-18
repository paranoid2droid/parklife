"""Merge duplicate parks introduced by P13 expansion.

For each (prefecture, name_ja) group with >1 rows:
  canonical = non-p13 row with lowest id, else lowest id overall
  Move observation/source FKs to canonical; delete park_species (rebuilt by dedupe);
  also fill canonical metadata (has_parking, parking_info, area_m2) from a dup
  if canonical is missing them.
  Delete duplicate park rows.

Then re-run scripts.dedupe to rebuild park_species.
"""
from __future__ import annotations

import sys
from pathlib import Path

from parklife import db

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    db_path = ROOT / "data" / "parklife.db"
    with db.connect(db_path) as conn:
        groups = list(conn.execute("""
            SELECT prefecture, name_ja
            FROM park
            WHERE name_ja IS NOT NULL AND name_ja != ''
            GROUP BY prefecture, name_ja
            HAVING COUNT(*) > 1
        """))
        print(f"duplicate groups: {len(groups)}")

        total_merged = 0
        for pref, name in groups:
            rows = list(conn.execute("""
                SELECT id, slug, has_parking, parking_info, area_m2, official_url, operator
                FROM park
                WHERE prefecture=? AND name_ja=?
                ORDER BY
                  CASE WHEN slug LIKE 'p13-%' THEN 1 ELSE 0 END,
                  id
            """, (pref, name)))
            canonical = rows[0]
            dups = rows[1:]
            cid = canonical["id"]
            print(f"\n{pref}/{name}: canonical id={cid} slug={canonical['slug']}")

            # Fill canonical metadata from dups where canonical is missing
            updates = {}
            if canonical["has_parking"] is None:
                for d in dups:
                    if d["has_parking"] is not None:
                        updates["has_parking"] = d["has_parking"]
                        updates["parking_info"] = d["parking_info"]
                        break
            if not canonical["area_m2"]:
                for d in dups:
                    if d["area_m2"]:
                        updates["area_m2"] = d["area_m2"]
                        break
            if not canonical["official_url"]:
                for d in dups:
                    if d["official_url"]:
                        updates["official_url"] = d["official_url"]
                        break
            if not canonical["operator"]:
                for d in dups:
                    if d["operator"]:
                        updates["operator"] = d["operator"]
                        break
            if updates:
                cols = ", ".join(f"{k}=?" for k in updates)
                conn.execute(f"UPDATE park SET {cols} WHERE id=?",
                             (*updates.values(), cid))
                print(f"  filled canonical: {list(updates.keys())}")

            for d in dups:
                did = d["id"]
                n_obs = conn.execute(
                    "UPDATE observation SET park_id=? WHERE park_id=?",
                    (cid, did)).rowcount
                n_src = conn.execute(
                    "UPDATE source SET park_id=? WHERE park_id=?",
                    (cid, did)).rowcount
                n_ps = conn.execute(
                    "DELETE FROM park_species WHERE park_id=?",
                    (did,)).rowcount
                conn.execute("DELETE FROM park WHERE id=?", (did,))
                print(f"  merged dup id={did} slug={d['slug']}: "
                      f"+{n_obs} obs, +{n_src} src, -{n_ps} ps rows")
                total_merged += 1

            # Also drop canonical's park_species; dedupe will rebuild.
            conn.execute("DELETE FROM park_species WHERE park_id=?", (cid,))
        conn.commit()

        remaining = conn.execute("SELECT COUNT(*) FROM park").fetchone()[0]
        print(f"\nmerged {total_merged} duplicate rows; "
              f"{remaining} parks remain")
    return 0


if __name__ == "__main__":
    sys.exit(main())
