"""For each park still unknown, count cached pages and show external links."""
import warnings
from pathlib import Path
from urllib.parse import urlparse
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from parklife import db
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

ROOT = Path(__file__).resolve().parent.parent

with db.connect(ROOT / "data" / "parklife.db") as conn:
    rows = list(conn.execute(
        "SELECT id, slug, prefecture, name_ja, official_url FROM park "
        "WHERE has_parking IS NULL ORDER BY prefecture, slug"
    ))
    for p in rows:
        cached = list(conn.execute(
            "SELECT url, raw_path FROM source WHERE park_id=? AND raw_path IS NOT NULL",
            (p["id"],),
        ))
        # find first homepage
        home = None
        for c in cached:
            if c["url"] == p["official_url"]:
                home = ROOT / c["raw_path"]
                break
        external_hosts = set()
        if home and home.exists():
            soup = BeautifulSoup(home.read_bytes(), "lxml")
            for sel in ("nav", "header", "footer", "script", "style"):
                for tag in soup.find_all(sel):
                    tag.decompose()
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if not href.startswith(("http://", "https://")):
                    continue
                host = urlparse(href).netloc
                if any(x in host for x in ("tokyo-park.or.jp", "twitter", "facebook",
                                            "google", "instagram", "youtube", "x.com")):
                    continue
                external_hosts.add(host)
        host_list = ", ".join(sorted(external_hosts)[:3])
        print(f"  {p['prefecture']:<8} {p['slug']:<26} {p['name_ja']:<22}  "
              f"cached={len(cached)}  ext={host_list[:50]}")
