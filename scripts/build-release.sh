#!/usr/bin/env bash
set -euo pipefail

# Build Fichero.app in Release configuration with embedded Python backend.
# Uses briefcase package to build the backend, then Xcode builds the app.
# Xcode's CopyFiles build phase embeds FicheroBackend.app automatically.
#
# Usage: scripts/build-release.sh [--skip-backend]

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_ROOT="$ROOT_DIR/fichero-api"
SWIFTUI_ROOT="$ROOT_DIR/fichero-swiftui"
PROJECT="$SWIFTUI_ROOT/fichero-swiftui.xcodeproj"
SCHEME="Fichero"
CONFIGURATION="Release"
DERIVED_DATA="$SWIFTUI_ROOT/build/xcode"
APP_PATH="$DERIVED_DATA/Products/$CONFIGURATION/Fichero.app"

SKIP_BACKEND=false
for arg in "$@"; do
  case $arg in
    --skip-backend) SKIP_BACKEND=true ;;
    --help|-h) echo "Usage: $0 [--skip-backend]"; exit 0 ;;
  esac
done

BACKEND_APP="$API_ROOT/build/fichero-backend/macos/app/FicheroBackend.app"

# ── 1. Build Python backend with Briefcase ──────────────────────────────────
if [ "$SKIP_BACKEND" = true ]; then
  echo "[1/3] Skipping backend build (--skip-backend)"
  if [ -d "$BACKEND_APP" ]; then
    echo "  Using existing backend at: $BACKEND_APP"
  else
    echo "  warning: no backend at $BACKEND_APP — Xcode will skip embedding"
  fi
else
  echo "[1/3] Building Python backend with Briefcase"
  cd "$API_ROOT"

  # Look for briefcase in dedicated venv (Python 3.13), then PATH
  if [ -x "$API_ROOT/.briefcase-venv/bin/briefcase" ]; then
    export PATH="$API_ROOT/.briefcase-venv/bin:$PATH"
  elif ! command -v briefcase >/dev/null 2>&1; then
    echo "error: briefcase not found. Set up with:" >&2
    echo "  python3.13 -m venv fichero-api/.briefcase-venv" >&2
    echo "  fichero-api/.briefcase-venv/bin/pip install briefcase" >&2
    exit 1
  fi

  # Find signing identity
  SIGNING_IDENTITY=$(security find-identity -v -p codesigning | grep "Developer ID Application" | head -1 | awk -F'"' '{print $2}' || true)
  if [ -z "$SIGNING_IDENTITY" ]; then
    SIGNING_IDENTITY=$(security find-identity -v -p codesigning | grep "Apple Development" | head -1 | awk -F'"' '{print $2}' || true)
  fi

  if [ -z "$SIGNING_IDENTITY" ]; then
    echo "error: no signing identity found" >&2
    exit 1
  fi

  # briefcase package = create + build + sign in one step
  briefcase package macOS --app fichero-backend --identity "$SIGNING_IDENTITY"

  if [ ! -d "$BACKEND_APP" ]; then
    echo "error: Briefcase package failed — $BACKEND_APP not found" >&2
    exit 1
  fi
  echo "  Backend packaged: $BACKEND_APP"
fi

# ── 2. Xcode Release build ──────────────────────────────────────────────────
# Xcode's CopyFiles build phase copies FicheroBackend.app into Resources
echo "[2/3] Xcode Release build"
cd "$ROOT_DIR"
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

# ── 3. Verify codesigning ───────────────────────────────────────────────────
echo "[3/3] Verifying codesign"
if codesign --verify --deep --strict "$APP_PATH" >/dev/null 2>&1; then
  echo "  Codesign verification: PASS"
else
  echo "  warning: codesign verification issue (may need Developer ID for distribution)"
fi

# Check backend is embedded
if [ -d "$APP_PATH/Contents/Resources/FicheroBackend.app" ]; then
  BACKEND_SIZE=$(du -sh "$APP_PATH/Contents/Resources/FicheroBackend.app" | cut -f1)
  echo "  Backend embedded: $BACKEND_SIZE"
else
  echo "  warning: FicheroBackend.app not in built app Resources"
fi

echo
echo "Fichero.app (Release): $APP_PATH"
