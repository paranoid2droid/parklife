"""Parse the four prefecture-level park list HTML pages cached under
data/raw/_seeds/ and emit data/seeds/<prefecture>.json.

One extractor per prefecture, since each site has its own structure.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "_seeds"
OUT = ROOT / "data" / "seeds"


def slug_from_url(url: str) -> str:
    """Last meaningful path segment, lowercased, [a-z0-9_-] only."""
    path = urlparse(url).path.rstrip("/")
    seg = path.rsplit("/", 1)[-1] if path else ""
    seg = seg.replace("index.html", "").replace(".html", "").strip("/-_")
    seg = re.sub(r"[^a-z0-9_-]", "-", seg.lower()).strip("-")
    return seg or "park"


# ---------------------------------------------------------------------------
# Tokyo: https://www.tokyo-park.or.jp/park_list/
# Pattern: <a href="/park/<slug>/index.html">名称 区/市 …</a>
# Excludes /park/news/ etc. by URL shape.
# ---------------------------------------------------------------------------

def parse_tokyo(html: bytes) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    base = "https://www.tokyo-park.or.jp"
    seen: set[str] = set()
    parks: list[dict] = []
    pat = re.compile(r"^/park/([a-z0-9_-]+)/index\.html$")
    for a in soup.find_all("a", href=True):
        m = pat.match(a["href"])
        if not m:
            continue
        slug = m.group(1)
        if slug in seen:
            continue
        text = " ".join(a.get_text().split())
        if not text:
            continue
        # split "名称 municipality1 municipality2"
        parts = text.split()
        name_ja = parts[0]
        municipality = " ".join(parts[1:]) or None
        seen.add(slug)
        parks.append({
            "slug": slug,
            "name_ja": name_ja,
            "municipality": municipality,
            "official_url": urljoin(base, a["href"]),
        })
    return parks


# ---------------------------------------------------------------------------
# Kanagawa: http://www.kanagawa-kouen.jp/parklist/list.html
# Pattern: <td class="c1"><div class="name"><a href="...">公園名</a></div></td>
# ---------------------------------------------------------------------------

def parse_kanagawa(html: bytes) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    parks: list[dict] = []
    seen: set[str] = set()
    for div in soup.select("div.name"):
        a = div.find("a", href=True)
        if not a:
            continue
        name_ja = " ".join(a.get_text().split())
        if not name_ja:
            continue
        url = a["href"]
        slug = slug_from_url(url)
        if slug in seen:
            slug = f"{slug}-{len(seen)}"
        seen.add(slug)
        parks.append({
            "slug": slug,
            "name_ja": name_ja,
            "official_url": url,
        })
    return parks


# ---------------------------------------------------------------------------
# Chiba: https://www.pref.chiba.lg.jp/kouen/toshikouen/guidemap/index.html
# Pattern: <a href="/kouen/toshikouen/guidemap/<slug>[/index.html|.html]">名称</a>
# ---------------------------------------------------------------------------

CHIBA_SKIP = {
    "shisetsu", "parkguide", "landscape", "documents", "citypark-150th-touroku",
    "aobanomorikyuukan", "futtsukouenkyuukan", "link", "index",
}


def parse_chiba(html: bytes) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    base = "https://www.pref.chiba.lg.jp"
    parks: list[dict] = []
    seen: set[str] = set()
    pat = re.compile(r"^/kouen/toshikouen/guidemap/([a-z0-9-]+)(?:/(?:index\.html)?|\.html)$")
    for a in soup.find_all("a", href=True):
        m = pat.match(a["href"])
        if not m:
            continue
        slug = m.group(1)
        if slug in CHIBA_SKIP or slug in seen:
            continue
        text = " ".join(a.get_text().split())
        if not text or "JPG" in text or "PDF" in text:
            continue
        seen.add(slug)
        parks.append({
            "slug": slug,
            "name_ja": text,
            "official_url": urljoin(base, a["href"]),
        })
    return parks


# ---------------------------------------------------------------------------
# Saitama: https://www.pref.saitama.lg.jp/a1105/bunka_kyouiku_kennei-kouen-syoukai.html
# The "各公園のホームページ" section has each park with three links: name,
# イベント, アクセス. We keep the first one (the public-name link) per group.
# We strip naming-rights prefixes from names manually since the public list
# at the top uses naming-rights names; the bottom section uses public names.
# ---------------------------------------------------------------------------

SAITAMA_SKIP_TEXT = {"イベント", "アクセス", "お知らせ", "緑花情報", "新着情報"}
SAITAMA_PARENS = re.compile(r"（([^（）]+?(?:公園|緑道))）")


def _saitama_slug(url: str) -> str:
    """Saitama URLs are messy: parks.or.jp/<slug>/, seibu-la.co.jp/<x-y>/, etc.
    Use host's first label + first path segment to maximize uniqueness."""
    p = urlparse(url)
    host = (p.hostname or "").split(".")[0] or "site"
    seg = (p.path.strip("/").split("/", 1)[0] or "").lower()
    seg = re.sub(r"[^a-z0-9_-]", "-", seg).strip("-")
    return (host + "-" + seg).strip("-") if seg else host


