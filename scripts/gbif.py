"""Phase E: GBIF occurrence enrichment.

For each park with lat/lon, query GBIF's occurrence/search endpoint
for records within RADIUS_KM. Aggregate to unique species (dedup by
speciesKey, accumulate count), then ingest as observations. Complements
iNaturalist by adding museum specimens and non-iNat citizen-science feeds.

Rate limit: GBIF asks for "reasonable" use; 1 req/sec is well under that.
Cache:    data/cache/gbif/<prefecture>__<slug>.json (combined raw pages)
Endpoint: https://api.gbif.org/v1/occurrence/search

Idempotency: same as inaturalist.py — observation upsert dedupes on
(park_id, species_id, source_id), so repeated runs are no-ops once cache
is warm.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from curl_cffi import requests

from parklife import db

ROOT = Path(__file__).resolve().parent.parent
UA = "parklife-bot/0.1 (research; contact: paranoid2droid@gmail.com)"
API = "https://api.gbif.org/v1/occurrence/search"

RADIUS_KM = 1.5
PAGE_LIMIT = 300
MAX_PAGES = 5  # cap at 1500 occurrences per park; almost always covers full diversity

# Animal classes → our taxon_group taxonomy
CLASS_TO_GROUP = {
    "Aves": "bird",
    "Mammalia": "mammal",
    "Reptilia": "reptile",
    "Testudines": "reptile",
    "Amphibia": "amphibian",
    "Insecta": "insect",
    "Arachnida": "arachnid",
    "Collembola": "springtail",
    "Bivalvia": "mollusk",
    "Gastropoda": "mollusk",
    "Cephalopoda": "mollusk",
    "Polyplacophora": "mollusk",
    "Scaphopoda": "mollusk",
    "Actinopterygii": "fish",
    "Chondrichthyes": "fish",
    "Elasmobranchii": "fish",
    "Cephalaspidomorphi": "fish",
    "Myxini": "fish",
    "Malacostraca": "crustacean",
    "Maxillopoda": "crustacean",
    "Branchiopoda": "crustacean",
    "Copepoda": "crustacean",
    "Ostracoda": "crustacean",
    "Chilopoda": "myriapod",
    "Diplopoda": "myriapod",
    "Echinoidea": "echinoderm",
    "Asteroidea": "echinoderm",
    "Ophiuroidea": "echinoderm",
    "Scyphozoa": "cnidarian",
    "Anthozoa": "cnidarian",
    "Hydrozoa": "cnidarian",
    "Cubozoa": "cnidarian",
    "Polychaeta": "annelid",
    "Clitellata": "annelid",
    "Pycnogonida": "sea_spider",
    "Chromadorea": "nematode",
    "Eurotatoria": "rotifer",
    "Stenolaemata": "bryozoan",
    "Rhynchonellata": "brachiopod",
}

PHYLUM_TO_GROUP = {
    "Arthropoda": "arthropod",
    "Echinodermata": "echinoderm",
    "Mollusca": "mollusk",
    "Annelida": "annelid",
    "Cnidaria": "cnidarian",
    "Platyhelminthes": "flatworm",
    "Nematoda": "nematode",
    "Rotifera": "rotifer",
    "Bryozoa": "bryozoan",
    "Brachiopoda": "brachiopod",
}

ORDER_TO_GROUP = {
    "Aulopiformes": "fish",
    "Beryciformes": "fish",
    "Cypriniformes": "fish",
    "Cyprinodontiformes": "fish",
    "Gadiformes": "fish",
    "Gobiesociformes": "fish",
    "Lophiiformes": "fish",
    "Mugiliformes": "fish",
    "Perciformes": "fish",
    "Pleuronectiformes": "fish",
    "Scorpaeniformes": "fish",
    "Syngnathiformes": "fish",
    "Tetraodontiformes": "fish",
    "Zeiformes": "fish",
}
FAMILY_TO_GROUP = {
    "Cheloniidae": "reptile",
}
# Kingdom-level fallback when class doesn't map (plants, fungi, etc.)
KINGDOM_TO_GROUP = {
    "Plantae": "plant",
    "Fungi": "mushroom",
}


def cache_path(slug: str, prefecture: str) -> Path:
    return ROOT / "data" / "cache" / "gbif" / f"{prefecture}__{slug}.json"


def fetch_park(slug: str, prefecture: str, lat: float, lon: float) -> tuple[str, list[dict]]:
    """Return ("cache"|"network", list_of_occurrence_records)."""
    cp = cache_path(slug, prefecture)
    cp.parent.mkdir(parents=True, exist_ok=True)
    if cp.exists():
        return ("cache", json.loads(cp.read_text(encoding="utf-8")))

    geo = f"{lat},{lon},{RADIUS_KM}km"
    all_results: list[dict] = []
    failed = False
    for page in range(MAX_PAGES):
        params = {
            "geoDistance": geo,
            "hasCoordinate": "true",
            "limit": PAGE_LIMIT,
            "offset": page * PAGE_LIMIT,
        }
        try:
            r = requests.get(
                API, params=params, headers={"User-Agent": UA},
                timeout=90, impersonate="chrome",
            )
        except Exception as e:
            print(f"    network error on {slug} page {page}: {type(e).__name__}: {e}")
            failed = True
            break
        if r.status_code != 200:
            print(f"    HTTP {r.status_code} on {slug} page {page}")
            break
        data = r.json()
        results = data.get("results") or []
        all_results.extend(results)
        if data.get("endOfRecords") or len(results) < PAGE_LIMIT:
            break
        time.sleep(1.0)

    # Don't cache on failure — let the next run retry
    if failed and not all_results:
        return ("error", [])
    # Partial success (some pages OK, then timeout) — cache what we have
    cp.write_text(json.dumps(all_results, ensure_ascii=False), encoding="utf-8")
    return ("network", all_results)


def aggregate_species(occurrences: list[dict]) -> dict[int, dict]:
    """Dedupe by speciesKey, accumulate occurrence counts + best metadata seen."""
    out: dict[int, dict] = {}
    for occ in occurrences:
        sk = occ.get("speciesKey")
        if not sk:
            continue
        info = out.get(sk)
        if info is None:
            cls = occ.get("class") or ""
            kingdom = occ.get("kingdom") or ""
            phylum = occ.get("phylum") or ""
            order = occ.get("order") or ""
            family = occ.get("family") or ""
            tg = (CLASS_TO_GROUP.get(cls)
                  or ORDER_TO_GROUP.get(order)
                  or FAMILY_TO_GROUP.get(family)
                  or PHYLUM_TO_GROUP.get(phylum)
                  or KINGDOM_TO_GROUP.get(kingdom))
            out[sk] = {
                "species": occ.get("species"),
                "scientific_name": occ.get("scientificName"),
                "kingdom": kingdom.lower() or None,
                "class": cls or None,
                "taxon_group": tg,
                "vernacular": occ.get("vernacularName") or None,
                "count": 1,
            }
        else:
            info["count"] += 1
    return out


def upsert_species(conn, sci_name: str, kingdom: str | None, taxon_group: str | None) -> int | None:
    if not sci_name:
        return None
    row = conn.execute("SELECT id FROM species WHERE scientific_name=?", (sci_name,)).fetchone()
    if row:
        sid = row["id"]
        conn.execute(
            """UPDATE species SET kingdom = COALESCE(kingdom, ?),
                                  taxon_group = COALESCE(taxon_group, ?)
               WHERE id=?""",
            (kingdom, taxon_group, sid),
        )
        return sid
    cur = conn.execute(
        """INSERT INTO species (scientific_name, kingdom, taxon_group)
           VALUES (?, ?, ?)""",
        (sci_name, kingdom, taxon_group),
    )
    return cur.lastrowid


def insert_source(conn, park_id: int, prefecture: str, slug: str, url: str) -> int:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rel = f"data/cache/gbif/{prefecture}__{slug}.json"
    cur = conn.execute(
        """INSERT OR IGNORE INTO source (park_id, url, fetched_at, http_status,
                                         content_sha256, raw_path)
           VALUES (?, ?, ?, 200, NULL, ?)""",
        (park_id, url, now, rel),
    )
    if cur.lastrowid:
        return cur.lastrowid
    row = conn.execute(
        "SELECT id FROM source WHERE park_id=? AND url=? ORDER BY id DESC LIMIT 1",
        (park_id, url),
    ).fetchone()
    return row["id"] if row else 0


def main(prefecture_filter: str | None = None, max_parks: int | None = None) -> int:
    db_path = ROOT / "data" / "parklife.db"
    with db.connect(db_path) as conn:
        sql = ("SELECT id, slug, prefecture, lat, lon, name_ja FROM park "
               "WHERE lat IS NOT NULL AND lon IS NOT NULL")
        params: list = []
        if prefecture_filter:
            sql += " AND prefecture=?"
            params.append(prefecture_filter)
        sql += " ORDER BY prefecture, name_ja"
        parks = list(conn.execute(sql, params))
    if max_parks:
        parks = parks[:max_parks]
    print(f"parks to enrich via GBIF: {len(parks)}")

    total_inserted = 0
    cache_hits = 0
    network_calls = 0

    with db.connect(db_path) as conn:
        for i, p in enumerate(parks, 1):
            src, occurrences = fetch_park(p["slug"], p["prefecture"], p["lat"], p["lon"])
            if src == "cache":
                cache_hits += 1
            else:
                network_calls += 1
                time.sleep(1.0)
            if not occurrences:
                if i % 20 == 0:
                    print(f"  [{i:>3}/{len(parks)}] {p['slug']:<25} (no occurrences)")
                continue

            species_map = aggregate_species(occurrences)
            api_url = f"{API}?geoDistance={p['lat']},{p['lon']},{RADIUS_KM}km"
            src_id = insert_source(conn, p["id"], p["prefecture"], p["slug"], api_url)

            park_inserted = 0
            for info in species_map.values():
                # GBIF's `species` is the binomial without author; `scientificName`
                # may include author. Prefer the binomial for our schema.
                sci = info.get("species") or info.get("scientific_name")
                if not sci:
                    continue
                sid = upsert_species(conn, sci, info.get("kingdom"), info.get("taxon_group"))
                if not sid:
                    continue
                conn.execute(
                    """INSERT OR IGNORE INTO species_alias (species_id, raw_name, lang, status)
                       VALUES (?, ?, 'sci', 'resolved')""",
                    (sid, sci),
                )
                if info.get("vernacular"):
                    conn.execute(
                        """INSERT OR IGNORE INTO species_alias (species_id, raw_name, lang, status)
                           VALUES (?, ?, 'en', 'resolved')""",
                        (sid, info["vernacular"]),
                    )
                # Dedup against any prior GBIF row for this (park, species).
                # Source rows multiply on rerun (different fetched_at), so we
                # match on the location_hint tag instead of source_id.
                existing = conn.execute(
                    """SELECT id FROM observation
                       WHERE park_id=? AND species_id=? AND location_hint='GBIF'""",
                    (p["id"], sid),
                ).fetchone()
                if existing:
                    continue
                conn.execute(
                    """INSERT INTO observation
                       (park_id, species_id, raw_name, months_bitmap,
                        location_hint, characteristics, source_id)
                       VALUES (?, ?, ?, NULL, ?, ?, ?)""",
                    (p["id"], sid, sci, "GBIF",
                     f"GBIF occurrences: {info['count']}", src_id),
                )
                park_inserted += 1
                total_inserted += 1
            conn.commit()
            if i % 10 == 0 or park_inserted:
                print(f"  [{i:>3}/{len(parks)}] {p['slug']:<25} +{park_inserted} "
                      f"(total ins={total_inserted} cache={cache_hits} net={network_calls})")

    print(f"\n=== GBIF enrichment done ===")
    print(f"  parks processed: {len(parks)}")
    print(f"  cache hits: {cache_hits}  network calls: {network_calls}")
    print(f"  observations inserted: {total_inserted}")
    return 0


if __name__ == "__main__":
    pref = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] in {"tokyo", "kanagawa", "chiba", "saitama"} else None
    cap = int(sys.argv[2]) if len(sys.argv) > 2 else None
    sys.exit(main(prefecture_filter=pref, max_parks=cap))
