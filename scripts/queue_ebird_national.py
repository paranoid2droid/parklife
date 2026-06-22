"""Append eBird enrichment tasks for all 43 newly-added prefectures to the
queue, followed by a re-run of normalize/backfill/dedupe so bird observations
get linked + deduped. Run AFTER the iNat/GBIF wave is already queued; these
lines land at EOF and run last. eBird key comes from data/.ebird_key.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUEUE = ROOT / "data" / "run_queue.txt"

PREFS = [
    "aichi", "osaka", "kyoto",
    "hokkaido", "aomori", "iwate", "miyagi", "akita", "yamagata", "fukushima",
    "ibaraki", "tochigi", "gunma", "niigata", "toyama", "ishikawa", "fukui",
    "yamanashi", "nagano", "gifu", "shizuoka", "mie", "shiga", "hyogo", "nara",
    "wakayama", "tottori", "shimane", "okayama", "hiroshima", "yamaguchi",
    "tokushima", "kagawa", "ehime", "kochi", "fukuoka", "saga", "nagasaki",
    "kumamoto", "oita", "miyazaki", "kagoshima", "okinawa",
]


def main() -> int:
    lines = ["", "# --- National eBird enrichment + re-dedupe (queued 2026-06-20) ---"]
    for pref in PREFS:
        lines.append(f"pending: ebird {pref}")
    lines += ["pending: normalize", "pending: backfill_observations",
              "pending: dedupe"]
    with QUEUE.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"appended {len(PREFS)} ebird tasks + 3 finishers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
