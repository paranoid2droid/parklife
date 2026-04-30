"""Investigate why Tokyo parks remain 'unknown' for parking — do their
homepages have an アクセス section at all? If yes but no 駐車場 mention,
they likely just have no parking lot.
"""
from __future__ import annotations
import warnings
from pathlib import Path
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from parklife import db
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

ROOT = Path(__file__).resolve().parent.parent


def homepage_path(conn, park_id: int, url: str) -> Path | None:
    r = conn.execute(
        "SELECT raw_path FROM source WHERE park_id=? AND url=? "
        "AND raw_path IS NOT NULL ORDER BY fetched_at DESC LIMIT 1",
        (park_id, url),
    ).fetchone()
    if not r:
        return None
    p = ROOT / r["raw_path"]
    return p if p.exists() else None


def main() -> None:
    db_path = ROOT / "data" / "parklife.db"
    cats = {"has_access_no_park": [], "has_access_with_park_kw": [],
            "no_access_section": [], "no_html": [],
            "very_short_page": []}
    with db.connect(db_path) as conn:
        rows = list(conn.execute(
            "SELECT id, slug, prefecture, official_url FROM park "
            "WHERE has_parking IS NULL"
        ))
        for p in rows:
            path = homepage_path(conn, p["id"], p["official_url"])
            if not path:
                cats["no_html"].append((p["prefecture"], p["slug"]))
                continue
            html = path.read_bytes()
            if len(html) < 5000:
                cats["very_short_page"].append((p["prefecture"], p["slug"]))
                continue
            soup = BeautifulSoup(html, "lxml")
            for sel in ("nav", "header", "footer", "script", "style"):
                for tag in soup.find_all(sel):
                    tag.decompose()
            text = soup.get_text(" ", strip=True)
            has_access = ("アクセス" in text or "交通案内" in text or "交通" in text)
            has_park_word = ("駐車場" in text or "パーキング" in text)
            if has_access and not has_park_word:
                cats["has_access_no_park"].append((p["prefecture"], p["slug"]))
            elif has_park_word:
                # word appears but classifier didn't catch it — needs investigation
                cats["has_access_with_park_kw"].append((p["prefecture"], p["slug"]))
            else:
                cats["no_access_section"].append((p["prefecture"], p["slug"]))

    for k, v in cats.items():
        print(f"\n{k}: {len(v)}")
        # show breakdown by prefecture
        by_pref: dict[str, int] = {}
        for pref, slug in v:
            by_pref[pref] = by_pref.get(pref, 0) + 1
        for pref, n in sorted(by_pref.items()):
            print(f"  {pref:<10} {n}")
        if k == "has_access_with_park_kw":
            print("  -- samples (parking keyword present but unclassified) --")
            for pref, slug in v[:10]:
                print(f"  {pref}/{slug}")


if __name__ == "__main__":
    main()
