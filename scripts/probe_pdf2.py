"""Same probe but using pdfminer.six (better Japanese CID support)."""
from __future__ import annotations
import re
import sys
from pathlib import Path

from pdfminer.high_level import extract_text

KATAKANA = re.compile(r"[ァ-ヺー]{2,12}")
ROOT = Path(__file__).resolve().parent.parent


def main(slug: str) -> None:
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
            text = extract_text(str(path))
        except Exception as e:
            print(f"  pdfminer error: {e!r}")
            continue
        print(f"  text length: {len(text)}")
        print(f"  start: {text[:600]!r}")
        tokens = sorted(set(m.group(0) for m in KATAKANA.finditer(text)))
        print(f"  unique katakana tokens (≥2 char): {len(tokens)}")
        print(f"  sample: {tokens[:30]}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "kasairinkai")