def parse_saitama(html: bytes) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    parks: list[dict] = []
    seen_slugs: set[str] = set()
    seen_names: set[str] = set()
    section = soup.find(id="gaibu-hp") or soup

    def add(name: str, url: str) -> None:
        if not name or name in seen_names:
            return
        if url.startswith(("/", "#", "javascript:")):
            return
        if not name.endswith(("公園", "緑道")):
            return
        slug = _saitama_slug(url)
        # disambiguate
        base = slug
        i = 2
        while slug in seen_slugs:
            slug = f"{base}-{i}"
            i += 1
        seen_slugs.add(slug)
        seen_names.add(name)
        parks.append({"slug": slug, "name_ja": name, "official_url": url})

    # Pass 1: top list — text contains "（公園名）（別ウィンドウで開きます）".
    # Use the parenthesised public name, not the naming-rights wrapper.
    for a in soup.find_all("a", href=True):
        text = " ".join(a.get_text().split())
        m = SAITAMA_PARENS.search(text)
        if not m:
            continue
        if "（別ウィンドウで開きます）" not in text:
            continue
        add(m.group(1), a["href"])

    # Pass 2: bottom "各公園のホームページ" section — first link in each
    # triplet (skip イベント/アクセス). Names here may include naming-rights
    # prefixes (no parens form); we collapse them in pass 3.
    for a in section.find_all_next("a", href=True):
        text = " ".join(a.get_text().split())
        if not text or text in SAITAMA_SKIP_TEXT:
            continue
        if text.startswith("パンフレット") or "ネーミングライツ" in text:
            continue
        add(text, a["href"])
        if len(parks) >= 60:
            break

    # Pass 3: collapse naming-rights / public-name pairs that point to the
    # same park. If name A is a strict substring of name B (and B is longer),
    # B is a naming-rights wrapper of A — drop B.
    public_names = {p["name_ja"] for p in parks}
    deduped: list[dict] = []
    for p in parks:
        n = p["name_ja"]
        is_wrapper = any(other != n and other in n for other in public_names)
        if is_wrapper:
            continue
        deduped.append(p)
    return deduped


# ---------------------------------------------------------------------------

EXTRACTORS = {
    "tokyo": (parse_tokyo, "東京都公園協会"),
    "kanagawa": (parse_kanagawa, "神奈川県公園協会"),
    "chiba": (parse_chiba, "千葉県"),
    "saitama": (parse_saitama, "埼玉県公園緑地協会"),
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for slug, (fn, operator) in EXTRACTORS.items():
        html = (RAW / f"{slug}.html").read_bytes()
        parks = fn(html)
        payload = {
            "prefecture": slug,
            "operator": operator,
            "parks": parks,
        }
        (OUT / f"{slug}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"{slug:10} {len(parks):>4} parks")


if __name__ == "__main__":
    main()
