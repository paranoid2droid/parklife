"""Inspect hama-rikyu (and a few zoos) full text to find any parking signal."""
import warnings
import re
from pathlib import Path
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from parklife import db
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

ROOT = Path(__file__).resolve().parent.parent

with db.connect(ROOT / "data" / "parklife.db") as conn:
    for slug in ("hama-rikyu", "tama-zoological-park", "ueno-zoological-gardens",
                 "kasai-rinkai-suizokuen", "inokashira-park-zoo",
                 "odaiba-kaihin", "wakasu-kaihin"):
        r = conn.execute(
            "SELECT raw_path FROM source WHERE park_id IN "
            "(SELECT id FROM park WHERE slug=?) AND url LIKE '%tokyo-park%' "
            "ORDER BY fetched_at DESC LIMIT 1", (slug,),
        ).fetchone()
        if not r:
            print(f"\n--- {slug}: NO HOMEPAGE CACHED ---")
            continue
        html = (ROOT / r["raw_path"]).read_bytes()
        soup = BeautifulSoup(html, "lxml")
        for sel in ("nav", "header", "footer", "script", "style"):
            for tag in soup.find_all(sel):
                tag.decompose()
        text = soup.get_text(" ", strip=True)
        print(f"\n--- {slug}  ({len(text)}c) ---")
        # find context around 駐車 or 駐輪 or 車
        for kw in ("駐車", "車での", "電車", "公共交通"):
            for m in list(re.finditer(kw, text))[:3]:
                start = max(0, m.start() - 40)
                end = min(len(text), m.end() + 100)
                print(f"  [{kw}] ...{text[start:end]}...")
