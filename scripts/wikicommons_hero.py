"""Fetch Wikimedia Commons hero photos via Wikidata P18.

For each species with a scientific_name, look up Wikidata's `taxon image`
(wdt:P18). When present, pull the file's license + author from the Commons
imageinfo API and insert the result as a `species_photo` row with
source='Wikimedia Commons' and sort_order=-1, so it sorts before any iNat
gallery photos and naturally becomes the modal hero / card thumbnail.

Caches:
  data/cache/wikidata_p18/<safe-binomial>.json  -- {filename or null}
  data/cache/commons/<safe-filename>.json       -- imageinfo metadata

Politeness: Wikidata SPARQL batched 80/req, Commons imageinfo batched 50/req,
each batch followed by 1.0s sleep. Idempotent.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import unquote

from curl_cffi import requests

from parklife import db

ROOT = Path(__file__).resolve().parent.parent
UA = "parklife-bot/0.1 (research; contact: paranoid2droid@gmail.com)"
SPARQL = "https://query.wikidata.org/sparql"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
WD_CACHE = ROOT / "data" / "cache" / "wikidata_p18"
CM_CACHE = ROOT / "data" / "cache" / "commons"
SPARQL_BATCH = 80
COMMONS_BATCH = 50

# Allowed Commons license strings (extmetadata.LicenseShortName.value).
# We accept any CC license + Public Domain; reject "All rights reserved"
# and proprietary tags. License names normalised to lowercase startswith.
ALLOWED_PREFIXES = ("cc", "public domain", "pdm", "fal", "wtfpl", "open", "ogl")


def safe_filename(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", s)[:140]


def wd_cache_path(binomial: str) -> Path:
    return WD_CACHE / f"{safe_filename(binomial)}.json"


def cm_cache_path(commons_filename: str) -> Path:
    return CM_CACHE / f"{safe_filename(commons_filename)}.json"


def parse_commons_filename(file_path_url: str) -> str | None:
    """Wikidata returns commons URLs like
    http://commons.wikimedia.org/wiki/Special:FilePath/<urlencoded-name>"""
    m = re.search(r"/Special:FilePath/(.+)$", file_path_url)
    if not m:
        return None
    return unquote(m.group(1))


def sparql_batch(binomials: list[str]) -> dict[str, str | None]:
    """Returns {binomial: commons_filename or None}."""
    if not binomials:
        return {}
    values = " ".join(f'"{b}"' for b in binomials if '"' not in b)
    q = f"""
SELECT ?name ?image WHERE {{
  VALUES ?name {{ {values} }}
  ?taxon wdt:P225 ?name; wdt:P18 ?image.
}}
"""
    try:
        r = requests.get(
            SPARQL,
            params={"query": q, "format": "json"},
            headers={"User-Agent": UA, "Accept": "application/sparql-results+json"},
            timeout=60, impersonate="chrome",
        )
    except Exception as e:
        print(f"  net err: {type(e).__name__}: {e}")
        return {b: None for b in binomials}
    if r.status_code != 200:
        return {b: None for b in binomials}
    out: dict[str, str | None] = {b: None for b in binomials}
    for row in (r.json().get("results") or {}).get("bindings", []):
        b = row.get("name", {}).get("value")
        img = row.get("image", {}).get("value")
        if b and img and not out.get(b):
            out[b] = parse_commons_filename(img)
    return out


