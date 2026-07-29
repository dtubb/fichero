#!/bin/bash
# Build the fm-bridge Swift CLI that exposes Apple Intelligence /
# FoundationModels to Python via subprocess. See FmBridge.swift for protocol.
#
# Usage: ./build.sh
# Or from repo root: fichero-server/bin/fm-bridge/build.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# -O      release-optimized
# -parse-as-library  required for @main when there's also top-level Codable structs
swiftc -O -parse-as-library -o fm-bridge FmBridge.swift

echo "✅ Built $SCRIPT_DIR/fm-bridge"
echo "   Smoke test: echo '{\"prompt\": \"hello\"}' | ./fm-bridge"
