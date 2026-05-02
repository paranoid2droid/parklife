"""Backfill detailed taxon groups for animal species from cached GBIF records.

Earlier GBIF enrichment only mapped a small set of animal classes. That left
crustaceans, echinoderms, myriapods, cnidarians, annelids, and several smaller
phyla as ``kingdom='animalia'`` with ``taxon_group=NULL``. The demo then had no
honest choice except "other animal".

This repair is cache-only and conservative: it updates animal species with a
missing ``taxon_group`` when their scientific name is present in the local GBIF
cache and maps to a known class or phylum.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from parklife import db
from scripts.gbif import CLASS_TO_GROUP, FAMILY_TO_GROUP, ORDER_TO_GROUP, PHYLUM_TO_GROUP

ROOT = Path(__file__).resolve().parent.parent

MANUAL_GROUPS = {
    # GBIF cache has this historical spelling without class/phylum metadata.
    # Current taxonomy treats it as Intybia histrio, a melyrid beetle.
    "Lajus histrio": "insect",
}


def group_for(occ: dict) -> str | None:
    cls = occ.get("class") or ""
    phylum = occ.get("phylum") or ""
    order = occ.get("order") or ""
    family = occ.get("family") or ""

    sci = occ.get("species") or occ.get("scientificName") or ""
    group = (MANUAL_GROUPS.get(sci)
             or CLASS_TO_GROUP.get(cls)
             or ORDER_TO_GROUP.get(order)
             or FAMILY_TO_GROUP.get(family)
             or PHYLUM_TO_GROUP.get(phylum))
    if group:
        return group
    return None


def cached_gbif_groups() -> dict[str, str]:
    by_scientific: dict[str, str] = {}
    cache_dir = ROOT / "data" / "cache" / "gbif"
    for path in sorted(cache_dir.glob("*.json")):
        try:
            records = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for occ in records:
            sci = occ.get("species") or occ.get("scientificName")
            if not sci or sci in by_scientific:
                continue
            group = group_for(occ)
            if group:
                by_scientific[sci] = group
    return by_scientific


def main() -> int:
    groups = cached_gbif_groups()
    changed = Counter()
    skipped = []
    with db.connect(ROOT / "data" / "parklife.db") as conn:
        rows = list(conn.execute("""
            SELECT id, scientific_name, common_name_ja, common_name_en
            FROM species
            WHERE kingdom = 'animalia'
              AND taxon_group IS NULL
              AND scientific_name IS NOT NULL
            ORDER BY id
        """))
        for row in rows:
            group = groups.get(row["scientific_name"])
            if not group:
                group = MANUAL_GROUPS.get(row["scientific_name"])
            if group:
                conn.execute(
                    "UPDATE species SET taxon_group=? WHERE id=?",
                    (group, row["id"]),
                )
                changed[group] += 1
            else:
                skipped.append(row)
        conn.commit()

    print(f"updated {sum(changed.values())} animal species")
    for group, count in changed.most_common():
        print(f"  {group}: {count}")
    if skipped:
        print(f"skipped {len(skipped)} species without a known cached GBIF class/phylum")
        for row in skipped[:20]:
            name = row["common_name_ja"] or row["common_name_en"] or row["scientific_name"]
            print(f"  {row['id']}: {name} / {row['scientific_name']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
