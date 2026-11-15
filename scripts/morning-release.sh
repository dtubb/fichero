#!/usr/bin/env bash
# morning-release.sh — the token-free morning release (spec:
# release.lane.morning-release-token-free). Run by launchd (see
# scripts/install-morning-release.sh); no model or AI call anywhere.
#
#   1. one run at a time (lock), log to ~/Library/Logs/Fichero/morning-release-<date>.log
#   2. fetch origin; nothing on origin/integration since the newest v* tag → text "nothing new", stop
#   3. cut release/<date> from origin/integration in its own worktree
#   4. release-all.sh: date stamp + build bump + every guard (disk, feed, iOS preflight,
#      TestFlight watchdog, ASC key)
#   5. publish only if the DMG part is OK and every DMG smokes clean (publish-release.sh;
#      pushes release/<date>, never main), then open the release/<date> → main PR
#   6. text the owner the summary table (FICHERO_NOTIFY_IMESSAGE; unset = no text)
#
# Env: FICHERO_MORNING_WORKTREE (default ~/code/fichero-worktrees/morning-release),
#      FICHERO_MORNING_ARGS (extra release-all.sh flags, e.g. "--skip-ios-testflight").
set -uo pipefail

SRC_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATE="$(date +%Y.%m.%d)"
LOG_DIR="$HOME/Library/Logs/Fichero"
mkdir -p "$LOG_DIR"
exec >>"$LOG_DIR/morning-release-${DATE//./-}.log" 2>&1
echo "=== morning release $(date '+%F %T') ==="

PY="$("$SRC_ROOT/scripts/find_project_python.sh" "$SRC_ROOT")" || exit 1
export PATH="$(dirname "$PY"):$PATH"   # the venv first: the engine build needs its python3
guard() { "$PY" "$SRC_ROOT/scripts/release_guard.py" "$@"; }
text() { guard notify "$1" || true; }

LOCK="$LOG_DIR/morning-release.lock"
guard lock "$LOCK" "$$" || exit 0
trap 'rm -f "$LOCK"' EXIT

git -C "$SRC_ROOT" fetch -q --tags origin || { text "Fichero morning release: git fetch failed"; exit 1; }
# a command substitution, not `read < <(...)`: only this way does the guard's failure (-1) stop the run
COUNT="$(guard new-commits origin/integration)" \
  || { text "Fichero morning release: cannot count commits since the last release tag"; exit 1; }
read -r NEW LAST_TAG <<<"$COUNT"
if [ "$NEW" -eq 0 ]; then
  echo "nothing new since $LAST_TAG"
  text "Fichero morning release: nothing new since $LAST_TAG"
  exit 0
fi
echo "$NEW commits since $LAST_TAG"

WT="${FICHERO_MORNING_WORKTREE:-$HOME/code/fichero-worktrees/morning-release}"
BRANCH="release/$DATE"
if [ -e "$WT/.git" ]; then
  git -C "$WT" checkout -q -B "$BRANCH" origin/integration
else
  git -C "$SRC_ROOT" worktree add -q -B "$BRANCH" "$WT" origin/integration
fi || { text "Fichero morning release: could not cut $BRANCH"; exit 1; }

SUMMARY="$WT/build/releases/summary.tsv"
mkdir -p "$WT/build/releases"
# shellcheck disable=SC2086  # FICHERO_MORNING_ARGS is a flag list
FICHERO_RELEASE_SUMMARY="$SUMMARY" "$WT/scripts/release-all.sh" ${FICHERO_MORNING_ARGS:-}
echo "release-all exit $?"
VERSION="$(sed -n 's/^MARKETING_VERSION = //p' "$WT/fichero/Configs/Version.xcconfig")"
BUILD="$(sed -n 's/^CURRENT_PROJECT_VERSION = //p' "$WT/fichero/Configs/Version.xcconfig")"
LABEL="Fichero $VERSION ($BUILD)"

if WHY="$(FICHERO_RELEASE_SUMMARY="$SUMMARY" guard may-publish "$VERSION" "$BUILD" \
      "$WT/build/releases/Fichero.dmg" "$WT/build/releases/Fichero-dev.dmg" 2>&1)"; then
  # guard publish records the Publish part from publish-release.sh's exit status
  if FICHERO_RELEASE_SUMMARY="$SUMMARY" guard publish "$WT" "$LABEL on $BRANCH" scripts/publish-release.sh; then
    PR_URL="$(cd "$WT" && gh pr create --base main --head "$BRANCH" --title "release: $LABEL" \
      --body "Morning release $LABEL, cut from origin/integration ($NEW commits since $LAST_TAG).")" \
      || PR_URL="(PR not opened; see the log)"
  fi
else
  FICHERO_RELEASE_SUMMARY="$SUMMARY" guard part Publish SKIPPED "held: $WHY"
fi

TABLE="$(FICHERO_RELEASE_SUMMARY="$SUMMARY" guard summary)"
echo "$TABLE"
text "$LABEL morning release
$TABLE${PR_URL:+
PR: $PR_URL}"
grep -q "	FAILED	" "$SUMMARY" && exit 1
exit 0
