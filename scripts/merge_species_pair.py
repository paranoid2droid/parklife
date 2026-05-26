"""Merge one species row into another by id.

Use when a generic/placeholder species row (e.g. `サクラ` with NULL
scientific_name) should be collapsed into a specific existing row
(e.g. `ソメイヨシノ` / *Cerasus × yedoensis*). All observations,
aliases, photos, and profiles attached to the source are repointed
to the destination; the source species row is deleted; the
canonical's `common_name_ja` is preserved, and the source's
common_name_ja is added as a `ja` alias if not already present.

Run dedupe afterwards.

Example:
    .venv/bin/python -m scripts.merge_species_pair --from 181 --to 252
"""
from __future__ import annotations

import argparse
from pathlib import Path

from parklife import db

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="src_id", type=int, required=True,
                    help="species.id to absorb (will be deleted)")
    ap.add_argument("--to", dest="dst_id", type=int, required=True,
                    help="species.id to keep (canonical)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.src_id == args.dst_id:
        print("source and destination are the same; nothing to do")
        return 0

    db_path = ROOT / "data" / "parklife.db"
    with db.connect(db_path) as conn:
        src = conn.execute(
            "SELECT id, scientific_name, common_name_ja FROM species WHERE id=?",
            (args.src_id,)).fetchone()
        dst = conn.execute(
            "SELECT id, scientific_name, common_name_ja FROM species WHERE id=?",
            (args.dst_id,)).fetchone()
        if not src:
            print(f"source id={args.src_id} not found"); return 1
        if not dst:
            print(f"destination id={args.dst_id} not found"); return 1

        print(f"  src: id={src['id']} sci={src['scientific_name']!r} ja={src['common_name_ja']!r}")
        print(f"  dst: id={dst['id']} sci={dst['scientific_name']!r} ja={dst['common_name_ja']!r}")

        obs_n = conn.execute(
            "SELECT COUNT(*) FROM observation WHERE species_id=?", (src['id'],)
        ).fetchone()[0]
        alias_n = conn.execute(
            "SELECT COUNT(*) FROM species_alias WHERE species_id=?", (src['id'],)
        ).fetchone()[0]
        print(f"  observations to move: {obs_n}")
        print(f"  aliases to move:      {alias_n}")

        if args.dry_run:
            print("(dry-run) no changes made")
            return 0

        cid, did = dst['id'], src['id']
        # Repoint observations
        conn.execute("UPDATE observation SET species_id=? WHERE species_id=?", (cid, did))

        # species_alias: collisions on UNIQUE(raw_name, lang) for resolver langs
        # are possible. Strategy: try INSERT OR IGNORE into dst then delete src,
        # mirroring merge_duplicate_species.py — except species_alias has no
        # other-side staging table, so we update species_id directly. Conflict
        # on the partial unique index will fail the UPDATE; handle by deleting
        # the conflicting src-side row first.
        src_aliases = list(conn.execute(
            "SELECT id, raw_name, lang FROM species_alias WHERE species_id=?", (did,)
        ))
        moved = dropped = 0
        for a in src_aliases:
            dup = conn.execute(
                "SELECT 1 FROM species_alias WHERE species_id=? AND raw_name=? AND lang IS ?",
                (cid, a['raw_name'], a['lang'])
            ).fetchone()
            if dup:
                conn.execute("DELETE FROM species_alias WHERE id=?", (a['id'],))
                dropped += 1
                continue
            try:
                conn.execute("UPDATE species_alias SET species_id=? WHERE id=?",
                             (cid, a['id']))
                moved += 1
            except Exception as e:
                # resolver-lang collision via partial unique index
                print(f"  alias collision on ({a['raw_name']!r}, {a['lang']!r}): {e} — dropping src row")
                conn.execute("DELETE FROM species_alias WHERE id=?", (a['id'],))
                dropped += 1
        print(f"  aliases moved: {moved}, dropped-as-dup: {dropped}")

        # Ensure src common_name_ja appears as a ja alias on dst (so resolver
        # still picks up future raw_name='サクラ' → species_id=252)
        if src['common_name_ja']:
            exists = conn.execute(
                "SELECT 1 FROM species_alias WHERE raw_name=? AND lang='ja'",
                (src['common_name_ja'],)
            ).fetchone()
            if not exists:
                conn.execute(
                    "INSERT INTO species_alias (species_id, raw_name, lang, status) "
                    "VALUES (?, ?, 'ja', 'resolved')",
                    (cid, src['common_name_ja']))
                print(f"  inserted ja alias: {src['common_name_ja']!r} → id={cid}")

        # species_photo
        conn.execute("""
            INSERT OR IGNORE INTO species_photo
              (species_id, url, thumb_url, attribution, source, sort_order, source_url)
            SELECT ?, url, thumb_url, attribution, source, sort_order, source_url
            FROM species_photo WHERE species_id=?
        """, (cid, did))
        conn.execute("DELETE FROM species_photo WHERE species_id=?", (did,))

        # species_profile
        conn.execute("""
            INSERT OR IGNORE INTO species_profile
              (species_id, lang, summary, habitat_hint, finding_tips,
               sources, updated_at, source_urls)
            SELECT ?, lang, summary, habitat_hint, finding_tips,
               sources, updated_at, source_urls
            FROM species_profile WHERE species_id=?
        """, (cid, did))
        conn.execute("DELETE FROM species_profile WHERE species_id=?", (did,))

        # park_species_photo
        conn.execute("""
            INSERT OR IGNORE INTO park_species_photo
              (park_id, species_id, url, thumb_url, attribution, source,
               source_url, sort_order, tier)
            SELECT park_id, ?, url, thumb_url, attribution, source,
               source_url, sort_order, tier
            FROM park_species_photo WHERE species_id=?
        """, (cid, did))
        conn.execute("DELETE FROM park_species_photo WHERE species_id=?", (did,))

        # park_species derived — drop both sides; dedupe will rebuild
        conn.execute("DELETE FROM park_species WHERE species_id IN (?, ?)", (cid, did))

        # Drop the now-empty src row
        conn.execute("DELETE FROM species WHERE id=?", (did,))
        conn.commit()
        print(f"merged species {did} → {cid}; run scripts.dedupe next")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
