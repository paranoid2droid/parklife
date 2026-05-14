"""Direct zh.wikipedia lookup by scientific name (and ja common name).

The earlier wikipedia_zh.py walks langlinks ja/en → zh, which depends on
ja/en having the article and a langlink. Many zh.wiki articles redirect
from the Latin binomial directly to the Chinese page; this script exploits
that.

Strategy per missing-zh species:
  1. Query zh.wiki for scientific_name with redirects=1.
  2. If the resolved title contains Han characters and is *not* the same
     as the input, store it as zh-Hans (or zh-Hant if char-set says so).
  3. Optionally fall back to common_name_ja as a title (ja kanji often
     resolves on zh.wiki).

Cached under data/cache/wikipedia_zh_direct/<safe-title>.json
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
CACHE_DIR = ROOT / "data" / "cache" / "wikipedia_zh_direct"
API = "https://zh.wikipedia.org/w/api.php"
BATCH = 50

HAN_RE = re.compile(r"[一-鿿]")


def safe_filename(title: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", title)[:120]


def cache_path(title: str) -> Path:
    return CACHE_DIR / f"{safe_filename(title)}.json"


def is_traditional_chinese(text: str) -> bool:
    HANT_ONLY = ("繁體萬個個鳥語雞嬰嶺鏡藥廣專點寶會勻來時對學園"
                 "為國體點選擇變對於關於開頭設計總計龍門開歷"
                 "區傳實業樣標準買賣賣處態應隨")
    return any(c in HANT_ONLY for c in text)


def fetch_batch(titles: list[str]) -> dict[str, str | None]:
    """Map input title → resolved zh.wiki title (after redirects+normalization)
    if the page exists, else None.
    """
    if not titles:
        return {}
    params = {
        "action": "query",
        "titles": "|".join(titles),
        "format": "json",
        "redirects": 1,
    }
    try:
        r = requests.get(API, params=params,
                         headers={"User-Agent": UA},
                         timeout=30, impersonate="chrome")
    except Exception as e:
        print(f"  net err: {type(e).__name__}: {e}")
        return {t: None for t in titles}
    if r.status_code != 200:
        return {t: None for t in titles}
    try:
        data = r.json()
    except Exception:
        return {t: None for t in titles}
    q = data.get("query") or {}
    aliases: dict[str, str] = {}
    for nrm in q.get("normalized") or []:
        aliases[nrm["from"]] = nrm["to"]
    for red in q.get("redirects") or []:
        aliases[red["from"]] = red["to"]
    # Resolve transitive aliases (normalized → redirected).
    def resolve(t: str) -> str:
        seen = set()
        while t in aliases and t not in seen:
            seen.add(t)
            t = aliases[t]
        return t

    page_titles: dict[str, dict] = {}
    for _, page in (q.get("pages") or {}).items():
        page_titles[page.get("title", "")] = page

    out: dict[str, str | None] = {}
    for t in titles:
        resolved = resolve(t)
        page = page_titles.get(resolved)
        if not page or "missing" in page:
            out[t] = None
            continue
        out[t] = resolved
    return out


def lookup(titles: list[str]) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    uncached: list[str] = []
    for t in titles:
        cp = cache_path(t)
        if cp.exists():
            try:
                out[t] = json.loads(cp.read_text(encoding="utf-8"))
            except Exception:
                uncached.append(t)
        else:
            uncached.append(t)

    if uncached:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        for i in range(0, len(uncached), BATCH):
            chunk = uncached[i:i+BATCH]
            res = fetch_batch(chunk)
            for t in chunk:
                cache_path(t).write_text(json.dumps(res.get(t), ensure_ascii=False),
                                          encoding="utf-8")
                out[t] = res.get(t)
            if (i // BATCH) % 5 == 0:
                done = min(i + BATCH, len(uncached))
                hits = sum(1 for v in out.values() if v)
                print(f"  batch {i//BATCH+1}: {done}/{len(uncached)} fetched, "
                      f"resolved so far: {hits}")
            time.sleep(1.0)
    return out


def looks_like_chinese_name(t: str | None, input_title: str) -> bool:
    """Treat as a real Chinese name only if it contains Han characters AND
    differs from the input (so we don't insert the input binomial back)."""
    if not t:
        return False
    if t == input_title:
        return False
    if not HAN_RE.search(t):
        return False
    # Guard against ja-kana-only titles when input was ja: require at least 2 Han chars.
    if len(HAN_RE.findall(t)) < 2:
        return False
    return True


def main(limit: int | None = None) -> int:
    db_path = ROOT / "data" / "parklife.db"
    with db.connect(db_path) as conn:
        species = list(conn.execute("""
            SELECT s.id, s.scientific_name, s.common_name_ja FROM species s
            WHERE NOT EXISTS (
                SELECT 1 FROM species_alias a
                WHERE a.species_id = s.id AND a.lang LIKE 'zh%'
            )
            ORDER BY s.id
        """))
    if limit:
        species = species[:limit]
    print(f"species missing zh alias: {len(species)}")

    # Title attempts per species: scientific_name first, then ja common name.
    by_title: dict[str, list[int]] = {}
    title_kind: dict[str, str] = {}
    for s in species:
        sci = (s["scientific_name"] or "").strip()
        ja = (s["common_name_ja"] or "").strip()
        if sci and sci not in by_title:
            by_title.setdefault(sci, []).append(s["id"])
            title_kind[sci] = "sci"
        elif sci:
            by_title[sci].append(s["id"])
        if ja and ja not in by_title:
            by_title.setdefault(ja, []).append(s["id"])
            title_kind[ja] = "ja"
        elif ja:
            by_title[ja].append(s["id"])

    titles = sorted(by_title.keys())
    print(f"unique titles to query: {len(titles)}")
    resolved = lookup(titles)

    # Pick best resolution per species: prefer the resolution from its scientific name.
    sp_resolved: dict[int, str] = {}
    for s in species:
        sci = (s["scientific_name"] or "").strip()
        ja = (s["common_name_ja"] or "").strip()
        for t in (sci, ja):
            if not t:
                continue
            r = resolved.get(t)
            if looks_like_chinese_name(r, t):
                sp_resolved[s["id"]] = r
                break

    inserted_hans = inserted_hant = 0
    skipped_existing = 0
    with db.connect(db_path) as conn:
        for sp_id, name in sp_resolved.items():
            lang = "zh-Hant" if is_traditional_chinese(name) else "zh-Hans"
            cur = conn.execute(
                """INSERT OR IGNORE INTO species_alias
                   (species_id, raw_name, lang, status)
                   VALUES (?, ?, ?, 'resolved')""",
                (sp_id, name, lang),
            )
            if cur.rowcount:
                if lang == "zh-Hans":
                    inserted_hans += 1
                else:
                    inserted_hant += 1
            else:
                skipped_existing += 1
        conn.commit()

    hits = sum(1 for v in resolved.values() if v)
    print(f"\n=== zh.wikipedia direct pass done ===")
    print(f"  titles resolved on zh.wiki: {hits}/{len(titles)} "
          f"({100*hits/max(1,len(titles)):.1f}%)")
    print(f"  species with new zh name:   {len(sp_resolved)}/{len(species)}")
    print(f"  zh-Hans aliases inserted:   {inserted_hans}")
    print(f"  zh-Hant aliases inserted:   {inserted_hant}")
    print(f"  skipped (already existed):  {skipped_existing}")
    return 0


if __name__ == "__main__":
    cap = int(sys.argv[1]) if len(sys.argv) > 1 else None
    sys.exit(main(limit=cap))
