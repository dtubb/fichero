#!/usr/bin/env bash
set -euo pipefail

# One command for the three release tracks:
#   1. Developer ID DMG for direct/Sparkle distribution.
#   2. Optional Mac TestFlight upload via App Store Connect.
#   3. Optional universal iPhone/iPad TestFlight upload via App Store Connect.
#
# Usage:
#   scripts/release-all.sh [--skip-dmg] [--skip-notarize]
#                          [--skip-testflight | --skip-mac-testflight | --skip-ios-testflight]
#                          [--mac-only | --ios-only] [--github] [--draft]
#                          [--dev | --tier <release|beta|alpha|dev>]
# --dev / --tier build the requested feature tier (default: release). `--dev`
# bakes ALL dev features into the archive (Dev Embedded mac config + dev
# FICHERO_FEATURE_TIER on iOS) so internal TestFlight/DMG builds expose the
# full alpha-grade surface, not just the stripped release features (#3365).
#
# See docs/contributor/release/release-lane.md for required certificates/profiles and the
# repeatable DMG, Sparkle/GitHub, and Mac TestFlight release cycle.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RELEASE_DIR="$ROOT_DIR/build/releases"
DMG_PATH="$RELEASE_DIR/Fichero.dmg"
MAC_ARCHIVE_PATH="$RELEASE_DIR/Fichero-macOS.xcarchive"
MAC_EXPORT_DIR="$RELEASE_DIR/testflight-export-macos"
MAC_EXPORT_OPTIONS="$RELEASE_DIR/ExportOptions-mac-testflight.plist"
IOS_ARCHIVE_PATH="$RELEASE_DIR/Fichero-iOS.xcarchive"
IOS_EXPORT_DIR="$RELEASE_DIR/testflight-export-ios"
IOS_EXPORT_OPTIONS="$RELEASE_DIR/ExportOptions-ios-testflight.plist"
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
IOS_APP_STORE_PROFILE_PATH="${IOS_APP_STORE_PROFILE_PATH:-$HOME/Downloads/App_Store_Connect.mobileprovision}"
IOS_APP_STORE_PROFILE_NAME="${IOS_APP_STORE_PROFILE_NAME:-App Store Connect}"
IOS_APP_STORE_SIGNING_CERT="${IOS_APP_STORE_SIGNING_CERT:-7CD87BA09F2DA8A79652710DE0F5E3C5DCD2CC35}"
IOS_APP_STORE_PROFILE_UUID=""
# Developer ID Application identity used by the DMG path (build-release-dmg.sh).
# Preflight test-signs with it so a missing keychain partition grant fails fast
# instead of hanging the DMG sign step 20 minutes in.
DEV_IDENTITY="${FICHERO_DEV_IDENTITY:-Developer ID Application: DANIEL GAVIN LIVINGSTONE TUBB (QAPB6CWYR6)}"
APP_BUNDLE_ID="${FICHERO_APP_BUNDLE_ID:-app.fichero.fichero}"

# Keep archive schemes aligned with the feature-tier build map.
# Sourced AFTER arg parsing below so --dev/--tier can set FICHERO_RELEASE_TIER
# before tier_build_map.sh resolves (scheme, config) from it.

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

install_provisioning_profile() {
  local source_path="$1"
  local default_name="$2"
  local uuid_var="$3"
  [ -f "$source_path" ] || return 0

  local plist
  plist="$(mktemp)"
  security cms -D -i "$source_path" > "$plist"
  local profile_uuid profile_name
  profile_uuid="$(/usr/libexec/PlistBuddy -c 'Print :UUID' "$plist")"
  profile_name="$(/usr/libexec/PlistBuddy -c 'Print :Name' "$plist" 2>/dev/null || printf '%s' "$default_name")"
  local profile_ext
  profile_ext="${source_path##*.}"
  mkdir -p "$HOME/Library/MobileDevice/Provisioning Profiles"
  cp "$source_path" \
    "$HOME/Library/MobileDevice/Provisioning Profiles/$profile_uuid.$profile_ext"
  rm -f "$plist"
  printf -v "$uuid_var" '%s' "$profile_uuid"
  echo "  Installed provisioning profile: $profile_name ($profile_uuid)"
}

