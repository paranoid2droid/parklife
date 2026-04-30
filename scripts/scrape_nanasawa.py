"""One-off ingester for 七沢森林公園 (Kanagawa, slug='nanasawa').

Nanasawa is the only kanagawa-park.or.jp park with structured 植物図鑑 /
生きもの図鑑 pages. We treat it as a one-off because the rest of the
prefecture has no shared template.

Source pages:
- https://www.kanagawa-park.or.jp/nanasawa/plants.html   (樹木 / 野草)
- https://www.kanagawa-park.or.jp/nanasawa/creatures.html (mammals, birds,
  butterflies, dragonflies, beetles, amphibians, reptiles)

Each species shows up as `<h4>名称（季節）</h4>` under category headings.
"""

from __future__ import annotations

import re
import warnings
from pathlib import Path

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

from parklife import db, fetch

ROOT = Path(__file__).resolve().parent.parent
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

PARENS = re.compile(r"[（(]([^)）]*)[）)]")
SEASON_TO_MONTHS = {
    "春": [3, 4, 5],
    "夏": [6, 7, 8],
    "秋": [9, 10, 11],
    "冬": [12, 1, 2],
    "初夏": [5, 6],
    "晩秋": [10, 11],
    "通年": list(range(1, 13)),
}


def _months_from_seasons(text: str) -> int:
    """Convert '春～秋' or '夏' or '春～秋' to a months bitmap."""
    months: set[int] = set()
    text = text.replace("〜", "～")
    if not text:
        return 0
    parts = re.split(r"[、，,]", text)
    for part in parts:
        rng = re.split(r"～|~", part)
        if len(rng) == 2 and rng[0] in SEASON_TO_MONTHS and rng[1] in SEASON_TO_MONTHS:
            order = ["春", "夏", "秋", "冬"]
            try:
                a, b = order.index(rng[0]), order.index(rng[1])
            except ValueError:
                continue
            cur = a
            while True:
                months.update(SEASON_TO_MONTHS[order[cur]])
                if cur == b:
                    break
                cur = (cur + 1) % 4
        elif part in SEASON_TO_MONTHS:
            months.update(SEASON_TO_MONTHS[part])
    bits = 0
    for m in months:
        bits |= 1 << (m - 1)
    return bits


def _parse(html: bytes, section_name: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    out: list[dict] = []
    for h4 in soup.find_all("h4"):
        raw = " ".join(h4.get_text().split())
        if not raw:
            continue
        m = PARENS.search(raw)
        annot = m.group(1) if m else ""
        name = PARENS.sub("", raw).strip()
        if not name:
            continue
        bitmap = _months_from_seasons(annot) or None
        out.append({
            "raw_name": name,
            "months_bitmap": bitmap,
            "characteristics": annot or None,
            "section": section_name,
        })
    return out


def main() -> None:
    db_path = ROOT / "data" / "parklife.db"
    with db.connect(db_path) as conn:
        park = conn.execute(
            "SELECT id, slug, prefecture FROM park WHERE slug=?", ("nanasawa",)
        ).fetchone()
        urls = [
            ("https://www.kanagawa-park.or.jp/nanasawa/plants.html",   "植物図鑑"),
            ("https://www.kanagawa-park.or.jp/nanasawa/creatures.html", "生きもの図鑑"),
        ]
        total = 0
        for url, section in urls:
            src_id, path = fetch.fetch_cached_or_new(
                conn, ROOT, park["id"], park["prefecture"], park["slug"], url
            )
            obs = _parse(path.read_bytes(), section)
            for o in obs:
                exists = conn.execute(
                    "SELECT id FROM observation WHERE park_id=? AND raw_name=? AND source_id=?",
                    (park["id"], o["raw_name"], src_id),
                ).fetchone()
                if exists:
                    continue
                conn.execute(
                    """INSERT INTO observation
                       (park_id, species_id, raw_name, months_bitmap,
                        location_hint, characteristics, source_id)
                       VALUES (?, NULL, ?, ?, ?, ?, ?)""",
                    (park["id"], o["raw_name"], o["months_bitmap"],
                     None, o["characteristics"], src_id),
                )
                conn.execute(
                    """INSERT OR IGNORE INTO species_alias
                       (species_id, raw_name, lang, status)
                       VALUES (NULL, ?, 'ja-kana', 'pending')""",
                    (o["raw_name"],),
                )
                total += 1
            conn.commit()
            print(f"{section:<10} {len(obs):>3} extracted")
        print(f"total inserted: {total}")


if __name__ == "__main__":
    main()
