"""Gap #8: Populate species.inat_taxon_id and species.photo_url by
re-reading the cached iNat species_counts JSONs (data/cache/inat/ and
data/cache/inat_monthly/). No new network calls.

Each cached JSON has results[*].taxon with `id`, `name`, `default_photo`.
We match by scientific_name (most reliable) or by preferred_common_name.

Run idempotently: only updates rows whose photo_url is currently NULL.
"""

from __future__ import annotations

import json
from pathlib import Path

from parklife import db

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIRS = [ROOT / "data" / "cache" / "inat",
              ROOT / "data" / "cache" / "inat_monthly"]


def best_photo_url(default_photo: dict | None) -> str | None:
    if not isinstance(default_photo, dict):
        return None
    return (default_photo.get("medium_url")
            or default_photo.get("url")
            or default_photo.get("square_url"))


def main() -> None:
    db_path = ROOT / "data" / "parklife.db"
    # collect best (taxon_id, photo_url) per scientific_name and per ja name
    sci_map: dict[str, tuple[int, str | None]] = {}
    ja_map:  dict[str, tuple[int, str | None]] = {}
    files_scanned = 0
    for d in CACHE_DIRS:
        if not d.is_dir():
            continue
        for f in d.glob("*.json"):
            files_scanned += 1
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            for r in (data.get("results") or []):
                t = r.get("taxon") or {}
                tid = t.get("id")
                sci = t.get("name")
                ja = t.get("preferred_common_name")
                photo = best_photo_url(t.get("default_photo"))
                if not tid:
                    continue
                if sci and sci not in sci_map:
                    sci_map[sci] = (tid, photo)
                if ja and ja not in ja_map:
                    ja_map[ja] = (tid, photo)
    print(f"scanned {files_scanned} cached files")
    print(f"  sci_map keys: {len(sci_map)}, ja_map keys: {len(ja_map)}")

    updated = 0
    with db.connect(db_path) as conn:
        rows = list(conn.execute(
            "SELECT id, scientific_name, common_name_ja FROM species "
            "WHERE photo_url IS NULL OR inat_taxon_id IS NULL"
        ))
        for r in rows:
            tid_photo = None
            if r["scientific_name"] and r["scientific_name"] in sci_map:
                tid_photo = sci_map[r["scientific_name"]]
            elif r["common_name_ja"] and r["common_name_ja"] in ja_map:
                tid_photo = ja_map[r["common_name_ja"]]
            if not tid_photo:
                continue
            tid, photo = tid_photo
            conn.execute(
                "UPDATE species SET inat_taxon_id = COALESCE(inat_taxon_id, ?), "
                "photo_url = COALESCE(photo_url, ?) WHERE id=?",
                (tid, photo, r["id"]),
            )
            updated += 1
        conn.commit()
    print(f"updated {updated} species rows with iNat taxon_id / photo_url")


if __name__ == "__main__":
    main()
