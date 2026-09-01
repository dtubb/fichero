#!/usr/bin/env bash
set -euo pipefail

# Stamp the embedded engine's identity into the HOST app's Info.plist, at embed
# time, so the running app can tell at launch whether the engine answering it is
# the engine that was embedded.
#
#   FicheroEmbeddedEngineVersion — CFBundleShortVersionString of the engine
#     bundle this build actually copied. What is INSIDE the app.
#   FicheroExpectedEngineVersion — `version` from the checkout's
#     fichero-server/pyproject.toml at build time. What the app SHOULD have got.
#
# The two are normally equal (clean-embedded-engine.sh --check-version refuses
# to stage a bundle whose label disagrees with pyproject). They come apart
# exactly when the embed phase copies a stage older than the checkout — the
# 2026-09-01 failure, where a Dev Embedded build announced engine 2026.8.27
# from a tree whose pyproject had moved on. Recording BOTH means the app can
# name which of the two drifted instead of reporting a bare disagreement.
#
# Usage: stamp_engine_version_into_app.sh <host app Info.plist> <staged engine .app>

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_PLIST="${1:?usage: $0 <host app Info.plist> <staged engine .app>}"
ENGINE_APP="${2:?usage: $0 <host app Info.plist> <staged engine .app>}"

if [ ! -f "$APP_PLIST" ]; then
  echo "error: host app Info.plist not found at $APP_PLIST" >&2
  exit 1
fi

EMBEDDED_VERSION="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' \
  "$ENGINE_APP/Contents/Info.plist" 2>/dev/null || true)"
EXPECTED_VERSION="$(grep -m1 '^version = "' "$ROOT_DIR/fichero-server/pyproject.toml" \
  | sed -E 's/^version = "([^"]+)".*/\1/')"

if [ -z "$EMBEDDED_VERSION" ] || [ -z "$EXPECTED_VERSION" ]; then
  # A stamp that lies is worse than no stamp: the launch check would compare
  # against an empty string and report every engine as mismatched.
  echo "error: could not read engine versions (embedded='$EMBEDDED_VERSION' expected='$EXPECTED_VERSION')" >&2
  exit 1
fi

set_key() {
  local key="$1" value="$2"
  /usr/libexec/PlistBuddy -c "Set :$key $value" "$APP_PLIST" 2>/dev/null \
    || /usr/libexec/PlistBuddy -c "Add :$key string $value" "$APP_PLIST"
}

set_key FicheroEmbeddedEngineVersion "$EMBEDDED_VERSION"
set_key FicheroExpectedEngineVersion "$EXPECTED_VERSION"

echo "  Embedded engine stamp: embedded=$EMBEDDED_VERSION expected=$EXPECTED_VERSION"
if [ "$EMBEDDED_VERSION" != "$EXPECTED_VERSION" ]; then
  echo "  warning: the staged engine ($EMBEDDED_VERSION) is not the checkout's version ($EXPECTED_VERSION) — restage it" >&2
fi
