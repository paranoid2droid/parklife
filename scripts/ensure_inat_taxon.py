"""Look up iNat taxon_id for species rows that lack one, or photos for
species rows that lack photo_url.

Strategy: prefer scientific_name search (most reliable). Fall back to
common_name_ja with locale=ja. Cache one JSON per scientific name to
avoid re-fetching.

Cache: data/cache/inat_taxa/<sanitized_sci>.json
Result: updates species.inat_taxon_id and (when available) photo_url.

Idempotent. Re-running is cheap (cached).
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

from curl_cffi import requests

from parklife import db

ROOT = Path(__file__).resolve().parent.parent
UA = "parklife-bot/0.1 (research; contact: paranoid2droid@gmail.com)"
API = "https://api.inaturalist.org/v1/taxa"
CACHE = ROOT / "data" / "cache" / "inat_taxa"
REQUEST_DELAY_SECONDS = 1.0


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)[:120]


def lookup(query: str, locale: str = "en") -> tuple[dict | None, bool]:
    cp = CACHE / f"{_safe(query)}__{locale}.json"
    cp.parent.mkdir(parents=True, exist_ok=True)
    if cp.exists():
        try:
            return json.loads(cp.read_text(encoding="utf-8")), False
        except Exception:
            pass
    r = requests.get(
        API, params={"q": query, "rank": "species", "per_page": 5, "locale": locale},
        headers={"User-Agent": UA, "Accept-Language": locale},
        impersonate="chrome", timeout=20,
    )
    if r.status_code != 200:
        return None, True
    data = r.json()
    cp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data, True


def best_match(data: dict, sci: str | None, ja: str | None) -> dict | None:
    if not data:
        return None
    results = data.get("results") or []
    # exact name match wins
    for r in results:
        if sci and r.get("name") and r["name"].lower() == sci.lower():
            return r
    # any partial sci-name match (e.g., subspecies) — accept if first word matches genus
    if sci:
        genus = sci.split()[0].lower()
        for r in results:
            if r.get("name", "").lower().startswith(genus):
                return r
    # match by ja vernacular
    if ja:
        for r in results:
            for v in (r.get("preferred_common_name"), r.get("matched_term")):
                if v and v == ja:
                    return r
    return results[0] if results else None


def main(limit: int | None = None, missing_photo: bool = False) -> int:
    db_path = ROOT / "data" / "parklife.db"
    where = (
        "(s.photo_url IS NULL OR s.photo_url = '')"
        if missing_photo
        else "s.inat_taxon_id IS NULL"
    )
    if missing_photo:
        where += " AND COALESCE(s.kingdom, '') NOT IN ('archaea', 'bacteria', 'chromista', 'protozoa')"
    with db.connect(db_path) as conn:
        rows = list(conn.execute(f"""
            SELECT s.id, s.scientific_name, s.common_name_ja, s.photo_url,
                   COUNT(DISTINCT ps.park_id) AS park_count
            FROM species s
            LEFT JOIN park_species ps ON ps.species_id = s.id
            WHERE {where}
              AND (s.scientific_name IS NOT NULL OR s.common_name_ja IS NOT NULL)
            GROUP BY s.id
            ORDER BY park_count DESC, s.id
        """))
    if limit:
        rows = rows[:limit]
    mode = "photo_url" if missing_photo else "taxon_id"
    print(f"species needing {mode} lookup: {len(rows)}")

    fetched = cache_hits = matched = updated = 0
    with db.connect(db_path) as conn:
        for i, r in enumerate(rows, 1):
            sci = r["scientific_name"]
            ja = r["common_name_ja"]
            data = None
            # 1) try sci first
            if sci:
                data, did_fetch = lookup(sci, "en")
                fetched += int(did_fetch)
                cache_hits += int(not did_fetch)
                if did_fetch:
                    time.sleep(REQUEST_DELAY_SECONDS)
                if not (data and data.get("results")):
                    data, did_fetch = lookup(sci, "ja")
                    fetched += int(did_fetch)
                    cache_hits += int(not did_fetch)
                    if did_fetch:
                        time.sleep(REQUEST_DELAY_SECONDS)
            # 2) try ja name if still nothing
            if (not data or not data.get("results")) and ja:
                data, did_fetch = lookup(ja, "ja")
                fetched += int(did_fetch)
                cache_hits += int(not did_fetch)
                if did_fetch:
                    time.sleep(REQUEST_DELAY_SECONDS)
            m = best_match(data or {}, sci, ja)
            if not m:
                continue
            tid = m.get("id")
            photo = (m.get("default_photo") or {}).get("medium_url") if m.get("default_photo") else None
            conn.execute(
                "UPDATE species SET inat_taxon_id = COALESCE(inat_taxon_id, ?), "
                "photo_url = COALESCE(photo_url, ?) WHERE id=?",
                (tid, photo, r["id"]),
            )
            matched += 1
            updated += 1
            if i % 25 == 0:
                conn.commit()
                print(f"  [{i:>4}/{len(rows)}] fetched={fetched} cache={cache_hits} matched={matched}")
        conn.commit()
    print(f"\n=== ensure_inat_taxon done ===")
    print(f"  rows tried: {len(rows)}  fetched: {fetched}  cache: {cache_hits}  matched: {matched}  updated: {updated}")
    return 0


if __name__ == "__main__":
    missing_photo = "--missing-photo" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--missing-photo"]
    limit = int(args[0]) if args else None
    sys.exit(main(limit, missing_photo=missing_photo))
