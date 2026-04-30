"""Tokyo-specific rule: if a TMG park's homepage has an アクセスマップ
section (always present in the template) but the entire page contains
no 駐車場 / パーキング keyword AT ALL, mark has_parking=0.

These are typically tiny ふ頭 / 緑道 / industrial parks that the TMG site
documents but provides no parking for.
"""
from __future__ import annotations
import warnings
from pathlib import Path
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from parklife import db
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

ROOT = Path(__file__).resolve().parent.parent

PARK_KW = ("駐車場", "パーキング")
ACCESS_KW = ("アクセスマップ", "交通案内", "アクセス")


def main() -> None:
    db_path = ROOT / "data" / "parklife.db"
    fixed = 0
    with db.connect(db_path) as conn:
        rows = list(conn.execute(
            "SELECT id, slug, official_url FROM park "
            "WHERE has_parking IS NULL AND prefecture='tokyo' "
            "AND official_url IS NOT NULL"
        ))
        for p in rows:
            r = conn.execute(
                "SELECT raw_path FROM source WHERE park_id=? AND url=? "
                "AND raw_path IS NOT NULL ORDER BY fetched_at DESC LIMIT 1",
                (p["id"], p["official_url"]),
            ).fetchone()
            if not r:
                continue
            html = (ROOT / r["raw_path"]).read_bytes()
            soup = BeautifulSoup(html, "lxml")
            for sel in ("nav", "header", "footer", "script", "style"):
                for tag in soup.find_all(sel):
                    tag.decompose()
            text = soup.get_text(" ", strip=True)
            has_access = any(k in text for k in ACCESS_KW)
            has_park = any(k in text for k in PARK_KW)
            if has_access and not has_park:
                # TMG template confirms the park exists but no parking is mentioned
                conn.execute(
                    "UPDATE park SET has_parking=0, parking_info='TMG template includes access but no parking section' "
                    "WHERE id=?",
                    (p["id"],),
                )
                fixed += 1
        conn.commit()
    print(f"defaulted {fixed} TMG parks (アクセスマップ present, no 駐車場 keyword) to has_parking=0")


if __name__ == "__main__":
    main()
