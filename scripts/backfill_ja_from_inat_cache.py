"""Backfill missing Japanese common names from cached iNaturalist responses.

Several enrichment passes created species from scientific names, then later
photo/taxon-id passes cached iNaturalist taxon payloads. Those cached taxon
objects often include Japanese `preferred_common_name` because the original
species-count requests used `locale=ja`, but older species rows may still have
`common_name_ja` as NULL.

This script is offline-only: it reads data/cache/inat* JSON files, matches by
taxon scientific name (and taxon id when available), and fills only missing
species.common_name_ja values. It also inserts a Japanese alias for search.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from parklife import db

ROOT = Path(__file__).resolve().parent.parent
CACHE_ROOT = ROOT / "data" / "cache"

# Good enough for rejecting English common names from non-ja iNat caches.
JP_RE = re.compile(r"[ぁ-んァ-ヶ一-龯々ー]")


def looks_japanese(name: str | None) -> bool:
    if not name:
        return False
    name = name.strip()
    if not name:
        return False
    # Reject plain Latin labels such as "White Wagtail".
    return bool(JP_RE.search(name))


def walk_taxa(obj: Any):
    """Yield taxon-ish dicts from iNat response shapes."""
    if isinstance(obj, dict):
        if obj.get("name") and (obj.get("preferred_common_name") or obj.get("matched_term")):
            yield obj
        taxon = obj.get("taxon")
        if isinstance(taxon, dict):
            yield taxon
        for v in obj.values():
            if isinstance(v, (dict, list)):
                yield from walk_taxa(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from walk_taxa(item)


def collect_candidates() -> tuple[dict[str, str], dict[int, str]]:
    by_sci: dict[str, Counter[str]] = defaultdict(Counter)
    by_tid: dict[int, Counter[str]] = defaultdict(Counter)

    cache_dirs = [
        CACHE_ROOT / "inat",
        CACHE_ROOT / "inat_monthly",
        CACHE_ROOT / "inat_captive",
        CACHE_ROOT / "inat_taxa",
    ]
    files = []
    for d in cache_dirs:
        if d.exists():
            files.extend(d.glob("*.json"))

    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for taxon in walk_taxa(data):
            sci = (taxon.get("name") or "").strip()
            ja = (taxon.get("preferred_common_name") or taxon.get("matched_term") or "").strip()
            tid = taxon.get("id")
            if not sci or not looks_japanese(ja):
                continue
            by_sci[sci][ja] += 1
            if isinstance(tid, int):
                by_tid[tid][ja] += 1

    def pick(counter: Counter[str]) -> str:
        # Most frequent across park caches wins; shorter breaks ties.
        return sorted(counter.items(), key=lambda kv: (-kv[1], len(kv[0]), kv[0]))[0][0]

    return (
        {sci: pick(c) for sci, c in by_sci.items()},
        {tid: pick(c) for tid, c in by_tid.items()},
    )


def main() -> int:
    by_sci, by_tid = collect_candidates()
    print(f"cached Japanese names: by_sci={len(by_sci)} by_taxon_id={len(by_tid)}")

    db_path = ROOT / "data" / "parklife.db"
    updated = alias_inserted = 0
    examples: list[tuple[str, str, str]] = []
    with db.connect(db_path) as conn:
        rows = list(conn.execute("""
            SELECT id, scientific_name, common_name_ja, common_name_en, inat_taxon_id
            FROM species
            WHERE common_name_ja IS NULL OR common_name_ja = ''
            ORDER BY id
        """))
        for r in rows:
            ja = None
            if r["inat_taxon_id"] is not None:
                ja = by_tid.get(r["inat_taxon_id"])
            if not ja and r["scientific_name"]:
                ja = by_sci.get(r["scientific_name"])
            if not ja:
                continue
            conn.execute("UPDATE species SET common_name_ja=? WHERE id=?", (ja, r["id"]))
            cur = conn.execute(
                """INSERT OR IGNORE INTO species_alias
                   (species_id, raw_name, lang, status)
                   VALUES (?, ?, 'ja', 'resolved')""",
                (r["id"], ja),
            )
            alias_inserted += cur.rowcount
            updated += 1
            if len(examples) < 20:
                examples.append((r["scientific_name"] or "", r["common_name_en"] or "", ja))
        conn.commit()

    print(f"species.common_name_ja filled: {updated}")
    print(f"ja aliases inserted: {alias_inserted}")
    if examples:
        print("examples:")
        for sci, en, ja in examples:
            print(f"  {sci:<36} {en:<32} -> {ja}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
