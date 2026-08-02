#!/usr/bin/env bash
set -euo pipefail

# Build a styled installer DMG containing Fichero.app + Applications symlink.
# Two-phase build: writable DMG → style with AppleScript → compress to UDZO.
# Usage: scripts/build-release-dmg.sh [--skip-backend] [--skip-app-build]

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAGE_DIR="$ROOT_DIR/build/releases/dmg-stage"
DMG_RW="$ROOT_DIR/build/releases/Fichero-rw.dmg"
DMG_PATH="$ROOT_DIR/build/releases/Fichero.dmg"
MANIFEST_PATH="$ROOT_DIR/build/releases/release-manifest.txt"
VOLUME_NAME="Fichero"
APP_NAME="Fichero.app"
source "$ROOT_DIR/scripts/tier_build_map.sh"
APP_PATH="$ROOT_DIR/fichero/build/xcode/Products/$MAC_CONFIG/$APP_NAME"
ICON_SOURCE="$ROOT_DIR/icons/fichero-icon.png"
SPARKLE_FEED_URL="${SPARKLE_FEED_URL:-https://raw.githubusercontent.com/dtubb/fichero/main/fichero/appcast.xml}"

EXTRA_ARGS=()
SKIP_APP_BUILD=false
for arg in "$@"; do
  case "$arg" in
    --skip-app-build) SKIP_APP_BUILD=true ;;
    *) EXTRA_ARGS+=("$arg") ;;
  esac
done

# ── 0. Auto-stamp the dated release version ─────────────────────────────────
# Every release auto-stamps TODAY's date (set-release-version.sh with no arg);
# a second build the same day bumps a sub-number. Opt out by exporting
# FICHERO_RELEASE_VERSION (the operator has stamped a specific version already).
# Channel defaults to the numeric release version; set
# FICHERO_RELEASE_BETA=1 only for an explicitly requested prerelease suffix.
if [ "$SKIP_APP_BUILD" = true ]; then
  echo "[0/6] Skipping version stamp (--skip-app-build; using already-built app)"
elif [ -n "${FICHERO_RELEASE_VERSION:-}" ]; then
  echo "[0/6] FICHERO_RELEASE_VERSION=$FICHERO_RELEASE_VERSION set — operator controls version, not auto-stamping"
else
  echo "[0/6] Auto-stamp dated release version"
  STAMP_ARGS=()
  [ "${FICHERO_RELEASE_BETA:-0}" = "1" ] && STAMP_ARGS+=(--beta)
  "$ROOT_DIR/scripts/set-release-version.sh" "${STAMP_ARGS[@]+"${STAMP_ARGS[@]}"}"
fi

# ── 1. Build Release app ────────────────────────────────────────────────────
if [ "$SKIP_APP_BUILD" = true ]; then
  echo "[1/6] Skipping Release app build (--skip-app-build)"
else
  echo "[1/6] Build Release app"
  "$ROOT_DIR/scripts/build-release.sh" "${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}"
fi

if [ ! -d "$APP_PATH" ]; then
  echo "error: Release app not found at $APP_PATH" >&2
  exit 1
fi

# Guardrail (#13): never ship a stale app. The built app's version MUST match the
# project's MARKETING_VERSION. A cached/pre-built Products/Release app of a
# different version (e.g. --skip-app-build, or a skipped stamp) must NOT be
# packaged + tagged as this release — that shipped a 07.07 app under a 07.08 tag
# and created a Sparkle update loop.
BUILT_VER="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$APP_PATH/Contents/Info.plist" 2>/dev/null)"
# #3234: the version lives ONLY in Version.xcconfig (pbxproj has no literals).
EXPECT_VER="$(awk -F' = ' '$1 == "MARKETING_VERSION" { print $2; exit }' "$ROOT_DIR/fichero/Configs/Version.xcconfig")"
if [ -n "$EXPECT_VER" ] && [ "$BUILT_VER" != "$EXPECT_VER" ]; then
  echo "error: built app version '$BUILT_VER' != project MARKETING_VERSION '$EXPECT_VER'." >&2
  echo "       Refusing to ship a stale app. Clean-build the app (drop --skip-app-build) or fix the version stamp." >&2
  exit 1
