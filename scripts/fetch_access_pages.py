"""For each park whose homepage didn't yield parking info, find the
access / 交通 sub-page link, fetch it, and re-extract parking from it.

Heuristic: scan the homepage for anchors whose text or href contains
'アクセス' / 'access' / '交通' / 'koutsu'. Follow the first within-domain
hit.

Idempotent — uses fetch_cached_or_new so re-runs are cheap.
"""
from __future__ import annotations

import warnings
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

from parklife import db, fetch
from scripts.extract_parking import (
    PARKING_KW, NEGATIVE_PATTERNS, POSITIVE_PATTERNS,
    get_block, classify, ensure_columns, find_homepage_html,
)

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
ROOT = Path(__file__).resolve().parent.parent

ACCESS_KW_TEXT = ("アクセス", "交通案内", "交通", "ご来園", "Access")
ACCESS_KW_HREF = ("access", "koutsu", "kotsu", "transit")


def find_access_link(html: bytes, base_url: str) -> str | None:
    soup = BeautifulSoup(html, "lxml")
    base_host = urlparse(base_url).netloc
    candidates: list[tuple[int, str]] = []
    for a in soup.find_all("a", href=True):
        text = " ".join(a.get_text().split())
        href = a["href"]
        score = 0
        for k in ACCESS_KW_TEXT:
            if k in text:
                score += 2
        for k in ACCESS_KW_HREF:
            if k in href.lower():
                score += 1
        if score == 0:
            continue
        full = urljoin(base_url, href)
        # only follow within-domain (avoid hopping to Twitter etc.)
        if urlparse(full).netloc != base_host:
            continue
        # avoid the homepage itself
        if full.rstrip("/") == base_url.rstrip("/"):
            continue
        candidates.append((score, full))
    if not candidates:
        return None
    candidates.sort(key=lambda x: -x[0])
    return candidates[0][1]


def main() -> None:
    db_path = ROOT / "data" / "parklife.db"
    fetched = updated_yes = updated_no = unknown_after = no_link = 0
    with db.connect(db_path) as conn:
        ensure_columns(conn)
        # only re-process parks that are currently 'unknown'
        parks = list(conn.execute(
            "SELECT id, slug, prefecture, official_url FROM park "
            "WHERE has_parking IS NULL AND official_url IS NOT NULL "
            "ORDER BY prefecture, slug"
        ))
        print(f"unknown parks to retry: {len(parks)}")
        for p in parks:
            home_path = find_homepage_html(conn, p["id"], p["official_url"])
            if not home_path:
                no_link += 1
                continue
            access_url = find_access_link(home_path.read_bytes(), p["official_url"])
            if not access_url:
                no_link += 1
                continue
            try:
                src_id, path = fetch.fetch_cached_or_new(
                    conn, ROOT, p["id"], p["prefecture"], p["slug"], access_url,
                    max_age_days=14, delay_s=1.0,
                )
                fetched += 1
            except Exception as e:
                print(f"  fetch err {p['slug']}: {e!r}")
                no_link += 1
                continue
            soup = BeautifulSoup(path.read_bytes(), "lxml")
            for sel in ("nav", "header", "footer", "script", "style"):
                for tag in soup.find_all(sel):
                    tag.decompose()
            block = get_block(soup)
            full_text = soup.get_text(" ", strip=True)
            has, info = classify(block, full_text)
            if has is not None:
                conn.execute(
                    "UPDATE park SET has_parking=?, parking_info=? WHERE id=?",
                    (has, info, p["id"]),
                )
                if has == 1: updated_yes += 1
                else: updated_no += 1
            else:
                unknown_after += 1
            if (fetched % 10) == 0:
                conn.commit()
                print(f"  fetched={fetched} yes={updated_yes} no={updated_no} still_unknown={unknown_after}")
        conn.commit()
    print(f"\n=== access-page parking pass done ===")
    print(f"  fetched: {fetched}")
    print(f"  updated yes: {updated_yes}")
    print(f"  updated no: {updated_no}")
    print(f"  still unknown after fetch: {unknown_after}")
    print(f"  no access link / fetch failed: {no_link}")


if __name__ == "__main__":
    main()
