"""Run after the bird-monthly script (PID 77705) completes:
  1) bird normalize/backfill (in case new species were inserted)
  2) insect-monthly  (long: ~25 min)
  3) mammal-monthly  (short: ~5 min, mostly cached due to fewer observations)
  4) re-export json + park markdown
  5) print final stats

The script waits for the parent bird run by polling /tmp/inat_monthly.log
for the completion sentinel string. Drop-in: launch this one in the
background and forget.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = Path("/tmp/inat_monthly.log")
SENTINEL = "monthly enrichment done"


def wait_for_h(timeout_s: int = 3600) -> bool:
    """Block until the bird run prints its done sentinel, or timeout."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            text = LOG.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            text = ""
        if SENTINEL in text:
            return True
        # also exit if the process disappeared (in case of error before sentinel)
        try:
            r = subprocess.run(["pgrep", "-f", "inaturalist_monthly bird"],
                                capture_output=True)
            if r.returncode != 0:
                return False  # process gone but no sentinel -> still safe to continue
        except Exception:
            pass
        time.sleep(15)
    return False


def run(*args: str) -> int:
    print(f"\n>>> {' '.join(args)}")
    return subprocess.call(list(args), cwd=ROOT)


def main() -> int:
    print(f"[finalize] waiting for bird run (sentinel: {SENTINEL!r})")
    ok = wait_for_h()
    print(f"[finalize] bird run {'completed' if ok else 'gone (no sentinel)'}")

    # 1. cleanup
    run(".venv/bin/python", "-m", "scripts.normalize")
    run(".venv/bin/python", "-m", "scripts.repair_kingdoms")
    run(".venv/bin/python", "-m", "scripts.backfill_observations")

    # 2. insect monthly
    print("\n[finalize] starting insect monthly enrichment")
    insect_log = Path("/tmp/inat_monthly_insect.log")
    with insect_log.open("w") as f:
        rc = subprocess.call(
            [".venv/bin/python", "-m", "scripts.inaturalist_monthly", "insect"],
            stdout=f, stderr=subprocess.STDOUT, cwd=ROOT,
        )
    print(f"[finalize] insect run rc={rc}")

    # 3. mammal monthly (small)
    print("\n[finalize] starting mammal monthly enrichment")
    mammal_log = Path("/tmp/inat_monthly_mammal.log")
    with mammal_log.open("w") as f:
        rc = subprocess.call(
            [".venv/bin/python", "-m", "scripts.inaturalist_monthly", "mammal"],
            stdout=f, stderr=subprocess.STDOUT, cwd=ROOT,
        )
    print(f"[finalize] mammal run rc={rc}")

    # 4. final cleanup pass
    run(".venv/bin/python", "-m", "scripts.normalize")
    run(".venv/bin/python", "-m", "scripts.backfill_observations")

    # 5. exports
    run(".venv/bin/python", "-m", "scripts.export_json")
    run(".venv/bin/python", "-m", "scripts.export_park_md")

    # 6. final stats
    run(".venv/bin/python", "-m", "scripts.query", "stats")
    return 0


if __name__ == "__main__":
    sys.exit(main())
