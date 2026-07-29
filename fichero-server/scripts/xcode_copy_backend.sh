#!/bin/bash
set -euo pipefail

# Copy Briefcase-built backend bundle into the built Swift app bundle.
# Intended for use in an Xcode Run Script build phase.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

BACKEND_APP_SOURCE="$API_ROOT/build/server/macos/app/Fichero Server.app"

if [[ -z "${BUILT_PRODUCTS_DIR:-}" || -z "${PRODUCT_NAME:-}" ]]; then
  echo "❌ BUILT_PRODUCTS_DIR / PRODUCT_NAME not set (must run from Xcode build phase)"
  exit 1
fi

DEST_DIR="$BUILT_PRODUCTS_DIR/$PRODUCT_NAME.app/Contents/Resources"
DEST_APP="$DEST_DIR/Fichero Server.app"

if [ ! -d "$BACKEND_APP_SOURCE" ]; then
  echo "❌ Backend bundle not found at: $BACKEND_APP_SOURCE"
  echo "Run ./fichero-server/scripts/build_backend_bundle.sh first."
  exit 1
fi

mkdir -p "$DEST_DIR"
rm -rf "$DEST_APP"
cp -R "$BACKEND_APP_SOURCE" "$DEST_APP"

echo "✅ Copied backend bundle to: $DEST_APP"
