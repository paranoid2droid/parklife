"""Queue-friendly wrapper around scripts/deploy_pages.sh (SKIP_BUILD=1).

Lets the autonomous queue (scripts.run_pending → `pending: deploy_pages`) push
an already-built site/ to gh-pages after e.g. `osm_parking → export_static`,
so long enrichment passes ship without a Claude session. Build first with
`pending: export_static`. Exit code = the shell script's.
"""
from __future__ import annotations

import glob
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    env = dict(os.environ, SKIP_BUILD="1")
    # launchd jobs start without SSH_AUTH_SOCK, so `git push` over ssh fails
    # with "Permission denied (publickey)". macOS keeps the user's ssh-agent
    # socket at /var/run/com.apple.launchd.*/Listeners — reuse it when unset.
    if not env.get("SSH_AUTH_SOCK"):
        socks = sorted(glob.glob("/var/run/com.apple.launchd.*/Listeners"))
        if socks:
            env["SSH_AUTH_SOCK"] = socks[0]
    return subprocess.call(["bash", str(ROOT / "scripts" / "deploy_pages.sh")], cwd=ROOT, env=env)


if __name__ == "__main__":
    sys.exit(main())