fi
echo "  Version check OK: app is $BUILT_VER"

# ── 2. Stage DMG contents ───────────────────────────────────────────────────
echo
echo "[2/6] Stage DMG contents"
rm -rf "$STAGE_DIR"
mkdir -p "$STAGE_DIR" "$ROOT_DIR/build/releases"
ditto "$APP_PATH" "$STAGE_DIR/$APP_NAME"
ln -s /Applications "$STAGE_DIR/Applications"
echo "  Staged: $APP_NAME + Applications symlink"
if [ -f "$STAGE_DIR/$APP_NAME/Contents/Info.plist" ]; then
  /usr/libexec/PlistBuddy -c "Set :SUFeedURL $SPARKLE_FEED_URL" "$STAGE_DIR/$APP_NAME/Contents/Info.plist"
  echo "  Sparkle feed: $SPARKLE_FEED_URL"
fi

# ── 2b. Re-sign staged app with Developer ID for notarization (inside-out) ───
# The Release build signed with Apple Development; notarytool requires Developer
# ID Application + hardened runtime + secure timestamp on EVERY Mach-O.
# `codesign --deep` recurses into Contents/Frameworks (Sparkle.framework signs
# fine) but NOT into loose .so/.dylib inside an embedded bundle under
# Contents/Resources — so Briefcase's 800+ ad-hoc Python extensions in
# Fichero Server.app survive --deep and notarization rejects them. Sign every
# Mach-O file individually first (with --timestamp), then re-seal every bundle
# innermost-first so parent seals capture already-signed children. See #2662.
echo "[2b/6] Re-sign staged app with Developer ID Application (inside-out + --timestamp)"
APP="$STAGE_DIR/$APP_NAME"
DEV_IDENTITY="${FICHERO_DEV_IDENTITY:-Developer ID Application: DANIEL GAVIN LIVINGSTONE TUBB (QAPB6CWYR6)}"

# Hardened runtime is mandatory for notarization but blocks several things the
# embedded CPython engine needs (executable memory, DYLD vars, loading non-
# Team-signed wheels). Sign the engine bundle + its main executable WITH the
# engine entitlements so it survives on a clean Mac (#3163); keep the outer app
# on its own release entitlements (else this re-sign strips user-selected file
# access); everything else signs plain-hardened.
ENGINE_APP="$APP/Contents/Resources/Fichero Server.app"
ENGINE_ENTITLEMENTS="$ROOT_DIR/fichero/fichero/FicheroEngine.entitlements"
APP_ENTITLEMENTS="$ROOT_DIR/fichero/fichero/FicheroRelease.entitlements"

# entitlements_for PATH → echo the entitlements file to sign PATH with, or ""
# for a plain hardened-runtime sign. Only the two bundles' main executables (and
# the bundles themselves) carry entitlements; loose dylibs/.so sign plain.
entitlements_for() {
  case "$1" in
    "$ENGINE_APP"|"$ENGINE_APP/Contents/MacOS/"*) printf '%s' "$ENGINE_ENTITLEMENTS" ;;
    "$APP"|"$APP/Contents/MacOS/"*)               printf '%s' "$APP_ENTITLEMENTS" ;;
    *)                                            printf '' ;;
  esac
}

# sign_hardened PATH → Developer ID + hardened runtime + timestamp, adding
# --entitlements when entitlements_for selects one. Returns codesign's status.
sign_hardened() {
  local target="$1" ent
  ent="$(entitlements_for "$target")"
  if [ -n "$ent" ]; then
    codesign --force --sign "$DEV_IDENTITY" --options runtime --timestamp \
      --entitlements "$ent" "$target" >/dev/null 2>&1
  else
    codesign --force --sign "$DEV_IDENTITY" --options runtime --timestamp \
      "$target" >/dev/null 2>&1
  fi
}

