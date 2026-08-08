"""Backfill GBIF rich fields (recency + observer diversity) from the existing
cache — no network. eventDate/recordedBy are already in the slim GBIF cache
(GBIF_OCC_KEYS); we just never used them. Computes per (park, species):
  last_year      = max eventDate year   (recency / currentness)
  observer_count = distinct recordedBy  (confidence: many observers > repeats)
and UPDATEs the matching GBIF observation rows. individualCount is NOT in the
cache (needs a re-pull) — captured going forward by gbif.py + the whitelist.

Idempotent; batched so it coexists with a running ingest.
"""
from __future__ import annotations

import glob
import json
import sqlite3
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "parklife.db"
CACHE = ROOT / "data" / "cache" / "gbif"


def year(ed: str | None) -> int | None:
    if ed and len(ed) >= 4 and ed[:4].isdigit():
        return int(ed[:4])
    return None


def main() -> None:
    conn = sqlite3.connect(DB, timeout=120)
    conn.execute("PRAGMA busy_timeout = 120000")
    cols = lambda t: {r[1] for r in conn.execute(f"PRAGMA table_info({t})")}
    for tbl, defs in [("observation", ["last_year INTEGER", "observer_count INTEGER",
                                        "individual_count INTEGER"]),
                      ("park_species", ["last_year INTEGER", "observer_count INTEGER"])]:
        have = cols(tbl)
        for d in defs:
            name = d.split()[0]
            if name not in have:
                conn.execute(f"ALTER TABLE {tbl} ADD COLUMN {d}")
                print(f"added {tbl}.{name}")
    conn.commit()

    # maps: (prefecture, slug) -> park_id ; scientific_name -> species_id
    park_of = {(r[0], r[1]): r[2] for r in
               conn.execute("SELECT prefecture, slug, id FROM park")}
    sp_of = {r[0]: r[1] for r in
             conn.execute("SELECT scientific_name, id FROM species WHERE scientific_name IS NOT NULL")}

    files = glob.glob(str(CACHE / "*.json"))
    print(f"gbif cache files: {len(files)}")
    # agg[(park_id, species_id)] = [max_year, set(observers)]
    agg: dict[tuple[int, int], list] = defaultdict(lambda: [None, set()])
    missing_park = missing_sp = 0
    for i, fp in enumerate(files, 1):
        stem = Path(fp).stem
        if "__" not in stem:
            continue
        pref, slug = stem.split("__", 1)
        pid = park_of.get((pref, slug))
        if pid is None:
            missing_park += 1
            continue
        try:
            recs = json.loads(Path(fp).read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(recs, list):
            continue
        for r in recs:
            sci = r.get("species") or r.get("scientificName")
            sid = sp_of.get(sci)
            if sid is None:
                missing_sp += 1
                continue
            a = agg[(pid, sid)]
            y = year(r.get("eventDate"))
            if y and (a[0] is None or y > a[0]):
                a[0] = y
            rb = r.get("recordedBy")
            if rb:
                a[1].add(rb)
        if i % 800 == 0:
            print(f"  ...{i}/{len(files)} scanned")

    ups = [(mx, len(obs) or None, pid, sid)
           for (pid, sid), (mx, obs) in agg.items() if mx or obs]
    print(f"pairs to update: {len(ups)}  (unmapped park files={missing_park}, unmapped species recs={missing_sp})")
    for i in range(0, len(ups), 10000):
        conn.executemany(
            "UPDATE observation SET last_year=?, observer_count=? "
            "WHERE park_id=? AND species_id=? AND location_hint='GBIF'",
            ups[i:i + 10000])
        conn.commit()
    print("GBIF rich-field backfill done")
    conn.close()


if __name__ == "__main__":
    main()
