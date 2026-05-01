"""Backfill Japanese vernacular labels from Wikidata by scientific name.

Queries Wikidata's taxon-name property (P225) for species whose
common_name_ja is missing, then uses the Japanese rdfs:label when it looks like
a real Japanese name. Results are cached per scientific name.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

from curl_cffi import requests

from parklife import db

ROOT = Path(__file__).resolve().parent.parent
UA = "parklife-bot/0.1 (research; contact: paranoid2droid@gmail.com)"
ENDPOINT = "https://query.wikidata.org/sparql"
CACHE_DIR = ROOT / "data" / "cache" / "wikidata_ja"
BATCH = 80
JP_RE = re.compile(r"[ぁ-んァ-ヶ一-龯々ー]")


def safe_filename(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", s)[:120]


def cache_path(sci: str) -> Path:
    return CACHE_DIR / f"{safe_filename(sci)}.json"


def looks_japanese(label: str | None, sci: str) -> bool:
    if not label:
        return False
    label = label.strip()
    if not label or label.lower() == sci.lower():
        return False
    return bool(JP_RE.search(label))


def build_query(names: list[str]) -> str:
    values = " ".join(f'"{n}"' for n in names if '"' not in n)
    return f"""
SELECT ?name ?label WHERE {{
  VALUES ?name {{ {values} }}
  ?taxon wdt:P225 ?name.
  ?taxon rdfs:label ?label FILTER(LANG(?label)="ja")
}}
"""


def fetch_batch(names: list[str]) -> dict[str, str]:
    q = build_query(names)
    r = requests.get(
        ENDPOINT,
        params={"query": q, "format": "json"},
        headers={"User-Agent": UA, "Accept": "application/sparql-results+json"},
        timeout=60,
        impersonate="chrome",
    )
    if r.status_code != 200:
        print(f"  HTTP {r.status_code}: {r.text[:200]}")
        return {}
    out: dict[str, str] = {}
    for row in r.json().get("results", {}).get("bindings", []):
        name = row.get("name", {}).get("value")
        label = row.get("label", {}).get("value")
        if name and looks_japanese(label, name):
            out.setdefault(name, label)
    return out


def lookup(names: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    uncached: list[str] = []
    for name in names:
        cp = cache_path(name)
        if cp.exists():
            try:
                data = json.loads(cp.read_text(encoding="utf-8"))
                label = data.get("ja") or ""
                if label:
                    out[name] = label
            except Exception:
                uncached.append(name)
        else:
            uncached.append(name)

    if uncached:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        for i in range(0, len(uncached), BATCH):
            chunk = uncached[i:i+BATCH]
            got = fetch_batch(chunk)
            for name in chunk:
                label = got.get(name, "")
                cache_path(name).write_text(
                    json.dumps({"ja": label}, ensure_ascii=False),
                    encoding="utf-8",
                )
                if label:
                    out[name] = label
            done = min(i + BATCH, len(uncached))
            print(f"  batch {i//BATCH+1}: {done}/{len(uncached)} fetched, hits={len(out)}")
            time.sleep(1.0)
    return out


def main(limit: int | None = None) -> int:
    db_path = ROOT / "data" / "parklife.db"
    with db.connect(db_path) as conn:
        rows = list(conn.execute("""
            SELECT id, scientific_name, common_name_en
            FROM species
            WHERE (common_name_ja IS NULL OR common_name_ja = '')
              AND scientific_name IS NOT NULL AND scientific_name <> ''
            ORDER BY id
        """))
    if limit:
        rows = rows[:limit]
    names = sorted({r["scientific_name"] for r in rows})
    print(f"species missing common_name_ja: {len(rows)}")
    print(f"unique scientific names to query: {len(names)}")
    labels = lookup(names)

    updated = alias_inserted = 0
    examples: list[tuple[str, str, str]] = []
    with db.connect(db_path) as conn:
        for r in rows:
            label = labels.get(r["scientific_name"])
            if not label:
                continue
            conn.execute("UPDATE species SET common_name_ja=? WHERE id=?", (label, r["id"]))
            cur = conn.execute(
                """INSERT OR IGNORE INTO species_alias
                   (species_id, raw_name, lang, status)
                   VALUES (?, ?, 'ja', 'resolved')""",
                (r["id"], label),
            )
            alias_inserted += cur.rowcount
            updated += 1
            if len(examples) < 20:
                examples.append((r["scientific_name"], r["common_name_en"] or "", label))
        conn.commit()

    print(f"\n=== Wikidata ja pass done ===")
    print(f"  labels found: {len(labels)}")
    print(f"  common_name_ja filled: {updated}")
    print(f"  ja aliases inserted: {alias_inserted}")
    if examples:
        print("examples:")
        for sci, en, ja in examples:
            print(f"  {sci:<36} {en:<32} -> {ja}")
    return 0


if __name__ == "__main__":
    cap = int(sys.argv[1]) if len(sys.argv) > 1 else None
    raise SystemExit(main(cap))
