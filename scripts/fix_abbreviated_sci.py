"""Some Wikipedia extractions captured the abbreviated form of a binomial
(e.g., 'L. radiata' instead of 'Lycoris radiata') because the regex caught
the second mention rather than the first.

For each affected species, re-read the cached Wikipedia JSON. If the cache
already has a longer form, use it; else reprocess the wikitext to expand
the abbreviation by matching the abbreviated genus letter against any
full Genus name found earlier in the article.
"""
from __future__ import annotations

import re
import json
from pathlib import Path

from parklife import db
from parklife.normalize import wikipedia

ROOT = Path(__file__).resolve().parent.parent
ABBREV = re.compile(r"^([A-Z])\.\s*([a-z]+)$")


def expand_one(name: str, abbrev_sci: str) -> str | None:
    """Try to expand 'X. yyy' by reading the Wikipedia cache for `name`."""
    cp = wikipedia.cache_path(ROOT, name)
    if not cp.exists():
        return None
    data = json.loads(cp.read_text(encoding="utf-8"))
    title = data.get("title")
    if not title:
        return None
    # re-fetch wikitext if needed via lookup_one (Wikipedia cache is JSON only,
    # not raw text, so we have to re-query) — skip for now: try local fix only.
    return None


def main() -> None:
    db_path = ROOT / "data" / "parklife.db"
    fixed = 0
    with db.connect(db_path) as conn:
        candidates = list(conn.execute(
            "SELECT id, scientific_name, common_name_ja FROM species "
            "WHERE scientific_name LIKE '_. %'"
        ))
        print(f"abbreviated sci names: {len(candidates)}")
        for r in candidates[:20]:
            print(f"  {r['common_name_ja']:<14}  {r['scientific_name']}")

        # Strategy: for each candidate, re-run the Wikipedia lookup in real time
        # (it'll hit network because we don't cache wikitext, only the JSON).
        # Skip if we already have a non-abbreviated form for this taxon via alias.
        for r in candidates:
            name = r["common_name_ja"]
            if not name:
                continue
            res = wikipedia.lookup_one(name)
            sci = res.scientific_name
            if sci and not ABBREV.match(sci):
                conn.execute(
                    "UPDATE species SET scientific_name=? WHERE id=?",
                    (sci, r["id"]),
                )
                fixed += 1
        conn.commit()
    print(f"fixed {fixed}/{len(candidates)} abbreviated sci names")


if __name__ == "__main__":
    main()
