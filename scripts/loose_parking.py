"""Final loose pass: for remaining 'unknown' parks, scan ALL cached
pages (homepage + access subpage + operator page) for any 駐車 mention.

Decision tree per park:
  1. If any cached page has explicit negative phrasing → has_parking = 0
  2. Else if any cached page mentions 駐車場 / 駐車スペース at all
     → has_parking = 1, parking_info = '(loose match) ...'
  3. Else: leave as unknown
"""
from __future__ import annotations
import re
import warnings
from pathlib import Path
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from parklife import db
from scripts.extract_parking import NEGATIVE_PATTERNS

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
ROOT = Path(__file__).resolve().parent.parent

PARK_RE = re.compile(r"駐車(?:場|スペース|区域|スポット|可)")


def all_cached_html(conn, park_id: int) -> list[Path]:
    paths = []
    for r in conn.execute(
        "SELECT DISTINCT raw_path FROM source "
        "WHERE park_id=? AND raw_path IS NOT NULL "
        "ORDER BY fetched_at DESC", (park_id,),
    ):
        p = ROOT / r["raw_path"]
        if p.exists():
            paths.append(p)
    return paths


def text_of(path: Path) -> str:
    try:
        soup = BeautifulSoup(path.read_bytes(), "lxml")
        for sel in ("nav", "header", "footer", "script", "style"):
            for tag in soup.find_all(sel):
                tag.decompose()
        return soup.get_text(" ", strip=True)
    except Exception:
        return ""


def main() -> None:
    db_path = ROOT / "data" / "parklife.db"
    yes = no = stay_unknown = 0
    with db.connect(db_path) as conn:
        rows = list(conn.execute(
            "SELECT id, slug, name_ja, prefecture FROM park "
            "WHERE has_parking IS NULL"
        ))
        for p in rows:
            paths = all_cached_html(conn, p["id"])
            decision = None
            evidence = ""
            for path in paths:
                text = text_of(path)
                if not text:
                    continue
                # 1) negative wins
                for pat in NEGATIVE_PATTERNS:
                    m = pat.search(text)
                    if m:
                        start = max(0, m.start() - 40)
                        end = min(len(text), m.end() + 100)
                        decision = 0
                        evidence = "(loose) " + text[start:end]
                        break
                if decision is not None:
                    break
                # 2) any 駐車 mention
                m = PARK_RE.search(text)
                if m:
                    start = max(0, m.start() - 40)
                    end = min(len(text), m.end() + 200)
                    decision = 1
                    evidence = "(loose) " + text[start:end]
                    # don't break — keep looking for negative on later pages
            if decision == 1:
                conn.execute(
                    "UPDATE park SET has_parking=1, parking_info=? WHERE id=?",
                    (evidence[:600], p["id"]),
                ); yes += 1
            elif decision == 0:
                conn.execute(
                    "UPDATE park SET has_parking=0, parking_info=? WHERE id=?",
                    (evidence[:600], p["id"]),
                ); no += 1
            else:
                stay_unknown += 1
        conn.commit()
    print(f"loose pass — yes={yes}  no={no}  still_unknown={stay_unknown}")


if __name__ == "__main__":
    main()
