"""Phase E3: Wikipedia langlinks → Chinese vernacular names.

For each species with common_name_ja (preferred) or scientific_name, query
ja.wikipedia.org's API for langlinks to zh.wikipedia. Fall back to
en.wikipedia for species missing on ja. Hans/Hant detected by char-set
heuristic; stored as species_alias rows lang='zh-Hans' or 'zh-Hant'.

Batches up to 50 titles per request (Wikipedia API cap). Politeness 1
req/sec between batches. Cached per (wiki, title) under
data/cache/wikipedia_zh/<wiki>/.
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
CACHE_DIR = ROOT / "data" / "cache" / "wikipedia_zh"
BATCH = 50


def safe_filename(title: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", title)[:120]


def cache_path(wiki: str, title: str) -> Path:
    return CACHE_DIR / wiki / f"{safe_filename(title)}.json"


def is_traditional_chinese(text: str) -> bool:
    """Loose Hant detector: presence of any Hant-only character."""
    HANT_ONLY = (
        "繁體萬個個鳥語雞嬰嶺鏡藥廣專點寶會勻來時對學園"
        "為國體點選擇變對於關於開頭設計總計龍門開歷"
        "區傳實業樣標準買賣賣處態應隨"
    )
    return any(c in HANT_ONLY for c in text)


def fetch_batch(wiki: str, titles: list[str]) -> dict[str, str | None]:
    """Return {title: zh_title or None} for a batch of (uncached) titles."""
    if not titles:
        return {}
    api = f"https://{wiki}.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "prop": "langlinks",
        "lllang": "zh",
        "titles": "|".join(titles),
        "format": "json",
        "redirects": 1,
        "lllimit": 1,
    }
    try:
        r = requests.get(api, params=params, headers={"User-Agent": UA},
                         timeout=30, impersonate="chrome")
    except Exception as e:
        print(f"  net err {wiki}: {type(e).__name__}: {e}")
        return {t: None for t in titles}
    if r.status_code != 200:
        return {t: None for t in titles}
    try:
        data = r.json()
    except Exception:
        return {t: None for t in titles}
    pages = (data.get("query") or {}).get("pages") or {}
    # Build a normalized title → zh map.
    out: dict[str, str | None] = {t: None for t in titles}
    # Wikipedia normalizes some titles; track redirects + normalizations.
    aliases: dict[str, str] = {}
    for nrm in (data.get("query") or {}).get("normalized") or []:
        aliases[nrm["from"]] = nrm["to"]
    for redir in (data.get("query") or {}).get("redirects") or []:
        aliases[redir["from"]] = redir["to"]

    title_to_zh: dict[str, str | None] = {}
    for _, p in pages.items():
        if "missing" in p:
            continue
        zh = None
        for ll in p.get("langlinks") or []:
            if ll.get("lang") == "zh":
                zh = ll.get("*") or None
                break
        title_to_zh[p.get("title")] = zh

    for t in titles:
        # walk redirect chain to resolved title
        cur = t
        seen = set()
        while cur in aliases and cur not in seen:
            seen.add(cur)
            cur = aliases[cur]
        out[t] = title_to_zh.get(cur)
    return out


def lookup(wiki: str, titles: list[str]) -> dict[str, str | None]:
    """Cache-aware batch lookup. Returns {title: zh_title or None}."""
    out: dict[str, str | None] = {}
    uncached: list[str] = []
    for t in titles:
        cp = cache_path(wiki, t)
        if cp.exists():
            try:
                out[t] = json.loads(cp.read_text(encoding="utf-8")).get("zh")
            except Exception:
                uncached.append(t)
        else:
            uncached.append(t)

    if uncached:
        cp_dir = CACHE_DIR / wiki
        cp_dir.mkdir(parents=True, exist_ok=True)
        for i in range(0, len(uncached), BATCH):
            chunk = uncached[i:i+BATCH]
            res = fetch_batch(wiki, chunk)
            for t, zh in res.items():
                cache_path(wiki, t).write_text(
                    json.dumps({"zh": zh}, ensure_ascii=False), encoding="utf-8")
                out[t] = zh
            time.sleep(1.0)
    return out


def main(limit: int | None = None) -> int:
    db_path = ROOT / "data" / "parklife.db"
    with db.connect(db_path) as conn:
        species = list(conn.execute("""
            SELECT id, scientific_name, common_name_ja
            FROM species
            WHERE (common_name_ja IS NOT NULL AND common_name_ja <> '')
               OR (scientific_name IS NOT NULL AND scientific_name <> '')
            ORDER BY id
        """))
        # Skip species that already have a zh alias.
        existing_zh_ids = {r["species_id"] for r in conn.execute(
            "SELECT DISTINCT species_id FROM species_alias WHERE lang LIKE 'zh%'")}
    species = [s for s in species if s["id"] not in existing_zh_ids]
    if limit:
        species = species[:limit]
    print(f"species needing zh lookup: {len(species)}")

    # Pass 1: ja.wikipedia using common_name_ja
    ja_titles_to_sids: dict[str, list[int]] = {}
    fallback: list[dict] = []
    for s in species:
        if s["common_name_ja"]:
            ja_titles_to_sids.setdefault(s["common_name_ja"], []).append(s["id"])
        else:
            fallback.append(s)

    print(f"pass 1 (ja.wiki): {len(ja_titles_to_sids)} unique titles")
    ja_titles = list(ja_titles_to_sids.keys())
    ja_results = lookup("ja", ja_titles)

    # Whatever didn't resolve via ja, retry on en.wiki using scientific_name
    unresolved_ids: set[int] = set()
    for t, sids in ja_titles_to_sids.items():
        if not ja_results.get(t):
            unresolved_ids.update(sids)

    sci_titles_to_sids: dict[str, list[int]] = {}
    for s in species:
        if s["id"] in unresolved_ids or s in fallback:
            if s["scientific_name"]:
                sci_titles_to_sids.setdefault(s["scientific_name"], []).append(s["id"])
    print(f"pass 2 (en.wiki by sci): {len(sci_titles_to_sids)} unique titles")
    en_results = lookup("en", list(sci_titles_to_sids.keys()))

    # Insert aliases
    inserted_hans = inserted_hant = 0
    with db.connect(db_path) as conn:
        for t, sids in ja_titles_to_sids.items():
            zh = ja_results.get(t)
            if not zh:
                continue
            lang = "zh-Hant" if is_traditional_chinese(zh) else "zh-Hans"
            for sid in sids:
                cur = conn.execute(
                    """INSERT OR IGNORE INTO species_alias (species_id, raw_name, lang, status)
                       VALUES (?, ?, ?, 'resolved')""",
                    (sid, zh, lang),
                )
                if cur.rowcount:
                    if lang == "zh-Hant":
                        inserted_hant += 1
                    else:
                        inserted_hans += 1
        for t, sids in sci_titles_to_sids.items():
            zh = en_results.get(t)
            if not zh:
                continue
            lang = "zh-Hant" if is_traditional_chinese(zh) else "zh-Hans"
            for sid in sids:
                cur = conn.execute(
                    """INSERT OR IGNORE INTO species_alias (species_id, raw_name, lang, status)
                       VALUES (?, ?, ?, 'resolved')""",
                    (sid, zh, lang),
                )
                if cur.rowcount:
                    if lang == "zh-Hant":
                        inserted_hant += 1
                    else:
                        inserted_hans += 1
        conn.commit()

    print(f"\n=== Wikipedia zh pass done ===")
    print(f"  ja.wiki hits: {sum(1 for v in ja_results.values() if v)}/{len(ja_results)}")
    print(f"  en.wiki hits: {sum(1 for v in en_results.values() if v)}/{len(en_results)}")
    print(f"  zh-Hans aliases inserted: {inserted_hans}")
    print(f"  zh-Hant aliases inserted: {inserted_hant}")
    return 0


if __name__ == "__main__":
    cap = int(sys.argv[1]) if len(sys.argv) > 1 else None
    sys.exit(main(limit=cap))
