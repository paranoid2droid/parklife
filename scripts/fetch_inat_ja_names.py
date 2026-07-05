"""Fill common_name_ja for tid-bearing species from iNaturalist (locale=ja).

After the kana-alias backfill, ~5k reachable species still show only a Latin
binomial but DO have an ``inat_taxon_id``. iNaturalist often has a curated
Japanese vernacular that never entered our DB. Fetch ``/v1/taxa/<ids>?locale=ja``
(batched 30 ids/request, cached one JSON per taxon), and adopt
``preferred_common_name`` ONLY when it is genuinely Japanese (contains kana or
kanji — locale=ja falls back to the English name otherwise, which we reject).

Collision-guarded exactly like scripts.backfill_display_gaps: never give two
co-occurring species the same displayed name (keeps homonyms/synonyms apart), so
it adds no duplicate cards. Idempotent, cached, reversible (display_backfill_log).

    .venv/bin/python -m scripts.fetch_inat_ja_names --dry-run
    .venv/bin/python -m scripts.fetch_inat_ja_names
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
import time
from collections import defaultdict
from pathlib import Path

from curl_cffi import requests

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "parklife.db"
CACHE = ROOT / "data" / "cache" / "inat_ja"
API = "https://api.inaturalist.org/v1/taxa"
UA = "parklife/1.0 (biodiversity map; contact via github paranoid2droid/parklife)"
DELAY = 0.7
BATCH = 30

JAPANESE = re.compile(r"[ぁ-んァ-ヶ一-龠々〆ヶ]")


def fetch(tids: list[int]) -> dict[int, dict]:
    CACHE.mkdir(parents=True, exist_ok=True)
    need = [t for t in tids if not (CACHE / f"{t}.json").exists()]
    if need:
        ids = ",".join(str(t) for t in need)
        try:
            r = requests.get(f"{API}/{ids}", params={"locale": "ja"},
                             headers={"User-Agent": UA, "Accept-Language": "ja"},
                             impersonate="chrome", timeout=30)
            results = r.json().get("results", []) if r.status_code == 200 else []
        except Exception as e:
            print("  fetch error:", e); results = []
        by = {res.get("id"): res for res in results}
        for t in need:
            (CACHE / f"{t}.json").write_text(json.dumps(by.get(t) or {}, ensure_ascii=False))
        time.sleep(DELAY)
    out = {}
    for t in tids:
        try:
            out[t] = json.loads((CACHE / f"{t}.json").read_text() or "{}")
        except Exception:
            out[t] = {}
    return out


def main() -> int:
    dry = "--dry-run" in sys.argv
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE IF NOT EXISTS display_backfill_log (
        species_id INTEGER, field TEXT, old_value TEXT, new_value TEXT,
        source TEXT, ts TEXT DEFAULT (datetime('now')))""")

    # tid -> [species_id...] for reachable, unnamed, tid-bearing species
    tid_species: dict[int, list[int]] = defaultdict(list)
    for r in conn.execute("""
        SELECT s.id, s.inat_taxon_id FROM species s
        WHERE (s.common_name_ja IS NULL OR s.common_name_ja='')
          AND s.inat_taxon_id IS NOT NULL
          AND EXISTS (SELECT 1 FROM park_species ps WHERE ps.species_id=s.id)"""):
        tid_species[r["inat_taxon_id"]].append(r["id"])
    tids = sorted(tid_species)
    print(f"candidate taxa: {len(tids)} tids over {sum(len(v) for v in tid_species.values())} species")

    # fetch (batched) and keep only genuinely-Japanese names
    proposed: dict[int, str] = {}   # species_id -> ja name
    got = rejected = 0
    for i in range(0, len(tids), BATCH):
        chunk = tids[i:i + BATCH]
        res = fetch(chunk)
        for t in chunk:
            nm = (res.get(t) or {}).get("preferred_common_name") or ""
            if nm and JAPANESE.search(nm):
                for sid in tid_species[t]:
                    proposed[sid] = nm
                got += 1
            elif nm:
                rejected += 1
        if not dry and i and i % (BATCH * 20) == 0:
            print(f"  ...{i}/{len(tids)} tids, {got} ja names so far")
    print(f"iNat returned a Japanese name for {got} taxa "
          f"({rejected} had only a non-Japanese name, skipped)")

    # collision guard (greedy, most-widespread first) — no duplicate cards
    npark = dict(conn.execute("SELECT species_id, COUNT(*) FROM park_species GROUP BY species_id"))
    sp_parks: dict[int, list[int]] = defaultdict(list)
    for sid, pid in conn.execute("SELECT species_id, park_id FROM park_species"):
        sp_parks[sid].append(pid)
    park_names: dict[int, set] = defaultdict(set)
    for pid, nm in conn.execute("""SELECT ps.park_id, s.common_name_ja FROM park_species ps
        JOIN species s ON s.id=ps.species_id
        WHERE s.common_name_ja IS NOT NULL AND s.common_name_ja!=''"""):
        park_names[pid].add(nm)

    pick: dict[int, str] = {}
    collisions = 0
    for sid in sorted(proposed, key=lambda s: (-npark.get(s, 0), s)):
        nm = proposed[sid]
        if any(nm in park_names[p] for p in sp_parks.get(sid, [])):
            collisions += 1
            continue
        pick[sid] = nm
        for p in sp_parks.get(sid, []):
            park_names[p].add(nm)

    print(f"assignable: {len(pick)} species "
          f"({collisions} skipped to avoid duplicate cards)")
    for sid, nm in list(pick.items())[:8]:
        print(f"  {sid}: {nm}")

    if dry:
        print("\n--dry-run: no DB writes")
        return 0
    for sid, nm in pick.items():
        conn.execute("INSERT INTO display_backfill_log(species_id,field,old_value,new_value,source)"
                     " VALUES(?,?,?,?,?)", (sid, "common_name_ja", None, nm, "inat-ja"))
        conn.execute("UPDATE species SET common_name_ja=? WHERE id=?", (nm, sid))
        conn.execute("INSERT OR IGNORE INTO species_alias(species_id,raw_name,lang)"
                     " VALUES(?,?,?)", (sid, nm, "ja"))
    conn.commit()
    print(f"\nwrote {len(pick)} common_name_ja from iNat (reversible via display_backfill_log)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
