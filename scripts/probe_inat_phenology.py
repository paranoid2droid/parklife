"""One-shot probe: verify the iNat phenology histogram endpoint shape on
a known species (Cerasus × yedoensis = ソメイヨシノ) and a known place.
Prints the response so we know the field structure.
"""
from __future__ import annotations
import json
from curl_cffi import requests

UA = "parklife-bot/0.1 (research; contact: paranoid2droid@gmail.com)"

def probe(taxon_id: int, place_id: int) -> None:
    url = "https://api.inaturalist.org/v1/observations/histogram"
    params = {
        "taxon_id": taxon_id,
        "place_id": place_id,
        "date_field": "observed",
        "interval": "month_of_year",
        "term_id": 12,           # Plant Phenology
        "term_value_id": 13,     # Flowering
        "verifiable": "true",
    }
    r = requests.get(url, params=params, headers={"User-Agent": UA},
                      impersonate="chrome", timeout=20)
    print("status:", r.status_code)
    print("url:", r.url)
    if r.status_code == 200:
        data = r.json()
        print(json.dumps(data, ensure_ascii=False, indent=2)[:2000])
    else:
        print(r.text[:500])


def probe2(taxon_id: int, place_id: int) -> None:
    url = "https://api.inaturalist.org/v1/observations/histogram"
    base = {
        "taxon_id": taxon_id, "place_id": place_id,
        "interval": "month_of_year", "verifiable": "true",
    }
    print("\n--- no annotation filter (all observations by month) ---")
    r = requests.get(url, params=base, headers={"User-Agent": UA},
                      impersonate="chrome", timeout=20)
    print("status:", r.status_code, " bytes:", len(r.content))
    if r.status_code == 200:
        print(json.dumps(r.json()["results"]["month_of_year"], indent=2))
    print("\n--- with term_id=12 only (any phenology annotation) ---")
    r = requests.get(url, params={**base, "term_id": 12},
                      headers={"User-Agent": UA}, impersonate="chrome", timeout=20)
    if r.status_code == 200:
        print(json.dumps(r.json()["results"]["month_of_year"], indent=2))


if __name__ == "__main__":
    # ソメイヨシノ — try a few possible taxon_ids
    print("=== Cerasus x yedoensis (51797) ===")
    probe2(51797, 6803)
    print("\n=== try ginkgo biloba (47148) ===")
    probe2(47148, 6803)
