"""Export the database to a portable JSON snapshot.

Output: data/export/parklife.json with the structure:
  {
    "generated_at": ISO-8601,
    "stats": { ... },
    "parks": [
      { "slug": ..., "name_ja": ..., "prefecture": ..., "lat": ..., "lon": ...,
        "observations": [
          { "raw_name": ..., "species": {...}, "months": [3,4,5], ... }
        ]
      }
    ],
    "species": [
      { "id": ..., "common_name_ja": ..., "scientific_name": ..., "taxon_group": ... }
    ]
  }

Designed so the JSON can drive a future map-based UI without DB access.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from parklife import db

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    db_path = ROOT / "data" / "parklife.db"
    out_dir = ROOT / "data" / "export"
    out_dir.mkdir(parents=True, exist_ok=True)
    with db.connect(db_path) as conn:
        species_rows = list(conn.execute(
            "SELECT id, scientific_name, common_name_ja, common_name_en, "
            "kingdom, taxon_group FROM species ORDER BY id"
        ))
        species_by_id = {r["id"]: dict(r) for r in species_rows}

        park_rows = list(conn.execute(
            "SELECT id, slug, name_ja, name_en, prefecture, municipality, "
            "operator, official_url, lat, lon FROM park ORDER BY prefecture, slug"
        ))
        parks_out: list[dict] = []
        for p in park_rows:
            # Deduped per-park species (use park_species)
            ps_rows = list(conn.execute("""
                SELECT species_id, months_bitmap, raw_names, location_hints,
                       characteristics, observation_count, source_count
                FROM park_species WHERE park_id=?
                ORDER BY species_id
            """, (p["id"],)))
            sp_out = []
            for o in ps_rows:
                months = [m+1 for m in range(12) if (o["months_bitmap"] or 0) & (1<<m)] or None
                sp = species_by_id.get(o["species_id"])
                sp_out.append({
                    "species_id": o["species_id"],
                    "scientific_name": sp["scientific_name"] if sp else None,
                    "common_name_ja": sp["common_name_ja"] if sp else None,
                    "common_name_en": sp["common_name_en"] if sp else None,
                    "kingdom": sp["kingdom"] if sp else None,
                    "taxon_group": sp["taxon_group"] if sp else None,
                    "months": months,
                    "raw_names": (o["raw_names"] or "").split("|"),
                    "location_hints": o["location_hints"],
                    "characteristics": o["characteristics"],
                    "observation_count": o["observation_count"],
                    "source_count": o["source_count"],
                })
            parks_out.append({
                "slug": p["slug"], "name_ja": p["name_ja"], "name_en": p["name_en"],
                "prefecture": p["prefecture"], "municipality": p["municipality"],
                "operator": p["operator"], "official_url": p["official_url"],
                "lat": p["lat"], "lon": p["lon"],
                "species_count": len(sp_out),
                "species": sp_out,
            })
        stats = {
            "parks_total": len(park_rows),
            "parks_with_obs": sum(1 for p in parks_out if p["species_count"]),
            "species_total": len(species_rows),
            "park_species_pairs": sum(p["species_count"] for p in parks_out),
            "by_kingdom": {},
            "by_taxon_group": {},
        }
        for r in conn.execute(
            "SELECT COALESCE(kingdom,'?') AS k, COUNT(*) FROM species GROUP BY k"
        ):
            stats["by_kingdom"][r[0]] = r[1]
        for r in conn.execute(
            "SELECT COALESCE(taxon_group,'?') AS g, COUNT(DISTINCT s.id) AS sp, COUNT(o.id) AS obs "
            "FROM species s LEFT JOIN observation o ON o.species_id=s.id GROUP BY g"
        ):
            stats["by_taxon_group"][r[0]] = {"species": r[1], "observations": r[2]}

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "stats": stats,
        "parks": parks_out,
        "species": species_rows and [dict(r) for r in species_rows],
    }
    full = out_dir / "parklife.json"
    full.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    # also a compact NDJSON of deduped (park, species, months) tuples
    compact = out_dir / "park_species.ndjson"
    with compact.open("w", encoding="utf-8") as f:
        for p in parks_out:
            for o in p["species"]:
                f.write(json.dumps({
                    "park_slug": p["slug"], "park_name": p["name_ja"],
                    "prefecture": p["prefecture"], "lat": p["lat"], "lon": p["lon"],
                    "species_ja": o["common_name_ja"], "species_sci": o["scientific_name"],
                    "taxon_group": o["taxon_group"], "kingdom": o["kingdom"],
                    "months": o["months"],
                    "source_count": o["source_count"],
                }, ensure_ascii=False) + "\n")
    print(f"wrote {full}  ({full.stat().st_size//1024} KB)")
    print(f"wrote {compact}  ({compact.stat().st_size//1024} KB)")
    print(f"stats: {json.dumps(stats, ensure_ascii=False, indent=2)}")


if __name__ == "__main__":
    main()
