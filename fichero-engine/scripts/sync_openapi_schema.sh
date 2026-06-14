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
PYTHONPATH="$API_ROOT/src" "$PYTHON_BIN" "$API_ROOT/scripts/generate_openapi_cli.py"

NEW_SCHEMA="$API_ROOT/tests/contracts/openapi.json"
DEST_SCHEMA="$REPO_ROOT/fichero/fichero-api-client/Sources/FicheroAPIClient/openapi.json"
LEGACY_SCHEMA="$REPO_ROOT/fichero/fichero-api-client/Sources/openapi.json"

# Fast path: if the freshly-exported schema is byte-identical to what the
# Swift package already has, the OpenAPIGenerator output is current too —
# no copy, no swift build. Saves ~2-3 minutes on the common no-op case.
# Slow path runs only when the engine routes actually changed.
#
# This makes the sync safe to run on EVERY build (no --skip-openapi-sync
# flag needed), eliminating the silent-stale-bindings class of bug that
# 31fc4141 and the page_content decode bug (today) both stemmed from.
dest_changed=0
legacy_changed=0
if [ ! -f "$DEST_SCHEMA" ] || ! cmp -s "$NEW_SCHEMA" "$DEST_SCHEMA"; then
  dest_changed=1
fi
if [ -f "$LEGACY_SCHEMA" ] && ! cmp -s "$NEW_SCHEMA" "$LEGACY_SCHEMA"; then
  legacy_changed=1
fi

if [ "$dest_changed" -eq 0 ] && [ "$legacy_changed" -eq 0 ]; then
  echo "✅ OpenAPI schema unchanged — Swift bindings already current (fast path)"
  exit 0
fi

if [ "$dest_changed" -eq 1 ]; then
  echo "↻ OpenAPI schema changed — regenerating Swift + Python bindings"
  cp "$NEW_SCHEMA" "$DEST_SCHEMA"
else
  echo "↻ Legacy OpenAPI schema copy changed — syncing without Swift rebuild"
fi

if [ "$legacy_changed" -eq 1 ]; then
  cp "$NEW_SCHEMA" "$LEGACY_SCHEMA"
fi

if [ "$dest_changed" -eq 0 ]; then
  echo "✅ Synced legacy OpenAPI schema copy"
  exit 0
fi

cd "$REPO_ROOT/fichero/fichero-api-client"
# Keep output compact while surfacing generation/build signal lines.
swift build 2>&1 | grep -E "error|warning: Schema|Writing data|Build complete" | head -30 || true

echo "✅ Synced backend OpenAPI schema into Swift client package (fichero-api-client)"
