"""Run after finalize_after_h is done. Adds iNat enrichment for the 17
parks that were retrofitted with manual coordinates after the original
Phase D run, plus monthly birds for them.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SENTINEL_FILES = [
    Path("/tmp/finalize.log"),
]


def wait_for_chain() -> None:
    """Wait until the parent finalize is done (no python.*scripts processes left)."""
    deadline = time.time() + 5400  # 90 min
    while time.time() < deadline:
        r = subprocess.run(["pgrep", "-f", "scripts.inaturalist_monthly"],
                           capture_output=True)
        if r.returncode != 0:
            return
        time.sleep(20)


def run(*args: str) -> int:
    print(f"\n>>> {' '.join(args)}")
    return subprocess.call(list(args), cwd=ROOT)


def main() -> int:
    print("[post] waiting for finalize chain to drain")
    wait_for_chain()
    print("[post] chain idle, running newly-coord iNat enrichment")

    # iNaturalist re-run will cache-hit the 192 existing parks and do
    # actual fetches only for the 17 newly-coord parks (~136 API calls).
    run(".venv/bin/python", "-m", "scripts.inaturalist")

    # Bird monthly enrichment for the new parks (cache-hit existing).
    run(".venv/bin/python", "-m", "scripts.inaturalist_monthly", "bird")

    # Insect + mammal monthly for new parks
    run(".venv/bin/python", "-m", "scripts.inaturalist_monthly", "insect")
    run(".venv/bin/python", "-m", "scripts.inaturalist_monthly", "mammal")

    # Final pass
    run(".venv/bin/python", "-m", "scripts.normalize")
    run(".venv/bin/python", "-m", "scripts.repair_kingdoms")
    run(".venv/bin/python", "-m", "scripts.backfill_observations")
    run(".venv/bin/python", "-m", "scripts.fix_audited_species")
    run(".venv/bin/python", "-m", "scripts.export_json")
    run(".venv/bin/python", "-m", "scripts.export_park_md")
    run(".venv/bin/python", "-m", "scripts.biodiversity_report")
    run(".venv/bin/python", "-m", "scripts.endemic_report")
    run(".venv/bin/python", "-m", "scripts.query", "stats")
    return 0


if __name__ == "__main__":
    sys.exit(main())
