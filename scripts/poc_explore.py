"""PoC step 1: fetch a park's main page and list candidate sub-pages
(nature/biodiversity/seasonal flowers etc) to figure out where the
species data actually lives.
"""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from parklife import db, fetch

ROOT = Path(__file__).resolve().parent.parent

# substrings to flag as nature/wildlife pages
KEYWORDS = (
    "自然", "生き物", "動物", "植物", "花", "野鳥", "鳥", "昆虫",
    "biodiversity", "nature", "flora", "fauna", "wildlife", "bird",
    "見ごろ", "見頃", "開花", "観察", "生態", "環境",
)


def main(slug: str) -> None:
    db_path = ROOT / "data" / "parklife.db"
    with db.connect(db_path) as conn:
        row = conn.execute(
            "SELECT id, name_ja, prefecture, official_url FROM park "
            "WHERE prefecture='tokyo' AND slug=?",
            (slug,),
        ).fetchone()
        if not row:
            print(f"park not found: {slug}", file=sys.stderr)
            sys.exit(1)
        park_id, name, pref, url = row["id"], row["name_ja"], row["prefecture"], row["official_url"]
        print(f"# {name}  ({url})")
        sid, path = fetch.fetch_cached_or_new(conn, ROOT, park_id, pref, slug, url)
        print(f"  cache: {path.relative_to(ROOT)}  source_id={sid}\n")
        soup = BeautifulSoup(path.read_bytes(), "lxml")
        seen: set[str] = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = " ".join(a.get_text().split())
            if not text:
                continue
            full = urljoin(url, href)
            host = urlparse(full).netloc
            if host and host != "www.tokyo-park.or.jp":
                continue
            if any(k in text for k in KEYWORDS) or any(k in full for k in KEYWORDS):
                if full in seen:
                    continue
                seen.add(full)
                print(f"  {text[:30]:<30}  {full}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "kasairinkai")