def lookup_wd(binomials: list[str]) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    uncached: list[str] = []
    for b in binomials:
        cp = wd_cache_path(b)
        if cp.exists():
            try:
                out[b] = json.loads(cp.read_text(encoding="utf-8"))
                continue
            except Exception:
                pass
        uncached.append(b)
    if uncached:
        WD_CACHE.mkdir(parents=True, exist_ok=True)
        for i in range(0, len(uncached), SPARQL_BATCH):
            chunk = uncached[i:i+SPARQL_BATCH]
            res = sparql_batch(chunk)
            for b in chunk:
                v = res.get(b)
                wd_cache_path(b).write_text(
                    json.dumps(v, ensure_ascii=False), encoding="utf-8")
                out[b] = v
            if (i // SPARQL_BATCH) % 5 == 0:
                done = min(i + SPARQL_BATCH, len(uncached))
                hits = sum(1 for v in out.values() if v)
                print(f"  WD batch {i//SPARQL_BATCH+1}: {done}/{len(uncached)} "
                      f"fetched, hits {hits}", flush=True)
            time.sleep(1.0)
    return out


def commons_batch(filenames: list[str]) -> dict[str, dict | None]:
    """Fetch imageinfo for up to COMMONS_BATCH files; return per-filename meta."""
    if not filenames:
        return {}
    titles = "|".join(f"File:{f}" for f in filenames if "|" not in f)
    params = {
        "action": "query",
        "prop": "imageinfo",
        "iiprop": "url|extmetadata|user",
        "iiextmetadatafilter": "License|LicenseShortName|Artist|Credit|"
                                "AttributionRequired|Copyrighted|UsageTerms|"
                                "ImageDescription",
        "titles": titles,
        "format": "json",
        "redirects": 1,
    }
    try:
        r = requests.get(COMMONS_API, params=params,
                         headers={"User-Agent": UA},
                         timeout=60, impersonate="chrome")
    except Exception as e:
        print(f"  net err commons: {type(e).__name__}: {e}")
        return {f: None for f in filenames}
    if r.status_code != 200:
        return {f: None for f in filenames}
    out: dict[str, dict | None] = {f: None for f in filenames}
    pages = ((r.json().get("query") or {}).get("pages") or {})
    title_to_input: dict[str, str] = {}
    for f in filenames:
        title_to_input[f"File:{f}".replace("_", " ")] = f
    for _, page in pages.items():
        title = page.get("title", "")
        original_input = title_to_input.get(title)
        if not original_input:
            # try without prefix normalisation
            for k, v in title_to_input.items():
                if k.lower() == title.lower():
                    original_input = v
                    break
        if not original_input:
            continue
        info = (page.get("imageinfo") or [{}])[0]
        out[original_input] = info or None
    return out


def lookup_commons(filenames: list[str]) -> dict[str, dict | None]:
    out: dict[str, dict | None] = {}
    uncached: list[str] = []
    for f in filenames:
        cp = cm_cache_path(f)
        if cp.exists():
            try:
                out[f] = json.loads(cp.read_text(encoding="utf-8"))
                continue
            except Exception:
                pass
        uncached.append(f)
    if uncached:
        CM_CACHE.mkdir(parents=True, exist_ok=True)
        for i in range(0, len(uncached), COMMONS_BATCH):
            chunk = uncached[i:i+COMMONS_BATCH]
            res = commons_batch(chunk)
            for f in chunk:
                v = res.get(f)
                cm_cache_path(f).write_text(
                    json.dumps(v, ensure_ascii=False), encoding="utf-8")
                out[f] = v
            if (i // COMMONS_BATCH) % 5 == 0:
                done = min(i + COMMONS_BATCH, len(uncached))
                ok = sum(1 for v in out.values() if v)
                print(f"  Commons batch {i//COMMONS_BATCH+1}: {done}/{len(uncached)} "
                      f"fetched, ok {ok}", flush=True)
            time.sleep(1.0)
    return out


def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


def license_ok(lic_short: str) -> bool:
    s = (lic_short or "").lower()
    return any(s.startswith(p) for p in ALLOWED_PREFIXES)


def build_attribution(meta: dict) -> tuple[str, str] | None:
    """Return (attribution_text, license_short) if licensable, else None."""
    em = meta.get("extmetadata") or {}
    def get(field: str) -> str:
        return strip_html((em.get(field) or {}).get("value") or "")
    lic = get("LicenseShortName")
    if not license_ok(lic):
        return None
    artist = get("Artist") or get("Credit") or meta.get("user") or ""
    artist = artist.strip(" ,;")
    if not artist:
        artist = "Wikimedia Commons"
    return (f"{artist} · {lic} · Wikimedia Commons", lic)


def main(limit: int | None = None) -> int:
    db_path = ROOT / "data" / "parklife.db"
    with db.connect(db_path) as conn:
        species = list(conn.execute("""
            SELECT s.id, s.scientific_name FROM species s
            JOIN park_species ps ON ps.species_id = s.id
            WHERE s.scientific_name IS NOT NULL AND s.scientific_name <> ''
            GROUP BY s.id
            ORDER BY s.id
        """))
    if limit:
        species = species[:limit]
    print(f"visible species with sci name: {len(species)}")

    binomials = sorted({s["scientific_name"] for s in species})
    print(f"unique binomials: {len(binomials)}")
    wd_results = lookup_wd(binomials)
    filenames = sorted({f for f in wd_results.values() if f})
    print(f"binomials with P18 image: {len(filenames)}")
    commons_meta = lookup_commons(filenames)

    inserted = updated = skipped = 0
    license_skipped = 0
    with db.connect(db_path) as conn:
        # Wipe old Commons rows so this is fully idempotent (license filter
        # may have changed across runs).
        deleted = conn.execute(
            "DELETE FROM species_photo WHERE source='Wikimedia Commons'"
        ).rowcount
        print(f"deleted prior Commons hero rows: {deleted}")
        for s in species:
            sci = s["scientific_name"]
            fn = wd_results.get(sci)
            if not fn:
                skipped += 1
                continue
            meta = commons_meta.get(fn)
            if not meta:
                skipped += 1
                continue
            attr = build_attribution(meta)
            if not attr:
                license_skipped += 1
                continue
            attribution, _ = attr
            url = (f"https://commons.wikimedia.org/wiki/Special:FilePath/"
                   f"{fn}?width=600")
            thumb = (f"https://commons.wikimedia.org/wiki/Special:FilePath/"
                     f"{fn}?width=240")
            source_url = f"https://commons.wikimedia.org/wiki/File:{fn}"
            cur = conn.execute(
                """INSERT OR IGNORE INTO species_photo
                   (species_id, url, thumb_url, attribution, source,
                    source_url, sort_order)
                   VALUES (?, ?, ?, ?, 'Wikimedia Commons', ?, -1)""",
                (s["id"], url, thumb, attribution, source_url),
            )
            if cur.rowcount:
                inserted += 1
            else:
                updated += 1
        conn.commit()

    print(f"\n=== wikicommons_hero done ===")
    print(f"  species processed: {len(species)}")
    print(f"  hero rows inserted: {inserted}")
    print(f"  no P18 / no commons meta: {skipped}")
    print(f"  filtered out (license not allowed): {license_skipped}")
    return 0


if __name__ == "__main__":
    cap = int(sys.argv[1]) if len(sys.argv) > 1 else None
    sys.exit(main(limit=cap))
