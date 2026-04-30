"""Verify which iNat place_id corresponds to Japan."""
from curl_cffi import requests
import json

UA = "parklife-bot/0.1"


def show(place_id: int):
    r = requests.get(f"https://api.inaturalist.org/v1/places/{place_id}",
                     headers={"User-Agent": UA}, impersonate="chrome", timeout=15)
    if r.status_code != 200:
        print(f"  {place_id}: {r.status_code}")
        return
    results = r.json().get("results") or []
    if not results:
        print(f"  {place_id}: empty results")
        return
    p = results[0]
    print(f"  place_id={place_id}: name={p.get('name')!r} display={p.get('display_name')!r} type={p.get('place_type')}")

# search for Japan
print("\nsearching 'Japan':")
r = requests.get("https://api.inaturalist.org/v1/places/autocomplete",
                  params={"q": "Japan"},
                  headers={"User-Agent": UA}, impersonate="chrome", timeout=15)
for p in (r.json().get("results") or [])[:5]:
    print(f"  id={p['id']} name={p.get('name')} display={p.get('display_name')}")
