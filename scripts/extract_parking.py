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

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
ROOT = Path(__file__).resolve().parent.parent

PARKING_KW = ("駐車場", "パーキング", "コインパーキング")

NEGATIVE_PATTERNS = [
    re.compile(r"駐車場(?:は|の用意は)?(?:ございません|ありません|なし|はない)"),
    re.compile(r"専用(?:の)?駐車場(?:は)?(?:ございません|ありません|なし)"),
    re.compile(r"公園(?:に|には)(?:専用)?駐車場(?:は)?(?:ありません|なし)"),
    re.compile(r"駐車場(?:は)?設置(?:しておりません|していません|されていません)"),
    re.compile(r"駐車場(?:は)?設けて(?:おりません|いません)"),
    re.compile(r"お車での(?:ご)?来園は(?:ご)?遠慮"),
    # bullet-style "駐車場 なし" / "駐車場：なし" (Chiba pref pages, etc.)
    re.compile(r"駐車場[\s:：]*(?:なし|無し|無|ない)(?![ぁ-んー])"),
]

# Restricted-access patterns — parking exists but not for general visitors.
# Per user constraint: 団体予約のみ, 障害者専用, 観光バス専用 should NOT count
# as "公開駐車場あり". These collapse to has_parking=0.
RESTRICTED_PATTERNS = [
    re.compile(r"団体(?:のお客様|利用|予約)?(?:の方)?のみ"),
    re.compile(r"事前(?:の)?(?:予約|申込)(?:制|のみ)"),
    re.compile(r"(?:身体)?障害者(?:の方)?(?:専用|のみ)"),
    re.compile(r"車椅子・?障害者(?:の方)?の(?:お)?車"),
    re.compile(r"観光バス(?:専用|のみ)"),
]

# accept signals (positive): explicit fee/capacity tells us there's parking
POSITIVE_PATTERNS = [
    re.compile(r"\d+\s*台"),
    re.compile(r"普通車\s*\d"),
    re.compile(r"\d+\s*分まで\d+\s*円"),
    re.compile(r"\d+\s*時間まで\d+\s*円"),
    re.compile(r"利用料金"),
    re.compile(r"営業時間"),
    re.compile(r"駐車料金"),
    # bullet-style "駐車場 あり" / "駐車場：あり"
    re.compile(r"駐車場[\s:：]*(?:あり|有り|有)(?![ぁ-んー])"),
]


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


def _evidence_window(text: str, match) -> str:
    start = max(0, match.start() - 60)
    end = min(len(text), match.end() + 140)
    return text[start:end]


def classify(block: str | None, full_text: str) -> tuple[int | None, str | None]:
    """Return (has_parking, parking_info)."""
    haystack = block or full_text

    # 1) Negative phrasing trumps anything else
    for p in NEGATIVE_PATTERNS:
        m = p.search(haystack)
        if m:
            return (0, _evidence_window(haystack, m))

    # 2) Restricted-access (団体予約のみ / 障害者専用 / 観光バスのみ) — count
    #    as "no public parking". Only check near a 駐車場 mention so we don't
    #    mis-fire on unrelated reservation language.
    for m in re.finditer(r"駐車", haystack):
        window = haystack[max(0, m.start() - 80): m.end() + 200]
        for p in RESTRICTED_PATTERNS:
            rm = p.search(window)
            if rm:
                return (0, _evidence_window(haystack, m))

    # 3) Heading-anchored block: presume parking exists (even without
    #    a positive marker, since the section itself signals one).
    if block:
        return (1, block[:600])

    # 4) No 駐車場 heading found — search full text for the word with
    #    positive context within ~150 chars (fee, capacity, hours).
    park_iter = list(re.finditer(r"駐車場|パーキング", full_text))
    for m in park_iter:
        ctx = full_text[max(0, m.start() - 80): m.end() + 200]
        if any(p.search(ctx) for p in POSITIVE_PATTERNS):
            return (1, _evidence_window(full_text, m))

    # 5) 駐車場 appears in stripped body (no nav/header/footer) but no
    #    explicit positive marker — treat as parking-exists. Body-level
    #    mentions in a facility list ("芝生広場、駐車場、野鳥観察舎") or in
    #    operational notes ("駐車場は混雑します") almost always indicate a
    #    real parking lot. Restricted/negative cases were ruled out above.
    if park_iter:
        m = park_iter[0]
        return (1, _evidence_window(full_text, m))

    return (None, None)


def ensure_columns(conn) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(park)")}
    if "parking_info" not in cols:
        conn.execute("ALTER TABLE park ADD COLUMN parking_info TEXT")
    if "has_parking" not in cols:
        conn.execute("ALTER TABLE park ADD COLUMN has_parking INTEGER")


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
            tmg_full_no_park = False
            for path in candidates:
                block, full_text = parse_html(path)
                h, i = classify(block, full_text)
                if h is not None:
                    has, info = h, i
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
                has, info = 0, "(TMG homepage with facility list, no parking mentioned)"
            conn.execute(
                "UPDATE park SET has_parking=?, parking_info=? WHERE id=?",
                (has, info, p["id"]),
            )
            if has == 1: yes += 1
            elif has == 0: no += 1
            else: unknown += 1
        conn.commit()
    print(f"yes={yes}  no={no}  unknown={unknown}  no_html={no_html}")
    print(f"total={yes+no+unknown+no_html}")


if __name__ == "__main__":
    main()