install_mac_app_store_profile() {
  install_provisioning_profile "$MAC_APP_STORE_PROFILE_PATH" "$MAC_APP_STORE_PROFILE_NAME" MAC_APP_STORE_PROFILE_UUID
}

install_ios_app_store_profile() {
  install_provisioning_profile "$IOS_APP_STORE_PROFILE_PATH" "$IOS_APP_STORE_PROFILE_NAME" IOS_APP_STORE_PROFILE_UUID
}

# ── Codesign keychain preflight ─────────────────────────────────────────────
# A codesign that needs a keychain partition grant pops a GUI prompt and hangs a
# headless release. Test-sign a throwaway binary with each identity the active
# lanes use BEFORE the long build, so a missing grant fails fast with the
# one-time fix instead of hanging mid-release. macOS ships no `timeout`, so the
# probe runs codesign in a subshell and kills it after HANG_SECONDS if it hasn't
# returned. On a keychain set up once (partition list persisted) every probe is
# instant and the whole lane runs unattended.
preflight_codesign_access() {
  local ids=("$@")
  local probe_dir probe_bin probe_src
  probe_dir="$(mktemp -d)"
  probe_src="$probe_dir/probe.c"
  probe_bin="$probe_dir/probe"
  printf 'int main(void){return 0;}\n' > "$probe_src"
  if ! cc -arch arm64 "$probe_src" -o "$probe_bin" 2>/dev/null; then
    echo "  codesign preflight: could not build probe binary (cc) — skipping" >&2
    rm -rf "$probe_dir"
    return 0
  fi
  local HANG_SECONDS=15
  local failed=0
  for id in "${ids[@]}"; do
    ( codesign --force --sign "$id" --timestamp=none "$probe_bin" >/dev/null 2>&1 ) &
    local pid=$!
    local hung=0 rc=0
    for _ in $(seq 1 "$HANG_SECONDS"); do
      kill -0 "$pid" 2>/dev/null || break
      sleep 1
    done
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
      hung=1
    else
      wait "$pid"; rc=$?
    fi
    if [ "$hung" = 1 ] || [ "$rc" -ne 0 ]; then
      echo "error: codesign cannot access signing identity '$id' without a prompt." >&2
      echo "  The release would hang here. One-time setup — run in Terminal" >&2
      echo "  (asks for your login password ONCE, then persists):" >&2
      echo "    security set-key-partition-list -S apple-tool:,apple:,codesign: \\" >&2
      echo "      -s -k <login-pw> ~/Library/Keychains/login.keychain-db" >&2
      failed=1
    else
      echo "  codesign OK: $id"
    fi
  done
  rm -rf "$probe_dir"
  [ "$failed" = 0 ]
}

SKIP_DMG=false
SKIP_NOTARIZE=false
RUN_MAC_TESTFLIGHT=true
RUN_IOS_TESTFLIGHT=true
RUN_GITHUB=false
GITHUB_ARGS=()
# Default: finish when the TestFlight upload succeeds and let Apple email the
# team when processing completes/fails (no polling, no JWT, no key dependency).
# Pass --wait-for-processing to instead block until each build reaches
# processingState=VALID in App Store Connect (polls the ASC REST API, like
# fastlane/pilot). Opt-in because it needs a valid ASC API key.
WAIT_FOR_PROCESSING=false

while [ $# -gt 0 ]; do
  case "$1" in
    --skip-dmg) SKIP_DMG=true ;;
    --skip-notarize) SKIP_NOTARIZE=true ;;
    --skip-testflight)
      RUN_MAC_TESTFLIGHT=false
      RUN_IOS_TESTFLIGHT=false
      ;;
    --skip-mac-testflight) RUN_MAC_TESTFLIGHT=false ;;
    --skip-ios-testflight) RUN_IOS_TESTFLIGHT=false ;;
    --mac-only) RUN_IOS_TESTFLIGHT=false ;;
    --ios-only) RUN_MAC_TESTFLIGHT=false ;;
    --github) RUN_GITHUB=true ;;
    --draft) GITHUB_ARGS+=("--draft") ;;
    --prerelease) GITHUB_ARGS+=("--prerelease") ;;
    --wait-for-processing) WAIT_FOR_PROCESSING=true ;;
    --dev) FICHERO_RELEASE_TIER=dev ;;
    --tier)
      shift
      FICHERO_RELEASE_TIER="${1:?--tier requires a value: release|beta|alpha|dev}"
      ;;
    --tier=*) FICHERO_RELEASE_TIER="${1#--tier=}" ;;
    --help|-h)
      sed -n '2,16p' "$0"
      exit 0
      ;;
    *)
      echo "error: unknown argument: $1" >&2
      exit 2
      ;;
  esac
  shift
