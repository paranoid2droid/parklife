"""Rebuild the `park_species` derived table.

Aggregates every `observation` row by (park_id, species_id):
  - months_bitmap = bitwise OR of source bitmaps (NULL counted as 0)
  - observation_count = number of source rows
  - source_count = number of distinct source_id values
  - raw_names = pipe-joined unique raw_name strings
  - location_hints / characteristics = '; '-joined unique non-empty values

Run after any ingestion change. Idempotent: drops and refills the table.
Skips observation rows where species_id IS NULL (we can't dedup unresolved
names — they stay only in the observation table for traceability).
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from parklife import db

ROOT = Path(__file__).resolve().parent.parent


def _join_unique(values, sep="; ") -> str | None:
    seen: list[str] = []
    for v in values:
        if v is None:
            continue
        v = str(v).strip()
        if not v or v in seen:
            continue
        seen.append(v)
    return sep.join(seen) if seen else None


def main() -> None:
    db_path = ROOT / "data" / "parklife.db"
    db.init(db_path)  # ensure park_species table exists
    with db.connect(db_path) as conn:
        # Species too microscopic to be a park "sighting" — kept in `observation`
        # for provenance but never surfaced in the clean park_species listing.
        # Bacteria/viruses/archaea are always dropped; protozoa/chromista only
        # when they lack a Japanese vernacular (so slime molds ススホコリ and
        # seaweeds ワカメ/ヒジキ, which DO have one, stay).
        noise = {r[0] for r in conn.execute("""
            SELECT id FROM species WHERE
                kingdom IN ('bacteria','viruses','archaea')
                OR (kingdom IN ('protozoa','chromista')
                    AND (common_name_ja IS NULL OR common_name_ja=''))
        """)}
        # plus species flagged by scripts.audit_scrape_only / reresolve_scrape_species
        # (scrape-derived, no iNat/GBIF corroboration, no valid re-map) — kept in
        # `observation` for provenance, excluded from the clean listing.
        _sup = ROOT / "data" / "suppressed_species.json"
        if _sup.exists():
            import json as _json
            noise |= {int(k) for k in _json.loads(_sup.read_text())}

        rows = conn.execute("""
            SELECT park_id, species_id, months_bitmap, raw_name,
                   location_hint, characteristics, source_id, evidence_tier,
                   obs_count, last_year, observer_count, individual_count
            FROM observation
            WHERE species_id IS NOT NULL
        """).fetchall()

        # 'onsite' (radius/scrape) outranks 'admin:municipality' (coarse regional).
        # The pair's tier is the strongest tier seen across its observations.
        TIER_RANK = {"onsite": 0, "admin:municipality": 1}

        # aggregate in Python (BIT_OR isn't available in this SQLite build)
        agg: dict[tuple[int, int], dict] = defaultdict(lambda: {
            "months": 0, "count": 0, "sources": set(),
            "raw_names": [], "loc": [], "chars": [], "tier": "admin:municipality",
            "abundance": 0, "indiv": 0, "last_year": None, "observers": 0,
        })
        for r in rows:
            if r["species_id"] in noise:
                continue
            key = (r["park_id"], r["species_id"])
            a = agg[key]
            a["months"] |= (r["months_bitmap"] or 0)
            a["count"] += 1
            if r["source_id"] is not None:
                a["sources"].add(r["source_id"])
            a["raw_names"].append(r["raw_name"])
            a["loc"].append(r["location_hint"])
            a["chars"].append(r["characteristics"])
            tier = r["evidence_tier"] or "onsite"
            if TIER_RANK.get(tier, 9) < TIER_RANK.get(a["tier"], 9):
                a["tier"] = tier
            # abundance = strongest on-site source signal (MAX, not SUM: iNat
            # monthly rows would otherwise multiply the same sightings). Admin
            # rows are regional record tallies, not on-site abundance — skip.
            if tier == "onsite" and r["obs_count"]:
                a["abundance"] = max(a["abundance"], r["obs_count"])
            if tier == "onsite" and r["individual_count"]:
                a["indiv"] = max(a["indiv"], r["individual_count"])
            if r["last_year"] and (a["last_year"] is None or r["last_year"] > a["last_year"]):
                a["last_year"] = r["last_year"]
            if r["observer_count"]:
                a["observers"] = max(a["observers"], r["observer_count"])

        conn.execute("DELETE FROM park_species")
        inserted = 0
        for (pid, sid), a in agg.items():
            conn.execute(
                """INSERT INTO park_species
                   (park_id, species_id, months_bitmap, observation_count,
                    source_count, raw_names, location_hints, characteristics,
                    evidence_tier, abundance, last_year, observer_count)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    pid, sid,
                    a["months"] or None,  # 0 → NULL (truly unknown vs known-no-month)
                    a["count"],
                    len(a["sources"]),
                    _join_unique(a["raw_names"], sep="|"),
                    _join_unique(a["loc"]),
                    _join_unique(a["chars"]),
                    a["tier"],
                    # prefer survey individual counts (モニタリングサイト1000 etc.) as
                    # the abundance signal; fall back to occurrence count.
                    (a["indiv"] or a["abundance"]) or None,
                    a["last_year"],
                    a["observers"] or None,
                ),
            )
            inserted += 1
        conn.commit()
    print(f"rebuilt park_species: {inserted} rows from {len(rows)} observations")
    print(f"  dedup ratio: {inserted/max(1,len(rows)):.1%}")


if __name__ == "__main__":
    main()
