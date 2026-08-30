"""Backfill Traditional-Chinese (zh-Hant) aliases from existing zh-Hans via OpenCC.

Thousands of species carry a simplified-Chinese alias (``lang='zh-Hans'`` — from
iNat/Wikidata/manual passes) but no traditional form, because only
``fetch_inat_zh_names`` derived zh-Hant and it ran on a subset. OpenCC's ``s2t``
converter is the same method that pass used, so we can lift the whole simplified
corpus to traditional locally — no network.

Convention (matches ``fetch_inat_zh_names``): insert a zh-Hant row ONLY when the
converted form differs from the simplified source. When s2t is a no-op (the name
has no simplified/traditional distinction, e.g. 花壇蟋蟀), no separate row is
needed — the UI falls back to zh-Hans. Idempotent (skips species that already
have any zh-Hant alias). Reversible::

    DELETE FROM species_alias WHERE status='opencc-hant';

Usage::

    .venv/bin/python -m scripts.backfill_zh_hant_opencc --dry-run [--limit N]
    .venv/bin/python -m scripts.backfill_zh_hant_opencc
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

from opencc import OpenCC

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "parklife.db"
_cc = OpenCC("s2t")


def main() -> int:
    dry = "--dry-run" in sys.argv
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    # One simplified source per species (prefer the shortest = usually the
    # canonical vernacular, not a compound); species with any zh-Hant skipped.
    rows = conn.execute(
        """
        SELECT s.id AS sid, s.scientific_name,
               (SELECT a.raw_name FROM species_alias a
                WHERE a.species_id=s.id AND a.lang='zh-Hans'
                ORDER BY LENGTH(a.raw_name), a.id LIMIT 1) AS hans
        FROM species s
        WHERE EXISTS (SELECT 1 FROM species_alias a
                      WHERE a.species_id=s.id AND a.lang='zh-Hans')
          AND NOT EXISTS (SELECT 1 FROM species_alias a
                          WHERE a.species_id=s.id AND a.lang='zh-Hant')
        ORDER BY s.id
        """
    ).fetchall()
    if limit:
        rows = rows[:limit]

    print(f"candidates (zh-Hans present, zh-Hant absent): {len(rows)}")

    inserts: list[tuple[int, str]] = []
    noop = 0
    for r in rows:
        hans = (r["hans"] or "").strip()
        if not hans:
            continue
        hant = _cc.convert(hans)
        if hant and hant != hans:
            inserts.append((r["sid"], hant))
        else:
            noop += 1

    print(f"  will insert zh-Hant for {len(inserts)} species "
          f"({noop} are s2t no-ops → UI falls back to zh-Hans)")
    for sid, hant in inserts[:15]:
        src = next(x["hans"] for x in rows if x["sid"] == sid)
        print(f"    {sid}: {src} -> {hant}")

    if dry:
        print("\n--dry-run: no DB writes")
        return 0

    for sid, hant in inserts:
        conn.execute(
            "INSERT INTO species_alias(species_id,raw_name,lang,status) VALUES(?,?,?,?)",
            (sid, hant, "zh-Hant", "opencc-hant"),
        )
    conn.commit()
    print(f"\nwrote {len(inserts)} zh-Hant aliases "
          f"(reversible: DELETE FROM species_alias WHERE status='opencc-hant')")
    return 0


if __name__ == "__main__":
    sys.exit(main())
