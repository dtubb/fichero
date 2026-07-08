#!/usr/bin/env bash
set -euo pipefail

# One command for the two release tracks:
#   1. Developer ID DMG for direct/Sparkle distribution.
#   2. Optional Mac TestFlight upload via App Store Connect.
#
# Usage:
#   scripts/release-all.sh [--skip-backend] [--skip-dmg] [--skip-notarize] [--skip-testflight] [--github] [--draft]
#
# See docs/contributor/release/release-lane.md for required certificates/profiles and the
# repeatable DMG, Sparkle/GitHub, and Mac TestFlight release cycle.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RELEASE_DIR="$ROOT_DIR/build/releases"
DMG_PATH="$RELEASE_DIR/Fichero.dmg"
ARCHIVE_PATH="$RELEASE_DIR/Fichero-macOS.xcarchive"
EXPORT_DIR="$RELEASE_DIR/testflight-export"
EXPORT_OPTIONS="$RELEASE_DIR/ExportOptions-mac-testflight.plist"
SPARKLE_FEED_URL="${SPARKLE_FEED_URL:-https://raw.githubusercontent.com/dtubb/fichero/main/fichero/appcast.xml}"
APP_STORE_CONNECT_KEY_PATH="${APP_STORE_CONNECT_KEY_PATH:-$HOME/Documents/Developer/Certificates/2026-07-5 App Store Connect/AuthKey_2MGYUR786H.p8}"
APP_STORE_CONNECT_KEY_ID="${APP_STORE_CONNECT_KEY_ID:-2MGYUR786H}"
APP_STORE_CONNECT_ISSUER_ID="${APP_STORE_CONNECT_ISSUER_ID:-6d2cfad9-6a3d-48a0-bdcc-9c75c308f812}"
MAC_APP_STORE_PROFILE_PATH="${MAC_APP_STORE_PROFILE_PATH:-$HOME/Downloads/Mac_App_Store_Connect.provisionprofile}"
MAC_APP_STORE_PROFILE_NAME="${MAC_APP_STORE_PROFILE_NAME:-Mac App Store Connect}"
MAC_APP_STORE_SIGNING_CERT="${MAC_APP_STORE_SIGNING_CERT:-7CD87BA09F2DA8A79652710DE0F5E3C5DCD2CC35}"
# Installer identity that signs the Mac App Store .pkg. This is a SEPARATE cert
# from the application cert above; provisioning profiles never carry it, so it must
# be named explicitly or xcodebuild tries (and fails) to resolve it via the profile.
MAC_APP_STORE_INSTALLER_CERT="${MAC_APP_STORE_INSTALLER_CERT:-3rd Party Mac Developer Installer}"
MAC_APP_STORE_PROFILE_UUID=""

project_setting() {
  local name="$1"
  awk -F'= ' -v name="$name" '$1 ~ name"[[:space:]]*$" { gsub(/[;"]/,"",$2); print $2; exit }' \
    "$ROOT_DIR/fichero/fichero.xcodeproj/project.pbxproj"
}

app_store_version() {
  local raw="${1%%-*}"
  local IFS=.
  local part
  local out=()

  for part in $raw; do
    [ -n "$part" ] || continue
    out+=("$((10#$part))")
    [ "${#out[@]}" -lt 3 ] || break
  done

  if [ "${#out[@]}" -eq 0 ]; then
    echo "1.0"
  else
    local IFS=.
    echo "${out[*]}"
  fi
}

install_mac_app_store_profile() {
  [ -f "$MAC_APP_STORE_PROFILE_PATH" ] || return 0

  local plist
  plist="$(mktemp)"
  security cms -D -i "$MAC_APP_STORE_PROFILE_PATH" > "$plist"
  MAC_APP_STORE_PROFILE_UUID="$(/usr/libexec/PlistBuddy -c 'Print :UUID' "$plist")"
  mkdir -p "$HOME/Library/MobileDevice/Provisioning Profiles"
  cp "$MAC_APP_STORE_PROFILE_PATH" \
    "$HOME/Library/MobileDevice/Provisioning Profiles/$MAC_APP_STORE_PROFILE_UUID.provisionprofile"
  rm -f "$plist"
  echo "  Installed Mac App Store profile: $MAC_APP_STORE_PROFILE_NAME ($MAC_APP_STORE_PROFILE_UUID)"
}

