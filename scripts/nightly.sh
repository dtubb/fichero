#!/usr/bin/env bash
# nightly.sh — 6am cron entrypoint. Keeps the dated (CalVer) version current so
# the repo/app never shows a stale date, and runs the date sanity check.
#
# What it does (idempotent, safe to run repeatedly):
#   1. pull main (ff-only; bail if the tree is dirty or diverged)
#   2. set-release-version.sh --beta  → stamp TODAY across frontend + backend
#   3. commit + push the bump (authored Claude) ONLY if the version changed
#   4. check_version_date.sh          → assert the version is date-shaped & current
#
# It does NOT build/notarize/upload — that's release-all.sh, opt-in and heavy
# (signing creds, DMG, TestFlight). Wire that in here once Daniel confirms the
# flags. ponytail: the bug was a dead cron target + no daily stamp; this fixes
# exactly that, nothing more.
#
#   crontab:  57 5 * * * /usr/bin/env bash /path/to/fichero/scripts/nightly.sh >> ~/fichero-nightly.log 2>&1
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
echo "=== nightly $(date '+%Y-%m-%d %H:%M:%S') ==="

# 1. only advance a clean, on-main tree — never fight local work
if [ -n "$(git status --porcelain)" ]; then
  echo "tree dirty — skipping nightly stamp (resolve locally)"; exit 0
fi
branch="$(git rev-parse --abbrev-ref HEAD)"
[ "$branch" = "main" ] || { echo "not on main ($branch) — skipping"; exit 0; }
git pull --quiet --ff-only || { echo "pull not ff — skipping"; exit 0; }

# 2. stamp today's dated version (frontend + backend, monotonic build int)
bash scripts/set-release-version.sh --beta

# 3. commit + push only if something actually changed
if git diff --quiet; then
  echo "version already current for today — nothing to commit"
else
  git -c user.name="Claude (Opus 4.8)" -c user.email="noreply@anthropic.com" \
    commit -aqm "chore(release): stamp dated version $(date +%Y.%m.%d)-beta"
  git push --quiet origin main && echo "pushed version bump" || echo "push failed (will retry tomorrow)"
fi

# 4. verify the resolved version is date-shaped and not stale/future
bash scripts/check_version_date.sh
echo "=== nightly done ==="
