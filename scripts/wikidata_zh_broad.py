"""Broader Wikidata zh backfill: P1843 (vernacular) + skos:altLabel + rdfs:label.

Targets species that still lack zh-Hans/zh-Hant aliases after scripts.wikidata_zh.
The original script queried only rdfs:label in 6 zh variants; this one adds:

  - wdt:P1843 (taxon common name, language-tagged literal) — often filled when
    rdfs:label is not.
  - skos:altLabel@zh* — Wikidata also-known-as labels.

Cache lives under data/cache/wikidata_zh_broad/ so the previous pass's cache
(7k+ files) is untouched.
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
CACHE_DIR = ROOT / "data" / "cache" / "wikidata_zh_broad"
BATCH = 60

ZH_LANGS = ["zh", "zh-cn", "zh-hans", "zh-hk", "zh-tw", "zh-hant"]


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
    lang_filter = ", ".join(f'"{l}"' for l in ZH_LANGS)
    return f"""
SELECT ?name ?label ?alt ?vname WHERE {{
  VALUES ?name {{ {values} }}
  ?taxon wdt:P225 ?name.
  OPTIONAL {{ ?taxon rdfs:label ?label   FILTER(LANG(?label)   IN ({lang_filter})) }}
  OPTIONAL {{ ?taxon skos:altLabel ?alt  FILTER(LANG(?alt)     IN ({lang_filter})) }}
  OPTIONAL {{ ?taxon wdt:P1843 ?vname    FILTER(LANG(?vname)   IN ({lang_filter})) }}
}}
"""


def fetch_batch(binomials: list[str]) -> dict[str, list[tuple[str, str]]]:
    """Return {binomial: [(lang, value), ...]} for any matched."""
    if not binomials:
        return {}
    q = build_query(binomials)
    try:
        r = requests.get(
            ENDPOINT,
            params={"query": q, "format": "json"},
            headers={"User-Agent": UA, "Accept": "application/sparql-results+json"},
            timeout=90,
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
    out: dict[str, list[tuple[str, str]]] = {}
    for row in data.get("results", {}).get("bindings", []):
        name = row.get("name", {}).get("value")
        if not name:
            continue
        bag = out.setdefault(name, [])
        for key in ("label", "alt", "vname"):
            cell = row.get(key)
            if cell and cell.get("value"):
                lang = cell.get("xml:lang", "")
                bag.append((lang, cell["value"]))
    return out


def lookup(binomials: list[str]) -> dict[str, list[tuple[str, str]]]:
    out: dict[str, list[tuple[str, str]]] = {}
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
                got = res.get(b, [])
                cache_path(b).write_text(json.dumps(got, ensure_ascii=False),
                                          encoding="utf-8")
                out[b] = got
            if (i // BATCH) % 5 == 0:
                done = min(i + BATCH, len(uncached))
                hits = sum(1 for v in out.values() if v)
                print(f"  batch {i//BATCH+1}: {done}/{len(uncached)} fetched, "
                      f"hits so far: {hits}")
            time.sleep(1.0)
    return out


def pick_label(pairs: list[tuple[str, str]]) -> tuple[str | None, str | None]:
    """Pick best (Hans, Hant) labels from the (lang, value) list."""
    hans = hant = None
    # Priority order: explicit Hans-ish first, then Hant-ish.
    HANS_PREF = ("zh-cn", "zh-hans", "zh")
    HANT_PREF = ("zh-hk", "zh-tw", "zh-hant")
    by_lang: dict[str, list[str]] = {}
    for lang, val in pairs:
        by_lang.setdefault(lang.lower(), []).append(val)
    for tag in HANS_PREF:
        if tag in by_lang and hans is None:
            for v in by_lang[tag]:
                if not is_traditional_chinese(v):
                    hans = v
                    break
    for tag in HANT_PREF:
        if tag in by_lang and hant is None:
            for v in by_lang[tag]:
                if is_traditional_chinese(v):
                    hant = v
                    break
    # Fallback: scan all values by char-set if still missing.
    if hans is None or hant is None:
        for lang, val in pairs:
            if is_traditional_chinese(val):
                if hant is None:
                    hant = val
            else:
                if hans is None:
                    hans = val
    return hans, hant


def main(limit: int | None = None) -> int:
    db_path = ROOT / "data" / "parklife.db"
    with db.connect(db_path) as conn:
        species = list(conn.execute("""
            SELECT s.id, s.scientific_name, s.common_name_ja FROM species s
            WHERE s.scientific_name IS NOT NULL AND s.scientific_name <> ''
              AND NOT EXISTS (
                SELECT 1 FROM species_alias a
                WHERE a.species_id = s.id AND a.lang LIKE 'zh%'
              )
            ORDER BY s.id
        """))
    if limit:
        species = species[:limit]
    print(f"species missing zh alias (queryable): {len(species)}")

    binomials = sorted({s["scientific_name"] for s in species})
    print(f"unique binomials to query: {len(binomials)}")
    results = lookup(binomials)

    inserted_hans = inserted_hant = 0
    skipped_existing = 0
    with db.connect(db_path) as conn:
        for s in species:
            pairs = results.get(s["scientific_name"]) or []
            if not pairs:
                continue
            hans, hant = pick_label(pairs)
            for label, lang in ((hans, "zh-Hans"), (hant, "zh-Hant")):
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
    print(f"\n=== Wikidata broad zh pass done ===")
    print(f"  binomials with any zh result: {hits}/{len(binomials)} "
          f"({100*hits/max(1,len(binomials)):.1f}%)")
    print(f"  zh-Hans aliases inserted: {inserted_hans}")
    print(f"  zh-Hant aliases inserted: {inserted_hant}")
    print(f"  skipped (already existed): {skipped_existing}")
    return 0


if __name__ == "__main__":
    cap = int(sys.argv[1]) if len(sys.argv) > 1 else None
    sys.exit(main(limit=cap))
