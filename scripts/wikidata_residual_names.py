"""Targeted Wikidata SPARQL for species in species_profiles_extra.json that
still lack common_name_en / zh-Hans alias after the iNat localized-name
pass.

Strategy: one batched query per ~50 binomials at a time. For each match we
collect:

  - ``rdfs:label@en``     -> candidate for ``common_name_en``
  - ``rdfs:label@zh-Hans`` / ``@zh-CN`` / ``@zh``  -> candidate for
    ``aliases.zh-Hans``
  - ``rdfs:label@zh-Hant`` / ``@zh-TW``           -> candidate for
    ``aliases.zh-Hant``
  - ``skos:altLabel`` (any zh*) and ``wdt:P1843`` (taxon common name)
    as fallback for zh.

Cache: ``data/cache/wikidata_residual/<batch_hash>.json``.

Usage::

    .venv/bin/python -m scripts.wikidata_residual_names           # dry-run
    .venv/bin/python -m scripts.wikidata_residual_names --apply
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import sys
import time
from pathlib import Path

from curl_cffi import requests

ROOT = Path(__file__).resolve().parent.parent
JSON_FP = ROOT / "data" / "species_profiles_extra.json"
DB_FP = ROOT / "data" / "parklife.db"
CACHE = ROOT / "data" / "cache" / "wikidata_residual"
UA = "parklife-bot/0.1 (research; contact: paranoid2droid@gmail.com)"
ENDPOINT = "https://query.wikidata.org/sparql"
BATCH = 50


def sparql(binomials: list[str]) -> dict[str, dict[str, list[str]]]:
    """Returns {scientific_name: {lang: [labels]}}."""
    values = " ".join(f'"{b}"' for b in binomials)
    query = f"""
