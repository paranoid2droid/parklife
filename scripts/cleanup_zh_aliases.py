"""One-shot cleanup of zh aliases that contain no Han characters.

Past runs of scripts.gbif_vernacular inserted GBIF `zho` entries verbatim,
including pinyin transcriptions like 'Bai Guo' / 'Felis catus'. These are
not real Chinese names and pollute the zh display path.

Drop any zh-Hans/zh-Hant alias whose raw_name contains zero Han characters.
Then re-process the GBIF cache picking only Han-containing names so we do
not regress on species that have both pinyin and Han entries.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from parklife import db

ROOT = Path(__file__).resolve().parent.parent
HAN_RE = re.compile(r"[一-鿿]")
GBIF_CACHE = ROOT / "data" / "cache" / "gbif" / "vernacular"


def is_traditional_chinese(text: str) -> bool:
    HANT_ONLY = ("繁體萬個個鳥語雞嬰嶺鏡藥廣專點寶會勻來時對學園"
                 "為國體點選擇變對於關於開頭設計總計龍門開歷"
                 "區傳實業樣標準買賣賣處態應隨")
    return any(c in HANT_ONLY for c in text)


def main() -> int:
    db_path = ROOT / "data" / "parklife.db"
    deleted = inserted_hans = inserted_hant = 0

    with db.connect(db_path) as conn:
        rows = list(conn.execute(
            """SELECT id, raw_name, lang FROM species_alias
               WHERE lang LIKE 'zh%'"""
        ))
        for r in rows:
            if not HAN_RE.search(r["raw_name"] or ""):
                conn.execute("DELETE FROM species_alias WHERE id=?", (r["id"],))
                deleted += 1
        conn.commit()
    print(f"Deleted {deleted} zh aliases without Han characters")

    # Re-process GBIF cache, only picking Han-containing names.
    with db.connect(db_path) as conn:
        species = list(conn.execute(
            """SELECT id, scientific_name FROM species
               WHERE scientific_name IS NOT NULL AND scientific_name <> ''"""
        ))
        sci_to_id = {s["scientific_name"]: s["id"] for s in species}

        for cache_file in GBIF_CACHE.glob("*.json"):
            try:
                payload = json.loads(cache_file.read_text(encoding="utf-8"))
            except Exception:
                continue
            match = payload.get("match") or {}
            sci = (match.get("scientificName") or "").split(" ")[:2]
            sci = " ".join(sci)
            sp_id = sci_to_id.get(sci)
            if not sp_id:
                # try the canonicalName from match
                cn = match.get("canonicalName")
                if cn:
                    sp_id = sci_to_id.get(cn)
            if not sp_id:
                continue
            hans_pool: list[str] = []
            hant_pool: list[str] = []
            for v in payload.get("vernaculars") or []:
                if (v.get("language") or "").lower() != "zho":
                    continue
                name = (v.get("vernacularName") or "").strip()
                if not HAN_RE.search(name):
                    continue
                if is_traditional_chinese(name):
                    hant_pool.append(name)
                else:
                    hans_pool.append(name)
            for pool, lang in ((hans_pool, "zh-Hans"), (hant_pool, "zh-Hant")):
                if not pool:
                    continue
                # Prefer the shortest Han-only name (typically canonical).
                best = min(pool, key=lambda s: (len(s), s))
                cur = conn.execute(
                    """INSERT OR IGNORE INTO species_alias
                       (species_id, raw_name, lang, status)
                       VALUES (?, ?, ?, 'resolved')""",
                    (sp_id, best, lang),
                )
                if cur.rowcount:
                    if lang == "zh-Hans":
                        inserted_hans += 1
                    else:
                        inserted_hant += 1
        conn.commit()

    print(f"Re-inserted from GBIF cache: zh-Hans={inserted_hans}, zh-Hant={inserted_hant}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
