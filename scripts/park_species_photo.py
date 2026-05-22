"""Per-(park, species) gallery photos, picked from already-cached iNat data.

For each visible (park, species) pair, scan the cached iNaturalist
observation JSONs for that species' taxon (`data/cache/inat_photos/<tid>.json`
and `data/cache/inat_photos_broad/<tid>.json`) and pick up to 5 photos taken
nearest to the park's coordinates.

Tiers:
  - 0: observation within RADIUS_AT_PARK_M of park centre
  - 1: observation within RADIUS_NEARBY_M of park centre

Diversity dedup mirrors `scripts/repopulate_species_photos.py`:
  - drop duplicates of the same (user, day)
  - drop near-duplicate locations from the same user within ~1km

Falls back to `species_photo` rows (treated as tier 2) so every modal still
gets 5 photos even when local observations are sparse.

No network calls — pure-local re-read of existing cache.

Usage:
  .venv/bin/python -m scripts.park_species_photo                # full sweep
  .venv/bin/python -m scripts.park_species_photo --parks 16,33  # POC
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

from parklife import db

ROOT = Path(__file__).resolve().parent.parent
CACHE_TIGHT = ROOT / "data" / "cache" / "inat_photos"
CACHE_BROAD = ROOT / "data" / "cache" / "inat_photos_broad"
CACHE_GBIF  = ROOT / "data" / "cache" / "gbif"

RADIUS_AT_PARK_M = 600     # tier 0
RADIUS_NEARBY_M  = 5000    # tier 1
DEDUP_RADIUS_M   = 1000    # same-user near-duplicate spatial dedup
MAX_PHOTOS = 5

SCHEMA = """
CREATE TABLE IF NOT EXISTS park_species_photo (
    id          INTEGER PRIMARY KEY,
    park_id     INTEGER NOT NULL REFERENCES park(id) ON DELETE CASCADE,
    species_id  INTEGER NOT NULL REFERENCES species(id) ON DELETE CASCADE,
    url         TEXT NOT NULL,
    thumb_url   TEXT,
    attribution TEXT,
    source      TEXT NOT NULL DEFAULT 'iNaturalist',
    source_url  TEXT,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    tier        INTEGER NOT NULL,
    UNIQUE(park_id, species_id, url)
);
CREATE INDEX IF NOT EXISTS idx_psp_pair ON park_species_photo(park_id, species_id);
"""


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _photo_urls(photo: dict) -> tuple[str | None, str | None]:
    medium = photo.get("medium_url")
    square = photo.get("square_url")
    url = photo.get("url")
    if not medium and url:
        medium = url.replace("/square.", "/medium.")
    return medium or url, square or url


def load_taxon_observations(taxon_id: int) -> list[dict]:
    """Return iNat observation dicts (tight + broad caches merged, de-dup by id)."""
    seen_ids: set = set()
    out: list[dict] = []
    for d in (CACHE_TIGHT, CACHE_BROAD):
        fp = d / f"{taxon_id}.json"
        if not fp.exists():
            continue
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        for obs in data.get("results") or []:
            oid = obs.get("id")
            if oid in seen_ids:
                continue
            seen_ids.add(oid)
            out.append(obs)
    return out


def candidates_for_pair(
    park_lat: float, park_lon: float, observations: list[dict]
) -> list[dict]:
    """Return list of photo candidates with tier + distance, sorted best-first."""
    cands: list[dict] = []
    for obs in observations:
        if obs.get("obscured"):
            continue
        loc = obs.get("location")
        if not loc:
            geo = obs.get("geojson") or {}
            coords = geo.get("coordinates") or []
            if len(coords) != 2:
                continue
            lon_o, lat_o = coords[0], coords[1]
        else:
            try:
                lat_s, lon_s = loc.split(",", 1)
                lat_o, lon_o = float(lat_s), float(lon_s)
            except Exception:
                continue
        try:
            d = haversine_m(park_lat, park_lon, lat_o, lon_o)
        except Exception:
            continue
        if d > RADIUS_NEARBY_M:
            continue
        tier = 0 if d <= RADIUS_AT_PARK_M else 1
        photos = obs.get("photos") or []
        user = (obs.get("user") or {}).get("login") or ""
        day = (obs.get("observed_on_details") or {}).get("date") or obs.get("observed_on") or ""
        oid = obs.get("id")
        for ph in photos:
            url, thumb = _photo_urls(ph)
            if not url:
                continue
            lic = ph.get("license_code") or ""
            cands.append({
                "tier": tier,
                "dist": d,
                "lat": lat_o,
                "lon": lon_o,
                "url": url,
                "thumb_url": thumb,
                "attribution": ph.get("attribution") or "",
                "source": "iNaturalist",
                "source_url": f"https://www.inaturalist.org/observations/{oid}" if oid else None,
                "license": lic,
                "user": user,
                "day": day,
            })
    cands.sort(key=lambda c: (c["tier"], c["dist"]))
    return cands


def load_gbif_park_index(prefecture: str, slug: str) -> dict[str, list[dict]]:
    """For a park, return {binomial_name -> [candidate dicts]} from GBIF cache.

    GBIF records are already park-scoped (1.5 km radius from scripts/gbif.py),
    so we treat distance leniently and rely on the cache file partitioning.
    """
    fp = CACHE_GBIF / f"{prefecture}__{slug}.json"
    if not fp.exists():
        return {}
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
    except Exception:
        return {}
    out: dict[str, list[dict]] = defaultdict(list)
    for rec in data:
        media = rec.get("media") or []
        if not media:
            continue
        binom = rec.get("species") or ""
        if not binom:
            continue
        lat = rec.get("decimalLatitude")
        lon = rec.get("decimalLongitude")
        creator = rec.get("recordedBy") or ""
        event_date = rec.get("eventDate") or ""
        day = event_date[:10] if event_date else ""
        gbif_key = rec.get("key")
        for m in media:
            url = m.get("identifier") or m.get("references")
            if not url or not url.startswith(("http://", "https://")):
                continue
            mtype = m.get("type") or ""
            fmt = m.get("format") or ""
            if mtype and mtype != "StillImage":
                continue
            if fmt and not fmt.startswith("image"):
                continue
            user = m.get("creator") or creator
            license_url = m.get("license") or ""
            attribution = m.get("rightsHolder") or m.get("creator") or creator
            if license_url:
                attribution = f"{attribution} ({license_url})" if attribution else license_url
            out[binom].append({
                "tier": 0,  # GBIF cache is already park-scoped
                "dist": 0.0,
                "lat": lat if lat is not None else 0.0,
                "lon": lon if lon is not None else 0.0,
                "url": url,
                "thumb_url": url,
                "attribution": attribution,
                "source": "GBIF",
                "source_url": f"https://www.gbif.org/occurrence/{gbif_key}" if gbif_key else None,
                "license": license_url,
                "user": user,
                "day": day,
            })
    return out


def pick_with_diversity(cands: list[dict], limit: int) -> list[dict]:
    """Pick up to `limit` photos applying (user, day) and (user, ~near) dedup."""
    chosen: list[dict] = []
    user_days: set[tuple[str, str]] = set()
    user_locs: dict[str, list[tuple[float, float]]] = defaultdict(list)
    seen_urls: set[str] = set()
    for c in cands:
        if c["url"] in seen_urls:
            continue
        key = (c["user"], c["day"])
        if c["user"] and key in user_days:
            continue
        too_close = False
        if c["user"]:
            for plat, plon in user_locs[c["user"]]:
                if haversine_m(c["lat"], c["lon"], plat, plon) < DEDUP_RADIUS_M:
                    too_close = True
                    break
        if too_close:
            continue
        chosen.append(c)
        seen_urls.add(c["url"])
        if c["user"]:
            user_days.add(key)
            user_locs[c["user"]].append((c["lat"], c["lon"]))
        if len(chosen) >= limit:
            break
    return chosen


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parks", help="comma-separated park ids (POC subset)")
    ap.add_argument("--limit", type=int, default=None,
                    help="cap on (park, species) pairs processed")
    ap.add_argument("--reset", action="store_true",
                    help="delete existing rows for processed parks first")
    args = ap.parse_args()

    db_path = ROOT / "data" / "parklife.db"
    db.init(db_path)
    with db.connect(db_path) as conn:
        conn.executescript(SCHEMA)

    park_filter = ""
    park_params: tuple = ()
    if args.parks:
        ids = [int(x) for x in args.parks.split(",") if x.strip()]
        placeholders = ",".join("?" * len(ids))
        park_filter = f"AND p.id IN ({placeholders})"
        park_params = tuple(ids)

    with db.connect(db_path) as conn:
        rows = list(conn.execute(f"""
            SELECT p.id AS park_id, p.slug, p.name_ja, p.prefecture,
                   p.lat, p.lon,
                   s.id AS species_id, s.inat_taxon_id, s.common_name_ja,
                   s.scientific_name
            FROM park_species ps
            JOIN park p   ON p.id  = ps.park_id
            JOIN species s ON s.id = ps.species_id
            WHERE p.lat IS NOT NULL AND p.lon IS NOT NULL
              AND COALESCE(s.kingdom,'') NOT IN ('archaea','bacteria','chromista','protozoa')
              {park_filter}
            ORDER BY p.id, s.id
        """, park_params))
    if args.limit:
        rows = rows[:args.limit]
    print(f"pairs to process: {len(rows)}", flush=True)

    if args.reset and args.parks:
        with db.connect(db_path) as conn:
            ids = [int(x) for x in args.parks.split(",") if x.strip()]
            ph = ",".join("?" * len(ids))
            n = conn.execute(
                f"DELETE FROM park_species_photo WHERE park_id IN ({ph})",
                tuple(ids),
            ).rowcount
            conn.commit()
            print(f"reset: deleted {n} existing rows for those parks")

    obs_cache: dict[int, list[dict]] = {}
    gbif_cache: dict[int, dict[str, list[dict]]] = {}  # park_id -> binomial idx
    tier0_pairs = tier1_pairs = empty_pairs = 0
    photos_inserted = 0
    gbif_contrib = inat_contrib = 0

    with db.connect(db_path) as conn:
        for i, r in enumerate(rows, 1):
            pid = r["park_id"]
            if pid not in gbif_cache:
                gbif_cache[pid] = load_gbif_park_index(r["prefecture"], r["slug"])
            gbif_idx = gbif_cache[pid]
            cands: list[dict] = []
            if r["scientific_name"] and r["scientific_name"] in gbif_idx:
                cands.extend(gbif_idx[r["scientific_name"]])
            tid = r["inat_taxon_id"]
            if tid:
                if tid not in obs_cache:
                    obs_cache[tid] = load_taxon_observations(tid)
                cands.extend(candidates_for_pair(r["lat"], r["lon"], obs_cache[tid]))
            cands.sort(key=lambda c: (c["tier"], c["dist"]))
            picks = pick_with_diversity(cands, MAX_PHOTOS)
            for p in picks:
                if p.get("source") == "GBIF":
                    gbif_contrib += 1
                else:
                    inat_contrib += 1
            if not picks:
                empty_pairs += 1
            elif picks[0]["tier"] == 0:
                tier0_pairs += 1
            else:
                tier1_pairs += 1
            for order, p in enumerate(picks):
                cur = conn.execute(
                    """INSERT OR IGNORE INTO park_species_photo
                       (park_id, species_id, url, thumb_url, attribution,
                        source, source_url, sort_order, tier)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (r["park_id"], r["species_id"], p["url"], p["thumb_url"],
                     p["attribution"], p.get("source", "iNaturalist"),
                     p["source_url"], order, p["tier"]),
                )
                photos_inserted += cur.rowcount
            if i % 2000 == 0:
                conn.commit()
                print(f"  [{i:>6}/{len(rows)}] tier0={tier0_pairs} "
                      f"tier1={tier1_pairs} empty={empty_pairs} "
                      f"rows+={photos_inserted}", flush=True)
        conn.commit()

    print("\n=== park_species_photo done ===")
    print(f"  pairs processed: {len(rows)}")
    print(f"  tier 0 (at park ≤{RADIUS_AT_PARK_M}m): {tier0_pairs}")
    print(f"  tier 1 (nearby  ≤{RADIUS_NEARBY_M}m):  {tier1_pairs}")
    print(f"  no local photo found:                  {empty_pairs}")
    print(f"  photo rows inserted: {photos_inserted}")
    print(f"  by source — GBIF: {gbif_contrib}, iNaturalist: {inat_contrib}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
