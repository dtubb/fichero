#!/bin/bash
set -e

###############################################################################
# Bundle Python Backend for Fichero.app
#
# This script:
# 1. Downloads Python-Apple-support (pre-compiled Python for macOS)
# 2. Installs all dependencies into the bundle
# 3. Signs all .so files with your developer certificate
# 4. Copies everything to Fichero/Resources/python/
#
# Usage:
#   ./scripts/bundle_python_backend.sh
#
# Requirements:
#   - Active Apple Developer certificate
#   - Xcode command line tools
###############################################################################

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BUNDLE_DIR="$PROJECT_ROOT/Fichero/Fichero/Resources/python"
TEMP_DIR="/tmp/fichero_python_bundle"

# Python version (must match your development environment)
PYTHON_VERSION="3.10"
PYTHON_FULL_VERSION="3.10.13"

# BeeWare Python-Apple-support release
BEEWARE_VERSION="3.10-b8"
BEEWARE_URL="https://github.com/beeware/Python-Apple-support/releases/download/${BEEWARE_VERSION}/Python-${PYTHON_FULL_VERSION}-macOS-support.b8.tar.gz"

echo "📦 Bundling Python backend for Fichero.app"
echo "=========================================="
echo "Python version: $PYTHON_FULL_VERSION"
echo "BeeWare version: $BEEWARE_VERSION"
echo "Bundle directory: $BUNDLE_DIR"
echo ""

# Clean up previous build
echo "🧹 Cleaning up previous build..."
rm -rf "$TEMP_DIR"
mkdir -p "$TEMP_DIR"
rm -rf "$BUNDLE_DIR"
mkdir -p "$BUNDLE_DIR"

# Step 1: Download Python-Apple-support
echo "⬇️  Downloading Python-Apple-support..."
cd "$TEMP_DIR"
curl -L -o python.tar.gz "$BEEWARE_URL"
tar -xzf python.tar.gz
rm python.tar.gz

# Step 2: Copy Python framework
echo "📁 Copying Python framework..."
cp -R "Python.xcframework/macos-arm64_x86_64/Python.framework" "$BUNDLE_DIR/"

# Create standard directory structure
mkdir -p "$BUNDLE_DIR/bin"
mkdir -p "$BUNDLE_DIR/lib/python${PYTHON_VERSION}/site-packages"

# Create python3 symlink in bin/
cd "$BUNDLE_DIR/bin"
ln -s ../Python.framework/Versions/Current/bin/python3 python3
ln -s python3 python
cd "$PROJECT_ROOT"

# Step 3: Install dependencies
echo "📦 Installing Python dependencies..."
# Use pip to install into the bundle
"$BUNDLE_DIR/bin/python3" -m pip install --upgrade pip

# Install from requirements
if [ -f "$PROJECT_ROOT/requirements.txt" ]; then
    echo "   Installing from requirements.txt..."
    "$BUNDLE_DIR/bin/python3" -m pip install -r "$PROJECT_ROOT/requirements.txt" \
        --target "$BUNDLE_DIR/lib/python${PYTHON_VERSION}/site-packages"
else
    echo "   Installing dependencies individually..."
    "$BUNDLE_DIR/bin/python3" -m pip install \
        --target "$BUNDLE_DIR/lib/python${PYTHON_VERSION}/site-packages" \
        fastapi \
        uvicorn[standard] \
        pydantic \
        duckdb \
        lancedb \
        langchain \
        langgraph \
        langchain-core \
        langchain-ollama \
        litellm \
        python-multipart \
        python-dotenv \
        aiofiles
fi

# Step 4: Install fichero package
echo "📦 Installing fichero package..."
cd "$PROJECT_ROOT"
"$BUNDLE_DIR/bin/python3" -m pip install -e . \
    --target "$BUNDLE_DIR/lib/python${PYTHON_VERSION}/site-packages"

# Step 5: Copy backend launcher script
echo "📄 Copying backend launcher..."
cp "$SCRIPT_DIR/start_backend.py" "$BUNDLE_DIR/"
chmod +x "$BUNDLE_DIR/start_backend.py"

# Step 6: Sign all .so files (required for hardened runtime)
echo "🔐 Signing .so files..."

# Get signing identity
SIGNING_IDENTITY=$(security find-identity -v -p codesigning | grep "Apple Development" | head -1 | awk '{print $2}')

if [ -z "$SIGNING_IDENTITY" ]; then
    echo "⚠️  Warning: No signing identity found. Skipping code signing."
    echo "   App may not run with hardened runtime enabled."
else
    echo "   Using signing identity: $SIGNING_IDENTITY"

    # Find and sign all .so files
    find "$BUNDLE_DIR" -name "*.so" -print0 | while IFS= read -r -d '' sofile; do
        echo "   Signing: $(basename "$sofile")"
        codesign --force --sign "$SIGNING_IDENTITY" \
            --options runtime \
            --timestamp \
            "$sofile" 2>/dev/null || echo "   ⚠️  Failed to sign $sofile"
    done

    # Sign Python framework
    echo "   Signing Python framework..."
    codesign --force --sign "$SIGNING_IDENTITY" \
        --options runtime \
        --timestamp \
        "$BUNDLE_DIR/Python.framework" 2>/dev/null || echo "   ⚠️  Failed to sign framework"
fi

# Step 7: Clean up
echo "🧹 Cleaning up..."
rm -rf "$TEMP_DIR"

# Step 8: Calculate bundle size
BUNDLE_SIZE=$(du -sh "$BUNDLE_DIR" | awk '{print $1}')
echo ""
echo "✅ Bundle complete!"
echo "   Location: $BUNDLE_DIR"
echo "   Size: $BUNDLE_SIZE"
echo ""
echo "Next steps:"
echo "1. Add $BUNDLE_DIR to Xcode project (Copy Bundle Resources)"
echo "2. Build and run Fichero.app"
echo "3. Backend will start automatically on app launch"
