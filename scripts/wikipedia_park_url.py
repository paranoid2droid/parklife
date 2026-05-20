"""Fill park.official_url for P13-only parks via JA Wikipedia.

For each park with empty official_url, query ja.wikipedia.org for an article
whose title matches `name_ja`. Extract the official-site URL from:

  1. Infobox parameter: `|公式サイト=` / `|サイト=` / `|公式url=` / `|url=`
  2. {{Official}} / {{Official URL}} / {{Official website}} template
  3. External links section: `[https://... 公式]` (the word 公式 must appear)
  4. First `[https://... <text>]` under == 外部リンク == section, if text
     contains the park name OR the word 公式

Per-park cache under data/cache/wikipedia_park_url/.
Polite: 1 query per request, 1.0 s sleep between network calls.
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
API = "https://ja.wikipedia.org/w/api.php"
CACHE = ROOT / "data" / "cache" / "wikipedia_park_url"
SLEEP_S = 1.0

INFOBOX_KEYS = ("公式サイト", "サイト", "url", "URL", "公式url", "ホームページ",
                "公式ホームページ", "website")
# Hosts that show up as "first citation" in infoboxes but are never the
# park's actual official site — they're references to library scans,
# law texts, personal blogs, foundation reports, etc.
HOST_BLACKLIST = (
    "dl.ndl.go.jp",          # National Diet Library digital collection
    "laws.e-gov.go.jp",      # Japanese government law portal
    "blog.goo.ne.jp",        # personal blogs
    "foundation.tokyu.co.jp",  # corporate foundation PDFs
    "stib.jp/wp-content",    # newsletter PDF
    "komazawa-u.ac.jp",      # academic seminar pages
    "syougai.metro.tokyo.lg.jp/image",  # TMG education-bureau PDFs
)


def is_blacklisted(url: str) -> bool:
    return any(bad in url for bad in HOST_BLACKLIST)
RE_TEMPLATE_OFFICIAL = re.compile(
    r"\{\{(?:Official|Official\s*URL|Official\s*website|公式サイト)\s*\|"
    r"\s*(?:url\s*=\s*)?([^\|\}]+?)(?:\||\}\})",
    re.IGNORECASE,
)
RE_EXTLINK = re.compile(r"\[(https?://[^\s\]]+)\s+([^\]]+?)\]")
RE_SECTION_EXTLINK = re.compile(
    r"==\s*外部リンク\s*==(.+?)(?:==|\Z)", re.DOTALL,
)


def cache_path(name: str) -> Path:
    safe = name.replace("/", "_")
    return CACHE / f"{safe}.json"


def fetch_wikitext(title: str) -> str | None:
    cp = cache_path(title)
    if cp.exists():
        try:
            data = json.loads(cp.read_text(encoding="utf-8"))
            return data.get("wikitext")
        except Exception:
            pass
    CACHE.mkdir(parents=True, exist_ok=True)
    params = {
        "action": "query",
        "format": "json",
        "titles": title,
        "prop": "revisions",
        "rvprop": "content",
        "rvslots": "main",
        "redirects": 1,
        "formatversion": 2,
    }
    try:
        r = requests.get(API, params=params,
                         headers={"User-Agent": UA},
                         timeout=30, impersonate="chrome")
    except Exception as e:
        print(f"  net err: {type(e).__name__}: {e}",
              file=sys.stderr, flush=True)
        return None
    time.sleep(SLEEP_S)
    if r.status_code != 200:
        print(f"  {r.status_code} for {title}", flush=True)
        return None
    try:
        payload = r.json()
    except Exception:
        return None
    pages = payload.get("query", {}).get("pages") or []
    if not pages:
        cp.write_text(json.dumps({"wikitext": None}, ensure_ascii=False),
                      encoding="utf-8")
        return None
    page = pages[0]
    if page.get("missing"):
        cp.write_text(json.dumps({"wikitext": None}, ensure_ascii=False),
                      encoding="utf-8")
        return None
    revs = page.get("revisions") or []
    if not revs:
        return None
    wikitext = (revs[0].get("slots", {}).get("main", {}).get("content")
                or revs[0].get("content"))
    cp.write_text(json.dumps({"wikitext": wikitext}, ensure_ascii=False),
                  encoding="utf-8")
    return wikitext


def normalize_url(u: str) -> str:
    u = u.strip()
    # Cite-template artefacts: drop everything after the first
    # wikitext-template separator/closer.
    for stop in ("|", "{", "}", "<", " ", "\n", "\t"):
        i = u.find(stop)
        if i >= 0:
            u = u[:i]
    u = u.rstrip(".,;)")
    if not u:
        return u
    # Unwrap web.archive.org/web/<ts>/<real_url> to get the real URL.
    m = re.match(r"https?://web\.archive\.org/web/[^/]+/(https?://.+)", u)
    if m:
        u = m.group(1)
    if not u.startswith(("http://", "https://")):
        u = "https://" + u
    return u


def _maybe(url: str, reason: str) -> tuple[str | None, str]:
    """Apply blacklist; return (None, reason) when rejected."""
    if not url:
        return None, "empty url"
    if is_blacklisted(url):
        return None, f"blacklisted host (from: {reason})"
    return url, reason


def extract_url(wikitext: str, park_name: str) -> tuple[str | None, str]:
    # 1. Infobox parameter
    for key in INFOBOX_KEYS:
        m = re.search(rf"\|\s*{re.escape(key)}\s*=\s*(.+)", wikitext)
        if m:
            value = m.group(1).split("\n")[0].strip()
            # Strip wiki template wrappers
            inner = re.search(r"\[(https?://[^\s\]]+)", value)
            if inner:
                u, r = _maybe(normalize_url(inner.group(1)),
                              f"infobox {key} extlink")
                if u:
                    return u, r
                continue
            tpl = RE_TEMPLATE_OFFICIAL.search(value)
            if tpl:
                u, r = _maybe(normalize_url(tpl.group(1)),
                              f"infobox {key} {{{{Official}}}}")
                if u:
                    return u, r
                continue
            if value.startswith(("http://", "https://")):
                u, r = _maybe(normalize_url(value.split()[0]),
                              f"infobox {key} bare URL")
                if u:
                    return u, r

    # 2. {{Official URL}} template anywhere in body
    m = RE_TEMPLATE_OFFICIAL.search(wikitext)
    if m:
        u, r = _maybe(normalize_url(m.group(1)), "body {{Official}} template")
        if u:
            return u, r

    # 3. External-links section
    sec = RE_SECTION_EXTLINK.search(wikitext)
    if sec:
        body = sec.group(1)
        for url, text in RE_EXTLINK.findall(body):
            txt = text.strip()
            if "公式" in txt:
                u, r = _maybe(normalize_url(url),
                              f"外部リンク '公式' ({txt[:30]})")
                if u:
                    return u, r
        for url, text in RE_EXTLINK.findall(body):
            txt = text.strip()
            if park_name and (park_name in txt or txt in park_name):
                u, r = _maybe(normalize_url(url),
                              f"外部リンク name match ({txt[:30]})")
                if u:
                    return u, r

    return None, "no candidate found"


def candidate_titles(name: str) -> list[str]:
    """Try a few title variants so we hit Wikipedia's preferred form."""
    out = [name]
    # Drop a leading 千葉県立 / 神奈川県立 / 埼玉県営 etc.
    stripped = re.sub(r"^(千葉県立|神奈川県立|埼玉県立|埼玉県営|東京都立|国営)",
                      "", name)
    if stripped and stripped != name:
        out.append(stripped)
    return out


