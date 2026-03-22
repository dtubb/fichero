#!/usr/bin/env bash
set -euo pipefail

# Build Fichero.app in Debug configuration with embedded Python backend.
# Usage: scripts/build-debug.sh [--skip-backend]

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_ROOT="$ROOT_DIR/fichero-api"
SWIFTUI_ROOT="$ROOT_DIR/fichero-swiftui"
PROJECT="$SWIFTUI_ROOT/fichero-swiftui.xcodeproj"
SCHEME="Fichero"
CONFIGURATION="Debug"
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
RESOURCES_DEST="$SWIFTUI_ROOT/fichero-swiftui/Resources/FicheroBackend.app"

TOTAL_STEPS=3
STEP=0

# ── 1. Build Python backend with Briefcase ──────────────────────────────────
STEP=$((STEP+1))
if [ "$SKIP_BACKEND" = true ]; then
  echo "[$STEP/$TOTAL_STEPS] Skipping backend build (--skip-backend)"
  if [ -d "$RESOURCES_DEST" ]; then
    echo "  Existing backend in Resources — will be included"
  else
    echo "  warning: no backend app in Resources — Fichero will build but backend won't start at runtime"
  fi
else
  echo "[$STEP/$TOTAL_STEPS] Building Python backend with Briefcase"
  cd "$API_ROOT"

  # Look for briefcase in project venvs first, then PATH
  if [ -x "$ROOT_DIR/.venv/bin/briefcase" ]; then
    export PATH="$ROOT_DIR/.venv/bin:$PATH"
  elif [ -x "$API_ROOT/.venv/bin/briefcase" ]; then
    export PATH="$API_ROOT/.venv/bin:$PATH"
  elif ! command -v briefcase >/dev/null 2>&1; then
    echo "Installing briefcase..."
    pip install briefcase
  fi

  # Clean previous build
  if [ -d "build/fichero-backend" ]; then
    chmod -R u+w build/fichero-backend 2>/dev/null || true
    rm -rf build/fichero-backend
  fi

  briefcase create macOS --app fichero-backend 2>/dev/null || true
  briefcase build macOS --app fichero-backend

  if [ ! -d "$BACKEND_APP" ]; then
    echo "error: Briefcase build failed — $BACKEND_APP not found" >&2
    exit 1
  fi
  echo "  Backend built: $BACKEND_APP"
fi

# ── 2. Copy backend into SwiftUI Resources ──────────────────────────────────
STEP=$((STEP+1))
echo "[$STEP/$TOTAL_STEPS] Embedding backend in SwiftUI Resources"
mkdir -p "$(dirname "$RESOURCES_DEST")"
if [ -d "$BACKEND_APP" ]; then
  rm -rf "$RESOURCES_DEST"
  cp -R "$BACKEND_APP" "$RESOURCES_DEST"
  echo "  Copied from Briefcase build"
elif [ -d "$RESOURCES_DEST" ]; then
  echo "  Using existing backend"
else
  echo "  No backend available — skipping embed"
fi

# ── 3. Xcode Debug build ────────────────────────────────────────────────────
STEP=$((STEP+1))
echo "[$STEP/$TOTAL_STEPS] Xcode Debug build"
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

echo
echo "Fichero.app (Debug): $APP_PATH"
