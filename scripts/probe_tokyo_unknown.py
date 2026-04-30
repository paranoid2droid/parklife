"""Show 駐車場 keyword context in Tokyo parks still unknown."""
import re
import warnings
from pathlib import Path
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from parklife import db
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

ROOT = Path(__file__).resolve().parent.parent

with db.connect(ROOT / "data" / "parklife.db") as conn:
    rows = list(conn.execute(
        "SELECT id, slug, official_url FROM park "
        "WHERE has_parking IS NULL AND prefecture='tokyo' LIMIT 6"
    ))
    for p in rows:
        r = conn.execute(
            "SELECT raw_path FROM source WHERE park_id=? AND url=? "
            "AND raw_path IS NOT NULL ORDER BY fetched_at DESC LIMIT 1",
            (p["id"], p["official_url"]),
        ).fetchone()
        if not r: continue
        html = (ROOT / r["raw_path"]).read_bytes()
        soup = BeautifulSoup(html, "lxml")
        for sel in ("nav", "header", "footer", "script", "style"):
            for tag in soup.find_all(sel):
                tag.decompose()
        text = soup.get_text(" ", strip=True)
        print(f"\n=== {p['slug']} ===")
        for m in re.finditer(r"駐車場|パーキング", text):
            start = max(0, m.start() - 60)
            end = min(len(text), m.end() + 100)
            print(f"  @ {m.start()}: ...{text[start:end]}...")
