"""Replace romaji ``common_name_ja`` placeholders (e.g. ``Yahazu-endo``)
with the canonical katakana name fetched from iNaturalist.

Background: ~69 species in the DB have an ASCII-prefix ``common_name_ja``
that leaked through from iNaturalist's locale fallback. They are invisible
to the curation pipeline (the batch query filter
``SUBSTR(common_name_ja,1,1) NOT BETWEEN 'A' AND 'Z'`` skips them) and
display as awkward romaji in the demo. Several have very high park-spread
(``Yahazu-endo`` np=140, ``Oni-tabirako`` np=130).

Strategy:
  1. Identify visible (in park_species) species with ASCII-prefix ja name
     and a non-NULL ``inat_taxon_id``.
  2. Fetch ``/v1/taxa/{id}?locale=ja`` (reusing the cache shared with
     ``scripts.inat_localized_names``).
  3. Accept the returned ``preferred_common_name`` only if it is
     unambiguously Japanese (contains katakana, hiragana, or CJK
     ideographs and contains no ASCII letters).
  4. If a sibling species row already exists with the canonical katakana
     name, REPORT IT (manual merge with ``scripts.merge_species_pair``
     follows). Otherwise UPDATE ``common_name_ja`` and add the romaji form
     as a ``ja`` alias so future scrapes that still use the romaji still
     resolve to this species.

Usage::

    .venv/bin/python -m scripts.fix_romaji_ja_names           # dry-run
    .venv/bin/python -m scripts.fix_romaji_ja_names --apply
"""
from __future__ import annotations

import json
import sqlite3
import sys
import time
from pathlib import Path

from curl_cffi import requests

ROOT = Path(__file__).resolve().parent.parent
DB_FP = ROOT / "data" / "parklife.db"
CACHE = ROOT / "data" / "cache" / "inat_taxon_localized"
UA = "parklife-bot/0.1 (research; contact: paranoid2droid@gmail.com)"
API = "https://api.inaturalist.org/v1/taxa"
REQUEST_DELAY_SECONDS = 1.0


def fetch_taxon_ja(taxon_id: int) -> dict | None:
    cp = CACHE / f"{taxon_id}__ja.json"
    cp.parent.mkdir(parents=True, exist_ok=True)
    if cp.exists():
        try:
            return json.loads(cp.read_text(encoding="utf-8"))
        except Exception:
            pass
    r = requests.get(
        f"{API}/{taxon_id}",
        params={"locale": "ja"},
        headers={"User-Agent": UA, "Accept-Language": "ja"},
        impersonate="chrome",
        timeout=20,
    )
    if r.status_code != 200:
        return None
    data = r.json()
    cp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    time.sleep(REQUEST_DELAY_SECONDS)
    return data


def is_japanese_name(name: str) -> bool:
    if not name:
        return False
    has_jp = False
    for ch in name:
        cp = ord(ch)
        if ("A" <= ch <= "Z") or ("a" <= ch <= "z"):
            return False  # any ASCII letter disqualifies
        # Hiragana 3040-309F, Katakana 30A0-30FF, CJK Unified 4E00-9FFF
        if 0x3040 <= cp <= 0x309F or 0x30A0 <= cp <= 0x30FF or 0x4E00 <= cp <= 0x9FFF:
            has_jp = True
    return has_jp


SKIP_IDS = {
    # Sawara (Chamaecyparis pisifera) — homonym with existing サワラ (the fish
    # Scomberomorus niphonius, id=588). Renaming would collide displayably;
    # leave as romaji until a disambiguation strategy is chosen.
    3417,
}


