#!/usr/bin/env bash
set -euo pipefail

# Build a release DMG containing Fichero.app.
# Calls build-release.sh first, then packages the .app into a DMG.
# Usage: scripts/build-release-dmg.sh [--skip-backend]

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAGE_DIR="$ROOT_DIR/build/releases/dmg-stage"
DMG_PATH="$ROOT_DIR/build/releases/Fichero.dmg"
MANIFEST_PATH="$ROOT_DIR/build/releases/release-manifest.txt"
APP_NAME="Fichero.app"
APP_PATH="$ROOT_DIR/fichero-swiftui/build/xcode/Products/Release/$APP_NAME"

EXTRA_ARGS=()
for arg in "$@"; do
  EXTRA_ARGS+=("$arg")
done

rm -rf "$STAGE_DIR"
mkdir -p "$ROOT_DIR/build/releases"

echo "[1/4] Build Release app"
"$ROOT_DIR/scripts/build-release.sh" "${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}"

echo
echo "[2/4] Stage app bundle"
mkdir -p "$STAGE_DIR"
ditto "$APP_PATH" "$STAGE_DIR/$APP_NAME"

echo "[3/4] Create DMG"
rm -f "$DMG_PATH"
hdiutil create \
  -volname "Fichero" \
  -srcfolder "$STAGE_DIR" \
  -ov \
  -format UDZO \
  "$DMG_PATH"

echo "[4/4] Write release manifest"
{
  echo "app_path=$APP_PATH"
  echo "dmg_path=$DMG_PATH"
  echo "bundle_id=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$APP_PATH/Contents/Info.plist")"
  echo "version=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$APP_PATH/Contents/Info.plist")"
  echo "build=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleVersion' "$APP_PATH/Contents/Info.plist")"
  echo "sparkle_feed_url=$(/usr/libexec/PlistBuddy -c 'Print :SUFeedURL' "$APP_PATH/Contents/Info.plist" 2>/dev/null || true)"
} > "$MANIFEST_PATH"

echo
echo "App:      $APP_PATH"
echo "DMG:      $DMG_PATH"
echo "Manifest: $MANIFEST_PATH"
