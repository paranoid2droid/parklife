"""Systemic audit: scrape-derived species with NO iNat/GBIF/eBird corroboration.

The website-scrape path (katakana narrative → Wikipedia normalizer) is the only
place a species' scientific name is *guessed*; iNat/GBIF/eBird carry authoritative
names. A guessed species that never appears anywhere in the (Japan-dense)
iNat/GBIF corpus is almost always wrong-context: a captive zoo animal, a bare
category word, or a normalization mis-map (e.g. ナナフシ→Myronides glaucus).

Signal to confirm it: **0 GBIF occurrence records in Japan**. This flags the whole
class at once instead of whack-a-mole disambiguation.

Writes data/suppressed_species.json (species_ids with a reason) which scripts.dedupe
excludes from park_species (rows stay in `observation` for provenance).

Usage: python -m scripts.audit_scrape_only [--apply]   (--apply writes the file)
"""
from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from parklife import db

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "suppressed_species.json"
CACHE = ROOT / "data" / "cache" / "gbif_jp_count"
UA = "parklife-bot/0.1 (research; contact: paranoid2droid@gmail.com)"
API_HINTS = ("iNaturalist (research grade)", "GBIF", "eBird", "GBIF-admin")


def _get(url: str) -> dict:
    return json.load(urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent": UA}), timeout=40))


def gbif_jp_count(sci: str) -> int | None:
    """GBIF occurrence records for this name in Japan (cached). None = unmatched."""
    CACHE.mkdir(parents=True, exist_ok=True)
    ck = CACHE / (urllib.parse.quote(sci, safe="") + ".json")
    if ck.exists():
        return json.loads(ck.read_text())
    m = _get("https://api.gbif.org/v1/species/match?" + urllib.parse.urlencode({"name": sci}))
    key = m.get("usageKey") if m.get("matchType") != "NONE" else None
    if not key:
        ck.write_text("null")
        return None
    d = _get("https://api.gbif.org/v1/occurrence/search?" + urllib.parse.urlencode(
        {"taxonKey": key, "country": "JP", "limit": 0}))
    n = d.get("count", 0)
    time.sleep(0.3)
    ck.write_text(json.dumps(n))
    return n


def scrape_only_species(conn):
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
        ORDER BY s.kingdom, s.scientific_name
    """, API_HINTS + API_HINTS).fetchall()


def main() -> int:
    apply = "--apply" in sys.argv
    with db.connect(ROOT / "data" / "parklife.db") as conn:
        rows = scrape_only_species(conn)
    print(f"scrape-only species: {len(rows)}")

    suppressed = {}
    kept = 0
    for r in rows:
        sid, ja, sci, kingdom = r["id"], r["common_name_ja"], r["scientific_name"], r["kingdom"]
        if not sci:
            # bare category word (コオロギ/トンボ…) with no scientific name → suppress
            suppressed[sid] = {"ja": ja, "sci": None, "reason": "generic-no-sciname"}
            print(f"  SUPPRESS [generic]  {ja}")
            continue
        n = gbif_jp_count(sci)
        if not n:  # 0 records OR unmatched name — GBIF-Japan can't corroborate it
            suppressed[sid] = {"ja": ja, "sci": sci,
                               "reason": "zero-gbif-japan" if n == 0 else "gbif-unmatched"}
            print(f"  SUPPRESS [{'0 JP' if n==0 else 'nomatch'}] {ja or '—':16} {sci}")
        else:
            kept += 1
            print(f"  keep ({n:>6} JP recs)   {ja or '—':16} {sci}")
    print(f"\nsuppress: {len(suppressed)}  keep: {kept}")
    if apply:
        OUT.write_text(json.dumps(suppressed, ensure_ascii=False, indent=1))
        print(f"wrote {OUT}")
    else:
        print("(dry-run — pass --apply to write data/suppressed_species.json)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
