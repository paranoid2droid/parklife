"""Some Tokyo park homepages are stubs that point at an external operator
site (e.g. www.tptc.co.jp for waterfront wharf parks). For parks still
unknown, look for an external URL embedded in the homepage HTML and
fetch it once to extract parking info.

Allowlisted operator domains (known managers of TMG-listed parks):
  - tptc.co.jp           Tokyo Waterfront City group (青海/有明/etc.)
  - kankyo.metro.tokyo   TMG environment dept (奥多摩/八丈/小笠原)
  - waters-takeshiba     waterfront facility
  - landscape sites we already handle

We keep the allowlist small to avoid following random links.
"""
from __future__ import annotations
import warnings
from pathlib import Path
from urllib.parse import urlparse
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from parklife import db, fetch
from scripts.extract_parking import (
    get_block, classify, ensure_columns,
)
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

ROOT = Path(__file__).resolve().parent.parent

OPERATOR_DOMAINS = (
    "tptc.co.jp",
    "kankyo.metro.tokyo.lg.jp",
    "waters-takeshiba",
    "tama-zoo.com",
    "tokyo-zoo.net",
    "kasai-seasidepark.jp",
    "ueno-zoo.net",
    # Tokyo park operator clusters discovered via probe_unknown_tokyo_links
    "seaside-park.jp",
    "sayamaparks.com",
    "tamaparks.com",
    "tokyo-eastpark.com",
    "musashinoparks.com",
    "ces-net.jp",
    "yumenoshima.jp",
    "yamafuru.com",
)


def find_operator_url(html: bytes) -> str | None:
    soup = BeautifulSoup(html, "lxml")
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href.startswith(("http://", "https://")):
            continue
        host = urlparse(href).netloc
        for d in OPERATOR_DOMAINS:
            if d in host:
                return href
    return None


def main() -> None:
    db_path = ROOT / "data" / "parklife.db"
    fetched = updated_yes = updated_no = no_link = 0
    with db.connect(db_path) as conn:
        ensure_columns(conn)
        parks = list(conn.execute(
            "SELECT id, slug, prefecture, official_url FROM park "
            "WHERE has_parking IS NULL AND official_url IS NOT NULL"
        ))
        print(f"unknown parks: {len(parks)}")
        for p in parks:
            r = conn.execute(
                "SELECT raw_path FROM source WHERE park_id=? AND url=? "
                "AND raw_path IS NOT NULL ORDER BY fetched_at DESC LIMIT 1",
                (p["id"], p["official_url"]),
            ).fetchone()
            if not r:
                continue
            home = (ROOT / r["raw_path"]).read_bytes()
            op = find_operator_url(home)
            if not op:
                no_link += 1
                continue
            try:
                src_id, path = fetch.fetch_cached_or_new(
                    conn, ROOT, p["id"], p["prefecture"], p["slug"], op,
                    max_age_days=14, delay_s=1.0,
                )
                fetched += 1
            except Exception as e:
                print(f"  fetch err {p['slug']}: {e!r}")
                continue
            soup = BeautifulSoup(path.read_bytes(), "lxml")
            for sel in ("nav", "header", "footer", "script", "style"):
                for tag in soup.find_all(sel):
                    tag.decompose()
            block = get_block(soup)
            text = soup.get_text(" ", strip=True)
            has, info = classify(block, text)
            if has is not None:
                conn.execute(
                    "UPDATE park SET has_parking=?, parking_info=? WHERE id=?",
                    (has, info, p["id"]),
                )
                if has == 1: updated_yes += 1
                else: updated_no += 1
            if (fetched % 5) == 0:
                conn.commit()
                print(f"  fetched={fetched} yes={updated_yes} no={updated_no}")
        conn.commit()
    print(f"\n=== external-operator pass ===")
    print(f"  fetched: {fetched}  yes: {updated_yes}  no: {updated_no}")
    print(f"  no operator link: {no_link}")


if __name__ == "__main__":
    main()
