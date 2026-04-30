"""Inspect how 駐車場 (parking) info appears in cached park HTML.

For each cached homepage, find any heading or block mentioning 駐車場 and
print the surrounding text. This guides the extractor design.
"""
from __future__ import annotations
import sys
from pathlib import Path
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"

KEYWORDS = ("駐車場", "パーキング", "コインパーキング")


def find_blocks(html: bytes, max_chars: int = 600) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    out: list[str] = []
    for tag in soup.find_all(["h2", "h3", "h4"]):
        text = " ".join(tag.get_text().split())
        if not text:
            continue
        if any(k in text for k in KEYWORDS):
            block = [text]
            for sib in tag.find_next_siblings():
                if sib.name and sib.name.startswith("h") and sib.name <= tag.name:
                    break
                t = " ".join(sib.get_text(" ", strip=True).split())
                if t:
                    block.append(t)
                if len(" ".join(block)) > max_chars:
                    break
            out.append(" / ".join(block))
    return out


def main(slugs: list[str]) -> None:
    for prefecture in ("tokyo", "kanagawa", "chiba", "saitama"):
        for slug in slugs:
            d = RAW / prefecture / slug
            if not d.is_dir():
                continue
            htmls = sorted(d.glob("*.html"), key=lambda p: p.stat().st_size, reverse=True)
            if not htmls:
                continue
            blocks = find_blocks(htmls[0].read_bytes())
            print(f"\n=== {prefecture}/{slug} ===")
            if not blocks:
                print("  (no 駐車場 mention)")
            for b in blocks[:3]:
                print(f"  - {b[:300]}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        main(sys.argv[1:])
    else:
        main(["kasairinkai", "yoyogi", "jindai", "shakujii", "hama-rikyu",
              "nanasawa", "mitsuike", "aoba", "makuhari",
              "www-omiya-park", "www-tokorozawa-kokuu"])
