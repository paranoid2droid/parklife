"""Second-pass official_url backfill for P13 parks.

Strategy: fetch a curated list of "park index" pages — prefecture park-
association sites (option A from HANDOFF TODO #1) plus the municipalities
with the largest residual P13 gaps (option B). From each index, harvest
`<a href>` anchors whose text contains 公園 / 緑地 / 霊園 / 庭園, and
build a normalized-name → URL lookup. Match residual parks by exact
name, then by stripped/normalized substring.

Per-page HTML cached under data/cache/association_park_url/.
Polite: 1.5 s sleep between fetches.
"""
from __future__ import annotations

import json
import re
import sys
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

from curl_cffi import requests

from parklife import db

ROOT = Path(__file__).resolve().parent.parent
UA = "parklife-bot/0.1 (research; contact: paranoid2droid@gmail.com)"
CACHE = ROOT / "data" / "cache" / "association_park_url"
SLEEP_S = 1.5

# (prefecture filter or None, label, url). Prefecture filter limits matching to
# parks in that prefecture — important because e.g. tokyo-park.or.jp shouldn't
# accidentally claim a Chiba park.
SOURCES: list[tuple[str | None, str, str]] = [
    # Option A: prefecture park-association indexes
    ("tokyo", "tokyo-park.or.jp", "https://www.tokyo-park.or.jp/park_list/index.html"),
    ("tokyo", "tmpa.or.jp", "https://www.tmpa.or.jp/park/"),
    ("kanagawa", "kanagawa-park.or.jp", "https://www.kanagawa-park.or.jp/parklist/"),
    ("chiba", "cga-net.jp", "https://www.cga-net.jp/?page_id=11"),
    ("saitama", "parks.or.jp", "https://www.parks.or.jp/parks/"),

    # Option B: top municipalities (>= ~3 residuals)
    ("chiba", "city.chiba.jp", "https://www.city.chiba.jp/toshi/koenryokuchi/kanri/index.html"),
    ("chiba", "city.chiba.jp/chuo-mihama", "https://www.city.chiba.jp/toshi/koenryokuchi/kanri/chuo-mihama/index.html"),
    ("chiba", "city.chiba.jp/hanamigawa-inage", "https://www.city.chiba.jp/toshi/koenryokuchi/kanri/hanamigawa-inage/index.html"),
    ("chiba", "city.chiba.jp/wakaba", "https://www.city.chiba.jp/toshi/koenryokuchi/kanri/wakaba/index.html"),
    ("chiba", "city.chiba.jp/midori", "https://www.city.chiba.jp/toshi/koenryokuchi/kanri/midori/index.html"),
    ("saitama", "city.saitama.jp", "https://www.city.saitama.jp/004/006/003/003/index.html"),
    ("tokyo", "city.hachioji.tokyo.jp", "https://www.city.hachioji.tokyo.jp/shisetsu/109/index.html"),
    ("kanagawa", "city.yokohama.lg.jp", "https://www.city.yokohama.lg.jp/kurashi/machizukuri-kankyo/midori-koen/midori/park-jouhou/index.html"),
    ("kanagawa", "city.atsugi.kanagawa.jp", "https://www.city.atsugi.kanagawa.jp/shisei/shoukai/shisetsu/koen/index.html"),
    ("saitama", "city.kumagaya.lg.jp", "https://www.city.kumagaya.lg.jp/kurashi/machi/koen/index.html"),
    ("tokyo", "city.ota.tokyo.jp", "https://www.city.ota.tokyo.jp/seikatsu/midori_park/park/index.html"),
    ("kanagawa", "city.kawasaki.jp", "https://www.city.kawasaki.jp/shisetsu/category/30-18-0-0-0-0-0-0-0-0.html"),
    ("kanagawa", "city.yokosuka.kanagawa.jp", "https://www.city.yokosuka.kanagawa.jp/4130/index.html"),
    ("kanagawa", "city.sagamihara.kanagawa.jp", "https://www.city.sagamihara.kanagawa.jp/shisetsu/kouen_kankou/index.html"),
    ("kanagawa", "city.kamakura.kanagawa.jp", "https://www.city.kamakura.kanagawa.jp/koen/index.html"),
    ("tokyo", "city.edogawa.tokyo.jp", "https://www.city.edogawa.tokyo.jp/shisetsuguide/bunya/koendobutsuen/index.html"),
    ("chiba", "city.ichikawa.lg.jp", "https://www.city.ichikawa.lg.jp/pla05/1111000004.html"),
]

# 凡そ noise we want to drop from anchor text matches
NOISE_TERMS = (
    "公園・", "霊園・", "公園緑地", "公園事業", "公園のご利用",
    "公園に関する", "公園 ", "公園で", "公園の",
)


