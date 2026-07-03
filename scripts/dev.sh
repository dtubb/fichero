#!/usr/bin/env bash
set -euo pipefail

# Fichero dev harness — one entry point for consistent build/launch across
# every mode (#2867). Builds fail inconsistently when everyone hand-rolls
# xcodebuild invocations; this pins scheme, configuration, destination,
# derivedData, and the resolved *backend mode* so the manager, Daniel, and
# CI all get the same result.
#
# Usage:
#   scripts/dev.sh <mode> [--run] [--help]
#
# Modes (build is always headless-safe; --run launches where supported):
#   debug-mac-uvicorn   Debug macOS app, backend = EXTERNAL uvicorn (you run it)
#   debug-mac-embed     Debug macOS app, backend = EMBEDDED (app spawns engine)
#   debug-ios-embed     Debug iOS app  (device or sim)
#   debug-ipad-embed    Debug iPad app (device or sim; same universal target)
#   release-mac         Release macOS app with embedded engine
#   release-ios         Release iOS app
#   release-ipad        Release iPad app
#   build-all           Compile-gate every buildable mode in sequence
#
# The backend mode is resolved and PRINTED for every mode so you always know
# whether the app will connect to your uvicorn or spawn its own engine.
#
# Destinations for iOS/iPad default to `generic/platform=iOS` (compiles for
# device without pinning a UDID — headless-safe). Override with:
#   DEVICE_ID=<udid>       build/run for a specific plugged-in device
#   SIM_NAME='iPhone 16'   build/run in a named simulator
#
# derivedDataPath goes to a per-mode scratch dir (macOS and iOS build products
# differ, so they must not share a derivedData). Override the root with
# DERIVED_ROOT. Headless macOS builds pass CODE_SIGNING_ALLOWED=NO so they
# succeed without a signing identity or an attached device.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT="$ROOT_DIR/fichero/fichero.xcodeproj"
SCHEME="Fichero"
DERIVED_ROOT="${DERIVED_ROOT:-${TMPDIR:-/tmp}/fichero-dev-derived}"

RUN=false
MODE="${1:-}"
shift || true
for arg in "$@"; do
  case "$arg" in
    --run) RUN=true ;;
    --help|-h) MODE="--help" ;;
    *) echo "error: unknown argument '$arg'" >&2; exit 2 ;;
  esac
done

usage() {
  sed -n '3,45p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

if [ -z "$MODE" ] || [ "$MODE" = "--help" ]; then
  usage
  exit 0
fi

# ios_destination: resolve the iOS/iPad destination from env, defaulting to a
# generic device build (headless-safe, no UDID needed).
ios_destination() {
  if [ -n "${DEVICE_ID:-}" ]; then
    echo "platform=iOS,id=$DEVICE_ID"
  elif [ -n "${SIM_NAME:-}" ]; then
    echo "platform=iOS Simulator,name=$SIM_NAME"
  else
    echo "generic/platform=iOS"
  fi
}

# do_build <config> <destination> <derived-subdir> [extra xcodebuild args...]
#
# The project pins SYMROOT to fichero/build/xcode/Products, so build products
# land there (per config+platform: Debug, Release, Debug-iphoneos, …) — modes
# don't clobber each other, and build-release.sh/smoke scripts find the app
# where they expect it. -derivedDataPath still gives each mode its own module
# cache/intermediates scratch dir. ponytail: don't override SYMROOT — the
# pinned layout already isolates by config, and other scripts depend on it.
do_build() {
  local config="$1" destination="$2" subdir="$3"; shift 3
  local derived="$DERIVED_ROOT/$subdir"
  echo "  scheme=$SCHEME config=$config destination=$destination"
  echo "  derivedData=$derived"
  xcodebuild \
    -project "$PROJECT" \
    -scheme "$SCHEME" \
    -configuration "$config" \
    -destination "$destination" \
    -derivedDataPath "$derived" \
    -skipPackagePluginValidation \
    "$@" \
    build
  APP_PATH="$ROOT_DIR/fichero/build/xcode/Products/$config${APP_SUFFIX:-}/Fichero.app"
}

# ── mode dispatch ───────────────────────────────────────────────────────────
case "$MODE" in
  debug-mac-uvicorn)
    echo "[dev] $MODE — backend: EXTERNAL uvicorn (run: scripts/start-backend.sh)"
    APP_SUFFIX="" do_build Debug "platform=macOS" mac-debug CODE_SIGNING_ALLOWED=NO
    echo
    echo "Backend mode: EXTERNAL. Start it separately:  scripts/start-backend.sh"
    echo "App: ${APP_PATH:-}"
    if [ "$RUN" = true ]; then open "$APP_PATH"; fi
    ;;

  debug-mac-embed)
    echo "[dev] $MODE — backend: EMBEDDED (app spawns its own engine)"
    echo "  note: the engine bundle is embedded by the Release run-script phase;"
    echo "        a Debug build embeds only if a prior Release build left one in"
    echo "        Resources. For a guaranteed embed, use release-mac."
    APP_SUFFIX="" do_build Debug "platform=macOS" mac-debug CODE_SIGNING_ALLOWED=NO
    echo
    echo "Backend mode: EMBEDDED. Do NOT run scripts/start-backend.sh (would be adopted as external)."
    echo "App: ${APP_PATH:-}"
    if [ "$RUN" = true ]; then open "$APP_PATH"; fi
    ;;

  debug-ios-embed|debug-ipad-embed)
    dest="$(ios_destination)"
    echo "[dev] $MODE — backend: REMOTE host required"
    echo "  note: iOS/iPad cannot spawn a local engine until in-process embed"
    echo "        (#2865) lands. Configure a remote engine host in Settings."
    APP_SUFFIX="-iphoneos" do_build Debug "$dest" ios-debug CODE_SIGNING_ALLOWED=NO
    echo
    echo "Backend mode: REMOTE (configure host in Settings; local embed pending #2865)."
    echo "Destination: $dest"
    ;;

  release-mac)
    echo "[dev] $MODE — backend: EMBEDDED briefcase engine"
    echo "  note: for a fully embedded engine bundle use scripts/build-release.sh"
    echo "        (runs the Briefcase engine build first). This compile-gates the host app."
    APP_SUFFIX="" do_build Release "platform=macOS" mac-release CODE_SIGNING_ALLOWED=NO
    echo
    echo "Backend mode: EMBEDDED. App: ${APP_PATH:-}"
    ;;

  release-ios|release-ipad)
    dest="$(ios_destination)"
    echo "[dev] $MODE — backend: REMOTE host required (local embed pending #2865)"
    APP_SUFFIX="-iphoneos" do_build Release "$dest" ios-release CODE_SIGNING_ALLOWED=NO
    echo
    echo "Backend mode: REMOTE. Destination: $dest"
    ;;

  build-all)
    echo "[dev] build-all — compile-gating every buildable mode"
    for m in debug-mac-embed debug-ios-embed release-mac release-ios; do
      echo
      echo "──── $m ────"
      "${BASH_SOURCE[0]}" "$m"
    done
    echo
    echo "build-all: all modes compiled"
    ;;

  *)
    echo "error: unknown mode '$MODE'" >&2
    echo
    usage
    exit 2
    ;;
esac
