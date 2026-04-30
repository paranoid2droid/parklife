"""Filter the Phase A scan: which Tokyo parks actually have animal-content
headings or block text (not just nav links)?
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    data = json.loads(
        (ROOT / "data" / "scan" / "tokyo_animal_candidates.json").read_text(encoding="utf-8")
    )
    interesting: list[tuple[str, dict]] = []
    for slug, info in data.items():
        if info.get("headings"):
            interesting.append((slug, info))

    print(f"Tokyo parks with animal-related HEADINGS: {len(interesting)}")
    print()
    for slug, info in interesting:
        print(f"  === {slug} ===")
        for h in info["headings"]:
            print(f"    H: {h}")
        for b in info.get("blocks", [])[:1]:  # first block only for brevity
            print(f"    text: {b['text'][:300]}")
        print()


if __name__ == "__main__":
    main()
