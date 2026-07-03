#!/usr/bin/env bash
set -euo pipefail

# Nightly automation (#2870) — build health-check + daily GitHub prerelease.
#
# Wired to a 6am cron by the manager. Each run:
#   1. Builds via scripts/dev.sh — build-all (compile health-check across every
#      mode) which also produces the release-mac artifact.
#   2. Generates a changelog from the PRs merged TODAY.
#   3. Creates OR updates a GitHub PRERELEASE tagged daily-YYYY-MM-DD with the
#      changelog and the built artifact.
#
# Idempotent: safe to re-run any number of times per day. The tag is stable
# (daily-YYYY-MM-DD), so a re-run EDITS the same release and re-uploads the
# asset with --clobber instead of failing on "already exists".
#
# Usage:
#   scripts/nightly-release.sh [--skip-build] [--dry-run] [--help]
#     --skip-build   Skip the dev.sh builds (use an existing artifact if present;
#                    otherwise publish notes only). For testing the release leg.
#     --dry-run      Print every build / mutating gh command instead of running
#                    it. Read-only gh queries (the changelog) still run.
#
# Requirements: gh authenticated with repo write; a machine free enough to
# build (dev.sh serializes builds via its own lock).

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEV="$ROOT_DIR/scripts/dev.sh"
TODAY="$(date +%F)"                 # YYYY-MM-DD (local date; cron runs at 6am)
TAG="daily-$TODAY"
TITLE="Nightly $TAG"
ARTIFACT_APP="$ROOT_DIR/fichero/build/xcode/Products/Release/Fichero.app"

SKIP_BUILD=false
DRY_RUN=false
for arg in "$@"; do
  case "$arg" in
    --skip-build) SKIP_BUILD=true ;;
    --dry-run|-n) DRY_RUN=true ;;
    --help|-h)
      awk '/^#!/{next} started&&!/^#/{exit} /^#/{started=1;sub(/^# ?/,"");print}' "${BASH_SOURCE[0]}"
      exit 0 ;;
    *) echo "error: unknown argument '$arg'" >&2; exit 2 ;;
  esac
done

# run: execute, or just print in --dry-run. Use for builds + mutating gh calls.
run() {
  if [ "$DRY_RUN" = true ]; then
    echo "[dry-run] $*"
  else
    "$@"
  fi
}

# ── 1. Build (health-check) ─────────────────────────────────────────────────
if [ "$SKIP_BUILD" = true ]; then
  echo "[nightly] skipping build (--skip-build)"
else
  echo "[nightly] build-all — compile health-check across every mode"
  run "$DEV" build-all
  # build-all includes release-mac, so the artifact is now at ARTIFACT_APP.
fi

# ── 2. Changelog from today's merged PRs ────────────────────────────────────
echo "[nightly] collecting PRs merged on $TODAY"
# Read-only query — safe to run even in --dry-run.
PR_LINES="$(gh pr list --state merged --search "merged:>=$TODAY" --limit 200 \
  --json number,title,author \
  --jq '.[] | "- #\(.number) \(.title) (@\(.author.login))"' 2>/dev/null || true)"

if [ -n "$PR_LINES" ]; then
  CHANGELOG="$PR_LINES"
else
  CHANGELOG="_No PRs merged on $TODAY._"
fi

NOTES="$(printf 'Automated nightly build for %s.\n\n## Merged today\n\n%s\n\n---\nBuilt from %s via scripts/dev.sh (unsigned health-check artifact).' \
  "$TODAY" "$CHANGELOG" "$(git -C "$ROOT_DIR" rev-parse --short HEAD)")"

echo "[nightly] changelog:"
echo "$CHANGELOG"

# ── 3. Package the artifact (if built) ──────────────────────────────────────
ASSET=""
if [ -d "$ARTIFACT_APP" ]; then
  ASSET="${TMPDIR:-/tmp}/Fichero-$TODAY.zip"
  echo "[nightly] zipping artifact → $ASSET"
  # ditto -c -k --keepParent produces a Finder-compatible .app zip.
  run ditto -c -k --keepParent "$ARTIFACT_APP" "$ASSET"
  [ "$DRY_RUN" = true ] && ASSET=""   # nothing was actually produced
else
  echo "[nightly] no built artifact at $ARTIFACT_APP — publishing notes only"
fi

# ── 4. Create or update the prerelease (idempotent) ─────────────────────────
TARGET="$(git -C "$ROOT_DIR" rev-parse HEAD)"
if gh release view "$TAG" >/dev/null 2>&1; then
  echo "[nightly] release $TAG exists — updating (idempotent)"
  run gh release edit "$TAG" --title "$TITLE" --notes "$NOTES" --prerelease
  [ -n "$ASSET" ] && run gh release upload "$TAG" "$ASSET" --clobber
else
  echo "[nightly] creating prerelease $TAG"
  if [ -n "$ASSET" ]; then
    run gh release create "$TAG" "$ASSET" --title "$TITLE" --notes "$NOTES" \
      --prerelease --target "$TARGET"
  else
    run gh release create "$TAG" --title "$TITLE" --notes "$NOTES" \
      --prerelease --target "$TARGET"
  fi
fi

echo "[nightly] done — $TAG"
