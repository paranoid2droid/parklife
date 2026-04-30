"""Phase A: extract katakana species names from Tokyo park narrative blocks.

Reads data/scan/tokyo_animal_candidates.json (built by scan_tokyo_animals.py),
tokenizes each block's text into katakana name candidates, and tries to
resolve each one via the Wikipedia normalizer (cached). Confirmed animal/
plant/insect/etc. species become `observation` rows linked to species.

Why the dual filter?  Naive katakana extraction also catches loanwords
(ボランティア / オープン / フィールド) and partial fragments. Wikipedia
resolution filters these out — only real taxa with a Wikipedia article
showing 動物界/植物界/etc. in the body get accepted.

Naming inference for season-from-context:
  - text near 通年/年間: months_bitmap = 0xFFF (all months)
  - text near 冬: winter (12,1,2)
  - text near 夏: summer (6,7,8)
  - text near 春: spring (3,4,5)
  - text near 秋: autumn (9,10,11)
  - default (block-wide):  None  (year-round / unknown)
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

from parklife import db
from parklife.normalize import wikipedia

ROOT = Path(__file__).resolve().parent.parent

# katakana words 2..12 chars, optionally containing 一 (long mark) and middle dot
KATAKANA_TOKEN = re.compile(r"[ァ-ヺー]{2,12}")

# obvious non-species katakana words to pre-filter
STOPWORDS = {
    "サンクチュアリ", "バード", "ボランティア", "フィールド",
    "ガイド", "コーナー", "ウォッチング", "スクール",
    "オープン", "アクセス", "ポイント", "イベント",
    "ミュージアム", "センター", "アウトドア", "ツアー",
    "プログラム", "コース", "ルート", "セクション",
    "テーマ", "シリーズ", "シーズン", "スタッフ", "ルール",
    "ハイキング", "ピクニック", "ジョギング", "サイクリング",
    "ガイダンス", "ニュース",
}

# season hints in surrounding text  → months
SEASON_BITS = {
    "春": (1<<2)|(1<<3)|(1<<4),    # Mar/Apr/May
    "夏": (1<<5)|(1<<6)|(1<<7),    # Jun/Jul/Aug
    "秋": (1<<8)|(1<<9)|(1<<10),   # Sep/Oct/Nov
    "冬": (1<<11)|(1<<0)|(1<<1),   # Dec/Jan/Feb
    "通年": (1<<12) - 1,
    "年間": (1<<12) - 1,
}

CACHE_TAXON = ROOT / "data" / "cache" / "tokyo_animal_resolution.json"


def split_segments(text: str) -> list[tuple[str, int | None]]:
    """Break a narrative block into (segment_text, months_bitmap) where
    bitmap reflects season hints near that segment. Splits on punctuation
    that often follows a 'season:' label like '通年: ...' or '冬：...'."""
    out: list[tuple[str, int | None]] = []
    # split on Japanese full-width colons / parens that precede season labels
    # crude rule: group by lines / fullstops
    lines = re.split(r"[。\n]", text)
    for line in lines:
        if not line.strip():
            continue
        bits = 0
        for kw, b in SEASON_BITS.items():
            if kw in line:
                bits |= b
        out.append((line, bits or None))
    return out


def candidate_tokens(text: str) -> list[str]:
    seen: list[str] = []
    for m in KATAKANA_TOKEN.finditer(text):
        tok = m.group(0).strip("ー")
        if not (2 <= len(tok) <= 12):
            continue
        if tok in STOPWORDS:
            continue
        if tok in seen:
            continue
        seen.append(tok)
    return seen


def main() -> int:
    scan_path = ROOT / "data" / "scan" / "tokyo_animal_candidates.json"
    if not scan_path.exists():
        print("missing scan output; run scan_tokyo_animals.py first", file=sys.stderr)
        return 1
    scan = json.loads(scan_path.read_text(encoding="utf-8"))

    # in-memory taxon cache — saves Wikipedia lookups across slugs
    cache: dict[str, dict] = {}
    if CACHE_TAXON.exists():
        cache = json.loads(CACHE_TAXON.read_text(encoding="utf-8"))

    db_path = ROOT / "data" / "parklife.db"
    accepted = rejected = inserted = checked = 0
    parks_touched = 0

    with db.connect(db_path) as conn:
        for slug, info in scan.items():
            if not info.get("blocks"):
                continue
            row = conn.execute(
                "SELECT id, prefecture FROM park WHERE prefecture='tokyo' AND slug=?", (slug,)
            ).fetchone()
            if not row:
                continue
            park_id = row["id"]
            # use the most recent source row for this park as the provenance
            src_row = conn.execute(
                "SELECT id FROM source WHERE park_id=? ORDER BY fetched_at DESC LIMIT 1",
                (park_id,),
            ).fetchone()
            source_id = src_row["id"] if src_row else None

            new_for_park = 0
            for block in info["blocks"]:
                heading = block["heading"]
                for segment, bitmap in split_segments(block["text"]):
                    for tok in candidate_tokens(segment):
                        checked += 1
                        cached = cache.get(tok)
                        if cached is None:
                            res = wikipedia.lookup_with_cache(tok, ROOT)
                            cache[tok] = res.to_dict()
                            cached = cache[tok]
                            time.sleep(0.15)  # politeness
                        # accept criteria:
                        if not cached.get("found"):
                            rejected += 1; continue
                        if cached.get("is_disambig"):
                            rejected += 1; continue
                        kingdom = cached.get("kingdom")
                        if kingdom not in ("animalia", "plantae", "fungi"):
                            rejected += 1; continue
                        # don't double-insert (park, raw, bitmap)
                        exists = conn.execute(
                            """SELECT id FROM observation WHERE park_id=? AND raw_name=?
                               AND ( (months_bitmap IS ?) OR (months_bitmap = ?) )""",
                            (park_id, tok, bitmap, bitmap),
                        ).fetchone()
                        if exists:
                            accepted += 1; continue
                        # link to species via species_alias (if any)
                        sa = conn.execute(
                            "SELECT species_id FROM species_alias WHERE raw_name=?",
                            (tok,),
                        ).fetchone()
                        species_id = sa["species_id"] if sa and sa["species_id"] else None
                        # if no alias yet, register a pending one (we'll re-normalize later)
                        if not sa:
                            conn.execute(
                                """INSERT OR IGNORE INTO species_alias
                                   (species_id, raw_name, lang, status)
                                   VALUES (NULL, ?, 'ja-kana', 'pending')""",
                                (tok,),
                            )
                        conn.execute(
                            """INSERT INTO observation
                               (park_id, species_id, raw_name, months_bitmap,
                                location_hint, characteristics, source_id)
                               VALUES (?, ?, ?, ?, ?, ?, ?)""",
                            (park_id, species_id, tok, bitmap, heading[:80], None, source_id),
                        )
                        accepted += 1
                        inserted += 1
                        new_for_park += 1
            if new_for_park:
                parks_touched += 1
            conn.commit()
            print(f"  {slug:<25} new={new_for_park}")

    CACHE_TAXON.parent.mkdir(parents=True, exist_ok=True)
    CACHE_TAXON.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n=== Phase A done ===")
    print(f"  parks touched: {parks_touched}")
    print(f"  candidate tokens checked: {checked}")
    print(f"  accepted (resolved animal/plant): {accepted}")
    print(f"  rejected (loanwords / not species): {rejected}")
    print(f"  observation rows inserted: {inserted}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
