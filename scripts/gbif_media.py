"""Third hero-photo source: GBIF occurrence media (StillImage).

The iNat + Wikimedia-Commons passes leave ~490 visible species with no photo —
mostly obscure insects/molluscs/fish that aren't on iNaturalist and have no
Wikidata P18 image. GBIF aggregates museum / herbarium / citizen-science media
that often covers exactly this long tail.

⚠️ Anti-pattern this script AVOIDS (the recurring "wrong-taxon photo" bug):
GBIF's `species/match` returns `matchType=HIGHERRANK` when it can only resolve
the name to a genus/family. Its occurrence images are then for the whole genus,
so attaching one would inject a wrong-species photo. We therefore accept ONLY
`EXACT`/`FUZZY` matches at `rank=SPECIES` whose canonical binomial still equals
the input binomial. HIGHERRANK and no-match are skipped (species stays photo-less,
honestly re-checkable later).

Idempotent + cached:
  - match:      data/cache/gbif_match/<slug>.json
  - media:      data/cache/gbif_media/<taxonKey>.json
Only species with zero existing photos are touched; re-runs are no-ops.

Usage:
  .venv/bin/python -m scripts.gbif_media [LIMIT] [--all] [--max-photos N]
  # default: visible species only (katakana ja-name + scientific_name), LIMIT=600
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from parklife import db
from parklife.licenses import parse_license

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "parklife.db"
MATCH_CACHE = ROOT / "data" / "cache" / "gbif_match"
MEDIA_CACHE = ROOT / "data" / "cache" / "gbif_media"
UA = "parklife/1.0 (flora-fauna research; contact via github paranoid2droid/parklife)"

# GBIF license URLs -> the CC code text that parklife.licenses.parse_license reads.
_LICENSE_CODE = [
    ("by-nc-sa", "CC BY-NC-SA"), ("by-nc-nd", "CC BY-NC-ND"), ("by-nc", "CC BY-NC"),
    ("by-sa", "CC BY-SA"), ("by-nd", "CC BY-ND"), ("by", "CC BY"),
    ("zero", "CC0"), ("publicdomain", "CC0"), ("cc0", "CC0"),
]


def license_text(url: str | None) -> str:
    if not url:
        return ""
    low = url.lower()
    for token, code in _LICENSE_CODE:
        if token in low:
            return code
    return ""


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")[:80]


def _get(url: str, timeout: int = 25) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _norm_binomial(name: str) -> str:
    """Lowercase genus+species tokens, dropping authorship / infra-rank cruft."""
    toks = re.findall(r"[A-Za-z]+", name.lower())
    return " ".join(toks[:2])


def match_species_key(sci: str) -> int | None:
    """GBIF usageKey for `sci`, ONLY when it's a trustworthy species match.

    Returns None for HIGHERRANK / no-match / a binomial that drifted under FUZZY.
    """
    cp = MATCH_CACHE / f"{_slug(sci)}.json"
    if cp.exists():
        m = json.loads(cp.read_text())
    else:
        url = "https://api.gbif.org/v1/species/match?" + urllib.parse.urlencode(
            {"name": sci, "strict": "false"})
        m = _get(url)
        cp.write_text(json.dumps(m, ensure_ascii=False))
        time.sleep(0.3)
    if m.get("matchType") not in ("EXACT", "FUZZY"):
        return None
    if m.get("rank") != "SPECIES":
        return None
    canonical = m.get("canonicalName") or m.get("species") or ""
    if _norm_binomial(canonical) != _norm_binomial(sci):
        return None
    return m.get("usageKey")


def fetch_media(taxon_key: int, limit: int = 20) -> list[dict]:
    cp = MEDIA_CACHE / f"{taxon_key}.json"
    if cp.exists():
        payload = json.loads(cp.read_text())
    else:
        url = "https://api.gbif.org/v1/occurrence/search?" + urllib.parse.urlencode(
            {"taxonKey": taxon_key, "mediaType": "StillImage", "limit": limit})
        payload = _get(url)
        cp.write_text(json.dumps(payload, ensure_ascii=False))
        time.sleep(0.3)
    out: list[dict] = []
    seen: set[str] = set()
    for occ in payload.get("results", []):
        for med in occ.get("media", []):
            ident = med.get("identifier")
            if not ident or ident in seen:
                continue
            seen.add(ident)
            holder = (med.get("rightsHolder") or med.get("creator")
                      or occ.get("rightsHolder") or "")
            lic_url = med.get("license") or occ.get("license") or ""
            code = license_text(lic_url)
            attribution = " · ".join(p for p in [
                f"© {holder}" if holder else "", code, "GBIF"] if p)
            out.append({
                "url": ident,
                "attribution": attribution,
                "license": parse_license(attribution),
                "source_url": f"https://www.gbif.org/occurrence/{occ.get('key')}",
            })
    return out


def main(limit: int | None, include_all: bool, max_photos: int) -> int:
    MATCH_CACHE.mkdir(parents=True, exist_ok=True)
    MEDIA_CACHE.mkdir(parents=True, exist_ok=True)
    db.init(DB_PATH)
    visible = ("" if include_all else
               "AND s.common_name_ja IS NOT NULL AND s.common_name_ja != '' "
               "AND SUBSTR(s.common_name_ja,1,1) NOT BETWEEN 'A' AND 'Z' ")
    with db.connect(DB_PATH) as conn:
        rows = conn.execute(
            f"""
            SELECT s.id, s.scientific_name, s.common_name_ja, s.photo_url
            FROM species s
            WHERE s.scientific_name IS NOT NULL {visible}
              AND s.photo_url IS NULL
              AND NOT EXISTS (SELECT 1 FROM species_photo p WHERE p.species_id = s.id)
            ORDER BY (SELECT COUNT(*) FROM park_species ps WHERE ps.species_id = s.id) DESC
            {'LIMIT ?' if limit else ''}
            """,
            ((limit,) if limit else ()),
        ).fetchall()
        print(f"candidates (no photo): {len(rows)}", flush=True)

        matched = inserted = species_with = skipped = 0
        for i, r in enumerate(rows, 1):
            sci = r["scientific_name"]
            try:
                key = match_species_key(sci)
            except Exception as e:  # noqa: BLE001 - network hiccup, skip & continue
                print(f"  match err {sci}: {e}", flush=True)
                continue
            if not key:
                skipped += 1
                continue
            matched += 1
            try:
                media = fetch_media(key)[:max_photos]
            except Exception as e:  # noqa: BLE001
                print(f"  media err {sci}: {e}", flush=True)
                continue
            if not media:
                continue
            for order, m in enumerate(media):
                conn.execute(
                    """INSERT OR IGNORE INTO species_photo
                       (species_id, url, thumb_url, attribution, license, source, source_url, sort_order)
                       VALUES (?, ?, ?, ?, ?, 'GBIF', ?, ?)""",
                    (r["id"], m["url"], m["url"], m["attribution"],
                     m["license"], m["source_url"], order),
                )
            # promote first image to the species hero if it has none
            conn.execute(
                "UPDATE species SET photo_url = ? WHERE id = ? AND photo_url IS NULL",
                (media[0]["url"], r["id"]),
            )
            inserted += len(media)
            species_with += 1
            if i % 25 == 0:
                conn.commit()
                print(f"  [{i}/{len(rows)}] matched={matched} species_photo'd={species_with} "
                      f"rows={inserted} skipped(no-trust-match)={skipped}", flush=True)
        conn.commit()

    print("\n=== gbif_media done ===", flush=True)
    print(f"  candidates: {len(rows)}", flush=True)
    print(f"  trustworthy species matches: {matched}  (skipped HIGHERRANK/no-match: {skipped})", flush=True)
    print(f"  species newly photo'd: {species_with}  photo rows inserted: {inserted}", flush=True)
    return species_with


if __name__ == "__main__":
    args = sys.argv[1:]
    include_all = "--all" in args
    args = [a for a in args if a != "--all"]
    max_photos = 5
    if "--max-photos" in args:
        idx = args.index("--max-photos")
        max_photos = int(args[idx + 1])
        del args[idx:idx + 2]
    limit = int(args[0]) if args else 600
    main(limit, include_all, max_photos)