done

# Resolve the (scheme, configuration) build map from the selected feature tier.
# Done after arg parsing so --dev/--tier above take effect.
source "$ROOT_DIR/scripts/tier_build_map.sh"

mkdir -p "$RELEASE_DIR"

echo "=== Fichero release ==="
echo "Sparkle feed: $SPARKLE_FEED_URL"

# ── Auto-stamp the dated release version (once, up front) ────────────────────
# Stamp TODAY's date across frontend + backend before any build path runs, so
# both the DMG and the TestFlight archive carry the same auto-incremented dated
# version. Opt out by exporting FICHERO_RELEASE_VERSION (operator controls it);
# channel defaults to the numeric release version. Set FICHERO_RELEASE_BETA=1
# only for an explicitly requested prerelease suffix. We
# export FICHERO_RELEASE_VERSION afterward so the nested build-release-dmg.sh
# sees the version already set and does not re-stamp.
if [ -n "${FICHERO_RELEASE_VERSION:-}" ]; then
  echo
  echo "── Version: FICHERO_RELEASE_VERSION=$FICHERO_RELEASE_VERSION set — not auto-stamping ──"
else
  echo
  echo "── Version: auto-stamp dated release ──"
  STAMP_ARGS=()
  [ "${FICHERO_RELEASE_BETA:-0}" = "1" ] && STAMP_ARGS+=(--beta)
  "$ROOT_DIR/scripts/set-release-version.sh" "${STAMP_ARGS[@]+"${STAMP_ARGS[@]}"}"
  # Pin the just-stamped MARKETING_VERSION so downstream scripts don't re-stamp.
  export FICHERO_RELEASE_VERSION="$(project_setting MARKETING_VERSION)"
fi

echo
echo "── Preflight: codesign keychain access ──"
# Fail fast if codesign would hang on a keychain prompt mid-release. Only test
# the identities the active lanes will actually sign with.
PREFLIGHT_IDS=()
[ "$SKIP_DMG" = false ] && PREFLIGHT_IDS+=("$DEV_IDENTITY")
if [ "$RUN_MAC_TESTFLIGHT" = true ] || [ "$RUN_IOS_TESTFLIGHT" = true ]; then
  PREFLIGHT_IDS+=("$MAC_APP_STORE_SIGNING_CERT")
fi
if [ "${#PREFLIGHT_IDS[@]}" -gt 0 ]; then
  preflight_codesign_access "${PREFLIGHT_IDS[@]}"
fi

echo
echo "── Engine: rebuild current Briefcase stage ──"
"$ROOT_DIR/scripts/preflight-embedded-engine.sh" --rebuild

if [ "$SKIP_DMG" = false ]; then
  echo
  echo "── DMG: build + Developer ID sign ──"
  "$ROOT_DIR/scripts/build-release-dmg.sh" --skip-backend
fi

if [ "$SKIP_NOTARIZE" = false ]; then
  echo
  echo "── DMG: notarize + staple ──"
  "$ROOT_DIR/scripts/notarize.sh" "$DMG_PATH"
fi

if [ "$RUN_MAC_TESTFLIGHT" = true ] || [ "$RUN_IOS_TESTFLIGHT" = true ]; then
  echo
  echo "── TestFlight: codesign keychain already preflighted above ──"
  echo "  (if a codesign hang ever appears here, the preflight at the top caught it first)"
fi

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
ENGINE_APP="$ROOT_DIR/fichero-server/build/server/macos/app/Fichero Server.app"

if [ "$RUN_MAC_TESTFLIGHT" = true ] || [ "$RUN_IOS_TESTFLIGHT" = true ]; then
  if [ -d "$ENGINE_APP" ]; then
    echo "  Cleaning embedded engine bundle for App Store distribution"
    if [ "$RUN_MAC_TESTFLIGHT" = true ]; then
      FICHERO_CODESIGN_IDENTITY="$MAC_APP_STORE_SIGNING_CERT" \
      "$ROOT_DIR/scripts/clean-embedded-engine.sh" "$ENGINE_APP"
    else
      "$ROOT_DIR/scripts/clean-embedded-engine.sh" "$ENGINE_APP"
    fi
  fi
