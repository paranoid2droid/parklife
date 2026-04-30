"""For each remaining has_parking IS NULL park, find the longest cached
body (after stripping nav/header/footer) across all non-iNat URLs, and
print the URL/length. Helps decide which need JS-rendered re-fetching.
"""
from __future__ import annotations
import sqlite3
import warnings
from pathlib import Path
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    c = sqlite3.connect(ROOT / "data" / "parklife.db")
    c.row_factory = sqlite3.Row
    rows = c.execute(
        "SELECT id, slug, prefecture, official_url FROM park "
        "WHERE has_parking IS NULL ORDER BY prefecture, slug"
    ).fetchall()
    for r in rows:
        srcs = c.execute(
            "SELECT url, raw_path FROM source WHERE park_id=? "
            "AND raw_path IS NOT NULL AND url NOT LIKE '%inaturalist%'",
            (r["id"],),
        ).fetchall()
        longest = 0
        best_url = None
        for s in srcs:
            p = ROOT / s["raw_path"]
            if not p.exists():
                continue
            soup = BeautifulSoup(p.read_bytes(), "lxml")
            for sel in ("nav", "header", "footer", "script", "style"):
                for t in soup.find_all(sel):
                    t.decompose()
            n = len(soup.get_text(" ", strip=True))
            if n > longest:
                longest, best_url = n, s["url"]
        print(f"{r['prefecture']}/{r['slug']:38} body={longest:>5}  {best_url}")


if __name__ == "__main__":
    main()
