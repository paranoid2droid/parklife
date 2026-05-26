"""Clean up species.common_name_ja placeholders that block profile curation.

Two categories of cleanup:

1. **Per-species fixes** for distinct placeholders (romaji-only, hybrid
   notation, genus-level fallback, or nakaguro-separated transliterations
   of the scientific name that have a real Japanese common name).
2. **Bulk strip of trailing ``（...）`` annotations** — many sedges and a
   handful of other species carry a redundant romaji transliteration or
   a ``（広義）`` qualifier inside parens. The bare katakana before the
   ``（`` is always the canonical name.

Idempotent — only updates rows whose current value still matches the
known placeholder; safe to re-run.
"""
from __future__ import annotations

from parklife import db
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "parklife.db"

# Per-species explicit fixes. Format: (scientific_name, old_value, new_value).
PER_SPECIES_FIXES = [
    ("Rudbeckia hirta",                       "オオハンゴンソウ属",                "アラゲハンゴンソウ"),
    ("Corylus sieboldiana",                   "tsuno-hashibami",                   "ツノハシバミ"),
    ("Allium thunbergii",                     "yama-rakkyō",                       "ヤマラッキョウ"),
    ("Anas zonorhyncha x platyrhynchos",      "雑種 マガモ ｘ カルガモ",          "マガモ×カルガモ雑種"),
    ("Turdus eunomus x naumanni",             "雑種 ツグミ ｘ ハチジョウツグミ",    "ツグミ×ハチジョウツグミ雑種"),
    # Nakaguro transliterations → canonical Japanese common names.
    ("Viola philippica",                      "ヴィオラ・フィリッピカ",            "スミレ"),
    ("Brassica rapa",                         "ブラッシカ・ラパ",                  "アブラナ"),
    ("Hypericum perforatum",                  "セント・ジョーンズ・ワート",        "セイヨウオトギリ"),
    ("Salvia guaranitica",                    "サルビア・ガラニチカ",              "メドーセージ"),
]


def main() -> None:
    db.init(DB)
    with db.connect(DB) as conn:
        # 1. Per-species explicit fixes.
        for sci, old, new in PER_SPECIES_FIXES:
            cur = conn.execute(
                "UPDATE species SET common_name_ja=? "
                "WHERE scientific_name=? AND common_name_ja=?",
                (new, sci, old),
            )
            if cur.rowcount:
                print(f"  fix {sci}: → {new!r}")

        # 2. Strip trailing parens annotation when there is real content
        #    before the first '（'. Defensive: skip would-be-empty results.
        rows = list(conn.execute(
            "SELECT id, common_name_ja FROM species "
            "WHERE common_name_ja LIKE '%（%）%'"
        ))
        bulk = 0
        for r in rows:
            name = r["common_name_ja"]
            i = name.find("（")
            if i <= 0:
                continue
            cleaned = name[:i].strip()
            if not cleaned or cleaned == name:
                continue
            conn.execute(
                "UPDATE species SET common_name_ja=? WHERE id=?",
                (cleaned, r["id"]),
            )
            bulk += 1
        print(f"  bulk-stripped parens annotation: {bulk} row(s)")

        conn.commit()


if __name__ == "__main__":
    main()