def main() -> int:
    apply = "--apply" in sys.argv
    conn = sqlite3.connect(DB_FP)
    conn.row_factory = sqlite3.Row

    targets = list(conn.execute("""
        SELECT s.id, s.common_name_ja, s.scientific_name, s.inat_taxon_id,
               (SELECT COUNT(DISTINCT park_id) FROM park_species WHERE species_id=s.id) AS np
          FROM species s
         WHERE SUBSTR(s.common_name_ja, 1, 1) BETWEEN 'A' AND 'Z'
           AND s.inat_taxon_id IS NOT NULL
           AND s.id IN (SELECT species_id FROM park_species)
         ORDER BY np DESC
    """))
    print(f"romaji-placeholder species with inat_taxon_id and park_species: {len(targets)}")

    resolved: list[dict] = []        # ready to UPDATE: no katakana sibling
    sibling_conflict: list[dict] = []  # would-be name already taken by another species row
    unresolved: list[dict] = []      # iNat didn't return a usable ja name

    for r in targets:
        if r["id"] in SKIP_IDS:
            continue
        d = fetch_taxon_ja(r["inat_taxon_id"])
        results = (d or {}).get("results") or []
        ja = ""
        if results:
            ja = (results[0].get("preferred_common_name") or "").strip()
            # Strip trailing "(広義)" / "（広義）" sensu-lato annotation —
            # consistent with the cleanup applied by fix_placeholder_names.
            for suffix in ("(広義)", "（広義）"):
                if ja.endswith(suffix):
                    ja = ja[: -len(suffix)].strip()
        if not is_japanese_name(ja):
            unresolved.append({**dict(r), "got": ja or "(empty)"})
            continue
        sib = conn.execute(
            "SELECT id, scientific_name FROM species WHERE common_name_ja=? AND id != ?",
            (ja, r["id"]),
        ).fetchone()
        entry = {**dict(r), "ja": ja, "sibling_id": sib["id"] if sib else None,
                 "sibling_sci": sib["scientific_name"] if sib else None}
        if sib:
            sibling_conflict.append(entry)
        else:
            resolved.append(entry)

    print(f"  ready to rename:      {len(resolved)}")
    print(f"  sibling-merge needed: {len(sibling_conflict)}")
    print(f"  iNat had no ja name:  {len(unresolved)}")

    print("\n=== Ready to rename (top 30 by np) ===")
    for r in resolved[:30]:
        print(f"  np={r['np']:3d}  id={r['id']:5d}  {r['common_name_ja']:28s}  ->  {r['ja']}")
    if len(resolved) > 30:
        print(f"  ... ({len(resolved) - 30} more)")

    if sibling_conflict:
        print("\n=== Sibling merge needed (use scripts.merge_species_pair) ===")
        for r in sibling_conflict:
            print(f"  np={r['np']:3d}  src id={r['id']} ({r['common_name_ja']!r}, {r['scientific_name']})")
            print(f"                 -> existing id={r['sibling_id']} ({r['ja']!r}, {r['sibling_sci']})")

    if unresolved:
        print("\n=== Unresolved (no ja name from iNat) ===")
        for r in unresolved:
            print(f"  np={r['np']:3d}  id={r['id']} {r['common_name_ja']!r} (sci={r['scientific_name']}, "
                  f"got={r['got']!r})")

    if not apply:
        print("\n(dry-run; pass --apply to update DB)")
        return 0

    renamed = aliased = 0
    for r in resolved:
        sid = r["id"]
        romaji = r["common_name_ja"]
        ja = r["ja"]
        conn.execute("UPDATE species SET common_name_ja=? WHERE id=?", (ja, sid))
        renamed += 1
        # Preserve the romaji form as a ja alias for resolver continuity
        exists = conn.execute(
            "SELECT 1 FROM species_alias WHERE raw_name=? AND lang='ja'", (romaji,)
        ).fetchone()
        if not exists:
            conn.execute(
                "INSERT INTO species_alias (species_id, raw_name, lang, status) "
                "VALUES (?, ?, 'ja', 'resolved')",
                (sid, romaji),
            )
            aliased += 1
    conn.commit()
    print(f"\nrenamed {renamed} species; added {aliased} romaji ja aliases for resolver continuity")
    if sibling_conflict:
        print(f"({len(sibling_conflict)} sibling-merge cases NOT touched — run merge_species_pair manually)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
