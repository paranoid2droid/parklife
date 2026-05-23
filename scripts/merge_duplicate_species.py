"""Merge species rows that share the same iNat taxon_id but live as separate
DB rows because of synonym/subspecies scientific-name variants.

Symptom this fixes: common species like ダイサギ / コチドリ / エナガ have a
row with the up-to-date binomial (rich species_photo gallery, profile) and
another row with the old binomial (no gallery, 0 species_photo), and the
demo's modal sometimes hits the empty row → only 1-2 photos.

Two phases:

  1. NULL out **pathological** inat_taxon_id values — IDs that have been
     assigned to wildly unrelated species (>3 distinct binomials sharing a
     single iNat ID is structurally impossible and points to bad backfill).

  2. For every remaining (inat_taxon_id) group with >1 row where all rows
     share a compatible binomial (same first 2 space-separated tokens),
     pick a canonical row (most park_species pairs, lowest id as tiebreak)
     and reassign FKs from the dups to the canonical:
       - observation.species_id  → UPDATE
       - species_alias.species_id → UPDATE
       - species_photo            → INSERT OR IGNORE then DELETE old (UNIQUE(species_id, url))
       - species_profile          → INSERT OR IGNORE (UNIQUE(species_id, lang))
       - park_species_photo       → INSERT OR IGNORE (UNIQUE(park_id, species_id, url))
       - park_species             → DELETE (rebuilt by dedupe)
     Then delete the dup species rows. Caller should follow up with:
       .venv/bin/python -m scripts.dedupe                 # rebuild park_species
       .venv/bin/python -m scripts.park_species_photo     # refresh local gallery

Run with --dry-run to preview without writing.
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

from parklife import db

ROOT = Path(__file__).resolve().parent.parent

# A single iNat taxon_id corresponds to one species. If the DB shows more than
# this many distinct binomials sharing the same iNat ID, the ID itself is
# bogus (placeholder / wrong backfill) and we NULL it out rather than merge.
MAX_BINOMIALS_PER_TID = 3


def binomial(sci: str | None) -> str:
    if not sci:
        return ""
    parts = sci.split()
    return " ".join(parts[:2]).lower() if parts else ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would be done without writing")
    args = ap.parse_args()

    db_path = ROOT / "data" / "parklife.db"
    with db.connect(db_path) as conn:
        all_rows = list(conn.execute("""
            SELECT id, inat_taxon_id, scientific_name, common_name_ja,
                   photo_url, kingdom, taxon_group
            FROM species
            WHERE inat_taxon_id IS NOT NULL
        """))
    groups: dict[int, list[dict]] = defaultdict(list)
    for r in all_rows:
        groups[r["inat_taxon_id"]].append(dict(r))

    bogus_tids: list[int] = []
    mergeable: dict[int, list[dict]] = {}
    for tid, rows in groups.items():
        if len(rows) < 2:
            continue
        binomials = {binomial(r["scientific_name"]) for r in rows if r["scientific_name"]}
        binomials.discard("")
        # Below MAX_BINOMIALS_PER_TID we trust iNat's taxon_id as identity even
        # when the local scientific_name strings differ — that's literally what
        # the iNat taxon record means (e.g. Casmerodius albus and Ardea alba
        # both resolve to iNat taxon 144455). Above it, the ID is structurally
        # impossible (one taxon ≠ 5+ unrelated species), so NULL it instead.
        if len(binomials) > MAX_BINOMIALS_PER_TID:
            bogus_tids.append(tid)
            continue
        mergeable[tid] = rows

    print(f"groups inspected: {sum(1 for g in groups.values() if len(g) > 1)}")
    print(f"bogus tids (>{MAX_BINOMIALS_PER_TID} binomials): {len(bogus_tids)} "
          f"covering {sum(len(groups[t]) for t in bogus_tids)} species rows")
    n_merge_rows = sum(len(v) for v in mergeable.values())
    print(f"mergeable tid groups: {len(mergeable)} covering "
          f"{n_merge_rows} species rows "
          f"(net delete = {n_merge_rows - len(mergeable)})")

    if args.dry_run:
        print("\n(dry-run) sample merges:")
        for tid, rows in list(mergeable.items())[:8]:
            rows.sort(key=lambda r: r["id"])
            names = [f"id={r['id']} {r['scientific_name']}" for r in rows]
            print(f"  tid={tid}: {' | '.join(names)}")
        return 0

    with db.connect(db_path) as conn:
        # 1. Phase 1 — null out bogus taxon IDs (preserve species rows)
        if bogus_tids:
            ph = ",".join("?" * len(bogus_tids))
            n = conn.execute(
                f"UPDATE species SET inat_taxon_id = NULL "
                f"WHERE inat_taxon_id IN ({ph})",
                tuple(bogus_tids),
            ).rowcount
            print(f"\nphase 1: NULLed inat_taxon_id on {n} species rows "
                  f"({len(bogus_tids)} bogus tids)")

        # 2. Phase 2 — merge synonym duplicates
        total_dups = 0
        for tid, rows in mergeable.items():
            # Re-fetch park_species counts to pick canonical
            ids = tuple(r["id"] for r in rows)
            ph = ",".join("?" * len(ids))
            np_rows = dict(conn.execute(
                f"SELECT species_id, COUNT(*) FROM park_species "
                f"WHERE species_id IN ({ph}) GROUP BY species_id",
                ids,
            ).fetchall())
            rows.sort(key=lambda r: (-np_rows.get(r["id"], 0), r["id"]))
            canonical = rows[0]
            dups = rows[1:]
            cid = canonical["id"]
            # Backfill canonical fields that are NULL from dups
            updates: dict[str, object] = {}
            if not canonical["photo_url"]:
                for d in dups:
                    if d["photo_url"]:
                        updates["photo_url"] = d["photo_url"]; break
            if not canonical["kingdom"]:
                for d in dups:
                    if d["kingdom"]:
                        updates["kingdom"] = d["kingdom"]; break
            if not canonical["taxon_group"]:
                for d in dups:
                    if d["taxon_group"]:
                        updates["taxon_group"] = d["taxon_group"]; break
            if not canonical["common_name_ja"]:
                for d in dups:
                    if d["common_name_ja"]:
                        updates["common_name_ja"] = d["common_name_ja"]; break
            if updates:
                cols = ", ".join(f"{k}=?" for k in updates)
                conn.execute(f"UPDATE species SET {cols} WHERE id=?",
                             (*updates.values(), cid))

            for d in dups:
                did = d["id"]
                conn.execute("UPDATE observation  SET species_id=? WHERE species_id=?", (cid, did))
                conn.execute("UPDATE species_alias SET species_id=? WHERE species_id=?", (cid, did))
                # species_photo — UNIQUE(species_id, url)
                conn.execute("""
                    INSERT OR IGNORE INTO species_photo
                      (species_id, url, thumb_url, attribution, source, sort_order, source_url)
                    SELECT ?, url, thumb_url, attribution, source, sort_order, source_url
                    FROM species_photo WHERE species_id=?
                """, (cid, did))
                conn.execute("DELETE FROM species_photo WHERE species_id=?", (did,))
                # species_profile — UNIQUE(species_id, lang)
                conn.execute("""
                    INSERT OR IGNORE INTO species_profile
                      (species_id, lang, summary, habitat_hint, finding_tips,
                       sources, updated_at, source_urls)
                    SELECT ?, lang, summary, habitat_hint, finding_tips,
                       sources, updated_at, source_urls
                    FROM species_profile WHERE species_id=?
                """, (cid, did))
                conn.execute("DELETE FROM species_profile WHERE species_id=?", (did,))
                # park_species_photo — UNIQUE(park_id, species_id, url)
                conn.execute("""
                    INSERT OR IGNORE INTO park_species_photo
                      (park_id, species_id, url, thumb_url, attribution, source,
                       source_url, sort_order, tier)
                    SELECT park_id, ?, url, thumb_url, attribution, source,
                       source_url, sort_order, tier
                    FROM park_species_photo WHERE species_id=?
                """, (cid, did))
                conn.execute("DELETE FROM park_species_photo WHERE species_id=?", (did,))
                # park_species — derived; just drop, dedupe will rebuild
                conn.execute("DELETE FROM park_species WHERE species_id=?", (did,))
                # Finally drop the dup species row
                conn.execute("DELETE FROM species WHERE id=?", (did,))
                total_dups += 1

            # Also drop canonical's park_species rows; dedupe will rebuild
            # using the now-redirected observations.
            conn.execute("DELETE FROM park_species WHERE species_id=?", (cid,))

        conn.commit()
        print(f"\nphase 2: merged {total_dups} dup species rows into "
              f"{len(mergeable)} canonical rows")

        remaining = conn.execute("SELECT COUNT(*) FROM species").fetchone()[0]
        print(f"species remaining: {remaining}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
