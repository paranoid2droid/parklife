"""Ingest GBIF *coordinate-less* occurrences as the 'admin:municipality' tier.

Complements scripts.gbif (which only ingests hasCoordinate=true within a radius).
~66% of Japan's beetle records in GBIF have no coordinates — museum specimens
carrying romaji stateProvince+county only. This script recovers them: per species
we already track, pull GBIF's coord-less records, group by (prefecture, 市区町村),
resolve to parks via parklife.admin_match (fail-closed gates), and insert an
observation tagged evidence_tier='admin:municipality' for each park in that
municipality.

Idempotent: observations dedup on (park_id, species_id, location_hint='GBIF-admin');
per-species GBIF pulls cache under data/cache/gbif_admin/. Re-run scripts.dedupe
afterwards to fold the new tier into park_species.

Usage:
    python -m scripts.gbif_admin --group insect --limit 200
    python -m scripts.gbif_admin "Coccinella septempunctata" "Trypoxylus dichotomus"
    python -m scripts.gbif_admin --group insect            # whole group
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from parklife import admin_match, db

ROOT = Path(__file__).resolve().parent.parent
UA = "parklife-bot/0.1 (research; contact: paranoid2droid@gmail.com)"
GBIF = "https://api.gbif.org/v1"
CACHE = ROOT / "data" / "cache" / "gbif_admin"
MAX_REC = 3000            # cap coord-less pull per species (common ones have thousands)
PAGE = 300


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    return json.load(urllib.request.urlopen(req, timeout=60))


_TK_CACHE = CACHE / "_taxonkeys.json"   # {scientific_name: usageKey or 0}
_tk: dict | None = None
_tk_dirty = 0


def _tk_load() -> dict:
    global _tk
    if _tk is None:
        _tk = json.loads(_TK_CACHE.read_text()) if _TK_CACHE.exists() else {}
    return _tk


def _tk_save(force: bool = False) -> None:
    global _tk_dirty
    if _tk is None:
        return
    _tk_dirty += 1
    if force or _tk_dirty % 100 == 0:
        CACHE.mkdir(parents=True, exist_ok=True)
        _TK_CACHE.write_text(json.dumps(_tk, ensure_ascii=False))


def taxon_key(sci: str) -> int | None:
    """sci -> GBIF usageKey, cached on disk so resume skips already-matched species
    without a live API call (0 = no match, also cached)."""
    tk = _tk_load()
    if sci in tk:
        return tk[sci] or None
    d = _get(f"{GBIF}/species/match?" + urllib.parse.urlencode({"name": sci}))
    key = d.get("usageKey") if d.get("matchType") != "NONE" else None
    tk[sci] = key or 0
    _tk_save()
    return key


def coordless_pairs(sci: str) -> dict[tuple[str, str], int] | None:
    """{(stateProvince, county): record_count} for a species' coord-less JP records.
    Cached per taxonKey. Returns None if the species can't be matched in GBIF."""
    CACHE.mkdir(parents=True, exist_ok=True)
    key = taxon_key(sci)
    if not key:
        return None
    cp = CACHE / f"{key}.json"
    if cp.exists():
        raw = json.loads(cp.read_text())
        return {tuple(k.split("\t")): v for k, v in raw.items()}
    pairs: dict[tuple[str, str], int] = defaultdict(int)
    for off in range(0, MAX_REC, PAGE):
        d = _get(f"{GBIF}/occurrence/search?" + urllib.parse.urlencode({
            "taxonKey": key, "country": "JP", "hasCoordinate": "false",
            "limit": PAGE, "offset": off}))
        for r in d.get("results", []):
            sp, co = r.get("stateProvince"), r.get("county")
            if sp and co:
                pairs[(sp.strip(), co.strip())] += 1
        if d.get("endOfRecords"):
            break
        time.sleep(0.5)
    cp.write_text(json.dumps({"\t".join(k): v for k, v in pairs.items()}, ensure_ascii=False))
    return dict(pairs)


