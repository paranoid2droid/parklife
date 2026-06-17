"""Normalize free-text photo attribution strings to a license family code.

Photo rows store attribution as the source emitted it, e.g.
  iNaturalist:        "(c) Елена Левкина, some rights reserved (CC BY-NC)"
  iNaturalist (free): "(c) name, all rights reserved"
  Wikimedia Commons:  "Alpsdake · CC BY-SA 4.0 · Wikimedia Commons"

`parse_license` extracts a normalized family code (version stripped) so we can
filter photos by reuse terms. `allows_commercial` is the gate that the
productization work cares about — which species keep at least one photo we can
ship in a commercial product.
"""

from __future__ import annotations

import re

# Canonical family codes, ordered longest-token-first so the most specific
# license matches before a shorter prefix (CC BY-NC before CC BY).
_CC_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"cc[\s-]*by-nc-sa", re.I), "CC BY-NC-SA"),
    (re.compile(r"cc[\s-]*by-nc-nd", re.I), "CC BY-NC-ND"),
    (re.compile(r"cc[\s-]*by-nc", re.I), "CC BY-NC"),
    (re.compile(r"cc[\s-]*by-sa", re.I), "CC BY-SA"),
    (re.compile(r"cc[\s-]*by-nd", re.I), "CC BY-ND"),
    (re.compile(r"cc[\s-]*by", re.I), "CC BY"),
    (re.compile(r"\bcc0\b", re.I), "CC0"),
]
_PD = re.compile(r"public domain", re.I)
# iNaturalist labels CC0 photos "no rights reserved" (copyright waived).
_CC0_WORDS = re.compile(r"no rights reserved", re.I)
_FAL = re.compile(r"\bFAL\b")  # Free Art License (copyleft, commercial OK)
_ARR = re.compile(r"all rights reserved", re.I)

# License families whose terms permit commercial reuse.
COMMERCIAL_OK = {"CC0", "PD", "CC BY", "CC BY-SA", "CC BY-ND", "FAL"}


def parse_license(attribution: str | None) -> str | None:
    """Return a normalized license family code, or None if unrecognizable."""
    if not attribution:
        return None
    for pat, code in _CC_PATTERNS:
        if pat.search(attribution):
            return code
    if _CC0_WORDS.search(attribution):
        return "CC0"
    if _PD.search(attribution):
        return "PD"
    if _FAL.search(attribution):
        return "FAL"
    if _ARR.search(attribution):
        return "ARR"
    return None


def allows_commercial(license_code: str | None) -> bool:
    """True if the (normalized) license permits commercial use."""
    return license_code in COMMERCIAL_OK
