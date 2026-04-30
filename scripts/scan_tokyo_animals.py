"""Phase A: rescan cached Tokyo HTML for animal/bird-related sections we
might have missed in the original 花の見ごろ-only pass.

Looks for:
  - sub-section headings containing 鳥/野鳥/動物/生き物/昆虫/魚/メダカ/etc.
  - links to sub-pages like /news/ or /assets/ that mention 鳥類/野鳥
  - 見どころ block content (some parks list 鳥類園 / 自然観察ゾーン)
  - structured lists of species names following animal-related headings

Output: data/scan/tokyo_animal_candidates.json
  { slug: { headings: [...], anchor_paths: [...], structured_blocks: [...] } }

This is a discovery pass — does NOT insert into DB. We use the output to
decide which parks deserve a second-pass scraper.
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent

ANIMAL_KW = (
    "野鳥", "鳥類", "鳥", "探鳥",
    "動物", "哺乳", "獣", "野生",
    "昆虫", "蝶", "チョウ", "トンボ", "セミ",
    "魚", "魚類", "メダカ",
    "両生", "爬虫", "カエル", "トカゲ", "ヘビ",
    "生き物", "生物多様", "観察",
    "サンクチュアリ", "保護区",
)

NATURE_PAGE_HINTS = (
    "shizen", "nature", "kansatsu", "yacho", "tori",
    "ikimono", "biodiversity", "creature",
    "鳥", "野鳥", "自然", "観察", "生き物",
)


def find_block_after(heading_tag) -> str:
    """Capture text from the heading until the next heading of >= rank."""
    parts: list[str] = []
    same_or_higher = {"h1", "h2", "h3", "h4"}
    rank = int(heading_tag.name[1])
    same_or_higher_filter = {f"h{i}" for i in range(1, rank + 1)}
    for sib in heading_tag.find_next_siblings():
        if getattr(sib, "name", None) in same_or_higher_filter:
            break
        text = " ".join(sib.get_text(" ", strip=True).split())
        if text:
            parts.append(text)
        if len(" ".join(parts)) > 800:
            break
    return " ".join(parts)


def scan_html(html: bytes) -> dict:
    soup = BeautifulSoup(html, "lxml")
    out = {"headings": [], "blocks": [], "anchor_hints": []}

    # 1) headings whose text contains animal keywords
    for tag in soup.find_all(["h2", "h3", "h4", "h5"]):
        text = " ".join(tag.get_text().split())
        if not text:
            continue
        if any(kw in text for kw in ANIMAL_KW):
            block = find_block_after(tag)
            out["headings"].append(text)
            if block:
                out["blocks"].append({"heading": text, "text": block[:1500]})

    # 2) anchors pointing at nature-themed sub-pages
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = " ".join(a.get_text().split())
        if any(h in href.lower() for h in NATURE_PAGE_HINTS) or any(k in text for k in ANIMAL_KW):
            out["anchor_hints"].append({"text": text, "href": href})

    return out


def main() -> int:
    raw_dir = ROOT / "data" / "raw" / "tokyo"
    if not raw_dir.is_dir():
        print(f"no cache dir: {raw_dir}", file=sys.stderr)
        return 1
    out: dict = {}
    parks_with_signal = 0
    for park_dir in sorted(raw_dir.iterdir()):
        if not park_dir.is_dir():
            continue
        # use the first/oldest html (should be the main page for most parks)
        htmls = sorted(park_dir.glob("*.html"))
        if not htmls:
            continue
        slug = park_dir.name
        scan = scan_html(htmls[0].read_bytes())
        if scan["headings"] or scan["blocks"] or scan["anchor_hints"]:
            out[slug] = scan
            parks_with_signal += 1

    out_path = ROOT / "data" / "scan" / "tokyo_animal_candidates.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    # print a summary so the run log captures it
    print(f"scanned {len(list(raw_dir.iterdir()))} park dirs")
    print(f"parks with animal signal: {parks_with_signal}")
    by_kw: dict[str, int] = defaultdict(int)
    for slug, info in out.items():
        for h in info["headings"]:
            for kw in ANIMAL_KW:
                if kw in h:
                    by_kw[kw] += 1
                    break
    print("top heading keywords:")
    for kw, n in sorted(by_kw.items(), key=lambda x: -x[1])[:10]:
        print(f"  {kw:<10} {n}")
    print(f"\noutput: {out_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