def insert_admin_source(conn, park_id: int, taxon_key_url: str) -> int:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    cur = conn.execute(
        """INSERT OR IGNORE INTO source (park_id, url, fetched_at, http_status,
                                         content_sha256, raw_path)
           VALUES (?, ?, ?, 200, NULL, NULL)""",
        (park_id, taxon_key_url, now),
    )
    if cur.lastrowid:
        return cur.lastrowid
    row = conn.execute(
        "SELECT id FROM source WHERE park_id=? AND url=? ORDER BY id DESC LIMIT 1",
        (park_id, taxon_key_url),
    ).fetchone()
    return row["id"] if row else 0


def select_species(conn, names: list[str], group: str | None,
                   kingdom: str | None, limit: int | None):
    if names:
        q = ("SELECT id, scientific_name, common_name_ja FROM species "
             "WHERE scientific_name IN (%s)" % ",".join("?" * len(names)))
        return conn.execute(q, names).fetchall()
    sql = ("SELECT id, scientific_name, common_name_ja FROM species "
           "WHERE scientific_name IS NOT NULL AND scientific_name!=''")
    params: list = []
    if group:
        sql += " AND taxon_group=?"
        params.append(group)
    if kingdom:
        sql += " AND kingdom=?"
        params.append(kingdom)
    sql += " ORDER BY id"
    if limit:
        sql += f" LIMIT {int(limit)}"
    return conn.execute(sql, params).fetchall()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("names", nargs="*", help="scientific names (default: --group/all)")
    ap.add_argument("--group", help="taxon_group filter, e.g. insect")
    ap.add_argument("--kingdom", help="kingdom filter, e.g. animalia")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    db_path = ROOT / "data" / "parklife.db"
    with db.connect(db_path) as conn:
        species = select_species(conn, args.names, args.group, args.kingdom, args.limit)
        print(f"species to process: {len(species)}")
        admin_match._load_parks(conn)  # warm the gazetteer once

        tot_obs = tot_parks = tot_species_hit = net = 0
        for i, s in enumerate(species, 1):
            sci = s["scientific_name"]
            try:
                pairs = coordless_pairs(sci)
            except Exception as e:
                print(f"  [{i}] {sci}: fetch error {type(e).__name__}")
                continue
            if not pairs:
                continue
            sci_q = urllib.parse.quote(sci)
            parks_for_species: set[int] = set()
            for (state, county), n in pairs.items():
                pids = admin_match.resolve(conn, state, county)
                for pid in pids:
                    parks_for_species.add(pid)
                    if args.dry_run:
                        continue
                    dup = conn.execute(
                        "SELECT 1 FROM observation WHERE park_id=? AND species_id=? "
                        "AND location_hint='GBIF-admin'", (pid, s["id"])).fetchone()
                    if dup:
                        continue
                    # url must be unique per (park, species): source has UNIQUE(url, fetched_at)
                    key_url = f"{GBIF}/occurrence/search?taxonKey_of={sci_q}&hasCoordinate=false&park={pid}"
                    src_id = insert_admin_source(conn, pid, key_url)
                    conn.execute(
                        """INSERT INTO observation
                           (park_id, species_id, raw_name, months_bitmap,
                            location_hint, characteristics, source_id, evidence_tier)
                           VALUES (?, ?, ?, NULL, 'GBIF-admin', ?, ?, 'admin:municipality')""",
                        (pid, s["id"], sci, f"GBIF admin-match: {county} ({n} recs)", src_id),
                    )
                    tot_obs += 1
            if parks_for_species:
                tot_species_hit += 1
                tot_parks += len(parks_for_species)
            if not args.dry_run:
                conn.commit()
            if parks_for_species:
                print(f"  [{i}/{len(species)}] {sci[:34]:34} {s['common_name_ja'] or '':10} "
                      f"-> {len(parks_for_species):>3} parks")

    _tk_save(force=True)
    print(f"\n=== gbif_admin done ({'DRY-RUN' if args.dry_run else 'written'}) ===")
    print(f"  species with ≥1 admin park: {tot_species_hit}")
    print(f"  observations inserted: {tot_obs}")
    print(f"  (avg parks/hit species: {tot_parks/max(1,tot_species_hit):.1f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
