"""Show structure of Tokyo unknown parks: what sections exist?"""
import warnings
from pathlib import Path
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from parklife import db
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

ROOT = Path(__file__).resolve().parent.parent

with db.connect(ROOT / "data" / "parklife.db") as conn:
    rows = list(conn.execute(
        "SELECT id, slug, official_url FROM park "
        "WHERE has_parking IS NULL AND prefecture='tokyo' LIMIT 5"
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
        size = len(html)
        text = soup.get_text(" ", strip=True)
        print(f"\n=== {p['slug']}  (HTML {size}B, text {len(text)}c)  ===")
        # show all h2/h3 headings
        for tag in soup.find_all(["h2", "h3"]):
            t = " ".join(tag.get_text().split())[:50]
            if t:
                print(f"  {tag.name}: {t}")
        # full raw page text fragment to confirm
        print(f"  text first 200c: {text[:200]}")
