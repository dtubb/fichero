#!/bin/bash
set -e

###############################################################################
# Build Backend Bundle with Briefcase
#
# This script:
# 1. Builds the Fichero backend using Briefcase
# 2. The resulting .app will be embedded in Fichero.app
#
# Usage:
#   ./scripts/build_backend_bundle.sh
#
# Output:
#   macOS/Fichero Backend.app (ready to embed)
###############################################################################

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "🔨 Building Fichero Backend with Briefcase"
echo "==========================================="
echo ""

cd "$PROJECT_ROOT"

# Check if Briefcase is installed
if ! command -v briefcase &> /dev/null; then
    echo "❌ Briefcase not found. Installing..."
    pip install briefcase
fi

# Clean previous build completely
echo "🧹 Cleaning previous build..."
if [ -d "build/fichero-backend" ]; then
    chmod -R u+w build/fichero-backend 2>/dev/null || true
    rm -rf build/fichero-backend || {
        echo "   Standard clean failed, using forced removal..."
        /bin/rm -rf build/fichero-backend
    }
fi

# Get the signing identity (same one Xcode uses)
echo "🔍 Finding signing identity..."
SIGNING_IDENTITY=$(security find-identity -v -p codesigning | grep "Apple Development" | head -1 | awk -F'"' '{print $2}')

if [ -z "$SIGNING_IDENTITY" ]; then
    echo "❌ No Apple Development signing identity found!"
    echo ""
    echo "Available identities:"
    security find-identity -v -p codesigning
    echo ""
    echo "Please ensure you have a valid Apple Development certificate."
    exit 1
fi

echo "🔐 Using signing identity: $SIGNING_IDENTITY"
echo ""

# Build and package backend with proper code signing
echo "🔨 Building and packaging backend app..."
briefcase package macOS --app fichero-backend --identity "$SIGNING_IDENTITY"

# The built app is in build/fichero-backend/macos/app/
BACKEND_APP_SOURCE="build/fichero-backend/macos/app/Fichero Backend.app"

# Verify output
if [ -d "$BACKEND_APP_SOURCE" ]; then
    BUNDLE_SIZE=$(du -sh "$BACKEND_APP_SOURCE" | awk '{print $1}')
    echo ""
    echo "✅ Backend bundle ready!"
    echo "   Location: $BACKEND_APP_SOURCE"
    echo "   Size: $BUNDLE_SIZE"
    echo ""
    echo "Next steps:"
    echo "1. Build Fichero.app in Xcode"
    echo "2. Backend will be automatically copied into Resources/"
    echo "3. Swift app will launch backend on startup"
else
    echo "❌ Build failed - $BACKEND_APP_SOURCE not found"
    exit 1
fi
