#!/usr/bin/env bash
set -euo pipefail

# Write the release's version and build number into a staged engine bundle, so the engine reports the release it
# shipped in, not the API contract version its pyproject carries (#6723, `contract.release-engine-reports-its-release`).
# One line, "<version> <build>", in fichero_server/release-stamp.txt inside the bundle. Never a tracked file.
#
# Usage: stamp_release_into_engine.sh <staged engine .app> <release version> <build>

ENGINE_APP="${1:?usage: $0 <staged engine .app> <release version> <build>}"
VERSION="${2:?usage: $0 <staged engine .app> <release version> <build>}"
BUILD="${3:?usage: $0 <staged engine .app> <release version> <build>}"

PKG="$ENGINE_APP/Contents/Resources/app/fichero_server"
if [ ! -d "$PKG" ]; then
  echo "error: no fichero_server package in the staged engine at $PKG" >&2
  exit 1
fi
case "$VERSION$BUILD" in
  *[[:space:]]*|"") echo "error: version '$VERSION' and build '$BUILD' must be non-empty and have no spaces" >&2; exit 1 ;;
esac
printf '%s %s\n' "$VERSION" "$BUILD" > "$PKG/release-stamp.txt"
echo "  Engine release stamp: $VERSION ($BUILD)"
