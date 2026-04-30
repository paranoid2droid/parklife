"""Resolve katakana species names to canonical taxa via the Japanese
Wikipedia API.

Why Wikipedia and not GBIF: GBIF's free-text search misfires on Japanese
vernacular katakana (e.g., サクラ → marine shrimp). Japanese Wikipedia has
near-100% coverage for common vernacular names and a structured taxobox.

Returned fields per name:
- title           Wikipedia article title (= canonical Japanese name)
- scientific_name best-effort Latin binomial; may be partial or None
- kingdom         'plantae' / 'animalia' / 'fungi' / None
- taxon_group     'bird' / 'mammal' / 'insect' / ... / None
- is_disambig     True if the page is a disambiguation hub
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path

from curl_cffi import requests

UA = "parklife-bot/0.1 (research; contact: paranoid2droid@gmail.com)"
API = "https://ja.wikipedia.org/w/api.php"

# regex: match a wiki-template Snamei{|i}|Genus|species form
SNAMEI = re.compile(
    r"\{\{Snamei(?:\|i)?\|+([A-Z][a-z]+)\|+([×]?[a-z]+(?:\s+[a-z]+)?)"
)
# match an italic Latin binomial in wikitext (full form, not the abbreviated
# 'G. biloba' shorthand used in subsequent paragraphs)
ITALIC_BINOMIAL = re.compile(
    r"''([A-Z][a-z]{2,}(?:\s+×)?\s+[a-z]+(?:\s+[a-z]+)?)''"
)
# raw italic abbreviation like 'G. biloba'
ABBREV_BINOMIAL = re.compile(
    r"''([A-Z]\.\s*[a-z]+)''"
)

DISAMBIG_MARKERS = ("{{Aimai}}", "__DISAMBIG__", "{{aimai", "{{Disambig")

KINGDOM_HINTS: list[tuple[str, str]] = [
    ("植物界", "plantae"),
    ("動物界", "animalia"),
    ("菌界",   "fungi"),
]

# ordered: most specific first
TAXON_HINTS: list[tuple[str, str]] = [
    ("鳥綱",     "bird"),
    ("哺乳綱",   "mammal"),
    ("両生綱",   "amphibian"),
    ("爬虫綱",   "reptile"),
    ("昆虫綱",   "insect"),
    ("クモ綱",   "arachnid"),
    ("条鰭綱",   "fish"),
    ("軟体動物", "mollusk"),
    ("マツ綱",   "tree"),
    ("単子葉植物", "herb"),
    ("被子植物",  "plant"),  # fallback for plants
]


@dataclass
class Resolved:
    raw_name: str
    found: bool
    title: str | None = None
    scientific_name: str | None = None
    kingdom: str | None = None
    taxon_group: str | None = None
    is_disambig: bool = False
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "raw_name": self.raw_name, "found": self.found, "title": self.title,
            "scientific_name": self.scientific_name, "kingdom": self.kingdom,
            "taxon_group": self.taxon_group, "is_disambig": self.is_disambig,
            "error": self.error,
        }


def _extract_scientific(text: str) -> str | None:
    head = text[:4000]  # taxobox is always near the top
    m = SNAMEI.search(head)
    if m:
        return f"{m.group(1)} {m.group(2)}".strip()
    # full italic binomial
    for m in ITALIC_BINOMIAL.finditer(head):
        s = m.group(1).strip()
        if 1 < len(s.split()) <= 4:
            return s
    # 学名 = ... line — try to grab a Latin binomial within
    line = re.search(r"学名\s*=\s*([^\n]+)", text)
    if line:
        seg = line.group(1)
        m2 = re.search(r"\b([A-Z][a-z]+(?:\s+×)?\s+[a-z]+(?:\s+[a-z]+)?)\b", seg)
        if m2:
            return m2.group(1)
    # last resort: abbreviated form
    m3 = ABBREV_BINOMIAL.search(head)
    return m3.group(1) if m3 else None


# taxon_group → implied kingdom (used as fallback when 動物界/植物界 don't
# appear as plain text in the article body)
GROUP_TO_KINGDOM: dict[str, str] = {
    "bird": "animalia", "mammal": "animalia", "amphibian": "animalia",
    "reptile": "animalia", "insect": "animalia", "arachnid": "animalia",
    "fish": "animalia", "mollusk": "animalia",
    "tree": "plantae", "shrub": "plantae", "herb": "plantae",
    "vine": "plantae", "fern": "plantae", "moss": "plantae",
    "plant": "plantae",
}


def _kingdom(text: str, taxon_group: str | None = None) -> str | None:
    for needle, val in KINGDOM_HINTS:
        if needle in text:
            return val
    if taxon_group and taxon_group in GROUP_TO_KINGDOM:
        return GROUP_TO_KINGDOM[taxon_group]
    return None


def _taxon_group(text: str, kingdom: str | None) -> str | None:
    for needle, val in TAXON_HINTS:
        if needle in text:
            return val
    if kingdom == "plantae":
        return "plant"
    return None


def _is_disambig(text: str) -> bool:
    head = text[:1500]
    return any(mk in head for mk in DISAMBIG_MARKERS)


def lookup_one(name: str, *, session: requests.Session | None = None) -> Resolved:
    sess = session or requests
    try:
        r = sess.get(
            API,
            params={
                "action": "query", "prop": "revisions", "rvprop": "content",
                "rvslots": "main", "titles": name, "redirects": 1, "format": "json",
            },
            timeout=20,
            headers={"User-Agent": UA},
        )
        r.raise_for_status()
        pages = r.json().get("query", {}).get("pages", {})
    except Exception as e:
        return Resolved(name, False, error=str(e)[:120])
    for pid, p in pages.items():
        if pid == "-1":
            return Resolved(name, False)
        title = p.get("title")
        revs = p.get("revisions") or []
        if not revs:
            return Resolved(name, True, title=title)
        text = revs[0]["slots"]["main"]["*"]
        if _is_disambig(text):
            return Resolved(name, True, title=title, is_disambig=True)
        # taxon_group first; kingdom can fall back to that
        kingdom_text = _kingdom(text)
        taxon = _taxon_group(text, kingdom_text)
        kingdom = kingdom_text or _kingdom(text, taxon)
        return Resolved(
            raw_name=name,
            found=True,
            title=title,
            scientific_name=_extract_scientific(text),
            kingdom=kingdom,
            taxon_group=taxon,
        )
    return Resolved(name, False)


def lookup_many(names: list[str], *, delay_s: float = 0.2) -> list[Resolved]:
    """Sequential fetches with politeness delay (Wikipedia rate-limit friendly)."""
    out: list[Resolved] = []
    for n in names:
        time.sleep(delay_s)
        out.append(lookup_one(n))
    return out


def cache_path(project_root: Path, name: str) -> Path:
    safe = name.replace("/", "_")
    return project_root / "data" / "cache" / "wikipedia" / f"{safe}.json"


def lookup_with_cache(name: str, project_root: Path, *, max_age_days: int = 90) -> Resolved:
    p = cache_path(project_root, name)
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        age_days = (time.time() - p.stat().st_mtime) / 86400
        if age_days < max_age_days:
            return Resolved(**json.loads(p.read_text(encoding="utf-8")))
    res = lookup_one(name)
    p.write_text(json.dumps(res.to_dict(), ensure_ascii=False), encoding="utf-8")
    return res
