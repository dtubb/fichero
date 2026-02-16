#!/bin/bash
set -e

###############################################################################
# Build Backend
#
# This script builds the Fichero backend (arm64 Apple Silicon only).
#
# Usage:
#   ./scripts/build_dual_backend.sh           # Fast update + build
#   ./scripts/build_dual_backend.sh --rebuild # Clean rebuild from scratch
#
# Output:
#   - build/fichero-backend/macos/app/FicheroBackend.app (arm64 binary)
###############################################################################

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
API_ROOT="$PROJECT_ROOT/fichero-api"

# Check for --rebuild flag
REBUILD=false
if [ "${1:-}" = "--rebuild" ]; then
    REBUILD=true
fi

echo "🔨 Building Fichero Backend (arm64)"
echo "===================================="
echo ""

cd "$API_ROOT"

# Clean build if --rebuild flag is set
if [ "$REBUILD" = true ]; then
    echo "🧹 Cleaning build directory (full rebuild)..."
    rm -rf build/fichero-backend
    echo "✅ Build directory cleaned"
    echo ""
fi

# Check if Briefcase is installed
if ! command -v briefcase &> /dev/null; then
    echo "❌ Briefcase not found. Installing..."
    pip install briefcase
fi

# Hardcoded signing identity to avoid Intune MDM certificate issues
SIGNING_IDENTITY="Apple Development: DANIEL GAVIN LIVINGSTONE TUBB (4H486QMRQP)"

echo "🔐 Using signing identity: $SIGNING_IDENTITY"
echo ""

###############################################################################
# Build backend
###############################################################################
echo "📱 Building backend (arm64)..."
echo ""

echo "🔨 Updating backend code..."
if briefcase update macOS --app fichero-backend 2>/dev/null; then
    echo "✅ Update successful"
else
    echo "⚠️  Update failed (app doesn't exist), doing full build..."
fi

echo "🔨 Building backend..."
briefcase build macOS --app fichero-backend

echo "🔐 Signing backend..."
codesign --force --sign "$SIGNING_IDENTITY" --deep --timestamp \
    "build/fichero-backend/macos/app/FicheroBackend.app"

BACKEND_SIZE=$(du -sh "build/fichero-backend/macos/app/FicheroBackend.app" | awk '{print $1}')
echo "✅ Backend built successfully (Size: $BACKEND_SIZE)"
echo ""

###############################################################################
# Summary
###############################################################################
echo "✅ Backend ready!"
echo ""
echo "📦 Binary (arm64 Apple Silicon):"
echo "   Location: build/fichero-backend/macos/app/FicheroBackend.app"
echo "   Size: $BACKEND_SIZE"
echo ""
echo "Next steps:"
echo "1. Copy FicheroBackend.app into your Xcode project Resources"
echo "2. Build Fichero.app in Xcode"
echo "3. Backend runs on Apple Silicon Macs"
