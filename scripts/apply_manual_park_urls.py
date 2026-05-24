"""Read data/manual_park_urls.json and update park.official_url accordingly.

Schema:
    { "<park slug>": "<url>" | "__no_url__" }

The sentinel "__no_url__" marks a park investigated by hand and found to
have no usable official URL. We persist that as a NULL official_url plus a
note in `park.notes` so we don't re-investigate it.

Idempotent. Safe to re-run.
"""
from __future__ import annotations

import json
from pathlib import Path

from parklife import db

ROOT = Path(__file__).resolve().parent.parent
NO_URL = "__no_url__"
NOTE_TAG = "[manual_url_pass3:no_url_found]"


def main() -> None:
    fp = ROOT / "data" / "manual_park_urls.json"
    if not fp.exists():
        print(f"no file: {fp}")
        return
    data = json.loads(fp.read_text(encoding="utf-8"))
    set_url = 0
    set_no = 0
    skipped = 0
    unknown = []
    with db.connect(ROOT / "data" / "parklife.db") as conn:
        for slug, val in data.items():
            row = conn.execute(
                "SELECT id, official_url, notes FROM park WHERE slug=?", (slug,)
            ).fetchone()
            if not row:
                unknown.append(slug)
                continue
            if val == NO_URL:
                existing_notes = row["notes"] or ""
                if NOTE_TAG not in existing_notes:
                    new_notes = (existing_notes + " " + NOTE_TAG).strip()
                    conn.execute(
                        "UPDATE park SET notes=? WHERE id=?",
                        (new_notes, row["id"]),
                    )
                    set_no += 1
                else:
                    skipped += 1
                continue
            if not isinstance(val, str) or not val.startswith(("http://", "https://")):
                print(f"  skip {slug}: not a URL: {val!r}")
                skipped += 1
                continue
            if row["official_url"] == val:
                skipped += 1
                continue
            conn.execute(
                "UPDATE park SET official_url=? WHERE id=?", (val, row["id"])
            )
            set_url += 1
        conn.commit()
    print(f"set_url={set_url} set_no={set_no} skipped={skipped} unknown={len(unknown)}")
    if unknown:
        print("unknown slugs (in JSON but not in DB):")
        for s in unknown[:20]:
            print(f"  {s}")


if __name__ == "__main__":
    main()