SELECT ?sci ?lang ?label WHERE {{
  VALUES ?sci {{ {values} }}
  ?taxon wdt:P225 ?sci.
  {{
    ?taxon rdfs:label ?label.
    BIND(LANG(?label) AS ?lang)
    FILTER(?lang IN ("en", "zh", "zh-cn", "zh-hans", "zh-tw", "zh-hant", "zh-hk"))
  }} UNION {{
    ?taxon skos:altLabel ?label.
    BIND(LANG(?label) AS ?lang)
    FILTER(?lang IN ("zh", "zh-cn", "zh-hans", "zh-tw", "zh-hant", "zh-hk"))
  }} UNION {{
    ?taxon wdt:P1843 ?label.
    BIND(LANG(?label) AS ?lang)
    FILTER(?lang IN ("zh", "zh-cn", "zh-hans", "zh-tw", "zh-hant", "zh-hk", "en"))
  }}
}}
"""
    key = hashlib.sha1(("|".join(sorted(binomials))).encode()).hexdigest()[:16]
    cp = CACHE / f"{key}.json"
    cp.parent.mkdir(parents=True, exist_ok=True)
    if cp.exists():
        try:
            return json.loads(cp.read_text(encoding="utf-8"))
        except Exception:
            pass
    r = requests.get(
        ENDPOINT,
        params={"query": query, "format": "json"},
        headers={"User-Agent": UA, "Accept": "application/sparql-results+json"},
        impersonate="chrome",
        timeout=60,
    )
    if r.status_code != 200:
        print(f"  [warn] sparql {r.status_code}: {r.text[:120]}")
        return {}
    j = r.json()
    out: dict[str, dict[str, list[str]]] = {}
    for b in j.get("results", {}).get("bindings", []):
        sci = b["sci"]["value"]
        lang = b["lang"]["value"]
        label = b["label"]["value"].strip()
        if not label:
            continue
        out.setdefault(sci, {}).setdefault(lang, []).append(label)
    cp.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    time.sleep(0.5)
    return out


def pick_zh_hans(label_map: dict[str, list[str]]) -> str | None:
    # Prefer zh-hans, then zh-cn, then zh (assumed simplified-ish).
    for lang in ("zh-hans", "zh-cn", "zh"):
        if label_map.get(lang):
            return label_map[lang][0]
    return None


def pick_zh_hant(label_map: dict[str, list[str]]) -> str | None:
    for lang in ("zh-hant", "zh-tw", "zh-hk"):
        if label_map.get(lang):
            return label_map[lang][0]
    return None


def pick_en(label_map: dict[str, list[str]]) -> str | None:
    if not label_map.get("en"):
        return None
    # Reject if the en label looks like a scientific name (capitalised single
    # word with no common-name suffix). Wikidata sometimes uses the binomial
    # itself as the English label.
    for v in label_map["en"]:
        if v.lower() in ("", "homo sapiens"):
            continue
        # Reject if v matches the pattern "Genus species" exactly
        if re.match(r"^[A-Z][a-z]+ [a-z]+$", v):
            continue
        return v
    return None


def main() -> int:
    apply = "--apply" in sys.argv
    data = json.loads(JSON_FP.read_text(encoding="utf-8"))
    conn = sqlite3.connect(DB_FP)

    en_targets: list[str] = []
    zh_targets: list[str] = []
    for sci, payload in data.items():
        row = conn.execute(
            "SELECT id, common_name_en FROM species WHERE scientific_name=?",
            (sci,),
        ).fetchone()
        if not row:
            continue
        sid, en = row
        if not en and not payload.get("common_name_en"):
            en_targets.append(sci)
        sidecar_zh = (payload.get("aliases") or {}).get("zh-Hans")
        has_zh = conn.execute(
            "SELECT 1 FROM species_alias WHERE species_id=? AND lang='zh-Hans'", (sid,)
        ).fetchone()
        if not has_zh and not sidecar_zh:
            zh_targets.append(sci)

    all_targets = sorted(set(en_targets) | set(zh_targets))
    print(f"EN targets: {len(en_targets)}, ZH targets: {len(zh_targets)}, union: {len(all_targets)}")

    en_found: dict[str, str] = {}
    zh_hans_found: dict[str, str] = {}
    zh_hant_found: dict[str, str] = {}
    for i in range(0, len(all_targets), BATCH):
        chunk = all_targets[i : i + BATCH]
        print(f"  batch {i//BATCH+1}/{(len(all_targets)+BATCH-1)//BATCH}: {len(chunk)} taxa")
        results = sparql(chunk)
        for sci in chunk:
            labels = results.get(sci) or {}
            if sci in en_targets:
                v = pick_en(labels)
                if v:
                    en_found[sci] = v
            if sci in zh_targets:
                v = pick_zh_hans(labels)
                if v:
                    zh_hans_found[sci] = v
                v2 = pick_zh_hant(labels)
                if v2:
                    zh_hant_found[sci] = v2

    print(f"  EN resolved: {len(en_found)}")
    print(f"  zh-Hans resolved: {len(zh_hans_found)}")
    print(f"  zh-Hant resolved: {len(zh_hant_found)}")
    print()
    print("=== EN samples (first 20) ===")
    for sci, v in list(en_found.items())[:20]:
        print(f"  {sci:38s} -> {v}")
    print()
    print("=== ZH-Hans samples (first 20) ===")
    for sci, v in list(zh_hans_found.items())[:20]:
        print(f"  {sci:38s} -> {v}")

    if not apply:
        print()
        print("(dry-run; pass --apply to write to sidecar)")
        return 0

    for sci, v in en_found.items():
        data[sci]["common_name_en"] = v
    for sci, v in zh_hans_found.items():
        aliases = data[sci].setdefault("aliases", {})
        aliases["zh-Hans"] = v
    for sci, v in zh_hant_found.items():
        aliases = data[sci].setdefault("aliases", {})
        aliases.setdefault("zh-Hant", v)

    JSON_FP.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {JSON_FP}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
