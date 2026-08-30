"""Repair mislabeled ``lang='en'`` aliases that actually hold Japanese/Chinese.

An early ingestion copied Japanese common names (and some CJK synonyms) into
``species_alias`` rows tagged ``lang='en'``. Result: ~20k of ~23k 'en' aliases
contain kana or Han ideographs — they are not English at all. This pollutes
search and inflates apparent English coverage.

Fix, per row (raw_name of an ``en`` alias):
  * contains kana (=Japanese):
      - if it equals the species' own ``common_name_ja`` -> DELETE (self-dup;
        the name already lives in the column and its ja alias)
      - else migrate to ``lang='ja'`` (a genuine synonym worth keeping
        searchable), status='fix-en2ja'; on UNIQUE(raw_name,lang) collision the
        migrate is skipped and the row is DELETEd (duplicate already present)
  * Han-only, no kana (=Chinese): migrate to ``lang='zh-Hans'`` status='fix-en2zh'
      (skip+DELETE on collision)
  * pure ASCII -> left untouched (real English)

Deleted rows are logged to data/fix_en_alias_deleted.json. Reversible:
  UPDATE species_alias SET lang='en',status='resolved' WHERE status IN('fix-en2ja','fix-en2zh');
  -- plus re-insert from the deleted-log if ever needed.

    .venv/bin/python -m scripts.fix_en_alias_language --dry-run
    .venv/bin/python -m scripts.fix_en_alias_language
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "parklife.db"
KANA = re.compile(r"[ぁ-んァ-ヶー゛゜]")
HAN = re.compile(r"[一-龥㐀-䶵]")


def main() -> int:
    dry = "--dry-run" in sys.argv
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        """SELECT a.id, a.species_id, a.raw_name, s.common_name_ja
           FROM species_alias a JOIN species s ON s.id=a.species_id
           WHERE a.lang='en'"""
    ).fetchall()

    to_ja, to_zh, to_del = [], [], []
    for r in rows:
        nm = r["raw_name"]
        if KANA.search(nm):
            if nm == (r["common_name_ja"] or ""):
                to_del.append(r)           # self-duplicate of the ja column
            else:
                to_ja.append(r)            # genuine ja synonym
        elif HAN.search(nm):
            to_zh.append(r)                # Chinese mislabeled as en
        # else pure ASCII → real English, leave

    print(f"en aliases total: {len(rows)}")
    print(f"  -> delete (self-dup of common_name_ja): {len(to_del)}")
    print(f"  -> migrate kana to ja (synonym):        {len(to_ja)}")
    print(f"  -> migrate Han-only to zh-Hans:         {len(to_zh)}")
    print(f"  -> untouched real ASCII English:        {len(rows)-len(to_del)-len(to_ja)-len(to_zh)}")
    print("\n  sample kana->ja:", [r["raw_name"] for r in to_ja[:8]])
    print("  sample Han->zh :", [r["raw_name"] for r in to_zh[:8]])

    if dry:
        print("\n--dry-run: no DB writes")
        return 0

    deleted_log = []
    migrated_ja = migrated_zh = collided_del = 0
    for r in to_del:
        conn.execute("DELETE FROM species_alias WHERE id=?", (r["id"],))
        deleted_log.append({"species_id": r["species_id"], "raw_name": r["raw_name"], "from": "en", "reason": "self-dup"})
    for r, lang, tag in [(x, "ja", "fix-en2ja") for x in to_ja] + [(x, "zh-Hans", "fix-en2zh") for x in to_zh]:
        exists = conn.execute("SELECT 1 FROM species_alias WHERE raw_name=? AND lang=?",
                              (r["raw_name"], lang)).fetchone()
        if exists:
            conn.execute("DELETE FROM species_alias WHERE id=?", (r["id"],))
            deleted_log.append({"species_id": r["species_id"], "raw_name": r["raw_name"], "from": "en", "reason": f"collision-{lang}"})
            collided_del += 1
        else:
            conn.execute("UPDATE species_alias SET lang=?, status=? WHERE id=?", (lang, tag, r["id"]))
            if lang == "ja":
                migrated_ja += 1
            else:
                migrated_zh += 1
    conn.commit()
    (ROOT / "data" / "fix_en_alias_deleted.json").write_text(
        json.dumps(deleted_log, ensure_ascii=False), encoding="utf-8")
    print(f"\napplied: migrated {migrated_ja} ->ja, {migrated_zh} ->zh-Hans; "
          f"deleted {len(to_del)} self-dups + {collided_del} collisions "
          f"(log: data/fix_en_alias_deleted.json)")
    print("reversible: UPDATE species_alias SET lang='en',status='resolved' "
          "WHERE status IN('fix-en2ja','fix-en2zh')")
    return 0


if __name__ == "__main__":
    sys.exit(main())
