#!/bin/bash
set -e

# Build backend bundle with Briefcase.
# Run from repo root: ./fichero-api/scripts/build_backend_bundle.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "🔨 Building Fichero Backend with Briefcase"
cd "$API_ROOT"

if ! command -v briefcase >/dev/null 2>&1; then
  echo "❌ Briefcase not found. Installing..."
  pip install briefcase
fi

if [ -d "build/engine" ]; then
  chmod -R u+w build/engine 2>/dev/null || true
  rm -rf build/engine || /bin/rm -rf build/engine
fi

SIGNING_IDENTITY=$(security find-identity -v -p codesigning | grep "Apple Development" | head -1 | awk -F'"' '{print $2}')
if [ -z "$SIGNING_IDENTITY" ]; then
  echo "❌ No Apple Development signing identity found"
  exit 1
fi

briefcase package macOS --app engine --identity "$SIGNING_IDENTITY"

BACKEND_APP_SOURCE="build/engine/macos/app/Fichero Engine.app"
if [ -d "$BACKEND_APP_SOURCE" ]; then
  echo "✅ Backend bundle ready: $BACKEND_APP_SOURCE"
else
  echo "❌ Build failed - $BACKEND_APP_SOURCE not found"
  exit 1
fi
