#!/bin/bash
# Syncs the OpenAPI schema from Python to Swift
#
# Run this whenever the Python API changes:
#   ./scripts/sync_openapi_schema.sh
#
# This updates:
#   - fichero-api/tests/contracts/openapi.json (for testing)
#   - fichero-api/tests/contracts/endpoints.json (for validation)
#   - fichero-swiftui/FicheroAPIClient/Sources/FicheroAPIClient/openapi.json (for code generation)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

echo "Exporting OpenAPI schema from Python..."
cd "$REPO_ROOT"
PYTHONPATH=fichero-api/src .venv/bin/python scripts/export_openapi_schema.py

echo ""
echo "Copying schema to Swift package..."
cp fichero-api/tests/contracts/openapi.json fichero-swiftui/FicheroAPIClient/Sources/FicheroAPIClient/openapi.json

echo ""
echo "Rebuilding Swift API client..."
cd fichero-swiftui/FicheroAPIClient
swift build 2>&1 | grep -E "(error|warning: Schema|Writing data|Build complete)" | head -30

echo ""
echo "Done! The Swift API client is now in sync with Python."
echo ""
echo "Next steps:"
echo "  1. Open Xcode and build to verify"
echo "  2. Run Swift tests to verify endpoint compatibility"
