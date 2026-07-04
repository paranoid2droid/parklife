"""Backfill two display gaps that leave park cards looking broken.

1. **common_name_ja from a Japanese-script alias.** A GBIF-vernacular ingestion
   bug tagged many Japanese (katakana/hiragana) common names as ``lang='en'`` in
   ``species_alias``, so they never got promoted to ``species.common_name_ja``.
   The card then shows only the Latin binomial. We promote a kana alias to the
   column (kana is unambiguously Japanese — Latin/English can't contain it).

2. **photo_url from a park-local photo.** Some species have no ``photo_url`` and
   no ``species_photo`` gallery, yet a ``park_species_photo`` exists — so the card
   thumbnail is blank while the modal shows a photo. We promote the park-local
   image to the species thumbnail.

Both are idempotent (only touch NULL/empty columns), reversible (old values
logged to ``display_backfill_log``), and reach-scoped (species that appear in at
least one park). Re-run after any GBIF/iNat ingestion.

    .venv/bin/python -m scripts.backfill_display_gaps --dry-run
    .venv/bin/python -m scripts.backfill_display_gaps
"""

from __future__ import annotations

import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "parklife.db"

# Katakana + hiragana only (unambiguously Japanese); excludes bare-kanji aliases
# that could be mislabeled Chinese.
KANA = "raw_name GLOB '*[ぁ-んァ-ヶ]*'"


def main() -> int:
    dry = "--dry-run" in sys.argv
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE IF NOT EXISTS display_backfill_log (
        species_id INTEGER, field TEXT, old_value TEXT, new_value TEXT,
        source TEXT, ts TEXT DEFAULT (datetime('now')))""")

    # --- 1. common_name_ja from a kana alias --------------------------------
    # (a) best kana alias per unnamed species
    proposed: dict[int, str] = {}
    for r in conn.execute(f"""
        SELECT a.species_id, a.raw_name
        FROM species_alias a
        JOIN species s ON s.id = a.species_id
        WHERE (s.common_name_ja IS NULL OR s.common_name_ja = '')
          AND a.{KANA}
          AND a.lang NOT IN ('zh-Hans', 'zh-Hant')
          AND EXISTS (SELECT 1 FROM park_species ps WHERE ps.species_id = a.species_id)
        ORDER BY a.species_id,
                 (a.lang IN ('ja', 'ja-kana')) DESC,   -- prefer explicitly-ja
                 LENGTH(a.raw_name) ASC,                -- then the concise name
                 a.id ASC
    """):
        proposed.setdefault(r["species_id"], r["raw_name"])

    # (b) collision guard: never give two co-occurring species the same displayed
    # name. Many "synonyms" (genus reassignments) and homonyms (アカザ = a plant
    # AND a catfish) share a Japanese name; naming both would show duplicate cards
    # in a park. Greedily assign, most-widespread species first; a candidate whose
    # name is already shown by a co-occurring species is left Latin-only.
    npark = dict(conn.execute("SELECT species_id, COUNT(*) FROM park_species GROUP BY species_id"))
    sp_parks: dict[int, list[int]] = defaultdict(list)
    for sid, pid in conn.execute("SELECT species_id, park_id FROM park_species"):
        sp_parks[sid].append(pid)
    park_names: dict[int, set] = defaultdict(set)   # park -> names already displayed
    for pid, nm in conn.execute("""
        SELECT ps.park_id, s.common_name_ja FROM park_species ps
        JOIN species s ON s.id = ps.species_id
        WHERE s.common_name_ja IS NOT NULL AND s.common_name_ja != ''"""):
        park_names[pid].add(nm)

    name_pick: dict[int, str] = {}
    collisions = 0
    for sid in sorted(proposed, key=lambda s: (-npark.get(s, 0), s)):
        nm = proposed[sid]
        parks = sp_parks.get(sid, [])
        if any(nm in park_names[p] for p in parks):
            collisions += 1
            continue
        name_pick[sid] = nm
        for p in parks:
            park_names[p].add(nm)

    # --- 2. photo_url from a park-local photo -------------------------------
    photo_rows = conn.execute("""
        SELECT pp.species_id, pp.url
        FROM park_species_photo pp
        JOIN species s ON s.id = pp.species_id
        WHERE (s.photo_url IS NULL OR s.photo_url = '')
          AND pp.url IS NOT NULL AND pp.url != ''
          AND NOT EXISTS (SELECT 1 FROM species_photo p WHERE p.species_id = s.id)
          AND EXISTS (SELECT 1 FROM park_species ps WHERE ps.species_id = pp.species_id)
        ORDER BY pp.species_id, pp.tier, pp.sort_order, pp.id
    """).fetchall()
    photo_pick: dict[int, str] = {}
    for r in photo_rows:
        photo_pick.setdefault(r["species_id"], r["url"])

    print(f"common_name_ja backfill: {len(name_pick)} species "
          f"({collisions} candidates left Latin-only to avoid duplicate cards)")
    print(f"photo_url backfill:      {len(photo_pick)} species")
    for sid, nm in list(name_pick.items())[:6]:
        print(f"  ja   {sid}: {nm}")
    for sid, url in list(photo_pick.items())[:3]:
        print(f"  img  {sid}: {url[:70]}")

    if dry:
        print("\n--dry-run: no changes written")
        return 0

    for sid, nm in name_pick.items():
        conn.execute("INSERT INTO display_backfill_log(species_id,field,old_value,new_value,source)"
                     " VALUES(?,?,?,?,?)", (sid, "common_name_ja", None, nm, "kana-alias"))
        conn.execute("UPDATE species SET common_name_ja=? WHERE id=?", (nm, sid))
    for sid, url in photo_pick.items():
        conn.execute("INSERT INTO display_backfill_log(species_id,field,old_value,new_value,source)"
                     " VALUES(?,?,?,?,?)", (sid, "photo_url", None, url, "park_species_photo"))
        conn.execute("UPDATE species SET photo_url=? WHERE id=?", (url, sid))
    conn.commit()
    print(f"\nwrote {len(name_pick)} names + {len(photo_pick)} photos "
          f"(reversible via display_backfill_log)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
