"""Resolve GBIF coordinate-less occurrence records to parks by 市区町村.

GBIF museum-specimen records for Japan carry romaji `stateProvince` (prefecture)
+ `county` (municipality) but no coordinates — ~66% of all Coleoptera records in
Japan are like this and our radius pipeline discards every one. This module maps
those romaji admin strings to the parks in that municipality, so the record can
enter as an explicit **'admin:municipality'** evidence tier (weaker than the
radius-matched 'onsite' tier — regional presence, not confirmed on-site).

Design invariant — **fail closed**: a miss is always preferable to a wrong
attach. Three gates must all pass:
  1. prefecture  — GBIF stateProvince must normalize to a real slug we use.
  2. reality     — the geocoded kanji municipality must actually be a park
                   municipality in that prefecture (no park there → nothing to
                   attach → drop).
  3. consistency — Nominatim's own prefecture for the result must match the slug,
                   rejecting cross-prefecture mis-geocodes.

Municipality resolution romaji→kanji uses Nominatim (ja), cached on disk; the
gates neutralise its occasional bad guesses.
"""
from __future__ import annotations

import json
import re
import time
from collections import defaultdict
from pathlib import Path

from curl_cffi import requests

from parklife import db

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "cache" / "nominatim_muni"
UA = "parklife-bot/0.1 (research; contact: paranoid2droid@gmail.com)"
NOM = "https://nominatim.openstreetmap.org/search"
KANJI_SUFFIX = ("市", "区", "町", "村")
_GUN = re.compile(r"^.+?郡")  # strip 〇〇郡 prefix on park-side town/village names

# GBIF prefecture kanji (from Nominatim addr.province/state) -> our slug, for the
# consistency gate. Built lazily from the DB's own prefecture slugs + kanji map.
_PREF_KANJI = {
    "北海道": "hokkaido", "青森県": "aomori", "岩手県": "iwate", "宮城県": "miyagi",
    "秋田県": "akita", "山形県": "yamagata", "福島県": "fukushima", "茨城県": "ibaraki",
    "栃木県": "tochigi", "群馬県": "gunma", "埼玉県": "saitama", "千葉県": "chiba",
    "東京都": "tokyo", "神奈川県": "kanagawa", "新潟県": "niigata", "富山県": "toyama",
    "石川県": "ishikawa", "福井県": "fukui", "山梨県": "yamanashi", "長野県": "nagano",
    "岐阜県": "gifu", "静岡県": "shizuoka", "愛知県": "aichi", "三重県": "mie",
    "滋賀県": "shiga", "京都府": "kyoto", "大阪府": "osaka", "兵庫県": "hyogo",
    "奈良県": "nara", "和歌山県": "wakayama", "鳥取県": "tottori", "島根県": "shimane",
    "岡山県": "okayama", "広島県": "hiroshima", "山口県": "yamaguchi", "徳島県": "tokushima",
    "香川県": "kagawa", "愛媛県": "ehime", "高知県": "kochi", "福岡県": "fukuoka",
    "佐賀県": "saga", "長崎県": "nagasaki", "熊本県": "kumamoto", "大分県": "oita",
    "宮崎県": "miyazaki", "鹿児島県": "kagoshima", "沖縄県": "okinawa",
}


def pref_slug(state: str | None) -> str | None:
    """Normalize a GBIF romaji stateProvince to our lowercase slug (fail soft)."""
    if not state:
        return None
    s = state.lower().strip()
    for junk in (" prefecture", "-ken", "-fu", "-to", " pref.", " pref", ",", "."):
        s = s.replace(junk, "")
    s = s.replace("ō", "o").replace("ū", "u").replace("ā", "a").replace(" ", "").strip()
    # common GBIF spellings / typos
    fix = {"hyogo": "hyogo", "nigata": "niigata", "tokyo": "tokyo", "osaka": "osaka",
           "kyoto": "kyoto", "gunnma": "gunma", "kanagawaken": "kanagawa"}
    s = fix.get(s, s)
    return s if s in _SLUGS else None


_SLUGS: set[str] = set()
_PARK_MUNI: dict[str, dict[str, set[int]]] = {}


def _load_parks(conn) -> None:
    """Build prefecture-slug set + {slug: {muni_token: {park_id}}} from the DB."""
    global _SLUGS
    _SLUGS = {r[0] for r in conn.execute("SELECT DISTINCT prefecture FROM park")}
    _PARK_MUNI.clear()
    for pid, pref, muni in conn.execute(
        "SELECT id, prefecture, municipality FROM park "
        "WHERE municipality IS NOT NULL AND municipality!=''"
    ):
        for part in muni.split():                    # "板橋区 練馬区" -> two tokens
            tok = _GUN.sub("", part)                 # "駿東郡長泉町" -> "長泉町"
            if tok:
                _PARK_MUNI.setdefault(pref, {}).setdefault(tok, set()).add(pid)


def _geocode(state: str, county: str) -> dict | None:
    """romaji (state, county) -> {'kanji': token, 'pref_kanji': str} via Nominatim, cached."""
    CACHE.mkdir(parents=True, exist_ok=True)
    q = f"{county}, {state}, Japan"
    ck = CACHE / (re.sub(r"[^A-Za-z0-9]+", "_", q)[:120] + ".json")
    if ck.exists():
        res = json.loads(ck.read_text())
    else:
        try:
            r = requests.get(
                NOM,
                params={"q": q, "format": "json", "countrycodes": "jp",
                        "addressdetails": 1, "limit": 1, "accept-language": "ja"},
                headers={"User-Agent": UA}, impersonate="chrome", timeout=20,
            )
            res = r.json() if r.status_code == 200 else []
        except Exception:
            res = []
        time.sleep(1.1)
        ck.write_text(json.dumps(res, ensure_ascii=False))
    if not res:
        return None
    addr = res[0].get("address", {})
    cands = [v for v in addr.values() if isinstance(v, str) and v.endswith(KANJI_SUFFIX)]
    spec = [c for c in cands if c.endswith(("区", "町", "村"))]
    kanji = spec[0] if spec else (cands[0] if cands else None)
    if not kanji:
        return None
    pref_kanji = addr.get("province") or addr.get("state") or ""
    return {"kanji": kanji, "pref_kanji": pref_kanji}


def resolve(conn, state: str | None, county: str | None) -> set[int]:
    """Return park ids in the (state, county) municipality, or empty set if any
    gate fails. Loads park municipalities once per connection."""
    if not _PARK_MUNI:
        _load_parks(conn)
    slug = pref_slug(state)
    if not slug or not county:
        return set()                                  # gate 1: prefecture
    g = _geocode(state, county)
    if not g:
        return set()
    # gate 3: consistency — geocoder's prefecture must match the record's
    if g["pref_kanji"] and _PREF_KANJI.get(g["pref_kanji"]) not in (None, slug):
        return set()
    kanji = g["kanji"]
    core = _GUN.sub("", kanji)
    muni = _PARK_MUNI.get(slug, {})
    hits: set[int] = set()
    for tok, pids in muni.items():                    # gate 2: reality
        if tok == kanji or tok == core or core in tok or tok in core:
            hits |= pids
    return hits
