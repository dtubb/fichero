#!/bin/bash
set -e

# Build backend (arm64 Apple Silicon).
# Run from repo root: ./fichero-api/scripts/build_dual_backend.sh [--rebuild]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

REBUILD=false
if [ "${1:-}" = "--rebuild" ]; then
  REBUILD=true
fi

cd "$API_ROOT"

if [ "$REBUILD" = true ]; then
  rm -rf build/fichero-backend
fi

if ! command -v briefcase >/dev/null 2>&1; then
  pip install briefcase
fi

SIGNING_IDENTITY="Apple Development: DANIEL GAVIN LIVINGSTONE TUBB (4H486QMRQP)"

briefcase update macOS --app fichero-backend 2>/dev/null || true
briefcase build macOS --app fichero-backend
codesign --force --sign "$SIGNING_IDENTITY" --deep --timestamp \
  "build/fichero-backend/macos/app/FicheroBackend.app"

echo "✅ Backend built: build/fichero-backend/macos/app/FicheroBackend.app"
