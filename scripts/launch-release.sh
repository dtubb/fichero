#!/usr/bin/env bash
set -euo pipefail

# Launch the built Fichero.app via LaunchServices (`open`) so it gets proper
# Window Server scene activation. (#760)
#
# Why this script exists: direct-exec'ing the binary from a terminal —
#   ./fichero/build/xcode/Products/Release/Fichero.app/Contents/MacOS/Fichero &
# does NOT draw a window on macOS 26. The Swift process starts and init() runs,
# but AppKit's scene activation lands in a state where nothing appears on
# screen and the WindowGroup's `.task {}` never fires (so the embedded engine
# never spawns). This is a known macOS behavior for GUI apps exec'd by a
# non-Aqua parent (a terminal): https://developer.apple.com/forums/thread/669266
# Launching through `open` hands the app to LaunchServices, which activates the
# scene correctly — the same path Finder / Spotlight / Dock use.
#
# Usage:
#   scripts/launch-release.sh            # launch the Release build
#   scripts/launch-release.sh --debug    # launch the Debug build instead
#   scripts/launch-release.sh --wait     # block until the app quits (-W)
#
# Build first if needed:
#   scripts/build-release.sh             # Release (embedded engine)
#   scripts/build-debug.sh               # Debug

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SWIFTUI_ROOT="$ROOT_DIR/fichero"
CONFIGURATION="Release"
WAIT=false

usage() {
  cat <<'EOF'
Usage:
  scripts/launch-release.sh            # launch the Release build
  scripts/launch-release.sh --debug    # launch the Debug build instead
  scripts/launch-release.sh --wait     # block until the app quits (-W)

Build first if needed:
  scripts/build-release.sh             # Release (embedded engine)
  scripts/build-debug.sh               # Debug
EOF
}

for arg in "$@"; do
  case "$arg" in
    --debug) CONFIGURATION="Debug" ;;
    --wait|-W) WAIT=true ;;
    --help|-h) usage; exit 0 ;;
    *) echo "error: unknown argument '$arg'" >&2; usage; exit 2 ;;
  esac
done

APP_PATH="$SWIFTUI_ROOT/build/xcode/Products/$CONFIGURATION/Fichero.app"

if [ ! -d "$APP_PATH" ]; then
  echo "error: $APP_PATH not found." >&2
  if [ "$CONFIGURATION" = "Release" ]; then
    echo "       Build it first: scripts/build-release.sh" >&2
  else
    echo "       Build it first: scripts/build-debug.sh" >&2
  fi
  exit 1
fi

echo "Launching ($CONFIGURATION) $APP_PATH via 'open -n'…" >&2
echo "  Logs go to the unified log, not this terminal. Tail them with:" >&2
echo "    scripts/tail-fichero-logs.sh" >&2

# -n: open a new instance even if one is already running.
# -W: wait for the app to exit before returning (opt-in via --wait).
if $WAIT; then
  exec open -n -W "$APP_PATH"
else
  exec open -n "$APP_PATH"
fi
