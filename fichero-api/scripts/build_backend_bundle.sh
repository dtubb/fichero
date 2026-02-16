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

if [ -d "build/fichero-backend" ]; then
  chmod -R u+w build/fichero-backend 2>/dev/null || true
  rm -rf build/fichero-backend || /bin/rm -rf build/fichero-backend
fi

SIGNING_IDENTITY=$(security find-identity -v -p codesigning | grep "Apple Development" | head -1 | awk -F'"' '{print $2}')
if [ -z "$SIGNING_IDENTITY" ]; then
  echo "❌ No Apple Development signing identity found"
  exit 1
fi

briefcase package macOS --app fichero-backend --identity "$SIGNING_IDENTITY"

BACKEND_APP_SOURCE="build/fichero-backend/macos/app/FicheroBackend.app"
if [ -d "$BACKEND_APP_SOURCE" ]; then
  echo "✅ Backend bundle ready: $BACKEND_APP_SOURCE"
else
  echo "❌ Build failed - $BACKEND_APP_SOURCE not found"
  exit 1
fi
