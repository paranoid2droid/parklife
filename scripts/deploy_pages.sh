#!/usr/bin/env bash
#
# Publish the static site (scripts/export_static.py -> site/) to an orphan
# `gh-pages` branch on the remote, WITHOUT storing generated data in main's
# history. This is what keeps the git-slim win permanent: the demo data never
# lands on `main`, so `main`'s .git stays ~26 MB no matter how often we deploy.
#
# How it stays clean:
#   * A throwaway index (GIT_INDEX_FILE) builds a tree from site/ — the main
#     working tree and index are never touched.
#   * The commit is an ORPHAN (no parent), so gh-pages is a single-commit branch
#     every deploy; force-push replaces it wholesale, no history accumulation.
#   * The loose objects this writes into your LOCAL .git are unreferenced after
#     the push; a routine `git gc` (or the auto-gc git runs itself) reclaims
#     them. Nothing here ever bloats what a clone of `main` receives.
#
# Usage:
#   scripts/deploy_pages.sh              # build site/ then deploy
#   SKIP_BUILD=1 scripts/deploy_pages.sh # deploy an already-built site/
#   REMOTE=origin BRANCH=gh-pages scripts/deploy_pages.sh
#
# First time only: GitHub → Settings → Pages → Source "Deploy from a branch",
# Branch: gh-pages / (root). Live at https://<user>.github.io/<repo>/
set -euo pipefail
cd "$(dirname "$0")/.."

SITE=site
BRANCH="${BRANCH:-gh-pages}"
REMOTE="${REMOTE:-origin}"

if [ -z "${SKIP_BUILD:-}" ]; then
  echo "→ building static export…"
  .venv/bin/python -m scripts.export_static
fi
[ -d "$SITE" ] || { echo "no $SITE/ — run scripts/export_static.py first"; exit 1; }

# Build a tree object from site/ using a private, throwaway index.
TMPIDX="$(mktemp -u)"
export GIT_INDEX_FILE="$TMPIDX"
git --work-tree="$SITE" add -A --force        # --force: site/ is gitignored
TREE="$(git write-tree)"
MSG="deploy: static site $(date -u +%Y-%m-%dT%H:%M:%SZ)"
COMMIT="$(printf '%s\n' "$MSG" | git commit-tree "$TREE")"   # no -p → orphan
unset GIT_INDEX_FILE
rm -f "$TMPIDX"

NFILES="$(find "$SITE" -type f | wc -l | tr -d ' ')"
echo "→ built orphan commit $COMMIT ($NFILES files)"
echo "→ force-pushing to $REMOTE $BRANCH…"
git push -f "$REMOTE" "$COMMIT:refs/heads/$BRANCH"

echo
echo "Deployed $NFILES files to $BRANCH on $REMOTE."
echo "If this is the first deploy, set Pages source to the $BRANCH branch (root)."
echo "Tip: run 'git gc' occasionally to reclaim local deploy objects."
