#!/bin/bash
set -e

# Build backend bundle with Briefcase.
# Run from repo root: ./fichero-server/scripts/build_backend_bundle.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
FM_BRIDGE_SOURCE="$API_ROOT/bin/fm-bridge/FmBridge.swift"
FM_BRIDGE_DEST="$API_ROOT/src/fichero_server/resources/bin/fm-bridge"

echo "🔨 Building Fichero Backend with Briefcase"
cd "$API_ROOT"

if ! command -v briefcase >/dev/null 2>&1; then
  echo "❌ Briefcase not found. Installing..."
  pip install briefcase
fi

if [ -d "build/server" ]; then
  chmod -R u+w build/server 2>/dev/null || true
  rm -rf build/server || /bin/rm -rf build/server
fi

if ! command -v swiftc >/dev/null 2>&1; then
  echo "❌ swiftc not found; can't build fm-bridge"
  exit 1
fi

mkdir -p "$(dirname "$FM_BRIDGE_DEST")"
swiftc -O -parse-as-library -o "$FM_BRIDGE_DEST" "$FM_BRIDGE_SOURCE"
chmod 755 "$FM_BRIDGE_DEST"

SIGNING_IDENTITY=$(security find-identity -v -p codesigning | grep "Apple Development" | head -1 | awk -F'"' '{print $2}')
if [ -z "$SIGNING_IDENTITY" ]; then
  echo "❌ No Apple Development signing identity found"
  exit 1
fi

BACKEND_APP_SOURCE="build/fichero_server/macos/app/Fichero Server.app"

# Build and SIGN as two steps, so there is a seam between them.
#
# kreuzberg's Rust binding resolves libpdfium.dylib by @loader_path — beside
# the binding — and extracts a copy into a temp dir when it is missing. macOS
# quarantines a file the app writes, Gatekeeper refuses to dlopen it, and PDF
# text extraction dies while the engine silently falls back to fitz for page
# splitting (#2430): PDFs import as images with no searchable text, on every
# machine. A dylib fetched at runtime can never inherit our notarization.
#
# pypdfium2 (in the briefcase requires) ships a real one, but under
# pypdfium2_raw/, which is not @loader_path. So place it BEFORE signing —
# after this the codesign pass seals it like everything else.
briefcase update macOS --app fichero_server
briefcase build macOS --app fichero_server
python3 "$API_ROOT/../scripts/place_pdfium_for_kreuzberg.py" \
  "$BACKEND_APP_SOURCE/Contents/Resources/app_packages"
briefcase package macOS --app fichero_server --identity "$SIGNING_IDENTITY"
if [ -d "$BACKEND_APP_SOURCE" ]; then
  echo "✅ Backend bundle ready: $BACKEND_APP_SOURCE"
else
  echo "❌ Build failed - $BACKEND_APP_SOURCE not found"
  exit 1
fi
