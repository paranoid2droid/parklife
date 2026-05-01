"""Phase E4: Wikidata SPARQL → Chinese vernacular labels.

For each species with scientific_name, query Wikidata via SPARQL
(P225 = taxon name) and pull labels in zh, zh-Hans, zh-Hant, zh-CN,
zh-TW, zh-HK. Insert as species_alias rows lang='zh-Hans' / 'zh-Hant'.

Wikidata is much denser than Wikipedia for taxonomic data — every
recognised binomial typically has a Q item with multilingual labels.

Batches 80 binomials per SPARQL query (VALUES list). Politeness 1
req/sec. Cache: data/cache/wikidata_zh/<safe-name>.json
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
ENDPOINT = "https://query.wikidata.org/sparql"
CACHE_DIR = ROOT / "data" / "cache" / "wikidata_zh"
BATCH = 80

# Wikidata variants we care about; map to our (lang_label, is_traditional) pair.
# Order matters — earlier entries have priority when multiple variants present.
VARIANT_PRIORITY = [
    ("zh-cn", "zh-Hans"),
    ("zh-hans", "zh-Hans"),
    ("zh", "zh-Hans"),  # default zh is usually Hans on Wikidata
    ("zh-hk", "zh-Hant"),
    ("zh-tw", "zh-Hant"),
    ("zh-hant", "zh-Hant"),
]


def safe_filename(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", s)[:120]


def cache_path(sci: str) -> Path:
    return CACHE_DIR / f"{safe_filename(sci)}.json"


def is_traditional_chinese(text: str) -> bool:
    HANT_ONLY = ("繁體萬個個鳥語雞嬰嶺鏡藥廣專點寶會勻來時對學園"
                 "為國體點選擇變對於關於開頭設計總計龍門開歷"
                 "區傳實業樣標準買賣賣處態應隨")
    return any(c in HANT_ONLY for c in text)


def build_query(binomials: list[str]) -> str:
    values = " ".join(f'"{b}"' for b in binomials if '"' not in b)
    # one OPTIONAL per variant we care about
    optionals = "\n".join(
        f'  OPTIONAL {{ ?taxon rdfs:label ?lab_{i} FILTER(LANG(?lab_{i})="{v}") }}'
        for i, (v, _) in enumerate(VARIANT_PRIORITY)
    )
    select_vars = " ".join(f"?lab_{i}" for i in range(len(VARIANT_PRIORITY)))
    return f"""
SELECT ?name {select_vars} WHERE {{
  VALUES ?name {{ {values} }}
  ?taxon wdt:P225 ?name.
{optionals}
}}
"""


def fetch_batch(binomials: list[str]) -> dict[str, dict[str, str]]:
    """Return {binomial: {variant: label, ...}} for any matched."""
    if not binomials:
        return {}
    q = build_query(binomials)
    try:
        r = requests.get(
            ENDPOINT,
            params={"query": q, "format": "json"},
            headers={"User-Agent": UA, "Accept": "application/sparql-results+json"},
            timeout=60,
            impersonate="chrome",
        )
    except Exception as e:
        print(f"  net err: {type(e).__name__}: {e}")
        return {}
    if r.status_code != 200:
        print(f"  HTTP {r.status_code}: {r.text[:200]}")
        return {}
    try:
        data = r.json()
    except Exception:
        return {}
    out: dict[str, dict[str, str]] = {}
    for row in data.get("results", {}).get("bindings", []):
        name = row.get("name", {}).get("value")
        if not name:
            continue
        bag = out.setdefault(name, {})
        for i, (variant, _) in enumerate(VARIANT_PRIORITY):
            v = row.get(f"lab_{i}", {}).get("value")
            if v and variant not in bag:
                bag[variant] = v
    return out


def lookup(binomials: list[str]) -> dict[str, dict[str, str]]:
    """Cache-aware. Returns {binomial: {variant: label}} (may be empty for misses)."""
    out: dict[str, dict[str, str]] = {}
    uncached: list[str] = []
    for b in binomials:
        cp = cache_path(b)
        if cp.exists():
            try:
                out[b] = json.loads(cp.read_text(encoding="utf-8"))
            except Exception:
                uncached.append(b)
        else:
            uncached.append(b)

    if uncached:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        for i in range(0, len(uncached), BATCH):
            chunk = uncached[i:i+BATCH]
            res = fetch_batch(chunk)
            for b in chunk:
                got = res.get(b, {})
                cache_path(b).write_text(json.dumps(got, ensure_ascii=False),
                                          encoding="utf-8")
                out[b] = got
            if (i // BATCH) % 10 == 0:
                done = min(i + BATCH, len(uncached))
                hits = sum(1 for v in out.values() if v)
                print(f"  batch {i//BATCH+1}: {done}/{len(uncached)} fetched, "
                      f"hits so far: {hits}")
            time.sleep(1.0)
    return out


def main(limit: int | None = None) -> int:
    db_path = ROOT / "data" / "parklife.db"
    with db.connect(db_path) as conn:
        species = list(conn.execute("""
            SELECT id, scientific_name, common_name_ja FROM species
            WHERE scientific_name IS NOT NULL AND scientific_name <> ''
            ORDER BY id
        """))
    if limit:
        species = species[:limit]
    print(f"species to query: {len(species)}")

    # Resolve via scientific_name (Wikidata's canonical taxon-name property)
    binomials = sorted({s["scientific_name"] for s in species})
    print(f"unique binomials: {len(binomials)}")
    results = lookup(binomials)

    # Pick best label per variant per species
    inserted_hans = inserted_hant = 0
    skipped_existing = 0
    with db.connect(db_path) as conn:
        for s in species:
            bag = results.get(s["scientific_name"]) or {}
            if not bag:
                continue
            picked_hans: str | None = None
            picked_hant: str | None = None
            for variant, lang_label in VARIANT_PRIORITY:
                v = bag.get(variant)
                if not v:
                    continue
                # Refine using char-set heuristic when label disagrees with variant tag
                detected = "zh-Hant" if is_traditional_chinese(v) else "zh-Hans"
                target = detected
                if target == "zh-Hans" and picked_hans is None:
                    picked_hans = v
                elif target == "zh-Hant" and picked_hant is None:
                    picked_hant = v

            for label, lang in ((picked_hans, "zh-Hans"), (picked_hant, "zh-Hant")):
                if not label:
                    continue
                cur = conn.execute(
                    """INSERT OR IGNORE INTO species_alias
                       (species_id, raw_name, lang, status)
                       VALUES (?, ?, ?, 'resolved')""",
                    (s["id"], label, lang),
                )
                if cur.rowcount:
                    if lang == "zh-Hans":
                        inserted_hans += 1
                    else:
                        inserted_hant += 1
                else:
                    skipped_existing += 1
        conn.commit()

    hits = sum(1 for v in results.values() if v)
    print(f"\n=== Wikidata zh pass done ===")
    print(f"  binomials with any zh label: {hits}/{len(binomials)} "
          f"({100*hits/max(1,len(binomials)):.1f}%)")
    print(f"  zh-Hans aliases inserted: {inserted_hans}")
    print(f"  zh-Hant aliases inserted: {inserted_hant}")
    print(f"  skipped (already existed): {skipped_existing}")
    return 0


if __name__ == "__main__":
    cap = int(sys.argv[1]) if len(sys.argv) > 1 else None
    sys.exit(main(limit=cap))