fi

if [ "$RUN_MAC_TESTFLIGHT" = true ]; then
  echo
  echo "── Mac TestFlight: archive + upload ──"

  echo "  TestFlight version: $TESTFLIGHT_MARKETING_VERSION ($TESTFLIGHT_BUILD_VERSION)"
  install_mac_app_store_profile

  rm -rf "$MAC_ARCHIVE_PATH"
  if ! xcodebuild -project "$ROOT_DIR/fichero/fichero.xcodeproj" \
    -scheme "$MAC_APP_STORE_SCHEME" \
    -configuration "$MAC_APP_STORE_CONFIG" \
    -destination "platform=macOS,arch=arm64" \
    -archivePath "$MAC_ARCHIVE_PATH" \
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

  # Re-sign the embedded engine in the archive with the DISTRIBUTION identity
  # and the two-key entitlements BEFORE export (#3952). The engine is embedded
  # by a shell-script phase, not the standard "Embed Helper Tools" phase, so
  # `xcodebuild -exportArchive` for TestFlight can re-sign it with the parent's
  # distribution entitlements — which include get-task-allow for TestFlight —
  # and get-task-allow is incompatible with com.apple.security.inherit, aborting
  # the engine child on launch. Pre-signing with distribution + the two-key set
  # makes the export's re-sign preserve the clean entitlements. The script
  # fails the release if get-task-allow is present after re-signing.
  if ! "$ROOT_DIR/scripts/resign_engine_in_archive.sh" \
    "$MAC_ARCHIVE_PATH" \
    "$MAC_APP_STORE_SIGNING_CERT" \
    "$ROOT_DIR/fichero/fichero/FicheroEngineAppStore.entitlements"; then
    echo "error: pre-export engine re-sign failed — the TestFlight build would abort the engine child (#3952)" >&2
    exit 1
  fi

  cat > "$MAC_EXPORT_OPTIONS" <<PLIST
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
  <!-- uploadSymbols=false skips IDEDistributionSymbolsStep. The embedded Python
       engine bundles a Mach-O the dSYM symbol extractor rejects with
       "unexpected Mach-O header code: 0xb17c0de"; the app itself packages/signs
       fine. Skipping symbol upload sidesteps that non-blocking step (we forgo
       crash symbolication, acceptable for a beta). -->
  <key>uploadSymbols</key>
  <false/>
  <key>manageAppVersionAndBuildNumber</key>
  <false/>
</dict>
</plist>
PLIST

  rm -rf "$MAC_EXPORT_DIR"
  if ! xcodebuild -exportArchive \
    -archivePath "$MAC_ARCHIVE_PATH" \
    -exportPath "$MAC_EXPORT_DIR" \
    -exportOptionsPlist "$MAC_EXPORT_OPTIONS" \
    -allowProvisioningUpdates \
    "${AUTH_ARGS[@]}"; then
    echo "error: Mac TestFlight export/upload failed" >&2
    echo "       Check App Store Connect permissions and Mac App Distribution/Mac Installer Distribution signing assets." >&2
    exit 1
  fi

  # exportArchive returns on upload completion, NOT when Apple finishes
  # processing the build into TestFlight. By default we stop here and let Apple
  # email the team when processing completes/fails — no polling, no JWT, no
  # ASC-key dependency. --wait-for-processing opts into polling the ASC REST
  # API until processingState=VALID (like fastlane/pilot); non-fatal on failure.
  if [ "$WAIT_FOR_PROCESSING" = true ] && [ -f "$APP_STORE_CONNECT_KEY_PATH" ]; then
    echo
    echo "  Mac TestFlight: waiting for Apple processing (until build is in TestFlight)…"
    if "$ROOT_DIR/scripts/wait-testflight-processing.py" \
      --key "$APP_STORE_CONNECT_KEY_PATH" \
      --key-id "$APP_STORE_CONNECT_KEY_ID" \
      --issuer-id "$APP_STORE_CONNECT_ISSUER_ID" \
      --bundle-id "$APP_BUNDLE_ID" \
      --version "$TESTFLIGHT_MARKETING_VERSION" \
      --build "$TESTFLIGHT_BUILD_VERSION" \
      --platform macos; then
      echo "  Mac TestFlight: confirmed in TestFlight"
    else
      echo "  warning: Mac TestFlight processing-wait exited non-zero — upload succeeded" >&2
      echo "           but processing was NOT confirmed. Check App Store Connect manually;" >&2
      echo "           the build will still process server-side." >&2
    fi
  else
    echo "  Mac TestFlight: uploaded — Apple will email when processing completes (or fails)."
  fi
