"""Extract parking info from each park's cached homepage.

For each park:
  1. Look up the source row whose `url` equals `park.official_url`
     (most-recent fetch); read that HTML.
  2. Find any h2/h3/h4/h5 heading containing 駐車場 / パーキング.
  3. Capture the heading + the next ~600 chars of body text as
     `park.parking_info`.
  4. Set `park.has_parking`:
       - 1 if a 駐車場 section exists AND text doesn't say なし/ありません
       - 0 if explicit "駐車場なし" / "駐車場はありません" / "駐車場の用意はありません"
       - NULL otherwise (unknown)

Idempotent. Run again whenever new HTML is cached.
"""
from __future__ import annotations

import re
import warnings
from pathlib import Path

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

from parklife import db
# Canonical rules live in parklife.parking (single source of truth). Re-exported
# here under the historical names so existing importers keep working.
from parklife.parking import (  # noqa: F401
    NEGATIVE_PATTERNS,
    PARKING_KW,
    POSITIVE_PATTERNS,
    RESTRICTED_PATTERNS,
    classify_text,
)

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
ROOT = Path(__file__).resolve().parent.parent


def get_block(soup: BeautifulSoup) -> str | None:
    for tag in soup.find_all(["h2", "h3", "h4", "h5"]):
        text = " ".join(tag.get_text().split())
        if not text or len(text) > 40:
            continue
        if not any(k in text for k in PARKING_KW):
            continue
        # collect next siblings until another h-tag of same/higher rank
        rank = int(tag.name[1])
        same_or_higher = {f"h{i}" for i in range(1, rank + 1)}
        chunks = [text]
        for sib in tag.find_next_siblings():
            if getattr(sib, "name", None) in same_or_higher:
                break
            t = " ".join(sib.get_text(" ", strip=True).split())
            if t:
                chunks.append(t)
            if sum(len(c) for c in chunks) > 700:
                break
        return " | ".join(chunks)
    return None


def classify(block: str | None, full_text: str) -> tuple[int | None, str | None]:
    """Back-compat wrapper: (has_parking, parking_info) without the source tier.

    New callers should use ``parklife.parking.classify_text`` directly to also
    get the evidence-tier tag.
    """
    has, _source, evidence = classify_text(block, full_text)
    return (has, evidence)


def ensure_columns(conn) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(park)")}
    if "parking_info" not in cols:
        conn.execute("ALTER TABLE park ADD COLUMN parking_info TEXT")
    if "has_parking" not in cols:
        conn.execute("ALTER TABLE park ADD COLUMN has_parking INTEGER")
    if "parking_source" not in cols:
        conn.execute("ALTER TABLE park ADD COLUMN parking_source TEXT")


def find_homepage_html(conn, park_id: int, official_url: str) -> Path | None:
    row = conn.execute(
        """SELECT raw_path FROM source
           WHERE park_id=? AND url=? AND raw_path IS NOT NULL
           ORDER BY fetched_at DESC LIMIT 1""",
        (park_id, official_url),
    ).fetchone()
    if not row:
        return None
    p = ROOT / row["raw_path"]
    return p if p.exists() else None


def find_alt_html(conn, park_id: int, official_url: str) -> list[Path]:
    """Other cached HTML pages for this park (operator domains, sub-pages).
    Excludes the official_url itself and iNaturalist API responses."""
    rows = conn.execute(
        """SELECT raw_path FROM source
           WHERE park_id=? AND raw_path IS NOT NULL
             AND url != ?
             AND url NOT LIKE '%inaturalist.com%'
             AND url NOT LIKE '%api.inaturalist%'
           ORDER BY fetched_at DESC""",
        (park_id, official_url),
    ).fetchall()
    out = []
    for r in rows:
        p = ROOT / r["raw_path"]
        if p.exists():
            out.append(p)
    return out


def parse_html(path: Path) -> tuple[str | None, str]:
    soup = BeautifulSoup(path.read_bytes(), "lxml")
    for sel in ("nav", "header", "footer", "script", "style"):
        for tag in soup.find_all(sel):
            tag.decompose()
    return get_block(soup), soup.get_text(" ", strip=True)


def main() -> None:
    db_path = ROOT / "data" / "parklife.db"
    yes = no = unknown = no_html = 0
    with db.connect(db_path) as conn:
        ensure_columns(conn)
        parks = list(conn.execute(
            "SELECT id, slug, prefecture, official_url FROM park WHERE official_url IS NOT NULL"
        ))
        for p in parks:
            candidates: list[Path] = []
            primary = find_homepage_html(conn, p["id"], p["official_url"])
            if primary:
                candidates.append(primary)
            candidates.extend(find_alt_html(conn, p["id"], p["official_url"]))
            if not candidates:
                no_html += 1
                continue
            has: int | None = None
            info: str | None = None
            source: str | None = None
            tmg_full_no_park = False
            for path in candidates:
                block, full_text = parse_html(path)
                h, src, i = classify_text(block, full_text)
                if h is not None:
                    has, source, info = h, src, i
                    break
                # Tokyo metropolitan park homepage (tokyo-park.or.jp) with a
                # full "施設" facility list and 交通案内 but never mentioning
                # 駐車場 → reliably means no public parking. Gate by domain
                # to avoid misfires on zoo / aquarium / TPTC stubs.
                src_url = ""
                row = conn.execute(
                    "SELECT url FROM source WHERE raw_path=? LIMIT 1",
                    (str(path.relative_to(ROOT)),),
                ).fetchone()
                if row:
                    src_url = row["url"]
                if (src_url.startswith("https://www.tokyo-park.or.jp/park/")
                        and "/zoo/" not in src_url
                        and len(full_text) > 2000
                        and "施設" in full_text
                        and "交通案内" in full_text
                        and "駐車場" not in full_text
                        and "パーキング" not in full_text):
                    tmg_full_no_park = True
            if has is None and tmg_full_no_park:
                from parklife.parking import SOURCE_TMG_NO_FACILITY
                has, source, info = (
                    0, SOURCE_TMG_NO_FACILITY,
                    "(TMG homepage with facility list, no parking mentioned)",
                )
            # Only write a verdict we actually have; never clobber an existing
            # row with NULL (lets OSM / later text fill genuinely-unknown rows).
            if has is not None:
                conn.execute(
                    "UPDATE park SET has_parking=?, parking_info=?, parking_source=? WHERE id=?",
                    (has, info, source, p["id"]),
                )
            if has == 1: yes += 1
            elif has == 0: no += 1
            else: unknown += 1
        conn.commit()
    print(f"yes={yes}  no={no}  unknown={unknown}  no_html={no_html}")
    print(f"total={yes+no+unknown+no_html}")


if __name__ == "__main__":
    main()
