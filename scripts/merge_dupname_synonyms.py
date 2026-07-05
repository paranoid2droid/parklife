"""Merge near-certain synonym pairs that share a Japanese name (dup cards).

The kana backfill exposed ~1,187 (park, ja-name) pairs where two *different*
species carry the same Japanese name. Most are legitimate — homonyms (アカザ = a
plant AND a catfish) or distinct congeners (アオスゲ = two Carex) — and must be
kept. But some are nomenclatural synonyms the taxonomy split across two rows.

We merge ONLY the near-certain synonyms, by a deliberately narrow rule:

  * exactly two reachable species share the ja-name,
  * same kingdom,
  * exactly ONE has an inat_taxon_id (the accepted iNat taxon; the other is a
    GBIF-only leftover), and
  * either
      - a GENUS REASSIGNMENT: identical species epithet, different genus
        (Poecilium maaki / Phymatodes maaki), or
      - a GENDER VARIANT: same genus, epithet stems match after stripping the
        Latin gender ending (Favonius saphirina / saphirinus).

The no-tid row is merged into the tid holder (the accepted taxon). Everything is
logged to species_merged_log (reversible) and park_species is rebuilt by
`scripts.dedupe` afterwards. Homonyms and distinct congeners are left untouched.

    .venv/bin/python -m scripts.merge_dupname_synonyms --dry-run
    .venv/bin/python -m scripts.merge_dupname_synonyms && .venv/bin/python -m scripts.dedupe
"""

from __future__ import annotations

import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "parklife.db"

_GENDER = re.compile(r"(us|um|is|es|os|a|e|i)$")


def parts(sci: str | None) -> tuple[str, str]:
    toks = (sci or "").split()
    return (toks[0] if toks else "", toks[1] if len(toks) > 1 else "")


def stem(epithet: str) -> str:
    """Strip one trailing Latin gender ending so saphirina==saphirinus."""
    return _GENDER.sub("", epithet.lower())


def main() -> int:
    dry = "--dry-run" in sys.argv
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    # reuse the DQ-audit reversibility table (same schema) so all merges log here
    conn.execute("""CREATE TABLE IF NOT EXISTS species_merged_log (
        id INTEGER PRIMARY KEY, orig_species_id INTEGER, scientific_name TEXT,
        common_name_ja TEXT, common_name_en TEXT, kingdom TEXT, taxon_group TEXT,
        rank TEXT, inat_taxon_id INTEGER, photo_url TEXT,
        merged_into INTEGER, merged_at TEXT, note TEXT)""")

    reach = set(r[0] for r in conn.execute("SELECT DISTINCT species_id FROM park_species"))
    # group reachable named species by ja-name
    byname: dict[str, list] = defaultdict(list)
    for r in conn.execute("""SELECT id, scientific_name, common_name_ja, common_name_en,
                             kingdom, taxon_group, rank, inat_taxon_id, photo_url
                             FROM species WHERE common_name_ja IS NOT NULL AND common_name_ja!=''"""):
        if r["id"] in reach:
            byname[r["common_name_ja"]].append(r)

    parks_of = defaultdict(set)
    for sid, pid in conn.execute("SELECT species_id, park_id FROM park_species"):
        parks_of[sid].add(pid)

    merges = []  # (canonical_row, drop_row, rule, cooccur)
    for nm, sp in byname.items():
        if len(sp) != 2:
            continue
        a, b = sp
        if (a["kingdom"] or "") != (b["kingdom"] or ""):
            continue
        tids = [x["inat_taxon_id"] is not None for x in sp]
        if sum(tids) != 1:                      # need exactly one accepted taxon
            continue
        canon, drop = (a, b) if a["inat_taxon_id"] is not None else (b, a)
        ga, ea = parts(canon["scientific_name"])
        gb, eb = parts(drop["scientific_name"])
        if not ea or not eb:
            continue
        if ea == eb and ga != gb:
            rule = "genus-reassignment"
        elif ga == gb and ga and stem(ea) == stem(eb) and ea != eb:
            rule = "gender-variant"
        else:
            continue
        cooccur = bool(parks_of[canon["id"]] & parks_of[drop["id"]])
        merges.append((canon, drop, rule, cooccur))

    print(f"synonym merge pairs: {len(merges)} "
          f"({sum(1 for m in merges if m[3])} co-occur → remove a dup card)")
    for canon, drop, rule, co in merges:
        flag = "DUP" if co else "   "
        print(f"  [{flag}] {rule:18s} {drop['common_name_ja']}: "
              f"{drop['scientific_name']} (tid={drop['inat_taxon_id']}) "
              f"→ {canon['scientific_name']} (tid={canon['inat_taxon_id']})")

    if dry:
        print("\n--dry-run: no changes written")
        return 0

    for canon, drop, rule, _ in merges:
        cid, did = canon["id"], drop["id"]
        conn.execute("""INSERT INTO species_merged_log
            (orig_species_id, scientific_name, common_name_ja, common_name_en, kingdom,
             taxon_group, rank, inat_taxon_id, photo_url, merged_into, merged_at, note)
            VALUES(?,?,?,?,?,?,?,?,?,?,datetime('now'),?)""",
            (did, drop["scientific_name"], drop["common_name_ja"], drop["common_name_en"],
             drop["kingdom"], drop["taxon_group"], drop["rank"], drop["inat_taxon_id"],
             drop["photo_url"], cid, "dupname-" + rule))
        conn.execute("UPDATE observation  SET species_id=? WHERE species_id=?", (cid, did))
        conn.execute("UPDATE species_alias SET species_id=? WHERE species_id=?", (cid, did))
        conn.execute("""INSERT OR IGNORE INTO species_photo
            (species_id,url,thumb_url,attribution,source,sort_order,source_url)
            SELECT ?,url,thumb_url,attribution,source,sort_order,source_url
            FROM species_photo WHERE species_id=?""", (cid, did))
        conn.execute("DELETE FROM species_photo WHERE species_id=?", (did,))
        conn.execute("""INSERT OR IGNORE INTO species_profile
            (species_id,lang,summary,habitat_hint,finding_tips,sources,updated_at,source_urls)
            SELECT ?,lang,summary,habitat_hint,finding_tips,sources,updated_at,source_urls
            FROM species_profile WHERE species_id=?""", (cid, did))
        conn.execute("DELETE FROM species_profile WHERE species_id=?", (did,))
        conn.execute("""INSERT OR IGNORE INTO park_species_photo
            (park_id,species_id,url,thumb_url,attribution,source,source_url,sort_order,tier)
            SELECT park_id,?,url,thumb_url,attribution,source,source_url,sort_order,tier
            FROM park_species_photo WHERE species_id=?""", (cid, did))
        conn.execute("DELETE FROM park_species_photo WHERE species_id=?", (did,))
        conn.execute("DELETE FROM park_species WHERE species_id=?", (did,))
        conn.execute("DELETE FROM park_species WHERE species_id=?", (cid,))  # dedupe rebuilds
        # keep the dropped name as an alias of the canonical (preserve provenance)
        if drop["scientific_name"]:
            conn.execute("INSERT OR IGNORE INTO species_alias(species_id,raw_name,lang)"
                         " VALUES(?,?,?)", (cid, drop["scientific_name"], "sci"))
        conn.execute("DELETE FROM species WHERE id=?", (did,))
    conn.commit()
    print(f"\nmerged {len(merges)} synonym rows (reversible via species_merged_log)")
    print("NOW RUN: .venv/bin/python -m scripts.dedupe")
    return 0


if __name__ == "__main__":
    sys.exit(main())