class AnchorParser(HTMLParser):
    def __init__(self, base: str):
        super().__init__()
        self.base = base
        self.cur_href: str | None = None
        self.cur_text: list[str] = []
        self.out: list[tuple[str, str]] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            d = dict(attrs)
            self.cur_href = d.get("href")
            self.cur_text = []

    def handle_data(self, data):
        if self.cur_href is not None:
            self.cur_text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.cur_href:
            txt = "".join(self.cur_text).strip()
            href = self.cur_href
            if txt and any(k in txt for k in ("公園", "緑地", "霊園", "庭園")):
                if not any(n in txt for n in NOISE_TERMS):
                    if href and not href.startswith(("#", "javascript:")):
                        full = urljoin(self.base, href)
                        self.out.append((txt, full))
            self.cur_href = None


def cache_path(label: str) -> Path:
    safe = re.sub(r"[^a-z0-9]+", "_", label.lower())
    return CACHE / f"{safe}.html"


def fetch(label: str, url: str) -> str | None:
    cp = cache_path(label)
    if cp.exists():
        return cp.read_text(encoding="utf-8", errors="replace")
    CACHE.mkdir(parents=True, exist_ok=True)
    try:
        r = requests.get(url, headers={"User-Agent": UA},
                         timeout=30, impersonate="chrome", verify=False)
    except Exception as e:
        print(f"  net err {url}: {type(e).__name__}: {e}",
              file=sys.stderr, flush=True)
        return None
    if r.status_code != 200:
        print(f"  {r.status_code} for {url}", flush=True)
        return None
    body = r.text
    cp.write_text(body, encoding="utf-8")
    time.sleep(SLEEP_S)
    return body


# Strip prefixes / suffixes that may differ between P13 names and Wikipedia
# / association anchors. Keep the stem.
PREFIX_RE = re.compile(
    r"^(?:千葉県立|神奈川県立|埼玉県立|埼玉県営|東京都立|"
    r"千葉市|横浜市|川崎市|横須賀市|相模原市|鎌倉市|"
    r"さいたま市|川口市|熊谷市|"
    r"市川市|松戸市|柏市|船橋市|"
    r"八王子市|大田区|江戸川区|足立区|国営)"
)


def norm(name: str) -> str:
    s = name.strip()
    s = PREFIX_RE.sub("", s)
    # Normalize visually similar small/full-size kana for matching.
    s = s.translate(str.maketrans({"ヶ": "ケ", "が": "ケ", "ガ": "ケ"}))
    s = re.sub(r"\s+", "", s)
    return s


def build_lookup() -> dict[str, list[tuple[str, str, str]]]:
    """Return: prefecture_or_any → list of (norm_name, raw_name, url)."""
    lookup: dict[str, list[tuple[str, str, str]]] = {}
    for pref, label, url in SOURCES:
        body = fetch(label, url)
        if not body:
            continue
        p = AnchorParser(url)
        try:
            p.feed(body)
        except Exception:
            pass
        bucket_key = pref or "*"
        for raw_text, href in p.out:
            n = norm(raw_text)
            if not n or len(n) < 2:
                continue
            lookup.setdefault(bucket_key, []).append((n, raw_text, href))
        print(f"  {label}: {len(p.out)} park-like anchors")
    return lookup


def main() -> int:
    db_path = ROOT / "data" / "parklife.db"
    with db.connect(db_path) as conn:
        rows = list(conn.execute("""
            SELECT id, slug, prefecture, name_ja, municipality
            FROM park
            WHERE slug LIKE 'p13-%'
              AND (official_url IS NULL OR official_url = '')
              AND name_ja IS NOT NULL AND name_ja != ''
            ORDER BY prefecture, municipality, name_ja
        """))
    print(f"residual P13 parks: {len(rows)}", flush=True)

    print("\n-- fetching index pages --", flush=True)
    lookup = build_lookup()

    print("\n-- matching --", flush=True)
    filled = 0
    skipped = 0
    with db.connect(db_path) as conn:
        for p in rows:
            n_park = norm(p["name_ja"])
            candidates = (lookup.get(p["prefecture"], [])
                          + lookup.get("*", []))
            best = None
            for n_anchor, raw_anchor, url in candidates:
                if n_anchor == n_park:
                    best = (raw_anchor, url, "exact")
                    break
            if not best:
                # substring either way (long anchor like "羽生水郷公園さいたま水族館")
                for n_anchor, raw_anchor, url in candidates:
                    if n_park == n_anchor:
                        continue
                    if len(n_park) >= 4 and (n_park in n_anchor
                                              or n_anchor in n_park):
                        best = (raw_anchor, url, "substr")
                        break
            if best:
                raw_anchor, url, how = best
                conn.execute("UPDATE park SET official_url=? WHERE id=?",
                             (url, p["id"]))
                filled += 1
                print(f"  [{how}] {p['prefecture']}/{p['name_ja']} → {url}  "
                      f"(anchor: {raw_anchor[:30]})", flush=True)
            else:
                skipped += 1
        conn.commit()

    print(f"\n=== association_park_url done ===")
    print(f"  parks probed:  {len(rows)}")
    print(f"  URL filled:    {filled}")
    print(f"  still empty:   {skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