def main(limit: int | None = None) -> int:
    db_path = ROOT / "data" / "parklife.db"
    with db.connect(db_path) as conn:
        rows = list(conn.execute("""
            SELECT id, slug, prefecture, name_ja
            FROM park
            WHERE slug LIKE 'p13-%'
              AND (official_url IS NULL OR official_url = '')
              AND name_ja IS NOT NULL AND name_ja != ''
            ORDER BY id
        """))
    if limit:
        rows = rows[:limit]
    print(f"P13 parks needing URL: {len(rows)}", flush=True)

    filled = 0
    no_page = 0
    no_url = 0
    failed = 0
    with db.connect(db_path) as conn:
        for i, p in enumerate(rows, 1):
            wikitext = None
            tried_title = None
            for title in candidate_titles(p["name_ja"]):
                try:
                    wikitext = fetch_wikitext(title)
                except Exception as e:
                    print(f"  [{i}] {p['name_ja']} fetch failed: {e}",
                          flush=True)
                    failed += 1
                    wikitext = None
                    break
                if wikitext:
                    tried_title = title
                    break
            if wikitext is None:
                if tried_title is None and not p["name_ja"]:
                    failed += 1
                else:
                    no_page += 1
                continue
            url, reason = extract_url(wikitext, p["name_ja"])
            if url:
                conn.execute("UPDATE park SET official_url=? WHERE id=?",
                             (url, p["id"]))
                filled += 1
                print(f"  [{i:>3}] {p['name_ja']}: {url}  "
                      f"(title={tried_title!r}, {reason})", flush=True)
            else:
                no_url += 1
            if i % 25 == 0:
                conn.commit()
                print(f"  [{i:>3}/{len(rows)}] filled={filled} "
                      f"no_page={no_page} no_url={no_url} "
                      f"failed={failed}", flush=True)
        conn.commit()

    print(f"\n=== wikipedia_park_url done ===")
    print(f"  parks probed:    {len(rows)}")
    print(f"  URL filled:      {filled}")
    print(f"  no wiki page:    {no_page}")
    print(f"  page but no URL: {no_url}")
    print(f"  failed:          {failed}")
    return 0


if __name__ == "__main__":
    cap = int(sys.argv[1]) if len(sys.argv) > 1 else None
    sys.exit(main(limit=cap))
