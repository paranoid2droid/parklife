"""Fetch English / Chinese common names from iNaturalist for species that
have an ``inat_taxon_id`` but lack ``common_name_en`` / ``zh-Hans`` alias.

Endpoint: ``GET /v1/taxa/{id}?locale=<locale>`` — returns the taxon with
``preferred_common_name`` set in the requested locale.

Targets: species listed in ``data/species_profiles_extra.json`` whose
profile is curated but whose name fields are still empty. Output is
written back to the same sidecar JSON as ``common_name_en`` /
``aliases.{zh-Hans,zh-Hant}`` fields, so re-running
``scripts.seed_species_profiles`` propagates them to the DB tables.

Caches one JSON per (taxon_id, locale) under
``data/cache/inat_taxon_localized/``. Idempotent.

Usage::

    .venv/bin/python -m scripts.inat_localized_names           # dry-run
    .venv/bin/python -m scripts.inat_localized_names --apply
"""

from __future__ import annotations

import json
import sqlite3
import sys
import time
from pathlib import Path

from curl_cffi import requests

ROOT = Path(__file__).resolve().parent.parent
JSON_FP = ROOT / "data" / "species_profiles_extra.json"
DB_FP = ROOT / "data" / "parklife.db"
CACHE = ROOT / "data" / "cache" / "inat_taxon_localized"
UA = "parklife-bot/0.1 (research; contact: paranoid2droid@gmail.com)"
API = "https://api.inaturalist.org/v1/taxa"
REQUEST_DELAY_SECONDS = 1.0

LOCALES_FOR = {"en": "en", "zh-Hans": "zh-CN", "zh-Hant": "zh-TW"}


def fetch_taxon(taxon_id: int, locale: str) -> dict | None:
    cp = CACHE / f"{taxon_id}__{locale}.json"
    cp.parent.mkdir(parents=True, exist_ok=True)
    if cp.exists():
        try:
            return json.loads(cp.read_text(encoding="utf-8"))
        except Exception:
            pass
    r = requests.get(
        f"{API}/{taxon_id}",
        params={"locale": locale},
        headers={"User-Agent": UA, "Accept-Language": locale},
        impersonate="chrome",
        timeout=20,
    )
    if r.status_code != 200:
        return None
    data = r.json()
    cp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    time.sleep(REQUEST_DELAY_SECONDS)
    return data


def extract_name(data: dict | None, locale: str) -> str | None:
    if not data:
        return None
    results = data.get("results") or []
    if not results:
        return None
    r = results[0]
    # iNat returns the locale-appropriate name in preferred_common_name.
    # english_common_name is also always available as a backup for locale=en.
    name = r.get("preferred_common_name") or ""
    if locale == "en" and not name:
        name = r.get("english_common_name") or ""
    name = name.strip()
    if not name:
        return None
    # Reject if the returned name is just a romanization of the JA name —
    # heuristic: ASCII letters with hyphens only and no real English words.
    if locale == "en" and "-" in name and " " not in name and name.replace("-", "").isalpha():
        return None
    return name


def main() -> int:
    apply = "--apply" in sys.argv
    data = json.loads(JSON_FP.read_text(encoding="utf-8"))
    conn = sqlite3.connect(DB_FP)

    en_targets: list[tuple[str, int]] = []
    zh_targets: list[tuple[str, int]] = []
    for sci, payload in data.items():
        row = conn.execute(
            "SELECT id, common_name_en, inat_taxon_id FROM species WHERE scientific_name=?",
            (sci,),
        ).fetchone()
        if not row:
            continue
        sid, en, taxid = row
        if not taxid:
            continue
        if not en and not payload.get("common_name_en"):
            en_targets.append((sci, taxid))
        has_zh = conn.execute(
            "SELECT 1 FROM species_alias WHERE species_id=? AND lang='zh-Hans'", (sid,)
        ).fetchone()
        sidecar_zh = (payload.get("aliases") or {}).get("zh-Hans")
        if not has_zh and not sidecar_zh:
            zh_targets.append((sci, taxid))

    print(f"EN targets: {len(en_targets)}")
    print(f"ZH targets: {len(zh_targets)}")
    print(f"(cached responses reused; ~1 new request/sec when uncached)")

    en_found: dict[str, str] = {}
    zh_found: dict[str, str] = {}
    for sci, tid in en_targets:
        d = fetch_taxon(tid, "en")
        n = extract_name(d, "en")
        if n:
            en_found[sci] = n
    print(f"  EN names resolved: {len(en_found)}")

    for sci, tid in zh_targets:
        d = fetch_taxon(tid, "zh-CN")
        n = extract_name(d, "zh-CN")
        if n:
            zh_found[sci] = n
    print(f"  ZH names resolved: {len(zh_found)}")

    print()
    print("=== EN samples (first 20) ===")
    for sci, n in list(en_found.items())[:20]:
        print(f"  {sci:38s} -> {n}")
    print()
    print("=== ZH samples (first 20) ===")
    for sci, n in list(zh_found.items())[:20]:
        print(f"  {sci:38s} -> {n}")

    if not apply:
        print()
        print("(dry-run; pass --apply to write to sidecar JSON)")
        return 0

    for sci, n in en_found.items():
        data[sci]["common_name_en"] = n
    for sci, n in zh_found.items():
        aliases = data[sci].setdefault("aliases", {})
        aliases["zh-Hans"] = n

    JSON_FP.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {JSON_FP}")
    print(f"  patched {len(en_found)} common_name_en + {len(zh_found)} zh-Hans")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
