"""Autonomous queue runner. Reads data/run_queue.txt and runs the next
pending command via the venv python. Designed to be triggered by launchd
every 30 minutes — between firings the system idles.

Queue file format (data/run_queue.txt):
  # comments allowed
  pending: inaturalist_monthly reptile
  pending: dedupe
  pending: export_json

After a line completes, its prefix flips:
  done(2026-04-29T03:00Z, 142s, rc=0): inaturalist_monthly reptile

Failures use 'failed(...)' so the next run skips them and the user can
inspect data/run_queue.log for the traceback.

Single-runner enforcement: a fcntl lock on data/run_queue.lock; if
another instance is mid-run, this one exits cleanly.
"""

from __future__ import annotations

import fcntl
import os
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUEUE = ROOT / "data" / "run_queue.txt"
LOG   = ROOT / "data" / "run_queue.log"
LOCK  = ROOT / "data" / "run_queue.lock"

VENV_PY = ROOT / ".venv" / "bin" / "python"

# Maximum wall time per task (seconds). Long-running iNat passes shouldn't
# hit this, but a stuck network call shouldn't pin the runner forever.
TASK_TIMEOUT = 4 * 3600

PENDING_PREFIX = "pending:"
DONE_PREFIX    = "done"     # actual line begins 'done(...): ...'
FAILED_PREFIX  = "failed"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log(msg: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"[{now_iso()}] {msg}\n")


def acquire_lock() -> int | None:
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(LOCK, os.O_WRONLY | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return None
    os.write(fd, f"{os.getpid()}\n".encode())
    return fd


def parse_queue() -> tuple[list[str], int | None]:
    """Return (lines, idx_of_first_pending). idx is None if queue empty."""
    if not QUEUE.exists():
        return ([], None)
    raw = QUEUE.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(raw):
        s = line.strip()
        if s.startswith(PENDING_PREFIX):
            return (raw, i)
    return (raw, None)


def write_queue(lines: list[str]) -> None:
    QUEUE.write_text("\n".join(lines) + "\n", encoding="utf-8")


SESSION_TIMEOUT = 23 * 3600  # cap a single launchd firing at ~23h to leave room


def run_one(cmd_part: str) -> tuple[int, float]:
    argv = shlex.split(cmd_part)
    module = argv[0]
    rest = argv[1:]
    full_cmd = [str(VENV_PY), "-m", f"scripts.{module}", *rest]
    log(f"running: {' '.join(full_cmd)}")
    t0 = time.time()
    try:
        r = subprocess.run(
            full_cmd, cwd=ROOT, timeout=TASK_TIMEOUT,
            capture_output=True, text=True,
        )
        rc = r.returncode
        stdout, stderr = r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        rc = 124
        stdout = ""
        stderr = f"TIMEOUT after {TASK_TIMEOUT}s"
    dt = time.time() - t0
    log(f"finished rc={rc} in {dt:.0f}s")
    if stdout:
        log("STDOUT (last 60 lines):\n" + "\n".join(stdout.splitlines()[-60:]))
    if stderr:
        log("STDERR (last 30 lines):\n" + "\n".join(stderr.splitlines()[-30:]))
    return rc, dt


def main() -> int:
    fd = acquire_lock()
    if fd is None:
        log("another runner holds the lock; exiting")
        return 0

    session_start = time.time()
    last_rc = 0
    try:
        while True:
            if time.time() - session_start > SESSION_TIMEOUT:
                log("session timeout reached; exiting (next launchd fire will resume)")
                break
            lines, idx = parse_queue()
            if idx is None:
                log("queue empty or no pending entries")
                break
            line = lines[idx]
            cmd_part = line.split(":", 1)[1].strip()
            if not cmd_part:
                log(f"malformed line at {idx}: {line!r}; marking failed")
                lines[idx] = f"failed({now_iso()}, 0s, rc=255): {line!r}"
                write_queue(lines)
                continue
            rc, dt = run_one(cmd_part)
            last_rc = rc
            prefix = "done" if rc == 0 else "failed"
            new_marker = f"{prefix}({now_iso()}, {dt:.0f}s, rc={rc}): {cmd_part}"
            # Re-read queue (a user may have edited it during the run)
            lines, _ = parse_queue()
            # Find the matching pending entry by content (in case ordering shifted)
            target_text = f"pending: {cmd_part}"
            replaced = False
            for j, l in enumerate(lines):
                if l.strip() == target_text:
                    lines[j] = new_marker
                    replaced = True
                    break
            if not replaced:
                # fall back to original index if nothing matched
                if idx < len(lines):
                    lines[idx] = new_marker
                else:
                    lines.append(new_marker)
            write_queue(lines)
            if rc != 0:
                log(f"task failed; continuing to next pending (so a single bad task doesn't block the queue)")
        return last_rc
    finally:
        try:
            os.close(fd)
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