if [ ! -f "$ENGINE_ENTITLEMENTS" ]; then
  echo "error: engine entitlements not found at $ENGINE_ENTITLEMENTS" >&2
  echo "  (embedded CPython needs these under hardened runtime — see #3163)" >&2
  exit 1
fi

# 2b.1 — collect every Mach-O in the app. `file {} +` batches one invocation per
# many files; grep Mach-O; drop the per-architecture lines `file` emits for
# universal binaries ("path (for architecture x86_64): ...") so only real paths
# remain. sort -u dedups.
#
# `LC_ALL=C` is load-bearing: `file` echoes bytes from the paths and contents it
# inspects, and the embedded engine ships files whose names are not valid UTF-8.
# Under a UTF-8 locale awk ABORTS on the first such byte ("towc: multibyte
# conversion failure") and takes the whole release with it — which is exactly
# how two release runs died today, both at this line. C locale treats input as
# bytes, which is all this filter needs.
macho_list="$(mktemp)"
find "$APP" -type f -exec file {} + 2>/dev/null \
  | LC_ALL=C awk -F': ' '/Mach-O/ && !/\(for architecture/ {print $1}' \
  | sort -u > "$macho_list"
macho_count=$(wc -l < "$macho_list" | tr -d ' ')
echo "  $macho_count Mach-O binaries to sign (Developer ID + hardened runtime + secure timestamp)"

# 2b.2 — sign each Mach-O individually. Keep this as a plain loop: when the
# script runs under xcodebuild, the inherited environment can be large enough
# that xargs cannot assemble even one command.
sign_fails=0
while IFS= read -r macho; do
  if ! sign_hardened "$macho"; then
    echo "  error: failed to re-sign Mach-O: $macho" >&2
    sign_fails=$((sign_fails + 1))
  fi
done < "$macho_list"
rm -f "$macho_list"
if [ "$sign_fails" -gt 0 ]; then
  echo "error: $sign_fails Mach-O binaries failed to re-sign" >&2
  exit 1
fi
echo "  Signed $macho_count Mach-O binaries"

# 2b.3 — re-seal every bundle innermost-first. Sorting bundle paths by length
# descending guarantees a nested bundle (Downloader.xpc, Updater.app,
# Fichero Server.app) is sealed before its parent, so the parent's seal hashes
# an already-correct child. Covers Sparkle.framework (+ XPC services + Updater),
# the embedded Fichero Server.app, and the outer Fichero.app.
bundle_list="$(mktemp)"
find "$APP" -type d \( -name '*.app' -o -name '*.framework' -o -name '*.xpc' \) \
  | awk '{print length, $0}' | sort -rn | cut -d' ' -f2- > "$bundle_list"
bundle_fails=0
while IFS= read -r bundle; do
  if ! sign_hardened "$bundle"; then
    echo "  error: failed to re-seal bundle: $bundle" >&2
    bundle_fails=$((bundle_fails + 1))
  fi
done < "$bundle_list"
rm -f "$bundle_list"
if [ "$bundle_fails" -gt 0 ]; then
  echo "error: $bundle_fails bundles failed to re-seal" >&2
  exit 1
fi
echo "  Re-sealed all bundles innermost-first"

# 2b.4 — verify the whole app
if ! codesign --verify --deep --strict "$APP" >/dev/null 2>&1; then
  echo "error: Developer ID re-sign verification failed for $APP" >&2
  exit 1
fi
echo "  Re-signed + verified: $APP_NAME"

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

# Style the Finder window via AppleScript. Finder automation can fail in
# headless/agent sessions; that should not block a signed, notarizable DMG.
if ! osascript <<APPLESCRIPT
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
then
  echo "  warning: Finder DMG styling failed — continuing with default layout" >&2
fi

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
