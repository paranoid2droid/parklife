"""Scraper for parks under the Tokyo Metropolitan Park Association
(tokyo-park.or.jp). All 137 parks share the same template; a single
extractor handles them all.

The template's `<h2>花の見ごろ情報</h2>` block contains four `<h4>` season
headings (春/夏/秋/冬) each followed by a `<p>` with comma-separated
katakana species names.

Output: observation rows with (raw_name, lang='ja-kana', season-months).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from bs4 import BeautifulSoup

# season -> months (1=Jan ... 12=Dec)
SEASON_MONTHS: dict[str, list[int]] = {
    "春": [3, 4, 5],
    "夏": [6, 7, 8],
    "秋": [9, 10, 11],
    "冬": [12, 1, 2],
}


def months_bitmap(months: Iterable[int]) -> int:
    """Pack months into a 12-bit field; bit 0 = January, bit 11 = December."""
    bits = 0
    for m in months:
        bits |= 1 << (m - 1)
    return bits


@dataclass
class RawObservation:
    raw_name: str         # e.g. 'ソメイヨシノ'
    months_bitmap: int    # 12-bit
    location_hint: str | None = None  # filled in if section had a sub-location
    characteristics: str | None = None
    section: str = "花の見ごろ"


def extract(html: bytes) -> list[RawObservation]:
    """Parse a TMG park page; return raw observations from 花の見ごろ情報."""
    soup = BeautifulSoup(html, "lxml")
    h2 = soup.find("h2", string=lambda s: s and "花の見ごろ" in s)
    if not h2:
        return []
    obs: list[RawObservation] = []
    # walk h4 elements that are descendants of the section between this h2 and the next h2
    for h4 in h2.find_all_next("h4"):
        # stop if we passed into a later h2 section
        if h4.find_previous("h2") is not h2:
            break
        season = h4.get_text(strip=True)
        if season not in SEASON_MONTHS:
            continue
        p = h4.find_next("p")
        if not p:
            continue
        text = " ".join(p.get_text().split())
        bitmap = months_bitmap(SEASON_MONTHS[season])
        # Names are separated by 、 (Japanese comma) or , (latin comma) — split on both.
        for token in text.replace(",", "、").split("、"):
            name = token.strip()
            if not name:
                continue
            obs.append(RawObservation(raw_name=name, months_bitmap=bitmap, section=season))
    return obs
