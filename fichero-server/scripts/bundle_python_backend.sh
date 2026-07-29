#!/bin/bash
set -e

# Bundle Python backend into Swift app resources.
# Run from repo root: ./fichero-server/scripts/bundle_python_backend.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$API_ROOT/.." && pwd)"
BUNDLE_DIR="$REPO_ROOT/fichero/fichero/Resources/python"
TEMP_DIR="/tmp/fichero_python_bundle"
FM_BRIDGE_SOURCE="$API_ROOT/bin/fm-bridge/FmBridge.swift"

PYTHON_VERSION="3.10"
PYTHON_FULL_VERSION="3.10.13"
BEEWARE_VERSION="3.10-b8"
BEEWARE_URL="https://github.com/beeware/Python-Apple-support/releases/download/${BEEWARE_VERSION}/Python-${PYTHON_FULL_VERSION}-macOS-support.b8.tar.gz"

rm -rf "$TEMP_DIR" "$BUNDLE_DIR"
mkdir -p "$TEMP_DIR" "$BUNDLE_DIR"

cd "$TEMP_DIR"
curl -L -o python.tar.gz "$BEEWARE_URL"
tar -xzf python.tar.gz
rm python.tar.gz

cp -R "Python.xcframework/macos-arm64_x86_64/Python.framework" "$BUNDLE_DIR/"
mkdir -p "$BUNDLE_DIR/bin" "$BUNDLE_DIR/lib/python${PYTHON_VERSION}/site-packages"
cd "$BUNDLE_DIR/bin"
ln -s ../Python.framework/Versions/Current/bin/python3 python3
ln -s python3 python

"$BUNDLE_DIR/bin/python3" -m pip install --upgrade pip
"$BUNDLE_DIR/bin/python3" -m pip install --target "$BUNDLE_DIR/lib/python${PYTHON_VERSION}/site-packages" \
  fastapi uvicorn[standard] pydantic duckdb lancedb langchain langgraph langchain-core \
  langchain-ollama litellm python-multipart python-dotenv aiofiles

"$BUNDLE_DIR/bin/python3" -m pip install -e "$API_ROOT" --target "$BUNDLE_DIR/lib/python${PYTHON_VERSION}/site-packages"
mkdir -p "$BUNDLE_DIR/lib/python${PYTHON_VERSION}/site-packages/fichero/resources/bin"
swiftc -O -parse-as-library \
  -o "$BUNDLE_DIR/lib/python${PYTHON_VERSION}/site-packages/fichero/resources/bin/fm-bridge" \
  "$FM_BRIDGE_SOURCE"
cp "$API_ROOT/scripts/start_backend.py" "$BUNDLE_DIR/"
chmod +x "$BUNDLE_DIR/start_backend.py"

rm -rf "$TEMP_DIR"
echo "✅ Python bundle ready at $BUNDLE_DIR"
