"""Import zh names from Catalogue of Life China (sp2000.org.cn) DwC-A.

Source: http://www.gbifchina.org.cn/resource?r=chinacol2023
Cached at: data/raw/sp2000/taxon.txt (extracted from chinacol2023.zip)

The TSV has scientificName + vernacularName columns. We match by exact
scientific_name first, then by binomial prefix (first two tokens) to handle
subspecies/varieties. Only Han-character vernaculars are imported. CoL China
is Hans-leaning, so all imports go in as zh-Hans (the OpenCC display path
already handles the Hant fallback).
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

from parklife import db

ROOT = Path(__file__).resolve().parent.parent
TAXON_TSV = ROOT / "data" / "raw" / "sp2000" / "taxon.txt"
HAN_RE = re.compile(r"[一-鿿]")


def is_traditional_chinese(text: str) -> bool:
    HANT_ONLY = ("繁體萬個個鳥語雞嬰嶺鏡藥廣專點寶會勻來時對學園"
                 "為國體點選擇變對於關於開頭設計總計龍門開歷"
                 "區傳實業樣標準買賣賣處態應隨")
    return any(c in HANT_ONLY for c in text)


def two(s: str) -> str:
    return " ".join(s.split()[:2])


def load_sp2000() -> tuple[dict[str, str], dict[str, str]]:
    """Return (exact_sci → vern, binomial_prefix → vern) maps for Han names."""
    exact: dict[str, str] = {}
    prefix: dict[str, str] = {}
    with TAXON_TSV.open(encoding="utf-8") as f:
        rdr = csv.DictReader(f, delimiter="\t")
        for row in rdr:
            v = (row.get("vernacularName") or "").strip()
            sci = (row.get("scientificName") or "").strip()
            if not v or not sci or not HAN_RE.search(v):
                continue
            # Prefer the first occurrence (CoL is generally curated)
            exact.setdefault(sci, v)
            prefix.setdefault(two(sci), v)
    return exact, prefix


def main() -> int:
    if not TAXON_TSV.exists():
        print(f"missing {TAXON_TSV}; download chinacol2023 DwC-A first")
        return 1

    db_path = ROOT / "data" / "parklife.db"
    print(f"loading sp2000 taxon.txt ...")
    exact, prefix = load_sp2000()
    print(f"  unique sci with Han vern: {len(exact)}, prefix entries: {len(prefix)}")

    inserted_hans = inserted_hant = 0
    skipped_existing = 0
    with db.connect(db_path) as conn:
        species = list(conn.execute("""
            SELECT s.id, s.scientific_name FROM species s
            WHERE s.scientific_name IS NOT NULL AND s.scientific_name <> ''
              AND NOT EXISTS (
                SELECT 1 FROM species_alias a
                WHERE a.species_id = s.id AND a.lang LIKE 'zh%'
              )
        """))
        print(f"  missing-zh queryable species: {len(species)}")

        matched = 0
        for s in species:
            sci = s["scientific_name"]
            name = exact.get(sci) or prefix.get(two(sci))
            if not name:
                continue
            matched += 1
            lang = "zh-Hant" if is_traditional_chinese(name) else "zh-Hans"
            cur = conn.execute(
                """INSERT OR IGNORE INTO species_alias
                   (species_id, raw_name, lang, status)
                   VALUES (?, ?, ?, 'resolved')""",
                (s["id"], name, lang),
            )
            if cur.rowcount:
                if lang == "zh-Hans":
                    inserted_hans += 1
                else:
                    inserted_hant += 1
            else:
                skipped_existing += 1
        conn.commit()

    print(f"\n=== sp2000 import done ===")
    print(f"  species matched: {matched}")
    print(f"  zh-Hans inserted: {inserted_hans}")
    print(f"  zh-Hant inserted: {inserted_hant}")
    print(f"  skipped (already existed): {skipped_existing}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
