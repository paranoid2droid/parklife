"""Check our DB for known iNat taxon ids and re-probe."""
from __future__ import annotations
import json
from curl_cffi import requests
from parklife import db
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UA = "parklife-bot/0.1 (research; contact: paranoid2droid@gmail.com)"


def probe(taxon_id: int, with_flowering: bool):
    params = {
        "taxon_id": taxon_id, "place_id": 6803,
        "interval": "month_of_year", "verifiable": "true",
    }
    if with_flowering:
        params["term_id"] = 12
        params["term_value_id"] = 13
    r = requests.get("https://api.inaturalist.org/v1/observations/histogram",
                     params=params, headers={"User-Agent": UA},
                     impersonate="chrome", timeout=20)
    if r.status_code != 200:
        return None
    return r.json().get("results", {}).get("month_of_year", {})


def main() -> None:
    with db.connect(ROOT / "data" / "parklife.db") as conn:
        for ja in ["ソメイヨシノ", "イチョウ", "アジサイ", "ヒガンバナ", "ツツジ", "ウメ"]:
            row = conn.execute(
                "SELECT id, scientific_name, inat_taxon_id FROM species WHERE common_name_ja=?",
                (ja,),
            ).fetchone()
            if not row:
                print(f"  {ja}: not found")
                continue
            tid = row["inat_taxon_id"]
            print(f"\n{ja}  (sci={row['scientific_name']}, inat_taxon={tid})")
            if not tid:
                continue
            all_ = probe(tid, False)
            flower = probe(tid, True)
            print(f"  all months:      {all_}")
            print(f"  flowering only:  {flower}")


if __name__ == "__main__":
    main()
