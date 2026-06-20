"""Canonical parking classifier — single source of truth.

Every code path that decides whether a park has public parking goes through
this module so the rules (and their confidence tiers) stay consistent as the
dataset grows nationwide. Pure functions, no DB / no I/O.

Two evidence channels feed one decision:

  * TEXT  — scraped from a park's official / operator pages (`classify_text`)
  * OSM   — amenity=parking elements near the park centre (`classify_osm`)

Each returns ``(has_parking, source, evidence)`` where:
  has_parking : 1 (public parking) | 0 (none / restricted-only) | None (unknown)
  source      : a stable tier tag (see SOURCE_* constants) recording HOW we know
  evidence    : short human-readable snippet for `park.parking_info`

Confidence ordering (high → low), also the priority a caller should apply:
  text:negative  > text:restricted > text:positive > text:mention
  > osm:present   > (osm:absent / unknown → None)

CRITICAL SEMANTICS — absence is not negation. "No OSM parking node within
RADIUS_M" or "no page mentions 駐車場" means **unknown**, NOT "no parking".
OSM coverage in Japan is sparse, so an OSM miss must leave has_parking NULL
and let later text enrichment settle it. Only explicit TEXT phrasing
(駐車場なし / ありません) or restricted-only access yields a confident 0.
This is what keeps confident-but-wrong negatives out of nationwide expansion.
"""
from __future__ import annotations

import re

# --- evidence-tier tags (stored in park.parking_source) ---------------------
SOURCE_TEXT_NEGATIVE = "text:negative"     # explicit "駐車場なし/ありません"        → 0
SOURCE_TEXT_RESTRICTED = "text:restricted"  # 団体/障害者/観光バス only               → 0
SOURCE_TEXT_POSITIVE = "text:positive"      # capacity / fee / hours / 駐車場 heading → 1
SOURCE_TEXT_MENTION = "text:mention"        # bare 駐車場 mention in body             → 1
SOURCE_OSM_PRESENT = "osm:present"          # public amenity=parking nearby          → 1
SOURCE_OSM_ABSENT = "osm:absent"            # OSM queried, none found                → None
SOURCE_TMG_NO_FACILITY = "tmg:no-facility"  # TMG facility list, no 駐車場            → 0
SOURCE_MANUAL = "manual"                    # human-curated override                  → 1/0
SOURCE_UNKNOWN = "unknown"                  # no evidence at all                     → None

PARKING_KW = ("駐車場", "パーキング", "コインパーキング")

NEGATIVE_PATTERNS = [
    re.compile(r"駐車場(?:は|の用意は)?(?:ございません|ありません|なし|はない)"),
    re.compile(r"専用(?:の)?駐車場(?:は)?(?:ございません|ありません|なし)"),
    re.compile(r"公園(?:に|には)(?:専用)?駐車場(?:は)?(?:ありません|なし)"),
    re.compile(r"駐車場(?:は)?設置(?:しておりません|していません|されていません)"),
    re.compile(r"駐車場(?:は)?設けて(?:おりません|いません)"),
    re.compile(r"お車での(?:ご)?来園は(?:ご)?遠慮"),
    # bullet-style "駐車場 なし" / "駐車場：なし" (Chiba pref pages, etc.)
    re.compile(r"駐車場[\s:：]*(?:なし|無し|無|ない)(?![ぁ-んー])"),
]

# Restricted-access — parking exists but not for general visitors.
# Per user constraint: 団体予約のみ / 障害者専用 / 観光バス専用 must NOT count as
# "公開駐車場あり". These collapse to has_parking=0.
RESTRICTED_PATTERNS = [
    re.compile(r"団体(?:のお客様|利用|予約)?(?:の方)?のみ"),
    re.compile(r"事前(?:の)?(?:予約|申込)(?:制|のみ)"),
    re.compile(r"(?:身体)?障害者(?:の方)?(?:専用|のみ)"),
    re.compile(r"車椅子・?障害者(?:の方)?の(?:お)?車"),
    re.compile(r"観光バス(?:専用|のみ)"),
]

