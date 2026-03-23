#!/usr/bin/env bash
set -euo pipefail

# Build Fichero.app in Release configuration with embedded Python backend.
# Codesigns with Developer ID Application if available.
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
RESOURCES_DEST="$SWIFTUI_ROOT/fichero-swiftui/Resources/FicheroBackend.app"

# ── 1. Build Python backend with Briefcase ──────────────────────────────────
if [ "$SKIP_BACKEND" = true ]; then
  echo "[1/4] Skipping backend build (--skip-backend)"
  if [ -d "$RESOURCES_DEST" ]; then
    echo "  Existing backend in Resources — will be included"
  else
    echo "  warning: no backend app in Resources — release will lack embedded backend"
  fi
else
  echo "[1/4] Building Python backend with Briefcase"
  cd "$API_ROOT"

  # Look for briefcase in dedicated venv (Python 3.13), then project venvs, then PATH
  if [ -x "$API_ROOT/.briefcase-venv/bin/briefcase" ]; then
    export PATH="$API_ROOT/.briefcase-venv/bin:$PATH"
  elif [ -x "$ROOT_DIR/.venv/bin/briefcase" ]; then
    export PATH="$ROOT_DIR/.venv/bin:$PATH"
  elif [ -x "$API_ROOT/.venv/bin/briefcase" ]; then
    export PATH="$API_ROOT/.venv/bin:$PATH"
  elif ! command -v briefcase >/dev/null 2>&1; then
    echo "error: briefcase not found. Set up with:" >&2
    echo "  python3.13 -m venv fichero-api/.briefcase-venv" >&2
    echo "  fichero-api/.briefcase-venv/bin/pip install briefcase" >&2
    exit 1
  fi

  # Clean previous build
  if [ -d "build/fichero-backend" ]; then
    chmod -R u+w build/fichero-backend 2>/dev/null || true
    rm -rf build/fichero-backend
  fi

  # Find signing identity for backend
  SIGNING_IDENTITY=$(security find-identity -v -p codesigning | grep "Developer ID Application" | head -1 | awk -F'"' '{print $2}' || true)
  if [ -z "$SIGNING_IDENTITY" ]; then
    SIGNING_IDENTITY=$(security find-identity -v -p codesigning | grep "Apple Development" | head -1 | awk -F'"' '{print $2}' || true)
    echo "  warning: no Developer ID Application identity — using Apple Development for backend"
  fi

  briefcase create macOS --app fichero-backend 2>/dev/null || true
  briefcase build macOS --app fichero-backend

  if [ -n "$SIGNING_IDENTITY" ]; then
    codesign --force --sign "$SIGNING_IDENTITY" --deep --timestamp \
      "build/fichero-backend/macos/app/FicheroBackend.app"
  fi

  if [ ! -d "$BACKEND_APP" ]; then
    echo "error: Briefcase build failed — $BACKEND_APP not found" >&2
    exit 1
  fi
  echo "  Backend built: $BACKEND_APP"
fi

# ── 2. Copy backend into SwiftUI Resources ──────────────────────────────────
echo "[2/4] Embedding backend in SwiftUI Resources"
mkdir -p "$(dirname "$RESOURCES_DEST")"
if [ -d "$BACKEND_APP" ]; then
  rm -rf "$RESOURCES_DEST"
  cp -R "$BACKEND_APP" "$RESOURCES_DEST"
  echo "  Copied from Briefcase build to: $RESOURCES_DEST"
elif [ -d "$RESOURCES_DEST" ]; then
  echo "  Using existing backend at: $RESOURCES_DEST"
else
  echo "  No backend available — skipping embed"
fi

# ── 3. Xcode Release build ──────────────────────────────────────────────────
echo "[3/4] Xcode Release build"
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

# ── 4. Codesign the final app ────────────────────────────────────────────────
echo "[4/4] Codesigning"
DEVELOPER_ID=$(security find-identity -v -p codesigning | grep "Developer ID Application" | head -1 | awk -F'"' '{print $2}' || true)

if [ -n "$DEVELOPER_ID" ]; then
  codesign --force --sign "$DEVELOPER_ID" --deep --timestamp --options runtime "$APP_PATH"
  echo "  Signed with: $DEVELOPER_ID"

  if codesign --verify --deep --strict "$APP_PATH" >/dev/null 2>&1; then
    echo "  Codesign verification: PASS"
  else
    echo "  warning: codesign verification failed" >&2
  fi
else
  echo "  warning: no Developer ID Application identity found"
  echo "  The app is signed with Xcode's default identity but cannot be notarized."
  echo "  Create a Developer ID Application certificate in Apple Developer portal."
fi

echo
echo "Fichero.app (Release): $APP_PATH"
