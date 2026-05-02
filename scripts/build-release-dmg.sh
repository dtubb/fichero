#!/usr/bin/env bash
set -euo pipefail

# Build a styled installer DMG containing Fichero.app + Applications symlink.
# Two-phase build: writable DMG → style with AppleScript → compress to UDZO.
# Usage: scripts/build-release-dmg.sh [--skip-backend]

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAGE_DIR="$ROOT_DIR/build/releases/dmg-stage"
DMG_RW="$ROOT_DIR/build/releases/Fichero-rw.dmg"
DMG_PATH="$ROOT_DIR/build/releases/Fichero.dmg"
MANIFEST_PATH="$ROOT_DIR/build/releases/release-manifest.txt"
VOLUME_NAME="Fichero"
APP_NAME="Fichero.app"
APP_PATH="$ROOT_DIR/fichero/build/xcode/Products/Release/$APP_NAME"
ICON_SOURCE="$ROOT_DIR/icon.png"

EXTRA_ARGS=()
for arg in "$@"; do
  EXTRA_ARGS+=("$arg")
done

# ── 1. Build Release app ────────────────────────────────────────────────────
echo "[1/6] Build Release app"
"$ROOT_DIR/scripts/build-release.sh" "${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}"

if [ ! -d "$APP_PATH" ]; then
  echo "error: Release app not found at $APP_PATH" >&2
  exit 1
fi

# ── 2. Stage DMG contents ───────────────────────────────────────────────────
echo
echo "[2/6] Stage DMG contents"
rm -rf "$STAGE_DIR"
mkdir -p "$STAGE_DIR" "$ROOT_DIR/build/releases"
ditto "$APP_PATH" "$STAGE_DIR/$APP_NAME"
ln -s /Applications "$STAGE_DIR/Applications"
echo "  Staged: $APP_NAME + Applications symlink"

# ── 3. Create volume icon ───────────────────────────────────────────────────
echo "[3/6] Create volume icon"
ICONSET_DIR="$ROOT_DIR/build/releases/VolumeIcon.iconset"
rm -rf "$ICONSET_DIR"
mkdir -p "$ICONSET_DIR"

if [ -f "$ICON_SOURCE" ]; then
  sips -z 16 16     "$ICON_SOURCE" --out "$ICONSET_DIR/icon_16x16.png"    >/dev/null 2>&1
  sips -z 32 32     "$ICON_SOURCE" --out "$ICONSET_DIR/icon_16x16@2x.png" >/dev/null 2>&1
  sips -z 32 32     "$ICON_SOURCE" --out "$ICONSET_DIR/icon_32x32.png"    >/dev/null 2>&1
  sips -z 64 64     "$ICON_SOURCE" --out "$ICONSET_DIR/icon_32x32@2x.png" >/dev/null 2>&1
  sips -z 128 128   "$ICON_SOURCE" --out "$ICONSET_DIR/icon_128x128.png"    >/dev/null 2>&1
  sips -z 256 256   "$ICON_SOURCE" --out "$ICONSET_DIR/icon_128x128@2x.png" >/dev/null 2>&1
  sips -z 256 256   "$ICON_SOURCE" --out "$ICONSET_DIR/icon_256x256.png"    >/dev/null 2>&1
  sips -z 512 512   "$ICON_SOURCE" --out "$ICONSET_DIR/icon_256x256@2x.png" >/dev/null 2>&1
  sips -z 512 512   "$ICON_SOURCE" --out "$ICONSET_DIR/icon_512x512.png"    >/dev/null 2>&1
  sips -z 1024 1024 "$ICON_SOURCE" --out "$ICONSET_DIR/icon_512x512@2x.png" >/dev/null 2>&1
  iconutil -c icns "$ICONSET_DIR" -o "$ROOT_DIR/build/releases/VolumeIcon.icns"
  echo "  Volume icon created"
else
  echo "  warning: icon.png not found at $ICON_SOURCE — skipping volume icon"
fi

# ── 4. Create writable DMG ──────────────────────────────────────────────────
echo "[4/6] Create writable DMG"
rm -f "$DMG_RW" "$DMG_PATH"
hdiutil create \
  -volname "$VOLUME_NAME" \
  -srcfolder "$STAGE_DIR" \
  -ov \
  -format UDRW \
  "$DMG_RW"

# ── 5. Style the DMG with AppleScript ───────────────────────────────────────
echo "[5/6] Style DMG layout"
MOUNT_OUTPUT=$(hdiutil attach "$DMG_RW" -readwrite -noverify -noautoopen)
MOUNT_POINT=$(echo "$MOUNT_OUTPUT" | grep -o '/Volumes/.*' | head -1)

if [ -z "$MOUNT_POINT" ]; then
  echo "error: could not mount DMG" >&2
  exit 1
fi

# Set volume icon
if [ -f "$ROOT_DIR/build/releases/VolumeIcon.icns" ]; then
  cp "$ROOT_DIR/build/releases/VolumeIcon.icns" "$MOUNT_POINT/.VolumeIcon.icns"
  SetFile -a C "$MOUNT_POINT" 2>/dev/null || true
fi

# Style the Finder window via AppleScript
osascript <<APPLESCRIPT
tell application "Finder"
    tell disk "$VOLUME_NAME"
        open
        set current view of container window to icon view
        set toolbar visible of container window to false
        set statusbar visible of container window to false
        set bounds of container window to {100, 100, 640, 400}
        set theViewOptions to icon view options of container window
        set arrangement of theViewOptions to not arranged
        set icon size of theViewOptions to 128
        set background color of theViewOptions to {60000, 60000, 60000}
        set position of item "$APP_NAME" of container window to {130, 150}
        set position of item "Applications" of container window to {410, 150}
        close
        open
        update without registering applications
        delay 2
        close
    end tell
end tell
APPLESCRIPT

# Let Finder finish writing .DS_Store
sync
sleep 2

hdiutil detach "$MOUNT_POINT" -quiet

# ── 6. Convert to compressed read-only DMG ──────────────────────────────────
echo "[6/6] Compress to final DMG"
hdiutil convert "$DMG_RW" -format UDZO -o "$DMG_PATH"
rm -f "$DMG_RW"

# Write release manifest
{
  echo "app_path=$APP_PATH"
  echo "dmg_path=$DMG_PATH"
  echo "bundle_id=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$APP_PATH/Contents/Info.plist")"
  echo "version=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$APP_PATH/Contents/Info.plist")"
  echo "build=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleVersion' "$APP_PATH/Contents/Info.plist")"
  echo "sparkle_feed_url=$(/usr/libexec/PlistBuddy -c 'Print :SUFeedURL' "$APP_PATH/Contents/Info.plist" 2>/dev/null || true)"
} > "$MANIFEST_PATH"

DMG_SIZE=$(du -sh "$DMG_PATH" | cut -f1)
echo
echo "App:      $APP_PATH"
echo "DMG:      $DMG_PATH ($DMG_SIZE)"
echo "Manifest: $MANIFEST_PATH"
