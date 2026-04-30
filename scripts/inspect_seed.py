"""Print all <a href> + text pairs from a seed list page, to help locate
the park list block. Run once per prefecture to design the extractor.
"""

from __future__ import annotations

import sys
from pathlib import Path

from bs4 import BeautifulSoup


def main(slug: str) -> None:
    path = Path(__file__).resolve().parent.parent / "data" / "raw" / "_seeds" / f"{slug}.html"
    soup = BeautifulSoup(path.read_bytes(), "lxml")
    for a in soup.find_all("a", href=True):
        text = " ".join(a.get_text().split())
        if not text:
            continue
        print(f"{a['href']}\t{text}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "tokyo")
