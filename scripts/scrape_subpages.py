"""Phase B: fetch park sub-pages (HTML or PDF) listed in
data/scan/tokyo_subpage_targets.json, extract katakana species names from
the resulting text, and insert observations.

Reuses:
  - parklife.fetch.fetch_cached_or_new for caching + source rows
  - parklife.normalize.wikipedia for taxon validation (file-cache hits)

For PDFs, uses pypdf to extract text. For HTML, BeautifulSoup. Then the
same extraction pipeline as Phase A: tokenize → Wikipedia validate →
upsert observation + alias.
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from parklife import db, fetch
from parklife.normalize import wikipedia
from scripts.extract_tokyo_animals import (
    KATAKANA_TOKEN, STOPWORDS, SEASON_BITS, candidate_tokens, split_segments,
)

ROOT = Path(__file__).resolve().parent.parent

# external nature-park pages we want to follow even though they live off-domain
EXTERNAL_OK = ("kankyo.metro.tokyo.lg.jp",)


def is_pdf(url: str) -> bool:
    return url.lower().split("?", 1)[0].endswith(".pdf")


def pdf_to_text(path: Path) -> str:
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        return "\n".join((p.extract_text() or "") for p in reader.pages)
    except Exception as e:
        print(f"    pdf parse failed: {e!r}")
        return ""


def html_to_text(path: Path) -> str:
    soup = BeautifulSoup(path.read_bytes(), "lxml")
    # remove nav/footer/script/style
    for sel in ["nav", "header", "footer", "script", "style"]:
        for tag in soup.find_all(sel):
            tag.decompose()
    return soup.get_text(" ", strip=True)


def main() -> int:
    targets_path = ROOT / "data" / "scan" / "tokyo_subpage_targets.json"
    targets = json.loads(targets_path.read_text(encoding="utf-8"))

    db_path = ROOT / "data" / "parklife.db"
    inserted = checked = accepted = 0
    parks_touched = 0

    # in-memory animal cache (shared with Phase A)
    cache_path = ROOT / "data" / "cache" / "tokyo_animal_resolution.json"
    cache: dict = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}

    with db.connect(db_path) as conn:
        for slug, anchors in targets.items():
            row = conn.execute(
                "SELECT id, prefecture, official_url FROM park "
                "WHERE prefecture='tokyo' AND slug=?", (slug,)
            ).fetchone()
            if not row:
                continue
            park_id, pref, base_url = row["id"], row["prefecture"], row["official_url"]

            new_for_park = 0
            for anchor in anchors:
                href = anchor["href"]
                # anchor may already be absolute http(s)
                target = href if href.startswith(("http://", "https://")) else urljoin(base_url, href)
                # skip kankyo.metro pages whose hostname differs unless allow-listed
                if target.startswith("http") and not any(d in target for d in EXTERNAL_OK + ("tokyo-park.or.jp",)):
                    continue
                # skip pure fragment
                if target.startswith("#") or "#" in target and target.split("#",1)[0] == base_url:
                    continue
                try:
                    src_id, path = fetch.fetch_cached_or_new(
                        conn, ROOT, park_id, pref, slug, target, max_age_days=14, delay_s=1.2,
                    )
                except Exception as e:
                    print(f"    [{slug}] fetch error {target}: {e!r}")
                    continue

                # extract text
                if is_pdf(target):
                    text = pdf_to_text(path)
                else:
                    try:
                        text = html_to_text(path)
                    except Exception as e:
                        print(f"    [{slug}] parse error {target}: {e!r}")
                        continue
                if not text or len(text) < 80:
                    continue

                # walk segments, extract candidates
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
                        # park-level dedup on (raw_name, bitmap)
                        existing = conn.execute(
                            """SELECT id FROM observation WHERE park_id=? AND raw_name=?
                               AND ( (months_bitmap IS NULL AND ? IS NULL)
                                  OR (months_bitmap = ?) )""",
                            (park_id, tok, bitmap, bitmap),
                        ).fetchone()
                        if existing:
                            accepted += 1; continue
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
                               VALUES (?, ?, ?, ?, ?, ?, ?)""",
                            (park_id, species_id, tok, bitmap, anchor["text"][:60], None, src_id),
                        )
                        accepted += 1; inserted += 1; new_for_park += 1
            conn.commit()
            print(f"  {slug:<25} new={new_for_park}")
            if new_for_park:
                parks_touched += 1

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n=== Phase B done ===")
    print(f"  parks touched: {parks_touched}")
    print(f"  candidates checked: {checked}")
    print(f"  accepted: {accepted}")
    print(f"  inserted: {inserted}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
