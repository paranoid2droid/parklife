"""For each OSM-only park (non-TMG), refetch the official_url AND any internal
links whose anchor text or href matches parking-relevant keywords. The goal is
to fill `data/raw/` with pages that actually contain a `駐車場` section, so a
later `scripts.reclassify_parking` can flip them off OSM heuristics.

Polite: 1.5s between network calls, 30-day cache. Each fetched page is recorded
in `source` as usual. Skips parks whose URL is on tokyo-park.or.jp (JS-rendered
SPA — out of scope for HTML-only scraping).
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from parklife import db, fetch

ROOT = Path(__file__).resolve().parent.parent
DELAY = 1.5
MAX_FOLLOWUPS = 4
KEYWORD_RE = re.compile(
    r"駐車|パーキング|アクセス|交通|利用案内|施設案内|ご利用|園内案内|案内|guide|access|parking",
    re.I,
)


def discover_followups(html: bytes, base_url: str) -> list[str]:
    """Return up to MAX_FOLLOWUPS absolute URLs whose anchor text or href hints
    at parking / access info, restricted to the same host as base_url."""
    soup = BeautifulSoup(html, "lxml")
    base_host = urlparse(base_url).netloc.lower()
    seen: set[str] = set()
    hits: list[tuple[int, str]] = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        absu = urljoin(base_url, href)
        u = urlparse(absu)
        if u.scheme not in ("http", "https"):
            continue
        if u.netloc.lower() != base_host:
            continue
        text = " ".join(a.get_text(" ", strip=True).split())
        if not KEYWORD_RE.search(text) and not KEYWORD_RE.search(href):
            continue
        key = absu.split("#", 1)[0]
        if key in seen or key == base_url:
            continue
        seen.add(key)
        score = 0
        if "駐車" in text or "parking" in text.lower(): score += 5
        if "アクセス" in text or "access" in text.lower(): score += 3
        if "交通" in text: score += 3
        if "案内" in text: score += 1
        if "利用" in text: score += 1
        hits.append((score, key))
    hits.sort(key=lambda x: -x[0])
    return [u for _, u in hits[:MAX_FOLLOWUPS]]


def main(limit: int | None = None) -> int:
    db_path = ROOT / "data" / "parklife.db"
    fetched = 0
    followups_fetched = 0
    skipped_tmg = 0
    errs = 0

    with db.connect(db_path) as conn:
        parks = list(conn.execute(
            """SELECT id, slug, prefecture, official_url
               FROM park
               WHERE parking_info LIKE 'OSM:%'
                 AND official_url IS NOT NULL
                 AND official_url != ''
               ORDER BY id"""
        ))
        if limit:
            parks = parks[:limit]
        print(f"OSM-only parks with URL: {len(parks)}", flush=True)

        for i, p in enumerate(parks, 1):
            url = p["official_url"]
            if "tokyo-park.or.jp" in url:
                skipped_tmg += 1
                continue
            try:
                _, path = fetch.fetch_cached_or_new(
                    conn, ROOT, p["id"], p["prefecture"], p["slug"], url,
                    max_age_days=30, delay_s=DELAY,
                )
                fetched += 1
                conn.commit()
            except Exception as e:
                print(f"  [{i}] {p['slug']} primary fetch err: {type(e).__name__}: {e}", flush=True)
                errs += 1
                continue
            try:
                followups = discover_followups(path.read_bytes(), url)
            except Exception as e:
                print(f"  [{i}] {p['slug']} parse err: {e}", flush=True)
                followups = []
            for fu in followups:
                try:
                    fetch.fetch_cached_or_new(
                        conn, ROOT, p["id"], p["prefecture"], p["slug"], fu,
                        max_age_days=30, delay_s=DELAY,
                    )
                    followups_fetched += 1
                    conn.commit()
                except Exception as e:
                    print(f"     followup err {fu[:70]}: {type(e).__name__}", flush=True)
                    errs += 1
            if i % 10 == 0:
                print(
                    f"  [{i:>3}/{len(parks)}] fetched={fetched} "
                    f"followups={followups_fetched} skipped_tmg={skipped_tmg} "
                    f"errs={errs}",
                    flush=True,
                )

    print()
    print("=== fetch_parking_followups done ===")
    print(f"  primary fetched      : {fetched}")
    print(f"  follow-ups fetched   : {followups_fetched}")
    print(f"  TMG SPA skipped      : {skipped_tmg}")
    print(f"  errors               : {errs}")
    return 0


if __name__ == "__main__":
    cap = int(sys.argv[1]) if len(sys.argv) > 1 else None
    sys.exit(main(limit=cap))
