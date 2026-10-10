#!/usr/bin/env bash
# Publish a built, notarized release: one command after `release-all.sh` has made the DMGs.
#
#   scripts/publish-release.sh            commit the version stamp + site snippets, push, then
#                                         GitHub release + appcast + site deploy (release-all --github)
#   scripts/publish-release.sh --dry-run  say what it would do
#
# Steps:
#   1. The DMGs for the stamped version exist in build/releases/ (Fichero.dmg; Fichero-dev.dmg if built).
#   2. The landing-page snippets are regenerated from RELEASE_NOTES.md (scripts/gen_site_releases.py:
#      docs/_latest.md names the new release under the Download button).
#   3. The stamp (Version.xcconfig, the engine's pyproject version, RELEASE_NOTES heading) and the
#      snippets are committed by explicit path and pushed to the current branch's origin, so GitHub
#      accepts the release's target commit.
#   4. release-all.sh --github with every build step skipped: create-github-release.sh (GitHub release,
#      DMG upload, Sparkle-signed appcast committed in the tubb.ca repo), then deploy-site.sh (MkDocs build
#      synced into tubb.ca/apps/fichero and pushed, which publishes the page and the feed).
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"
DRY=0
[[ "${1:-}" == "--dry-run" || "${1:-}" == "-n" ]] && DRY=1

VERSION=$(sed -n 's/^MARKETING_VERSION *= *//p' fichero/Configs/Version.xcconfig | tr -d ' ')
BUILD=$(sed -n 's/^CURRENT_PROJECT_VERSION *= *//p' fichero/Configs/Version.xcconfig | tr -d ' ')
[[ -n "$VERSION" ]] || { echo "error: no MARKETING_VERSION in fichero/Configs/Version.xcconfig" >&2; exit 1; }
[[ -f build/releases/Fichero.dmg ]] || { echo "error: build/releases/Fichero.dmg is missing — run release-all.sh first" >&2; exit 1; }
grep -q "^## $VERSION\$" RELEASE_NOTES.md || { echo "error: RELEASE_NOTES.md has no '## $VERSION' section" >&2; exit 1; }

BRANCH=$(git rev-parse --abbrev-ref HEAD)
echo "Publishing Fichero $VERSION (build $BUILD) from $BRANCH"
ls -la build/releases/*.dmg

STAMP_FILES=(fichero/Configs/Version.xcconfig fichero-server/pyproject.toml RELEASE_NOTES.md CHANGELOG.md)
if [[ $DRY == 1 ]]; then
  echo "[dry run] would regenerate docs/_latest.md, commit ${STAMP_FILES[*]} docs/_latest.md docs/_releases*, push $BRANCH,"
  echo "[dry run] then run release-all.sh --skip-dmg --skip-notarize --skip-testflight --github"
  exit 0
fi

"${PYTHON:-python3}" scripts/gen_site_releases.py
# Every tracked file the release changed (the stamp, the contract re-exported at the stamped version) plus the snippets.
git add -u
git add -- docs/_latest.md docs/_releases* 2>/dev/null || true
if ! git diff --cached --quiet; then
  git commit -m "release: Fichero $VERSION (build $BUILD)"
fi
git push origin "HEAD:$BRANCH"

# The version is pinned so release-all does not stamp a new one over the built DMGs.
FICHERO_RELEASE_VERSION="$VERSION" scripts/release-all.sh --skip-dmg --skip-notarize --skip-testflight --github
echo "Published Fichero $VERSION (build $BUILD): GitHub release, appcast and site."
