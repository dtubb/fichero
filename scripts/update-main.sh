#!/usr/bin/env bash
set -euo pipefail

# Update main at the released sha (owner 2026-11-16: after each release, PR integration -> main at the
# released sha and merge). main is protected: a release/<version> branch, a PR and a --merge, never a
# push to main and never a v* tag. Exit 0: in origin/main now; 3: already there, nothing done; else failed.
# Usage: scripts/update-main.sh <released sha> <version>

SHA="$1" VERSION="$2" BRANCH="release/$2"
cd "${FICHERO_REPO_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
git fetch -q origin main
if git merge-base --is-ancestor "$SHA" origin/main; then
  echo "$SHA is already in origin/main"
  exit 3
fi
git push origin "$SHA:refs/heads/$BRANCH"
gh pr view "$BRANCH" --json url -q .url 2>/dev/null \
  || gh pr create --base main --head "$BRANCH" --title "Release $VERSION" \
       --body "Release $VERSION at $SHA, opened by scripts/update-main.sh after the publish."
gh pr merge "$BRANCH" --merge
git fetch -q origin main
if ! git merge-base --is-ancestor "$SHA" origin/main; then
  echo "error: $SHA is not in origin/main after merging $BRANCH" >&2
  exit 1
fi
echo "main updated: $SHA in origin/main by $BRANCH"
