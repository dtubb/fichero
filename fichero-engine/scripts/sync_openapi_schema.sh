#!/bin/bash
set -e

# Sync OpenAPI schema from fichero-engine into the Swift package imported by the SwiftUI app.
# Run from repo root: ./fichero-engine/scripts/sync_openapi_schema.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$API_ROOT/.." && pwd)"

if [ -n "${FICHERO_PYTHON_BIN:-}" ] && [ -x "${FICHERO_PYTHON_BIN}" ]; then
  PYTHON_BIN="${FICHERO_PYTHON_BIN}"
elif [ -n "${VIRTUAL_ENV:-}" ] && [ -x "${VIRTUAL_ENV}/bin/python" ]; then
  PYTHON_BIN="${VIRTUAL_ENV}/bin/python"
elif [ -x "$API_ROOT/.venv/bin/python" ]; then
  PYTHON_BIN="$API_ROOT/.venv/bin/python"
elif [ -x "$REPO_ROOT/.venv/bin/python" ]; then
  PYTHON_BIN="$REPO_ROOT/.venv/bin/python"
else
  PYTHON_BIN="python3"
fi

cd "$REPO_ROOT"
PYTHONPATH="$API_ROOT/src" FICHERO_FEATURE_TIER=dev "$PYTHON_BIN" "$API_ROOT/scripts/export_openapi_schema.py"

cp "$API_ROOT/tests/contracts/openapi.json" "$REPO_ROOT/fichero/fichero-api-client/Sources/FicheroAPIClient/openapi.json"

cd "$REPO_ROOT/fichero/fichero-api-client"
# Keep output compact while surfacing generation/build signal lines.
swift build 2>&1 | grep -E "error|warning: Schema|Writing data|Build complete" | head -30 || true

echo "✅ Synced backend OpenAPI schema into Swift client package (fichero-api-client)"
