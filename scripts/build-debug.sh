#!/usr/bin/env bash
set -euo pipefail

# Build Fichero.app in Debug configuration.
# In debug mode, run the backend separately with: scripts/start-backend.sh
# Usage: scripts/build-debug.sh

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SWIFTUI_ROOT="$ROOT_DIR/fichero"
PROJECT="$SWIFTUI_ROOT/fichero.xcodeproj"
SCHEME="Fichero"
CONFIGURATION="Debug"
DERIVED_DATA="$SWIFTUI_ROOT/build/xcode"
APP_PATH="$DERIVED_DATA/Products/$CONFIGURATION/Fichero.app"

echo "[1/1] Xcode Debug build"
xcodebuild \
  -project "$PROJECT" \
  -scheme "$SCHEME" \
  -configuration "$CONFIGURATION" \
  -derivedDataPath "$DERIVED_DATA" \
  -skipPackagePluginValidation \
  build

if [ ! -d "$APP_PATH" ]; then
  echo "error: built app not found at $APP_PATH" >&2
  exit 1
fi

echo
echo "Fichero.app (Debug): $APP_PATH"
echo
echo "For debug, run the backend separately:"
echo "  scripts/start-backend.sh"
