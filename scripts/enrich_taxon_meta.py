"""Enrich taxon_group (②) and English names (④) from iNaturalist in one pass.

Both come from ``GET /v1/taxa/{ids}?locale=en``: the response carries
``iconic_taxon_name`` (locale-independent) AND ``preferred_common_name`` (the
English vernacular for locale=en). Fetching once fills both, batched + cached
one slim JSON per taxon under ``data/cache/inat_taxmeta/``.

Fail-closed identity gate for BOTH writes: the returned taxon's scientific
``name`` must equal ours (case-folded, space-normalized) — never adopt metadata
fetched for a different taxon.

②  taxon_group: only when currently NULL/'?'. iNat's iconic taxon maps cleanly
    to our fine groups for the vertebrate/arthropod/mollusk/plant/fungus classes;
    generic iconic buckets (Animalia/Chromista/Protozoa) are left as-is (we can't
    pick fish-vs-tunicate-vs-worm from the iconic name alone). kingdom is already
    set, so this only refines the group.

④  common_name_en + an ``en`` alias (status='inat-en'): only when the species
    has no English name yet. Rejects romaji-of-the-JA-name (ascii, hyphens, no
    spaces) like inat_localized_names does.

Reversible::
    UPDATE species SET taxon_group='?' WHERE ... (see backup)  -- group is in-place
    DELETE FROM species_alias WHERE status='inat-en';
    -- common_name_en writes are logged to data/enrich_en_applied.json

Usage::
    .venv/bin/python -m scripts.enrich_taxon_meta --dry-run [--limit N]
    .venv/bin/python -m scripts.enrich_taxon_meta [--limit N]
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
import time
from pathlib import Path

from curl_cffi import requests

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "parklife.db"
CACHE = ROOT / "data" / "cache" / "inat_taxmeta"
API = "https://api.inaturalist.org/v1/taxa"
UA = "parklife/1.0 (biodiversity map; contact via github paranoid2droid/parklife)"
DELAY = 0.7
BATCH = 30

ICONIC_TO_GROUP = {
    "Actinopterygii": "fish",
    "Amphibia": "amphibian",
    "Reptilia": "reptile",
    "Aves": "bird",
    "Mammalia": "mammal",
    "Mollusca": "mollusk",
    "Arachnida": "arachnid",
    "Insecta": "insect",
    "Plantae": "plant",
    "Fungi": "mushroom",
    # generic buckets left unmapped on purpose (too coarse):
    # "Animalia", "Chromista", "Protozoa"
}

KANA = re.compile(r"[ぁ-んァ-ヶ゛゜ー]")


def norm_sci(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip()).lower()


def is_romaji(name: str) -> bool:
    """Reject an English field that is really a romanization of the JA name."""
    return bool(name) and "-" in name and " " not in name and name.replace("-", "").isalpha()


def fetch(tids: list[int]) -> dict[int, dict]:
    CACHE.mkdir(parents=True, exist_ok=True)
    need = [t for t in tids if not (CACHE / f"{t}.json").exists()]
    if need:
        ids = ",".join(str(t) for t in need)
        try:
            r = requests.get(f"{API}/{ids}", params={"locale": "en"},
                             headers={"User-Agent": UA, "Accept-Language": "en"},
                             impersonate="chrome", timeout=30)
            results = r.json().get("results", []) if r.status_code == 200 else []
        except Exception as e:
            print("  fetch error:", e); results = []
        by = {res.get("id"): res for res in results}
        for t in need:
            res = by.get(t) or {}
            slim = {"id": res.get("id"), "name": res.get("name"),
                    "iconic_taxon_name": res.get("iconic_taxon_name"),
                    "preferred_common_name": res.get("preferred_common_name"),
                    "english_common_name": res.get("english_common_name")}
            (CACHE / f"{t}.json").write_text(json.dumps(slim, ensure_ascii=False))
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

    rows = conn.execute("""
        SELECT s.id, s.scientific_name, s.common_name_ja, s.common_name_en,
               s.taxon_group, s.inat_taxon_id,
               (SELECT COUNT(*) FROM park_species ps WHERE ps.species_id=s.id) np,
               EXISTS(SELECT 1 FROM species_alias a WHERE a.species_id=s.id AND a.lang='en') has_en_alias
        FROM species s
        WHERE s.inat_taxon_id IS NOT NULL
          AND s.scientific_name IS NOT NULL AND s.scientific_name != ''
          AND (
                (s.taxon_group IS NULL OR s.taxon_group='?')          -- needs group
             OR (s.common_name_en IS NULL OR s.common_name_en='')     -- needs en
              )
        ORDER BY np DESC, s.scientific_name
    """).fetchall()
    if limit:
        rows = rows[:limit]

    # dedupe tids for fetching
    tids = sorted({r["inat_taxon_id"] for r in rows})
    print(f"targets: {len(rows)} species over {len(tids)} tids "
          f"(need group and/or en); cached reused, ~1 req/sec new")

    meta: dict[int, dict] = {}
    for i in range(0, len(tids), BATCH):
        meta.update(fetch(tids[i:i + BATCH]))
        if not dry and i and i % (BATCH * 20) == 0:
            print(f"  ...{i}/{len(tids)} tids fetched")

    group_updates: list[tuple[int, str, str]] = []   # (sid, old, new)
    en_updates: list[tuple[int, str]] = []           # (sid, en)
    id_mismatch = 0
    for r in rows:
        m = meta.get(r["inat_taxon_id"]) or {}
        if norm_sci(m.get("name")) != norm_sci(r["scientific_name"]):
            id_mismatch += 1
            continue
        # ② group
        if (r["taxon_group"] is None or r["taxon_group"] == "?"):
            g = ICONIC_TO_GROUP.get(m.get("iconic_taxon_name") or "")
            if g:
                group_updates.append((r["id"], r["taxon_group"], g))
        # ④ en
        if not (r["common_name_en"] or "").strip() and not r["has_en_alias"]:
            en = (m.get("preferred_common_name") or m.get("english_common_name") or "").strip()
            if en and not is_romaji(en) and not KANA.search(en):
                en_updates.append((r["id"], en))

    print(f"\n② taxon_group fills: {len(group_updates)}")
    from collections import Counter
    gc = Counter(g for _, _, g in group_updates)
    for g, n in gc.most_common():
        print(f"    {g}: {n}")
    for sid, old, new in group_updates[:10]:
        sci = next(x["scientific_name"] for x in rows if x["id"] == sid)
        print(f"      {sci} : {old!r} -> {new}")
    print(f"\n④ common_name_en fills: {len(en_updates)}")
    for sid, en in en_updates[:15]:
        sci = next(x["scientific_name"] for x in rows if x["id"] == sid)
        print(f"      {sci} -> {en}")
    print(f"\n(identity-gate skips: {id_mismatch})")

    if dry:
        print("\n--dry-run: no DB writes")
        return 0

    for sid, _, new in group_updates:
        conn.execute("UPDATE species SET taxon_group=? WHERE id=?", (new, sid))
    alias_written = 0
    for sid, en in en_updates:
        conn.execute("UPDATE species SET common_name_en=? WHERE id=?", (en, sid))
        # en names are not globally unique across species, but species_alias has a
        # UNIQUE(raw_name,lang) index — attach the alias only where free; the
        # column (used for display) is always set above, the alias (search) best-effort.
        cur = conn.execute("INSERT OR IGNORE INTO species_alias(species_id,raw_name,lang,status)"
                           " VALUES(?,?,?,?)", (sid, en, "en", "inat-en"))
        alias_written += cur.rowcount
    conn.commit()
    (ROOT / "data" / "enrich_en_applied.json").write_text(
        json.dumps({"group": group_updates, "en": en_updates}, ensure_ascii=False, indent=1))
    print(f"\napplied: {len(group_updates)} groups + {len(en_updates)} en names "
          f"({alias_written} en aliases written, rest column-only due to name collision; "
          f"reversible: DELETE FROM species_alias WHERE status='inat-en'; "
          f"group log in data/enrich_en_applied.json)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