# Positive signals: explicit capacity / fee / hours prove a real public lot.
POSITIVE_PATTERNS = [
    re.compile(r"\d+\s*台"),
    re.compile(r"普通車\s*\d"),
    re.compile(r"\d+\s*分まで\d+\s*円"),
    re.compile(r"\d+\s*時間まで\d+\s*円"),
    re.compile(r"利用料金"),
    re.compile(r"営業時間"),
    re.compile(r"駐車料金"),
    # bullet-style "駐車場 あり" / "駐車場：あり"
    re.compile(r"駐車場[\s:：]*(?:あり|有り|有)(?![ぁ-んー])"),
]


def _evidence_window(text: str, match) -> str:
    start = max(0, match.start() - 60)
    end = min(len(text), match.end() + 140)
    return text[start:end]


def classify_text(
    block: str | None, full_text: str
) -> tuple[int | None, str, str | None]:
    """Classify from scraped text. Returns (has_parking, source, evidence).

    Returns (None, SOURCE_UNKNOWN, None) when the text carries no signal — the
    caller should then fall back to OSM. Absence of a 駐車場 mention is treated
    as unknown, never as a confident "no parking".
    """
    haystack = block or full_text

    # 1) Negative phrasing trumps anything else.
    for p in NEGATIVE_PATTERNS:
        m = p.search(haystack)
        if m:
            return (0, SOURCE_TEXT_NEGATIVE, _evidence_window(haystack, m))

    # 2) Restricted-access (団体予約のみ / 障害者専用 / 観光バスのみ) — count as
    #    "no public parking". Only check near a 駐車 mention so unrelated
    #    reservation language doesn't mis-fire.
    for m in re.finditer(r"駐車", haystack):
        window = haystack[max(0, m.start() - 80): m.end() + 200]
        for p in RESTRICTED_PATTERNS:
            if p.search(window):
                return (0, SOURCE_TEXT_RESTRICTED, _evidence_window(haystack, m))

    # 3) Heading-anchored 駐車場 block → parking exists (the section itself is
    #    the signal). Distinguish "positive marker present" from a bare block.
    if block:
        if any(p.search(block) for p in POSITIVE_PATTERNS):
            return (1, SOURCE_TEXT_POSITIVE, block[:600])
        return (1, SOURCE_TEXT_MENTION, block[:600])

    # 4) No heading — search body for the word with positive context nearby.
    park_iter = list(re.finditer(r"駐車場|パーキング", full_text))
    for m in park_iter:
        ctx = full_text[max(0, m.start() - 80): m.end() + 200]
        if any(p.search(ctx) for p in POSITIVE_PATTERNS):
            return (1, SOURCE_TEXT_POSITIVE, _evidence_window(full_text, m))

    # 5) Bare 駐車場 mention in stripped body (facility list / ops note) — almost
    #    always a real lot; restricted/negative were ruled out above.
    if park_iter:
        return (1, SOURCE_TEXT_MENTION, _evidence_window(full_text, park_iter[0]))

    return (None, SOURCE_UNKNOWN, None)


def classify_osm(
    usable_count: int, radius_m: int
) -> tuple[int | None, str, str]:
    """Classify from an OSM amenity=parking query result.

    ``usable_count`` = number of public (non-private/disused) parking elements
    found within ``radius_m``. Presence → 1; **absence → None (unknown)**, never
    a confident 0, because OSM under-mapping is indistinguishable from a genuine
    lack of parking. Callers must not overwrite a NULL row's text verdict.
    """
    if usable_count > 0:
        return (
            1,
            SOURCE_OSM_PRESENT,
            f"OSM: {usable_count} amenity=parking element(s) within {radius_m}m",
        )
    return (
        None,
        SOURCE_OSM_ABSENT,
        f"OSM: no amenity=parking within {radius_m}m (unknown, not confirmed absent)",
    )