SKIP_BACKEND=false
SKIP_DMG=false
SKIP_NOTARIZE=false
SKIP_TESTFLIGHT=false
RUN_GITHUB=false
GITHUB_ARGS=()

for arg in "$@"; do
  case "$arg" in
    --skip-backend) SKIP_BACKEND=true ;;
    --skip-dmg) SKIP_DMG=true ;;
    --skip-notarize) SKIP_NOTARIZE=true ;;
    --skip-testflight) SKIP_TESTFLIGHT=true ;;
    --github) RUN_GITHUB=true ;;
    --draft) GITHUB_ARGS+=("--draft") ;;
    --help|-h)
      sed -n '2,12p' "$0"
      exit 0
      ;;
    *)
      echo "error: unknown argument: $arg" >&2
      exit 2
      ;;
  esac
done

mkdir -p "$RELEASE_DIR"

echo "=== Fichero release ==="
echo "Sparkle feed: $SPARKLE_FEED_URL"

# ── Auto-stamp the dated release version (once, up front) ────────────────────
# Stamp TODAY's date across frontend + backend before any build path runs, so
# both the DMG and the TestFlight archive carry the same auto-incremented dated
# version. Opt out by exporting FICHERO_RELEASE_VERSION (operator controls it);
# channel defaults to beta — set FICHERO_RELEASE_BETA=0 for a stable stamp. We
# export FICHERO_RELEASE_VERSION afterward so the nested build-release-dmg.sh
# sees the version already set and does not re-stamp.
if [ -n "${FICHERO_RELEASE_VERSION:-}" ]; then
  echo
  echo "── Version: FICHERO_RELEASE_VERSION=$FICHERO_RELEASE_VERSION set — not auto-stamping ──"
else
  echo
  echo "── Version: auto-stamp dated release ──"
  STAMP_ARGS=()
  [ "${FICHERO_RELEASE_BETA:-1}" != "0" ] && STAMP_ARGS+=(--beta)
  "$ROOT_DIR/scripts/set-release-version.sh" "${STAMP_ARGS[@]+"${STAMP_ARGS[@]}"}"
  # Pin the just-stamped MARKETING_VERSION so downstream scripts don't re-stamp.
  export FICHERO_RELEASE_VERSION="$(project_setting MARKETING_VERSION)"
fi

if [ "$SKIP_DMG" = false ]; then
  echo
  echo "── DMG: build + Developer ID sign ──"
  BUILD_ARGS=()
  [ "$SKIP_BACKEND" = true ] && BUILD_ARGS+=("--skip-backend")
  "$ROOT_DIR/scripts/build-release-dmg.sh" "${BUILD_ARGS[@]+"${BUILD_ARGS[@]}"}"
fi

if [ "$SKIP_NOTARIZE" = false ]; then
  echo
  echo "── DMG: notarize + staple ──"
  "$ROOT_DIR/scripts/notarize.sh" "$DMG_PATH"
fi

