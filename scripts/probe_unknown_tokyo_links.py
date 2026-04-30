"""Show external links in remaining unknown Tokyo park homepages."""
import warnings
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from parklife import db
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

ROOT = Path(__file__).resolve().parent.parent

domains = Counter()
samples_per_domain: dict[str, list[str]] = {}

with db.connect(ROOT / "data" / "parklife.db") as conn:
    rows = list(conn.execute(
        "SELECT id, slug, official_url FROM park "
        "WHERE has_parking IS NULL AND prefecture='tokyo'"
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
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if not href.startswith(("http://","https://")):
                continue
            host = urlparse(href).netloc
            if "tokyo-park.or.jp" in host or "twitter" in host or "facebook" in host or "google" in host:
                continue
            domains[host] += 1
            samples_per_domain.setdefault(host, []).append(p["slug"])

print(f"distinct external hosts in {len(rows)} unknown-Tokyo homepages: {len(domains)}")
for host, n in domains.most_common(20):
    parks = samples_per_domain.get(host, [])
    parks_uniq = sorted(set(parks))
    print(f"  {n:>4}  {host:<40} (parks: {len(parks_uniq)})  e.g. {parks_uniq[:3]}")
