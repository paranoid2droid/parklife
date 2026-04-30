"""Load seed park lists from data/seeds/*.yaml.

Seed YAML format (per file = one prefecture):

    prefecture: tokyo
    operator: 東京都公園協会
    parks:
      - slug: yoyogi
        name_ja: 代々木公園
        name_en: Yoyogi Park
        municipality: 渋谷区
        official_url: https://...
        lat: 35.671
        lon: 139.694
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import json


@dataclass
class SeedPark:
    slug: str
    name_ja: str
    prefecture: str
    operator: str | None = None
    name_en: str | None = None
    municipality: str | None = None
    official_url: str | None = None
    lat: float | None = None
    lon: float | None = None


def load(seed_dir: str | Path) -> list[SeedPark]:
    """Load all seed JSON files from the directory.

    Using JSON (not YAML) to avoid an extra dependency; switch later if needed.
    """
    parks: list[SeedPark] = []
    for path in sorted(Path(seed_dir).glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        prefecture = data["prefecture"]
        operator = data.get("operator")
        for raw in data.get("parks", []):
            parks.append(
                SeedPark(
                    slug=raw["slug"],
                    name_ja=raw["name_ja"],
                    prefecture=prefecture,
                    operator=raw.get("operator", operator),
                    name_en=raw.get("name_en"),
                    municipality=raw.get("municipality"),
                    official_url=raw.get("official_url"),
                    lat=raw.get("lat"),
                    lon=raw.get("lon"),
                )
            )
    return parks