if [ "$SKIP_TESTFLIGHT" = false ]; then
  echo
  echo "── Mac TestFlight: archive + upload ──"

  AUTH_ARGS=()
  if [ -f "$APP_STORE_CONNECT_KEY_PATH" ]; then
    echo "  Using App Store Connect API key: $APP_STORE_CONNECT_KEY_ID"
    AUTH_ARGS=(
      -authenticationKeyPath "$APP_STORE_CONNECT_KEY_PATH"
      -authenticationKeyID "$APP_STORE_CONNECT_KEY_ID"
      -authenticationKeyIssuerID "$APP_STORE_CONNECT_ISSUER_ID"
    )
  else
    echo "  App Store Connect API key not found; falling back to Xcode account credentials"
  fi

  PROJECT_MARKETING_VERSION="$(project_setting MARKETING_VERSION)"
  PROJECT_BUILD_VERSION="$(project_setting CURRENT_PROJECT_VERSION)"
  TESTFLIGHT_MARKETING_VERSION="${TESTFLIGHT_MARKETING_VERSION:-$(app_store_version "$PROJECT_MARKETING_VERSION")}"
  TESTFLIGHT_BUILD_VERSION="${TESTFLIGHT_BUILD_VERSION:-${PROJECT_BUILD_VERSION:-$(date +%Y%m%d)}}"

  echo "  TestFlight version: $TESTFLIGHT_MARKETING_VERSION ($TESTFLIGHT_BUILD_VERSION)"
  install_mac_app_store_profile

  if ! xcodebuild -project "$ROOT_DIR/fichero/fichero.xcodeproj" \
    -scheme Fichero \
    -configuration Release \
    -destination "platform=macOS,arch=arm64" \
    -archivePath "$ARCHIVE_PATH" \
    -skipPackagePluginValidation \
    -allowProvisioningUpdates \
    "${AUTH_ARGS[@]}" \
    ARCHS=arm64 \
    ONLY_ACTIVE_ARCH=YES \
    SWIFT_COMPILATION_MODE=singlefile \
    SWIFT_ENABLE_BATCH_MODE=NO \
    SWIFT_OPTIMIZATION_LEVEL=-Onone \
    MARKETING_VERSION="$TESTFLIGHT_MARKETING_VERSION" \
    CURRENT_PROJECT_VERSION="$TESTFLIGHT_BUILD_VERSION" \
    SPARKLE_FEED_URL="$SPARKLE_FEED_URL" \
    archive; then
    echo "error: macOS archive failed; check Xcode signing, sandbox, and embedded engine build phase" >&2
    exit 1
  fi

  cat > "$EXPORT_OPTIONS" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>method</key>
  <string>app-store-connect</string>
  <key>destination</key>
  <string>upload</string>
  <key>teamID</key>
  <string>QAPB6CWYR6</string>
  <key>signingStyle</key>
  <string>manual</string>
  <key>signingCertificate</key>
  <string>$MAC_APP_STORE_SIGNING_CERT</string>
  <key>installerSigningCertificate</key>
  <string>$MAC_APP_STORE_INSTALLER_CERT</string>
  <key>provisioningProfiles</key>
  <dict>
    <key>app.fichero.fichero</key>
    <string>${MAC_APP_STORE_PROFILE_UUID:-$MAC_APP_STORE_PROFILE_NAME}</string>
  </dict>
  <key>testFlightInternalTestingOnly</key>
  <true/>
  <key>uploadSymbols</key>
  <true/>
  <key>manageAppVersionAndBuildNumber</key>
  <false/>
</dict>
</plist>
PLIST

  rm -rf "$EXPORT_DIR"
  if ! xcodebuild -exportArchive \
    -archivePath "$ARCHIVE_PATH" \
    -exportPath "$EXPORT_DIR" \
    -exportOptionsPlist "$EXPORT_OPTIONS" \
    -allowProvisioningUpdates \
    "${AUTH_ARGS[@]}"; then
    echo "error: Mac TestFlight export/upload failed" >&2
    echo "       Check App Store Connect permissions and Mac App Distribution/Mac Installer Distribution signing assets." >&2
    exit 1
  fi
fi

if [ "$RUN_GITHUB" = true ]; then
  echo
  echo "── GitHub/Sparkle release ──"
  "$ROOT_DIR/scripts/create-github-release.sh" "${GITHUB_ARGS[@]+"${GITHUB_ARGS[@]}"}"
fi

echo
echo "Done."
echo "DMG:      $DMG_PATH"
echo "Archive:  $ARCHIVE_PATH"
