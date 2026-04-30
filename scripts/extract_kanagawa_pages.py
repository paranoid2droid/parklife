"""Phase F: extract species mentions from Kanagawa/Saitama park HTML.

Strategy: even though each park has a custom layout, we apply the SAME
narrative-text scanning approach as Phase A:
  1. fetch each park's main page (cached)
  2. capture all paragraph/list text in the page body
  3. tokenise katakana strings
  4. validate via Wikipedia normalizer (cached)
  5. accept any token that resolves to a wild species

iNaturalist already provides much more comprehensive species lists for
these parks (Phase D), so this pass is supplementary — picking up species
mentioned by the park itself, which encodes editorial intent ("we want
visitors to look for these").

Refuses to fetch external 指定管理者 sites that 403 our default UA;
extends Phase A's logic to handle parks whose main page is at a non-
tokyo-park.or.jp domain (kanagawa-park.or.jp, parks.or.jp, etc.).
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

from bs4 import BeautifulSoup

from parklife import db, fetch
from parklife.normalize import wikipedia
from scripts.extract_tokyo_animals import (
    candidate_tokens, split_segments, KATAKANA_TOKEN, STOPWORDS,
)

ROOT = Path(__file__).resolve().parent.parent

CACHE_PATH = ROOT / "data" / "cache" / "tokyo_animal_resolution.json"


def page_text(path: Path) -> str:
    soup = BeautifulSoup(path.read_bytes(), "lxml")
    for sel in ["nav", "header", "footer", "script", "style"]:
        for tag in soup.find_all(sel):
            tag.decompose()
    return soup.get_text(" ", strip=True)


def main(prefectures: list[str]) -> int:
    db_path = ROOT / "data" / "parklife.db"
    cache: dict = json.loads(CACHE_PATH.read_text(encoding="utf-8")) if CACHE_PATH.exists() else {}

    placeholders = ",".join(["?"] * len(prefectures))
    with db.connect(db_path) as conn:
        rows = list(conn.execute(
            f"SELECT id, slug, prefecture, official_url, name_ja FROM park "
            f"WHERE prefecture IN ({placeholders}) AND official_url IS NOT NULL "
            f"ORDER BY prefecture, slug",
            prefectures,
        ))
    print(f"parks to scan: {len(rows)} ({prefectures})")

    inserted = checked = 0
    parks_touched = 0

    with db.connect(db_path) as conn:
        for i, p in enumerate(rows, 1):
            new_for_park = 0
            try:
                src_id, path = fetch.fetch_cached_or_new(
                    conn, ROOT, p["id"], p["prefecture"], p["slug"], p["official_url"],
                    max_age_days=14, delay_s=1.0,
                )
            except Exception as e:
                print(f"  [{i:>3}/{len(rows)}] {p['prefecture']} {p['slug']:<25} fetch err {e!r}")
                continue
            try:
                text = page_text(path)
            except Exception as e:
                print(f"  [{i:>3}/{len(rows)}] {p['prefecture']} {p['slug']:<25} parse err {e!r}")
                continue
            if len(text) < 80:
                continue

            for segment, bitmap in split_segments(text):
                for tok in candidate_tokens(segment):
                    checked += 1
                    cached = cache.get(tok)
                    if cached is None:
                        res = wikipedia.lookup_with_cache(tok, ROOT)
                        cache[tok] = res.to_dict()
                        cached = cache[tok]
                        time.sleep(0.15)
                    if not cached.get("found") or cached.get("is_disambig"):
                        continue
                    kingdom = cached.get("kingdom")
                    if kingdom not in ("animalia", "plantae", "fungi"):
                        continue
                    existing = conn.execute(
                        """SELECT id FROM observation WHERE park_id=? AND raw_name=?
                           AND ( (months_bitmap IS NULL AND ? IS NULL)
                              OR (months_bitmap = ?) )""",
                        (p["id"], tok, bitmap, bitmap),
                    ).fetchone()
                    if existing:
                        continue
                    sa = conn.execute(
                        "SELECT species_id FROM species_alias WHERE raw_name=?", (tok,),
                    ).fetchone()
                    species_id = sa["species_id"] if sa and sa["species_id"] else None
                    if not sa:
                        conn.execute(
                            """INSERT OR IGNORE INTO species_alias
                               (species_id, raw_name, lang, status)
                               VALUES (NULL, ?, 'ja-kana', 'pending')""",
                            (tok,),
                        )
                    conn.execute(
                        """INSERT INTO observation
                           (park_id, species_id, raw_name, months_bitmap,
                            location_hint, characteristics, source_id)
                           VALUES (?, ?, ?, ?, NULL, NULL, ?)""",
                        (p["id"], species_id, tok, bitmap, src_id),
                    )
                    inserted += 1; new_for_park += 1
            conn.commit()
            if new_for_park:
                parks_touched += 1
                print(f"  [{i:>3}/{len(rows)}] {p['prefecture']:<8} {p['slug']:<25} +{new_for_park}")

    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n=== Phase F done ===")
    print(f"  parks touched: {parks_touched}")
    print(f"  candidates checked: {checked}")
    print(f"  inserted: {inserted}")
    return 0


if __name__ == "__main__":
    prefectures = sys.argv[1:] if len(sys.argv) > 1 else ["kanagawa", "saitama", "chiba"]
    sys.exit(main(prefectures))
