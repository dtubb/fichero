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

briefcase package macOS --app fichero_server --identity "$SIGNING_IDENTITY"

BACKEND_APP_SOURCE="build/fichero_server/macos/app/Fichero Server.app"
if [ -d "$BACKEND_APP_SOURCE" ]; then
  echo "✅ Backend bundle ready: $BACKEND_APP_SOURCE"
else
  echo "❌ Build failed - $BACKEND_APP_SOURCE not found"
  exit 1
fi
