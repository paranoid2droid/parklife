"""Run the geographic-enrichment passes for the national-pilot prefectures.

Sequentially runs iNaturalist, GBIF, and eBird for each pilot prefecture,
then normalize + dedupe. All passes are cached/idempotent, so this only
fetches the newly-seeded parks. Logs progress to stdout.
"""
from __future__ import annotations

import sys

PILOT = ["aichi", "osaka", "kyoto"]


def run():
    from scripts import inaturalist, gbif, ebird

    for pref in PILOT:
        print(f"\n##### iNaturalist: {pref} #####", flush=True)
        inaturalist.main(prefecture_filter=pref)
    for pref in PILOT:
        print(f"\n##### GBIF: {pref} #####", flush=True)
        gbif.main(prefecture_filter=pref)
    for pref in PILOT:
        print(f"\n##### eBird: {pref} #####", flush=True)
        ebird.main(prefecture_filter=pref)
    print("\nDONE enrichment fetch.", flush=True)


if __name__ == "__main__":
    sys.exit(run())
