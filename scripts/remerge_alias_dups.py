"""Fold species rows whose scientific_name is a `sci` alias of ANOTHER row.

Why this exists: until 2026-09-18 the ingesters (gbif / inaturalist / ebird /
inaturalist_monthly) matched `species.scientific_name` only, so a synonym that
had been merged into a canonical row (and left behind as a `sci` alias) was
re-created as a fresh, ja-name-less duplicate on the next ingestion
(`Poecile varius` → 725 parks Latin-only while ヤマガラ sat on `Sittiparus
varius`). The ingesters now go through `db.resolve_species_id`; this pass
repairs the rows that were created before that fix. Idempotent; safe to
re-run after any ingestion.

Rules:
  * Only species reachable from park_species are considered (invisible rows
    are harmless).
  * Names listed in data/alias_dup_exclusions.json are NOT merged — the alias
    was found to be wrong, so it is deleted instead (the row stays).
  * Everything else is merged into the alias target via
    merge_species_pair.merge_pair (logged to species_merged_log, reversible).

RE-RUN scripts.dedupe afterwards.

Usage:
    .venv/bin/python -m scripts.remerge_alias_dups [--dry-run]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from parklife import db
from scripts.merge_species_pair import merge_pair

ROOT = Path(__file__).resolve().parent.parent
EXCL = ROOT / "data" / "alias_dup_exclusions.json"

FIND_SQL = """
SELECT s.id AS src_id, s.scientific_name AS src_sci, s.common_name_ja AS src_ja,
       t.id AS dst_id, t.scientific_name AS dst_sci, t.common_name_ja AS dst_ja,
       (SELECT COUNT(*) FROM park_species WHERE species_id=s.id) AS np,
       COUNT(DISTINCT al.species_id) AS n_targets
FROM species s
JOIN species_alias al ON al.raw_name = s.scientific_name AND al.lang='sci'
                      AND al.species_id != s.id
JOIN species t ON t.id = al.species_id
WHERE EXISTS (SELECT 1 FROM park_species WHERE species_id = s.id)
GROUP BY s.id
ORDER BY np DESC
"""


def main(dry_run: bool) -> int:
    excl = {k: v for k, v in json.loads(EXCL.read_text()).items() if not k.startswith("_")}
    with db.connect(ROOT / "data" / "parklife.db") as conn:
        rows = list(conn.execute(FIND_SQL))
        print(f"visible species whose sci name is a sci-alias of another row: {len(rows)}")
        merged = skipped = unaliased = 0
        for r in rows:
            tag = f"{r['src_sci']} ({r['src_ja'] or '-'}, np={r['np']}) → {r['dst_sci']} ({r['dst_ja'] or '-'})"
            if r["n_targets"] > 1:
                print(f"  SKIP ambiguous ({r['n_targets']} targets): {tag}")
                skipped += 1
                continue
            if r["src_sci"] in excl:
                print(f"  UNALIAS (excluded: {excl[r['src_sci']]}): {tag}")
                if not dry_run:
                    conn.execute(
                        "DELETE FROM species_alias WHERE raw_name=? AND lang='sci' AND species_id=?",
                        (r["src_sci"], r["dst_id"]))
                unaliased += 1
                continue
            print(f"  MERGE {tag}")
            if not dry_run:
                merge_pair(conn, r["src_id"], r["dst_id"],
                           note="remerge_alias_dups (ingester bypassed sci alias)", verbose=False)
            merged += 1
        if dry_run:
            print(f"(dry-run) would merge {merged}, unalias {unaliased}, skip {skipped}")
            return 0
        conn.commit()
        print(f"merged {merged}, unaliased {unaliased}, skipped {skipped} — now run scripts.dedupe")
    return 0


if __name__ == "__main__":
    sys.exit(main(dry_run="--dry-run" in sys.argv[1:]))
