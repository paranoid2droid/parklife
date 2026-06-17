"""Re-pick species_photo gallery from cached iNat data with diversity + licensing.

Reads cached iNat observation payloads under data/cache/inat_photos/ and
data/cache/inat_photos_broad/, applies a diversity filter (one photo per
(user, observed-day) and per (user, week, ~1km grid)), keeps only photos
with a Creative-Commons license, and rewrites the species_photo table for
each species — replacing the existing iNat rows so older insertions do not
keep stale, license-unknown, or near-duplicate frames.

Idempotent: pure local re-processing, no network.

Stores attribution + source_url for each photo so the demo modal can show
required credit and link back to the original iNat observation page.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

from parklife import db
from parklife.licenses import parse_license

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIRS = [
    ROOT / "data" / "cache" / "inat_photos",
    ROOT / "data" / "cache" / "inat_photos_broad",
]
LOC_BUCKET_DEG = 0.01           # ~1.1 km — collapse same-spot bursts
WEEK_BUCKET_DAYS = 7            # combine with location to drop multi-week revisits

# Allowed Creative Commons license codes (lowercase, as iNat returns them).
ALLOWED_LICENSE = {
    "cc0", "cc-by", "cc-by-sa", "cc-by-nc", "cc-by-nc-sa",
    "cc-by-nd", "cc-by-nc-nd", "pd", "pdm",
}


def load_taxon_to_species() -> dict[int, int]:
    db_path = ROOT / "data" / "parklife.db"
    with db.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT id, inat_taxon_id FROM species "
            "WHERE inat_taxon_id IS NOT NULL"
        ).fetchall()
    return {r["inat_taxon_id"]: r["id"] for r in rows}


def medium_url(url: str) -> str:
    """Convert a square iNat URL to medium for display."""
    if not url:
        return ""
    return url.replace("/square.", "/medium.")


def epoch_day(date_str: str | None) -> int | None:
    """Return YYYY-MM-DD as days-since-epoch, or None for unparseable."""
    if not date_str:
        return None
    try:
        from datetime import date
        y, m, d = date_str.split("-")[:3]
        return (date(int(y), int(m), int(d)) - date(1970, 1, 1)).days
    except Exception:
        return None


def location_bucket(geo: dict | None) -> tuple[int, int] | None:
    if not geo:
        return None
    coords = geo.get("coordinates") or []
    if len(coords) < 2:
        return None
    lon, lat = coords[0], coords[1]
    try:
        return (
            int(math.floor(lat / LOC_BUCKET_DEG)),
            int(math.floor(lon / LOC_BUCKET_DEG)),
        )
    except (TypeError, ValueError):
        return None


def pick_diverse(payloads: list[dict], target: int) -> list[dict]:
    """Return up to `target` diverse photo records, sorted by quality preference.
    Each record: {url, thumb_url, attribution, source_url, license_code}."""
    seen_user_day: set[tuple[int, int]] = set()
    seen_user_geo_week: set[tuple[int, int, int, int]] = set()
    seen_url: set[str] = set()
    out: list[dict] = []

    for payload in payloads:
        for obs in payload.get("results") or []:
            if obs.get("captive"):
                continue
            uid = (obs.get("user") or {}).get("id")
            day = epoch_day(obs.get("observed_on"))
            week = day // WEEK_BUCKET_DAYS if day is not None else None
            geo = location_bucket(obs.get("geojson"))
            obs_id = obs.get("id")
            obs_uri = obs.get("uri") or (
                f"https://www.inaturalist.org/observations/{obs_id}" if obs_id else ""
            )
            # Skip if same observer + same day already represented
            if uid is not None and day is not None and (uid, day) in seen_user_day:
                continue
            # Or same observer + same ~1km square + same week
            if (uid is not None and week is not None and geo is not None
                    and (uid, week, geo[0], geo[1]) in seen_user_geo_week):
                continue

            # Take only the first licensed photo from this observation
            for photo in obs.get("photos") or []:
                lic = (photo.get("license_code") or "").lower()
                if lic not in ALLOWED_LICENSE:
                    continue
                url = photo.get("url") or ""
                if not url or url in seen_url:
                    continue
                seen_url.add(url)
                out.append({
                    "url": medium_url(url),
                    "thumb_url": url,
                    "attribution": photo.get("attribution") or "",
                    "license_code": lic,
                    "source_url": obs_uri,
                })
                if uid is not None and day is not None:
                    seen_user_day.add((uid, day))
                if (uid is not None and week is not None and geo is not None):
                    seen_user_geo_week.add((uid, week, geo[0], geo[1]))
                break  # one photo per observation
            if len(out) >= target:
                return out
    return out


def main(target: int = 6) -> int:
    db_path = ROOT / "data" / "parklife.db"
    taxon_to_species = load_taxon_to_species()
    print(f"species with inat_taxon_id: {len(taxon_to_species)}")

    cache_files: dict[int, list[Path]] = {}
    for d in CACHE_DIRS:
        if not d.exists():
            continue
        for f in d.glob("*.json"):
            try:
                tid = int(f.stem)
            except ValueError:
                continue
            cache_files.setdefault(tid, []).append(f)
    print(f"cached taxa: {len(cache_files)}")

    with db.connect(db_path) as conn:
        # Wipe existing iNat rows so we start fresh and avoid mixing old+new ordering.
        deleted = conn.execute(
            "DELETE FROM species_photo WHERE source = 'iNaturalist'"
        ).rowcount
        print(f"deleted prior iNaturalist photo rows: {deleted}")
        conn.commit()

        species_with_photos = 0
        total_photos = 0
        no_license_skipped = 0

        for i, (tid, paths) in enumerate(cache_files.items(), 1):
            sp_id = taxon_to_species.get(tid)
            if not sp_id:
                continue
            payloads = []
            for p in paths:
                try:
                    payloads.append(json.loads(p.read_text(encoding="utf-8")))
                except Exception:
                    continue
            picks = pick_diverse(payloads, target=target)
            if not picks:
                # Count how many photos existed but had no license, for stats
                for p in payloads:
                    for obs in p.get("results") or []:
                        for photo in obs.get("photos") or []:
                            lic = (photo.get("license_code") or "").lower()
                            if lic not in ALLOWED_LICENSE:
                                no_license_skipped += 1
                continue
            species_with_photos += 1
            for order, photo in enumerate(picks):
                cur = conn.execute(
                    """INSERT OR IGNORE INTO species_photo
                       (species_id, url, thumb_url, attribution, license, source,
                        source_url, sort_order)
                       VALUES (?, ?, ?, ?, ?, 'iNaturalist', ?, ?)""",
                    (sp_id, photo["url"], photo["thumb_url"],
                     photo["attribution"], parse_license(photo["attribution"]),
                     photo["source_url"], order),
                )
                total_photos += cur.rowcount
            if i % 500 == 0:
                conn.commit()
                print(f"  [{i:>5}/{len(cache_files)}] species_with_photos="
                      f"{species_with_photos} photos={total_photos}")
        conn.commit()

    print(f"\n=== repopulate done ===")
    print(f"  species written: {species_with_photos}")
    print(f"  photo rows: {total_photos}")
    print(f"  unlicensed photos skipped (sample stat): {no_license_skipped}")
    return 0


if __name__ == "__main__":
    target = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    sys.exit(main(target=target))
