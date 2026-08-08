"""Systemic remediation for scrape-normalization errors.

The 122 scrape-only species (no iNat/GBIF/eBird corroboration) include real but
MIS-NAMED Japanese species (ツワブキ→Farfugium grande, should be F. japonicum),
not just noise. Blanket-suppressing would hide common natives. Instead RE-RESOLVE
each by its Japanese name through iNat's authoritative ja-vernacular index:

  - exact preferred_common_name == ja-name AND species rank  -> RE-MAP to that sci
  - otherwise                                                -> SUPPRESS

Only species the audit flagged (uncorroborated) are touched. --dry-run prints the
plan; --apply performs it (re-map = point observations/aliases at the correct
species, find-or-create it; suppress = add to data/suppressed_species.json).
"""
from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from parklife import db
from scripts.audit_scrape_only import gbif_jp_count

ROOT = Path(__file__).resolve().parent.parent
SUP = ROOT / "data" / "suppressed_species.json"
CACHE = ROOT / "data" / "cache" / "inat_ja_resolve"
UA = "parklife-bot/0.1 (research; contact: paranoid2droid@gmail.com)"
API_HINTS = ("iNaturalist (research grade)", "GBIF", "eBird", "GBIF-admin")


def inat_resolve_ja(name: str) -> dict | None:
    """iNat taxon whose Japanese common name EXACTLY equals `name` and is a
    species (or below). Returns {sci, rank, obs} or None. Cached."""
    CACHE.mkdir(parents=True, exist_ok=True)
    ck = CACHE / (urllib.parse.quote(name, safe="") + ".json")
    if ck.exists():
        return json.loads(ck.read_text())
    url = "https://api.inaturalist.org/v1/taxa?" + urllib.parse.urlencode(
        {"q": name, "locale": "ja", "per_page": 5})
    try:
        d = json.load(urllib.request.urlopen(
            urllib.request.Request(url, headers={"User-Agent": UA}), timeout=20))
    except Exception:
        d = {"results": []}
    time.sleep(0.7)

    import re as _re
    def norm(s):  # drop iNat qualifiers: ツワブキ(広義) / (s.l.) / 〜属 / spaces
        s = _re.sub(r"[（(].*?[)）]", "", s or "")
        return s.replace("属", "").replace(" ", "").strip()
    target = norm(name)
    hit = None
    for r in d.get("results", []):
        cn = r.get("preferred_common_name") or ""
        if r.get("rank_level", 100) <= 10 and norm(cn) == target and target:
            hit = {"sci": r.get("name"), "rank": r.get("rank"),
                   "obs": r.get("observations_count"), "cn": cn}
            break
    ck.write_text(json.dumps(hit, ensure_ascii=False))
    return hit


def flagged_species(conn):
    """scrape-only + not corroborated by iNat/GBIF/eBird (same set as the audit)."""
    ph = ",".join("?" * len(API_HINTS))
    return conn.execute(f"""
        WITH ok AS (
          SELECT species_id,
                 SUM(CASE WHEN location_hint IN ({ph}) THEN 1 ELSE 0 END) api_n,
                 SUM(CASE WHEN location_hint IN ({ph}) THEN 0 ELSE 1 END) scrape_n
          FROM observation WHERE species_id IS NOT NULL GROUP BY species_id)
        SELECT s.id, s.common_name_ja, s.scientific_name, s.kingdom
        FROM ok JOIN species s ON s.id = ok.species_id
        WHERE ok.scrape_n > 0 AND ok.api_n = 0
        ORDER BY s.kingdom, s.common_name_ja
    """, API_HINTS + API_HINTS).fetchall()


def find_or_create_species(conn, sci, kingdom, taxon_group):
    row = conn.execute("SELECT id FROM species WHERE scientific_name=?", (sci,)).fetchone()
    if row:
        return row["id"]
    cur = conn.execute(
        "INSERT INTO species (scientific_name, kingdom, taxon_group) VALUES (?, ?, ?)",
        (sci, kingdom, taxon_group))
    return cur.lastrowid


def main() -> int:
    apply = "--apply" in sys.argv
    remaps, suppresses, review = [], [], []
    with db.connect(ROOT / "data" / "parklife.db") as conn:
        rows = flagged_species(conn)
        print(f"flagged (uncorroborated scrape) species: {len(rows)}\n")
        corroborated = 0
        for r in rows:
            sid, ja, sci, kingdom = r["id"], r["common_name_ja"], r["scientific_name"], r["kingdom"]
            # Only act on the UNcorroborated ones. A scrape-only species that GBIF
            # DOES have Japanese records for (legit cultivars: キンギョツバキ etc.)
            # is fine as-is — never touch it.
            if sci and gbif_jp_count(sci):
                corroborated += 1
                continue
            hit = inat_resolve_ja(ja) if ja else None
            if hit and hit["sci"] and hit["sci"] != sci:
                remaps.append((sid, ja, sci, hit["sci"], hit["obs"]))
            elif hit and hit["sci"] == sci:
                pass  # already correct — leave
            elif not sci:
                # bare category word (コオロギ/タンポポ…) — unambiguously not a species
                suppresses.append((sid, ja, sci))
            else:
                # has a plausible sci name but no iNat ja-match & 0 GBIF-JP: could be a
                # correct-but-rare cultivar (ホザキサクラソウ) OR foreign noise. Don't
                # auto-suppress — flag for review.
                review.append((sid, ja, sci))

        print(f"=== RE-MAP ({len(remaps)}) — fix wrong sci name of a real JA species (auto-safe) ===")
        for sid, ja, old, new, obs in remaps:
            print(f"  {ja or '—':16} {str(old):28} -> {new}  ({obs} iNat obs)")
        print(f"\n=== SUPPRESS ({len(suppresses)}) — bare category words, no scientific name (auto-safe) ===")
        for sid, ja, sci in suppresses:
            print(f"  {ja or '—':16}")
        print(f"\n=== REVIEW ({len(review)}) — has a sci name, uncorroborated & no iNat ja-match (NOT auto-touched) ===")
        for sid, ja, sci in review:
            print(f"  {ja or '—':16} {sci}")

        if apply:
            # 1. re-maps
            for sid, ja, old, new, obs in remaps:
                tg = conn.execute("SELECT taxon_group FROM species WHERE id=?", (sid,)).fetchone()["taxon_group"]
                tgt = find_or_create_species(conn, new, None, tg)
                conn.execute("UPDATE observation SET species_id=? WHERE species_id=?", (tgt, sid))
                conn.execute("UPDATE species_alias SET species_id=? WHERE species_id=?", (tgt, sid))
                # keep the ja name as an alias on the target if missing
                conn.execute("INSERT INTO species_alias (species_id, raw_name, lang, status) "
                             "SELECT ?, ?, 'ja', 'resolved' WHERE NOT EXISTS "
                             "(SELECT 1 FROM species_alias WHERE species_id=? AND raw_name=? AND lang='ja')",
                             (tgt, ja, tgt, ja))
            # 2. suppress list (dedupe reads this)
            existing = json.loads(SUP.read_text()) if SUP.exists() else {}
            for sid, ja, sci in suppresses:
                existing[str(sid)] = {"ja": ja, "sci": sci, "reason": "scrape-uncorroborated-no-ja-match"}
            SUP.write_text(json.dumps(existing, ensure_ascii=False, indent=1))
            conn.commit()
            print(f"\nAPPLIED: {len(remaps)} re-mapped, {len(suppresses)} suppressed -> {SUP.name}")
            print("Re-run scripts.dedupe to rebuild park_species.")
        else:
            print("\n(dry-run — pass --apply to perform)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
