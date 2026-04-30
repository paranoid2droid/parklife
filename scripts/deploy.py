"""Regenerate the GitHub Pages demo into ./docs/.

Pipeline:
  1. Run all export scripts to refresh data/export/* from the live DB.
  2. Sync the publishable subset into ./docs/ (which GitHub Pages serves).

Commit + push is intentionally NOT done here — review the diff and commit
manually from the repo root:
    git add docs && git commit -m "..." && git push
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPORT_DIR = ROOT / "data" / "export"
DOCS_DIR = ROOT / "docs"

REGEN_MODULES = (
    "scripts.dedupe",
    "scripts.export_json",
    "scripts.export_park_md",
    "scripts.biodiversity_report",
    "scripts.bird_seasonal_report",
    "scripts.endemic_report",
    "scripts.export_html",
)

# What to copy from data/export → docs/ (relative paths)
DEPLOY_FILES = (
    "index.html",
    "REPORT.md",
    "BIRDS.md",
    "ENDEMIC.md",
    "parklife.json",
    "park_species.ndjson",
)
DEPLOY_DIRS = ("parks_md",)


def run(*args: str, cwd: Path | None = None) -> int:
    cmd = list(args)
    print("$ " + " ".join(cmd))
    rc = subprocess.call(cmd, cwd=cwd or ROOT)
    if rc != 0:
        print(f"  ! exit {rc}")
    return rc


def main() -> int:
    venv_py = ROOT / ".venv" / "bin" / "python"
    for mod in REGEN_MODULES:
        rc = run(str(venv_py), "-m", mod)
        if rc != 0:
            print(f"abort: {mod} failed")
            return rc

    DOCS_DIR.mkdir(exist_ok=True)

    for rel in DEPLOY_FILES:
        src = EXPORT_DIR / rel
        if not src.exists():
            print(f"  skip (missing): {rel}")
            continue
        shutil.copy2(src, DOCS_DIR / rel)
        print(f"  copied: {rel}")
    for rel in DEPLOY_DIRS:
        src = EXPORT_DIR / rel
        dst = DOCS_DIR / rel
        if dst.exists():
            shutil.rmtree(dst)
        if src.is_dir():
            shutil.copytree(src, dst)
            print(f"  copied dir: {rel}/")

    print("\nDone. Review with `git status docs` and commit when ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
