"""Append per-prefecture iNat+GBIF enrichment tasks for the 40 remaining
prefectures to data/run_queue.txt, followed by a single normalize→dedupe
finisher. eBird is intentionally omitted (needs EBIRD_API_KEY).

Idempotent-ish: only appends lines that are not already present as a
`pending:`/`done(...)`/`failed(...)` entry for the same command.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUEUE = ROOT / "data" / "run_queue.txt"

PREFS = [
    "hokkaido", "aomori", "iwate", "miyagi", "akita", "yamagata", "fukushima",
    "ibaraki", "tochigi", "gunma", "niigata", "toyama", "ishikawa", "fukui",
    "yamanashi", "nagano", "gifu", "shizuoka", "mie", "shiga", "hyogo", "nara",
    "wakayama", "tottori", "shimane", "okayama", "hiroshima", "yamaguchi",
    "tokushima", "kagawa", "ehime", "kochi", "fukuoka", "saga", "nagasaki",
    "kumamoto", "oita", "miyazaki", "kagoshima", "okinawa",
]


def main() -> int:
    existing = QUEUE.read_text(encoding="utf-8") if QUEUE.exists() else ""
    cmds: list[str] = []
    for pref in PREFS:
        cmds.append(f"inaturalist {pref}")
        cmds.append(f"gbif {pref}")
    # Single finisher after all enrichment.
    cmds += ["normalize", "backfill_observations", "dedupe"]

    new_lines = []
    skipped = 0
    for c in cmds:
        if f": {c}\n" in existing or f": {c}" in existing.splitlines():
            skipped += 1
            continue
        new_lines.append(f"pending: {c}")

    header = ("\n# --- National expansion enrichment (40 prefs, iNat+GBIF) "
              "queued 2026-06-20 ---")
    body = header + "\n" + "\n".join(new_lines) + "\n"
    with QUEUE.open("a", encoding="utf-8") as f:
        f.write(body)
    print(f"appended {len(new_lines)} pending tasks (skipped {skipped} dupes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
