"""Conservative fixer for wrong Japanese names attached to a species.

Different error class from the scrape mis-maps: a real GBIF species carries a
WRONG common_name_ja (e.g. Polistes canadensis mislabeled オオスズメバチ, whose
real bearer is Vespa mandarinia — mis-attached during GBIF-vernacular backfill).
These have GBIF-Japan records, so the 0-GBIF-JP gate can't catch them.

Signal (BOTH directions must disagree — conservative, no false NULLs):
  forward: iNat taxon for our common_name_ja  -> sci F   (F != our sci)
  reverse: iNat ja-name for our scientific_name -> R      (R is None, or norm(R)
           != norm(our ja))
When both hold, our common_name_ja does not belong to our species -> NULL it
(demote to Latin-only, so park lists / search stop claiming the wrong 和名). Does
NOT re-map occurrences or merge species. Reversible (back up first).

Guards: skip （…）disambiguation suffixes; skip normalized-equal forward names;
and skip when our sci and the ja-name's sci resolve to the SAME GBIF accepted
species (taxonomic synonym, e.g. キアゲハ Papilio machaon=hippocrates).

⚠️ REVIEW-ONLY. This does NOT auto-fix: taxonomic splits (カルガモ Anas
poecilorhyncha vs zonorhyncha — both validly カルガモ) and subspecies still slip
past every guard, so blanket-NULLing would delete correct 和名 from common
species. It writes a ranked review list (data/janame_review.json) for a human to
curate; genuine mis-attachments (Polistes canadensis→オオスズメバチ) are in there,
mixed with a few synonym/split false positives — decide per row.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from parklife import db

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "cache" / "inat_taxa_verify"
UA = "parklife-bot/0.1 (research; contact: paranoid2droid@gmail.com)"


def _norm(s: str | None) -> str:
    if not s:
        return ""
    s = re.sub(r"[（(].*?[)）]", "", s)  # drop （…） / (…)
    return s.replace("属", "").replace(" ", "").strip()


def _cached_taxa(q: str) -> list:
    CACHE.mkdir(parents=True, exist_ok=True)
    ck = CACHE / (hashlib.md5(q.encode()).hexdigest() + ".json")
    if ck.exists():
        return json.loads(ck.read_text())
    url = "https://api.inaturalist.org/v1/taxa?" + urllib.parse.urlencode(
        {"q": q, "locale": "ja", "per_page": 5})
    try:
        d = json.load(urllib.request.urlopen(
            urllib.request.Request(url, headers={"User-Agent": UA}), timeout=20))
        res = d.get("results", [])
    except Exception:
        res = []
    time.sleep(0.7)
    slim = [{"name": r.get("name"), "cn": r.get("preferred_common_name"),
             "rank_level": r.get("rank_level")} for r in res]
    ck.write_text(json.dumps(slim, ensure_ascii=False))
    return slim


def forward_sci(ja: str) -> str | None:
    """iNat sci whose ja common name == ja (species rank)."""
    for r in _cached_taxa(ja):
        if r.get("rank_level", 100) <= 10 and _norm(r.get("cn")) == _norm(ja):
            return r["name"]
    return None


def reverse_ja(sci: str) -> str | None:
    """iNat ja common name for this scientific name."""
    for r in _cached_taxa(sci):
        if r.get("name") == sci:
            return r.get("cn")
    return None


_GBIF_KEY_CACHE = CACHE / "_gbif_accepted.json"
_gk: dict | None = None


def gbif_accepted_key(sci: str) -> int | None:
    """GBIF accepted-species key (resolves synonyms), cached."""
    global _gk
    if _gk is None:
        _gk = json.loads(_GBIF_KEY_CACHE.read_text()) if _GBIF_KEY_CACHE.exists() else {}
    if sci in _gk:
        return _gk[sci]
    try:
        d = json.load(urllib.request.urlopen(urllib.request.Request(
            "https://api.gbif.org/v1/species/match?" + urllib.parse.urlencode({"name": sci}),
            headers={"User-Agent": UA}), timeout=20))
        key = d.get("acceptedUsageKey") or d.get("usageKey")
    except Exception:
        key = None
    time.sleep(0.2)
    _gk[sci] = key
    CACHE.mkdir(parents=True, exist_ok=True)
    _GBIF_KEY_CACHE.write_text(json.dumps(_gk, ensure_ascii=False))
    return key


def main() -> int:
    apply = "--apply" in sys.argv
    limit = next((int(a) for a in sys.argv[1:] if a.isdigit()), None)
    with db.connect(ROOT / "data" / "parklife.db") as conn:
        sql = """
            SELECT s.id, s.scientific_name, s.common_name_ja, COUNT(ps.park_id) np
            FROM species s JOIN park_species ps ON ps.species_id = s.id
            WHERE s.scientific_name IS NOT NULL AND s.scientific_name != ''
              AND s.common_name_ja IS NOT NULL AND s.common_name_ja != ''
              AND s.common_name_ja NOT LIKE '%（%'  -- skip 和名 with a disambig suffix
              AND s.common_name_ja NOT LIKE '%属' AND s.common_name_ja NOT LIKE '%科'
              AND s.common_name_ja NOT LIKE '%類'
            GROUP BY s.id ORDER BY np DESC, s.scientific_name
        """
        rows = conn.execute(sql).fetchall()
        if limit:
            rows = rows[:limit]
        print(f"scanning {len(rows)} visible species (bidirectional iNat check)…\n")
        fixes, checked = [], 0
        for r in rows:
            sid, sci, ja, np = r["id"], r["scientific_name"], r["common_name_ja"], r["np"]
            checked += 1
            fwd = forward_sci(ja)
            if not fwd or fwd == sci or _norm(fwd) == _norm(sci):
                continue  # our ja maps back to our sci (or a synonym) — fine
            rev = reverse_ja(sci)
            if rev and _norm(rev) == _norm(ja):
                continue  # iNat also calls our sci this ja-name — leave
            # GBIF backbone: same accepted species => taxonomic synonym, not an error
            if gbif_accepted_key(sci) and gbif_accepted_key(sci) == gbif_accepted_key(fwd):
                continue
            fixes.append({"id": sid, "sci": sci, "ja": ja, "ja_belongs_to": fwd,
                          "inat_sci_ja": rev, "np": np})
            print(f"  np={np:>3}  {ja:14} on {sci:26} -> 和名 belongs to {fwd}"
                  f"{' (iNat sci-ja=' + rev + ')' if rev else ' (iNat sci-ja=none)'}")
            if checked % 100 == 0:
                print(f"  … {checked}/{len(rows)} scanned, {len(fixes)} flagged")
    review = ROOT / "data" / "janame_review.json"
    review.write_text(json.dumps(fixes, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nflagged for review: {len(fixes)} / {len(rows)} scanned -> {review.name}")
    print("REVIEW-ONLY — no changes applied (splits/subspecies still slip past the guards;"
          " curate by hand). --apply is intentionally not supported.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
