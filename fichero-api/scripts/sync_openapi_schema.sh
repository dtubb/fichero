#!/bin/bash
set -e

# Sync OpenAPI schema from backend to Swift API client.
# Run from repo root: ./fichero-api/scripts/sync_openapi_schema.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$API_ROOT/.." && pwd)"

cd "$REPO_ROOT"
PYTHONPATH="$API_ROOT/src" "$REPO_ROOT/.venv/bin/python" "$API_ROOT/scripts/export_openapi_schema.py"

cp "$API_ROOT/tests/contracts/openapi.json" "$REPO_ROOT/fichero-swiftui/FicheroAPIClient/Sources/FicheroAPIClient/openapi.json"

cd "$REPO_ROOT/fichero-swiftui/FicheroAPIClient"
swift build 2>&1 | grep -E "(error|warning: Schema|Writing data|Build complete)" | head -30 || true

echo "✅ OpenAPI schema synced"
