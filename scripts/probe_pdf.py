"""Inspect what pypdf extracts from a target PDF, and count katakana tokens."""
from __future__ import annotations
import re
import sys
from pathlib import Path

from pypdf import PdfReader

KATAKANA = re.compile(r"[ァ-ヺー]{2,12}")
ROOT = Path(__file__).resolve().parent.parent


def main(slug: str) -> None:
    # find the largest PDF source for this park
    from parklife import db
    with db.connect(ROOT / "data" / "parklife.db") as conn:
        rows = list(conn.execute("""
            SELECT s.raw_path, s.url FROM source s JOIN park p ON p.id=s.park_id
            WHERE p.slug=? AND LOWER(s.url) LIKE '%.pdf%'
            ORDER BY s.id
        """, (slug,)))
    for r in rows:
        path = ROOT / r["raw_path"]
        if not path.exists():
            continue
        size = path.stat().st_size
        print(f"\n=== {r['url'][:80]}  ({size//1024} KB) ===")
        try:
            reader = PdfReader(str(path))
        except Exception as e:
            print(f"  pypdf error: {e!r}")
            continue
        print(f"  pages: {len(reader.pages)}")
        all_text: list[str] = []
        for i, p in enumerate(reader.pages):
            try:
                t = p.extract_text() or ""
            except Exception as e:
                t = f"<page {i} extract error: {e!r}>"
            all_text.append(t)
        joined = "\n".join(all_text)
        print(f"  text length: {len(joined)}")
        # show first 500 chars
        print(f"  start: {joined[:500]!r}")
        tokens = sorted(set(m.group(0) for m in KATAKANA.finditer(joined)))
        print(f"  unique katakana tokens (≥2 char): {len(tokens)}")
        print(f"  sample: {tokens[:30]}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "kasairinkai")
