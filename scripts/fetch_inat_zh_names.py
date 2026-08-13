"""Fill Chinese aliases (zh-Hans + zh-Hant) for tid-bearing species from iNaturalist.

Thousands of visible species have a real katakana ``common_name_ja`` and an
``inat_taxon_id`` but no Chinese alias. iNaturalist curators enter simplified-
Chinese vernaculars (``locale=zh-CN``) that never entered our DB. Fetch
``/v1/taxa/<ids>?locale=zh-CN`` (batched, one JSON cached per taxon) and adopt
``preferred_common_name`` ONLY when it is genuinely Chinese and the returned
taxon's scientific ``name`` matches ours (fail-closed identity gate — never
attach a name fetched for a different taxon). zh-Hant is derived from the
simplified form via OpenCC (iNat's zh-TW is sparse), consistent with the manual
curation method.

Accept rule (all must hold):
  * iNat ``results[tid].name`` == our ``scientific_name`` (exact, case-folded)
  * ``preferred_common_name`` contains a Han ideograph
  * it contains NO kana (rejects Japanese fallbacks)
  * it differs from our ``common_name_ja`` (rejects same-kanji echoes)

Collision-guarded like scripts.fetch_inat_ja_names: never give two co-occurring
species the same Chinese name. Inserts carry ``status='inat-zh'`` (simplified) /
``'inat-zh-hant'`` (traditional) so the whole pass is reversible:
    DELETE FROM species_alias WHERE status LIKE 'inat-zh%';
Idempotent (candidates already carrying a zh alias are skipped), cached.

    .venv/bin/python -m scripts.fetch_inat_zh_names --dry-run [--limit N]
    .venv/bin/python -m scripts.fetch_inat_zh_names [--limit N]
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

try:
    from opencc import OpenCC
    _cc = OpenCC("s2t")
    def to_hant(s: str) -> str:
        return _cc.convert(s)
except Exception:  # pragma: no cover - opencc must be installed
    def to_hant(s: str) -> str:
        return s

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "parklife.db"
CACHE = ROOT / "data" / "cache" / "inat_zh"
API = "https://api.inaturalist.org/v1/taxa"
UA = "parklife/1.0 (biodiversity map; contact via github paranoid2droid/parklife)"
DELAY = 0.7
BATCH = 30

KANA = re.compile(r"[ぁ-んァ-ヶ゛゜ー]")       # hiragana/katakana → Japanese, reject
HAN = re.compile(r"[一-龥㐀-䶵]")               # CJK ideograph → required


def norm_sci(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip()).lower()


def fetch(tids: list[int]) -> dict[int, dict]:
    CACHE.mkdir(parents=True, exist_ok=True)
    need = [t for t in tids if not (CACHE / f"{t}.json").exists()]
    if need:
        ids = ",".join(str(t) for t in need)
        try:
            r = requests.get(f"{API}/{ids}", params={"locale": "zh-CN"},
                             headers={"User-Agent": UA, "Accept-Language": "zh-CN"},
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
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    # visible, real-katakana-named, tid-bearing species with NO zh alias yet.
    rows = conn.execute("""
        SELECT s.id, s.scientific_name, s.common_name_ja, s.inat_taxon_id,
               (SELECT COUNT(*) FROM park_species ps WHERE ps.species_id=s.id) AS np
        FROM species s
        WHERE s.inat_taxon_id IS NOT NULL
          AND s.scientific_name IS NOT NULL
          AND s.common_name_ja IS NOT NULL AND s.common_name_ja != ''
          AND SUBSTR(s.common_name_ja,1,1) NOT BETWEEN 'A' AND 'Z'
          AND s.common_name_ja NOT LIKE '%属'
          AND EXISTS (SELECT 1 FROM park_species ps WHERE ps.species_id=s.id)
          AND NOT EXISTS (SELECT 1 FROM species_alias a
                          WHERE a.species_id=s.id AND a.lang IN ('zh-Hans','zh-Hant'))
        ORDER BY np DESC, s.scientific_name
    """).fetchall()
    if limit:
        rows = rows[:limit]

    tid_species: dict[int, list[sqlite3.Row]] = defaultdict(list)
    for r in rows:
        tid_species[r["inat_taxon_id"]].append(r)
    tids = sorted(tid_species)
    print(f"candidate taxa: {len(tids)} tids over {len(rows)} species (missing zh)")

    # fetch + apply the fail-closed accept rule
    proposed: dict[int, str] = {}   # species_id -> zh-Hans name
    got = mismatch = nonzh = 0
    for i in range(0, len(tids), BATCH):
        chunk = tids[i:i + BATCH]
        res = fetch(chunk)
        for t in chunk:
            r = res.get(t) or {}
            nm = (r.get("preferred_common_name") or "").strip()
            inat_name = r.get("name") or ""
            for sp in tid_species[t]:
                # identity gate: iNat taxon must be OUR species
                if norm_sci(inat_name) != norm_sci(sp["scientific_name"]):
                    mismatch += 1
                    continue
                if not nm or not HAN.search(nm) or KANA.search(nm) or nm == sp["common_name_ja"]:
                    nonzh += 1
                    continue
                proposed[sp["id"]] = nm
                got += 1
        if not dry and i and i % (BATCH * 20) == 0:
            print(f"  ...{i}/{len(tids)} tids, {got} zh names so far")
    print(f"iNat gave a usable zh name for {got} species "
          f"({mismatch} tid/sci mismatch skipped, {nonzh} no-zh/echo skipped)")

    # collision guard (most-widespread first): no duplicate zh name among co-occurring species
    npark = dict(conn.execute("SELECT species_id, COUNT(*) FROM park_species GROUP BY species_id"))
    sp_parks: dict[int, list[int]] = defaultdict(list)
    for sid, pid in conn.execute("SELECT species_id, park_id FROM park_species"):
        sp_parks[sid].append(pid)
    park_zh: dict[int, set] = defaultdict(set)
    for pid, nm in conn.execute("""SELECT ps.park_id, a.raw_name FROM park_species ps
        JOIN species_alias a ON a.species_id=ps.species_id
        WHERE a.lang='zh-Hans'"""):
        park_zh[pid].add(nm)

    pick: dict[int, str] = {}
    collisions = 0
    for sid in sorted(proposed, key=lambda s: (-npark.get(s, 0), s)):
        nm = proposed[sid]
        if any(nm in park_zh[p] for p in sp_parks.get(sid, [])):
            collisions += 1
            continue
        pick[sid] = nm
        for p in sp_parks.get(sid, []):
            park_zh[p].add(nm)

    print(f"assignable: {len(pick)} species ({collisions} skipped to avoid duplicate zh names)")
    for sid, nm in list(pick.items())[:12]:
        print(f"  {sid}: {nm} / {to_hant(nm)}")

    if dry:
        print("\n--dry-run: no DB writes")
        return 0
    n = 0
    for sid, nm in pick.items():
        conn.execute("INSERT INTO species_alias(species_id,raw_name,lang,status)"
                     " VALUES(?,?,?,?)", (sid, nm, "zh-Hans", "inat-zh"))
        hant = to_hant(nm)
        if hant and hant != nm:
            conn.execute("INSERT INTO species_alias(species_id,raw_name,lang,status)"
                         " VALUES(?,?,?,?)", (sid, hant, "zh-Hant", "inat-zh-hant"))
        n += 1
    conn.commit()
    print(f"\nwrote zh aliases for {n} species "
          f"(reversible: DELETE FROM species_alias WHERE status LIKE 'inat-zh%')")
    return 0


if __name__ == "__main__":
    sys.exit(main())