fi

if [ "$RUN_IOS_TESTFLIGHT" = true ]; then
  echo
  echo "── iPhone/iPad TestFlight: archive + upload ──"
  echo "  TestFlight version: $TESTFLIGHT_MARKETING_VERSION ($TESTFLIGHT_BUILD_VERSION)"
  install_ios_app_store_profile

  rm -rf "$IOS_ARCHIVE_PATH"
  if ! xcodebuild -project "$ROOT_DIR/fichero/fichero.xcodeproj" \
    -scheme "$IOS_SCHEME" \
    -configuration "$IOS_CONFIG" \
    -destination "generic/platform=iOS" \
    -archivePath "$IOS_ARCHIVE_PATH" \
    -skipPackagePluginValidation \
    -allowProvisioningUpdates \
    "${AUTH_ARGS[@]}" \
    MARKETING_VERSION="$TESTFLIGHT_MARKETING_VERSION" \
    CURRENT_PROJECT_VERSION="$TESTFLIGHT_BUILD_VERSION" \
    FICHERO_FEATURE_TIER="$IOS_ARCHIVE_FEATURE_TIER" \
    archive; then
    echo "error: iOS archive failed; check Xcode signing and remote-client release settings" >&2
    exit 1
  fi

  cat > "$IOS_EXPORT_OPTIONS" <<PLIST
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
  <string>$IOS_APP_STORE_SIGNING_CERT</string>
  <key>provisioningProfiles</key>
  <dict>
    <key>app.fichero.fichero</key>
    <string>${IOS_APP_STORE_PROFILE_UUID:-$IOS_APP_STORE_PROFILE_NAME}</string>
  </dict>
  <key>uploadSymbols</key>
  <true/>
  <key>manageAppVersionAndBuildNumber</key>
  <false/>
</dict>
</plist>
PLIST

  rm -rf "$IOS_EXPORT_DIR"
  if ! xcodebuild -exportArchive \
    -archivePath "$IOS_ARCHIVE_PATH" \
    -exportPath "$IOS_EXPORT_DIR" \
    -exportOptionsPlist "$IOS_EXPORT_OPTIONS" \
    "${AUTH_ARGS[@]}"; then
    echo "error: iOS TestFlight export/upload failed" >&2
    echo "       Check the installed iOS App Store profile, Apple Distribution identity, and keychain access for codesign." >&2
    exit 1
  fi

  # By default: stop here, Apple emails on processing completion. Opt into
  # polling with --wait-for-processing (see the Mac TestFlight block above).
  if [ "$WAIT_FOR_PROCESSING" = true ] && [ -f "$APP_STORE_CONNECT_KEY_PATH" ]; then
    echo
    echo "  iPhone/iPad TestFlight: waiting for Apple processing (until build is in TestFlight)…"
    if "$ROOT_DIR/scripts/wait-testflight-processing.py" \
      --key "$APP_STORE_CONNECT_KEY_PATH" \
      --key-id "$APP_STORE_CONNECT_KEY_ID" \
      --issuer-id "$APP_STORE_CONNECT_ISSUER_ID" \
      --bundle-id "$APP_BUNDLE_ID" \
      --version "$TESTFLIGHT_MARKETING_VERSION" \
      --build "$TESTFLIGHT_BUILD_VERSION" \
      --platform ios; then
      echo "  iPhone/iPad TestFlight: confirmed in TestFlight"
    else
      echo "  warning: iPhone/iPad TestFlight processing-wait exited non-zero — upload succeeded" >&2
      echo "           but processing was NOT confirmed. Check App Store Connect manually;" >&2
      echo "           the build will still process server-side." >&2
    fi
  else
    echo "  iPhone/iPad TestFlight: uploaded — Apple will email when processing completes (or fails)."
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
echo "Mac archive: $MAC_ARCHIVE_PATH"
echo "iOS archive: $IOS_ARCHIVE_PATH"
