"""Phase F prep: fetch each non-Tokyo park's main page for later inspection.

Just downloads + caches; does not extract. Subsequent extractors can read
data/raw/<prefecture>/<slug>/<sha>.html and decide what to do per page.

Idempotent: skips parks where we already have a cached fetch < 14d old.
"""

from __future__ import annotations

import sys
from pathlib import Path

from parklife import db, fetch

ROOT = Path(__file__).resolve().parent.parent


def main(prefectures: list[str]) -> int:
    db_path = ROOT / "data" / "parklife.db"
    with db.connect(db_path) as conn:
        rows = list(conn.execute(
            f"SELECT id, slug, prefecture, official_url, name_ja FROM park "
            f"WHERE prefecture IN ({','.join(['?']*len(prefectures))}) "
            f"AND official_url IS NOT NULL ORDER BY prefecture, slug",
            prefectures,
        ))
    print(f"to fetch: {len(rows)} parks across {prefectures}")

    ok = err = 0
    with db.connect(db_path) as conn:
        for i, r in enumerate(rows, 1):
            try:
                src_id, path = fetch.fetch_cached_or_new(
                    conn, ROOT, r["id"], r["prefecture"], r["slug"], r["official_url"],
                    max_age_days=14, delay_s=1.0,
                )
                size = path.stat().st_size if path.exists() else 0
                print(f"  [{i:>3}/{len(rows)}] {r['prefecture']:<8} {r['slug']:<28} {size:>7}B")
                ok += 1
            except Exception as e:
                err += 1
                print(f"  [{i:>3}/{len(rows)}] {r['prefecture']:<8} {r['slug']:<28} ERROR {e!r}")
            conn.commit()
    print(f"\nfetched: ok={ok} err={err}")
    return 0


if __name__ == "__main__":
    prefectures = sys.argv[1:] if len(sys.argv) > 1 else ["kanagawa", "saitama"]
    sys.exit(main(prefectures))
