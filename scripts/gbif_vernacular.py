"""Phase E2: GBIF vernacular-name enrichment.

For every species in the DB with a scientific_name, hit GBIF in two steps:
  1. species/match?name=<sci>  →  canonical usageKey
  2. species/<key>/vernacularNames?limit=200  →  all common names

Updates:
  - species.common_name_en : set when currently NULL and we have an English name
  - species.common_name_ja : set when currently NULL and we have a Japanese name
  - species_alias rows     : 'zh-Hans', 'zh-Hant', plus duplicates for verification

Both API responses are cached per scientific_name under
data/cache/gbif/vernacular/. Idempotent: skips species that already have all
target-language names populated.

Rate limit: 1 req/sec.
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
MATCH_API = "https://api.gbif.org/v1/species/match"
VERN_API = "https://api.gbif.org/v1/species/{key}/vernacularNames"
CACHE_DIR = ROOT / "data" / "cache" / "gbif" / "vernacular"

# GBIF returns ISO-639-3 codes; map them to our lang labels.
# zh-Hans / zh-Hant: GBIF often uses just 'zho'; we attempt to detect
# by character set (presence of Hant-only chars) when only 'zho' tag exists.
LANG_MAP = {
    "eng": "en",
    "jpn": "ja",
    "zho": "zh",  # split into zh-Hans / zh-Hant downstream
}


def safe_filename(sci_name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", sci_name)[:120]


def cache_path(sci_name: str) -> Path:
    return CACHE_DIR / f"{safe_filename(sci_name)}.json"


def fetch_match(sci_name: str) -> dict | None:
    """Resolve scientific name → GBIF usageKey via /species/match."""
    params = {"name": sci_name, "strict": "false"}
    r = requests.get(
        MATCH_API, params=params, headers={"User-Agent": UA},
        timeout=30, impersonate="chrome",
    )
    if r.status_code != 200:
        return None
    return r.json()


def fetch_vernaculars(usage_key: int) -> list[dict]:
    """Pull all vernacular names for a GBIF taxon."""
    url = VERN_API.format(key=usage_key)
    r = requests.get(
        url, params={"limit": 500},
        headers={"User-Agent": UA}, timeout=30, impersonate="chrome",
    )
    if r.status_code != 200:
        return []
    data = r.json()
    return data.get("results") or []


def is_traditional_chinese(text: str) -> bool:
    """Heuristic: text contains characters that exist in Hant but not in Hans
    (rough — not perfect; good enough for filtering common-name corpora)."""
    HANT_ONLY = "繁體萬個個鳥語雞嬰嶺鏡藥廣專點寶會勻來時對學園"
    return any(c in HANT_ONLY for c in text)


def fetch_for_species(sci_name: str) -> dict:
    """Return cached or freshly-fetched payload: {match, vernaculars}."""
    cp = cache_path(sci_name)
    cp.parent.mkdir(parents=True, exist_ok=True)
    if cp.exists():
        return json.loads(cp.read_text(encoding="utf-8"))

    payload = {"match": None, "vernaculars": []}
    match = fetch_match(sci_name)
    payload["match"] = match
    time.sleep(1.0)
    if match and match.get("usageKey"):
        payload["vernaculars"] = fetch_vernaculars(match["usageKey"])
        time.sleep(1.0)

    cp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return payload


def pick_best(names_in_lang: list[str]) -> str | None:
    """Choose a representative name when multiple exist for the same language."""
    if not names_in_lang:
        return None
    # Shorter is usually the canonical common name (vs. multi-word descriptions).
    return min(names_in_lang, key=lambda s: (len(s), s))


def categorize(vernaculars: list[dict]) -> dict[str, list[str]]:
    """Bucket vernacularNames into our lang labels (en, ja, zh-Hans, zh-Hant)."""
    out: dict[str, list[str]] = {"en": [], "ja": [], "zh-Hans": [], "zh-Hant": []}
    for v in vernaculars:
        name = (v.get("vernacularName") or "").strip()
        if not name:
            continue
        lang3 = (v.get("language") or "").lower()
        target = LANG_MAP.get(lang3)
        if not target:
            continue
        if target == "zh":
            target = "zh-Hant" if is_traditional_chinese(name) else "zh-Hans"
        out[target].append(name)
    return out


def main(limit: int | None = None) -> int:
    db_path = ROOT / "data" / "parklife.db"

    with db.connect(db_path) as conn:
        species = list(conn.execute(
            """SELECT id, scientific_name, common_name_ja, common_name_en
               FROM species
               WHERE scientific_name IS NOT NULL AND scientific_name <> ''
               ORDER BY id"""
        ))
    if limit:
        species = species[:limit]
    print(f"species to enrich (vernacular): {len(species)}")

    counts = {"en_set": 0, "ja_set": 0, "zh_alias": 0, "no_match": 0, "cache_hit": 0, "net": 0}

    with db.connect(db_path) as conn:
        for i, s in enumerate(species, 1):
            sci = s["scientific_name"]
            cp = cache_path(sci)
            was_cached = cp.exists()
            try:
                payload = fetch_for_species(sci)
            except Exception as e:
                print(f"  [{i}/{len(species)}] ERR {sci}: {e}")
                continue
            counts["cache_hit" if was_cached else "net"] += 1

            match = payload.get("match") or {}
            if not match.get("usageKey"):
                counts["no_match"] += 1
                continue

            vern_buckets = categorize(payload.get("vernaculars") or [])

            # Update species.common_name_en/ja if currently NULL
            best_en = pick_best(vern_buckets["en"])
            if best_en and not s["common_name_en"]:
                conn.execute("UPDATE species SET common_name_en=? WHERE id=?", (best_en, s["id"]))
                counts["en_set"] += 1
            best_ja = pick_best(vern_buckets["ja"])
            if best_ja and not s["common_name_ja"]:
                conn.execute("UPDATE species SET common_name_ja=? WHERE id=?", (best_ja, s["id"]))
                counts["ja_set"] += 1

            # Insert zh-Hans / zh-Hant aliases (one of each, if available)
            for lang in ("zh-Hans", "zh-Hant"):
                best_zh = pick_best(vern_buckets[lang])
                if best_zh:
                    conn.execute(
                        """INSERT OR IGNORE INTO species_alias
                           (species_id, raw_name, lang, status)
                           VALUES (?, ?, ?, 'resolved')""",
                        (s["id"], best_zh, lang),
                    )
                    counts["zh_alias"] += 1

            if i % 50 == 0:
                conn.commit()
                print(f"  [{i:>4}/{len(species)}] {sci[:40]:<40} "
                      f"en+={counts['en_set']} ja+={counts['ja_set']} "
                      f"zh+={counts['zh_alias']} cache={counts['cache_hit']} net={counts['net']}")
        conn.commit()

    print(f"\n=== GBIF vernacular pass done ===")
    print(f"  species processed: {len(species)}")
    print(f"  no-match: {counts['no_match']}")
    print(f"  cache hits: {counts['cache_hit']}  network calls: {counts['net']}")
    print(f"  common_name_en filled: {counts['en_set']}")
    print(f"  common_name_ja filled: {counts['ja_set']}")
    print(f"  zh-Hans/zh-Hant aliases inserted: {counts['zh_alias']}")
    return 0


if __name__ == "__main__":
    cap = int(sys.argv[1]) if len(sys.argv) > 1 else None
    sys.exit(main(limit=cap))
