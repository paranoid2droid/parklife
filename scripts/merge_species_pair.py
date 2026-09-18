"""Merge one species row into another by id.

Use when a generic/placeholder species row (e.g. `サクラ` with NULL
scientific_name) should be collapsed into a specific existing row
(e.g. `ソメイヨシノ` / *Cerasus × yedoensis*). All observations,
aliases, photos, and profiles attached to the source are repointed
to the destination; the source species row is deleted; the
canonical's `common_name_ja` is preserved (filled from the source if
the canonical had none), and the source's common_name_ja is added as
a `ja` alias if not already present. The source's scientific_name is
kept as a `sci` alias so ingesters (`db.resolve_species_id`) route
future records to the canonical instead of re-creating the row.
Every merge is logged to `species_merged_log` (reversible).

Run dedupe afterwards.

Example:
    .venv/bin/python -m scripts.merge_species_pair --from 181 --to 252
"""
from __future__ import annotations

import argparse
from pathlib import Path

from parklife import db

ROOT = Path(__file__).resolve().parent.parent

MERGED_LOG_DDL = """CREATE TABLE IF NOT EXISTS species_merged_log (
    id INTEGER PRIMARY KEY, orig_species_id INTEGER, scientific_name TEXT,
    common_name_ja TEXT, common_name_en TEXT, kingdom TEXT, taxon_group TEXT,
    rank TEXT, inat_taxon_id INTEGER, photo_url TEXT,
    merged_into INTEGER, merged_at TEXT, note TEXT)"""


