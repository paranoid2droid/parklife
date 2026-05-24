"""Second-pass parking classifier for parks currently flagged with OSM-only
inference.

For each park whose `parking_info` starts with 'OSM:', scan every cached HTML
under any source row for that park (not just the official_url), run the
existing `extract_parking.classify`, and overwrite has_parking/parking_info
ONLY when the classifier returns a definite verdict (not None).

This catches cases where the official_url itself is a JS-rendered SPA stub
(e.g. tokyo-park.or.jp/park/*/index.html) but operator-domain sub-pages
(tptc.co.jp, parks.or.jp, municipality pages) hold the real text.

Idempotent. Safe to re-run.
"""
from __future__ import annotations

from pathlib import Path

from parklife import db
from scripts.extract_parking import classify, parse_html

ROOT = Path(__file__).resolve().parent.parent


def candidate_paths(conn, park_id: int) -> list[tuple[Path, str]]:
    rows = conn.execute(
        """SELECT raw_path, url FROM source
           WHERE park_id=? AND raw_path IS NOT NULL
             AND raw_path LIKE 'data/raw/%'
           ORDER BY fetched_at DESC""",
        (park_id,),
    ).fetchall()
    out: list[tuple[Path, str]] = []
    seen: set[str] = set()
    for r in rows:
        if r["raw_path"] in seen:
            continue
        seen.add(r["raw_path"])
        p = ROOT / r["raw_path"]
        if p.exists():
            out.append((p, r["url"]))
    return out


def main() -> None:
    db_path = ROOT / "data" / "parklife.db"
    flipped_yes = flipped_no = unchanged = no_html = 0
    flips: list[tuple[str, int, int, str]] = []

    with db.connect(db_path) as conn:
        parks = list(conn.execute(
            """SELECT id, slug, prefecture, name_ja, official_url,
                      has_parking AS old_has, parking_info AS old_info
               FROM park
               WHERE parking_info LIKE 'OSM:%'
                 AND official_url IS NOT NULL
                 AND official_url != ''
               ORDER BY id"""
        ))
        print(f"OSM-only parks with URL to reclassify: {len(parks)}", flush=True)

        for i, p in enumerate(parks, 1):
            cands = candidate_paths(conn, p["id"])
            if not cands:
                no_html += 1
                continue
            verdict = None
            evidence = None
            src_used = None
            for path, src_url in cands:
                try:
                    block, full_text = parse_html(path)
                except Exception:
                    continue
                h, info = classify(block, full_text)
                if h is not None:
                    verdict, evidence, src_used = h, info, src_url
                    break
            if verdict is None:
                unchanged += 1
                continue
            old_has = p["old_has"]
            tag = f"scraped({src_used[:60]}): {evidence[:400] if evidence else ''}"
            conn.execute(
                "UPDATE park SET has_parking=?, parking_info=? WHERE id=?",
                (verdict, tag, p["id"]),
            )
            if verdict == 1: flipped_yes += 1
            else: flipped_no += 1
            if verdict != old_has:
                flips.append((p["name_ja"], old_has, verdict, src_used))
            if i % 25 == 0:
                conn.commit()
                print(
                    f"  [{i:>3}/{len(parks)}] flipped_yes={flipped_yes} "
                    f"flipped_no={flipped_no} unchanged={unchanged} "
                    f"no_html={no_html}",
                    flush=True,
                )
        conn.commit()

    print()
    print("=== reclassify done ===")
    print(f"  parks examined : {len(parks)}")
    print(f"  set has_parking=1 from cached text : {flipped_yes}")
    print(f"  set has_parking=0 from cached text : {flipped_no}")
    print(f"  no definite verdict (kept OSM)     : {unchanged}")
    print(f"  no usable cached HTML              : {no_html}")
    print()
    print(f"=== {len(flips)} verdict changes vs prior OSM call ===")
    for name, old, new, src in flips[:60]:
        print(f"  {name}  {old} -> {new}  via {src[:80]}")
    if len(flips) > 60:
        print(f"  ... and {len(flips) - 60} more")


if __name__ == "__main__":
    main()