def merge_pair(conn, src_id: int, dst_id: int, note: str = "manual pair merge",
               verbose: bool = True) -> None:
    """Fold species `src_id` into `dst_id` inside the caller's transaction.

    Does NOT commit. Deletes both sides' `park_species` rows (dedupe rebuilds).
    """
    if src_id == dst_id:
        raise ValueError("source and destination are the same")
    conn.execute(MERGED_LOG_DDL)
    cols = ("id, scientific_name, common_name_ja, common_name_en, kingdom, "
            "taxon_group, rank, inat_taxon_id, photo_url")
    src = conn.execute(f"SELECT {cols} FROM species WHERE id=?", (src_id,)).fetchone()
    dst = conn.execute(f"SELECT {cols} FROM species WHERE id=?", (dst_id,)).fetchone()
    if not src:
        raise LookupError(f"source id={src_id} not found")
    if not dst:
        raise LookupError(f"destination id={dst_id} not found")
    cid, did = dst["id"], src["id"]
    say = print if verbose else (lambda *a, **k: None)

    conn.execute("""INSERT INTO species_merged_log
        (orig_species_id, scientific_name, common_name_ja, common_name_en, kingdom,
         taxon_group, rank, inat_taxon_id, photo_url, merged_into, merged_at, note)
        VALUES(?,?,?,?,?,?,?,?,?,?,datetime('now'),?)""",
        (did, src["scientific_name"], src["common_name_ja"], src["common_name_en"],
         src["kingdom"], src["taxon_group"], src["rank"], src["inat_taxon_id"],
         src["photo_url"], cid, note))

    conn.execute("UPDATE observation SET species_id=? WHERE species_id=?", (cid, did))

    # species_alias: UNIQUE(raw_name, lang) collisions → drop the src-side row.
    src_aliases = list(conn.execute(
        "SELECT id, raw_name, lang FROM species_alias WHERE species_id=?", (did,)))
    moved = dropped = 0
    for a in src_aliases:
        dup = conn.execute(
            "SELECT 1 FROM species_alias WHERE species_id=? AND raw_name=? AND lang IS ?",
            (cid, a["raw_name"], a["lang"])).fetchone()
        if dup:
            conn.execute("DELETE FROM species_alias WHERE id=?", (a["id"],))
            dropped += 1
            continue
        try:
            conn.execute("UPDATE species_alias SET species_id=? WHERE id=?", (cid, a["id"]))
            moved += 1
        except Exception as e:  # partial unique index on resolver langs
            say(f"  alias collision on ({a['raw_name']!r}, {a['lang']!r}): {e} — dropping src row")
            conn.execute("DELETE FROM species_alias WHERE id=?", (a["id"],))
            dropped += 1
    say(f"  aliases moved: {moved}, dropped-as-dup: {dropped}")

    # Keep the source binomial reachable as a sci alias of the canonical.
    if src["scientific_name"]:
        conn.execute(
            "INSERT OR IGNORE INTO species_alias (species_id, raw_name, lang, status) "
            "VALUES (?, ?, 'sci', 'resolved')", (cid, src["scientific_name"]))

    if src["common_name_ja"]:
        if not dst["common_name_ja"]:
            conn.execute("UPDATE species SET common_name_ja=? WHERE id=?",
                         (src["common_name_ja"], cid))
            say(f"  canonical had no ja-name; took {src['common_name_ja']!r} from source")
        exists = conn.execute(
            "SELECT 1 FROM species_alias WHERE raw_name=? AND lang='ja'",
            (src["common_name_ja"],)).fetchone()
        if not exists:
            conn.execute(
                "INSERT INTO species_alias (species_id, raw_name, lang, status) "
                "VALUES (?, ?, 'ja', 'resolved')", (cid, src["common_name_ja"]))
            say(f"  inserted ja alias: {src['common_name_ja']!r} → id={cid}")
    for col in ("common_name_en", "kingdom", "taxon_group", "inat_taxon_id", "photo_url"):
        if src[col] and not dst[col]:
            conn.execute(f"UPDATE species SET {col}=? WHERE id=? AND {col} IS NULL",
                         (src[col], cid))

    conn.execute("""
        INSERT OR IGNORE INTO species_photo
          (species_id, url, thumb_url, attribution, source, sort_order, source_url)
        SELECT ?, url, thumb_url, attribution, source, sort_order, source_url
        FROM species_photo WHERE species_id=?""", (cid, did))
    conn.execute("DELETE FROM species_photo WHERE species_id=?", (did,))

    conn.execute("""
        INSERT OR IGNORE INTO species_profile
          (species_id, lang, summary, habitat_hint, finding_tips,
           sources, updated_at, source_urls)
        SELECT ?, lang, summary, habitat_hint, finding_tips,
           sources, updated_at, source_urls
        FROM species_profile WHERE species_id=?""", (cid, did))
    conn.execute("DELETE FROM species_profile WHERE species_id=?", (did,))

    conn.execute("""
        INSERT OR IGNORE INTO park_species_photo
          (park_id, species_id, url, thumb_url, attribution, source,
           source_url, sort_order, tier)
        SELECT park_id, ?, url, thumb_url, attribution, source,
           source_url, sort_order, tier
        FROM park_species_photo WHERE species_id=?""", (cid, did))
    conn.execute("DELETE FROM park_species_photo WHERE species_id=?", (did,))

    # park_species is derived — drop both sides; dedupe will rebuild
    conn.execute("DELETE FROM park_species WHERE species_id IN (?, ?)", (cid, did))
    conn.execute("DELETE FROM species WHERE id=?", (did,))


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
        obs_n = conn.execute("SELECT COUNT(*) FROM observation WHERE species_id=?",
                             (src["id"],)).fetchone()[0]
        alias_n = conn.execute("SELECT COUNT(*) FROM species_alias WHERE species_id=?",
                               (src["id"],)).fetchone()[0]
        print(f"  observations to move: {obs_n}")
        print(f"  aliases to move:      {alias_n}")
        if args.dry_run:
            print("(dry-run) no changes made")
            return 0
        merge_pair(conn, src["id"], dst["id"])
        conn.commit()
        print(f"merged species {src['id']} → {dst['id']}; run scripts.dedupe next")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
