#!/bin/bash
set -e

# Sync OpenAPI schema from fichero-engine into the Swift package imported by the SwiftUI app.
# Run from repo root: ./fichero-engine/scripts/sync_openapi_schema.sh
#
# INTERPRETER: set FICHERO_PYTHON_BIN to the venv that has the engine
# editable-installed, or activate it first. Otherwise the fallback chain below
# may pick a partially-installed env, whose placeholder version silently
# rewrites info.version across all four committed openapi.json copies (#4199):
#
#   FICHERO_PYTHON_BIN=/path/to/.venv/bin/python ./fichero-engine/scripts/sync_openapi_schema.sh
#
# A backwards version move now ABORTS the sync before anything is copied.

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  sed -n '4,15p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
  exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$API_ROOT/.." && pwd)"

if [ -n "${FICHERO_PYTHON_BIN:-}" ] && [ -x "${FICHERO_PYTHON_BIN}" ]; then
  PYTHON_BIN="${FICHERO_PYTHON_BIN}"
elif [ -n "${VIRTUAL_ENV:-}" ] && [ -x "${VIRTUAL_ENV}/bin/python" ]; then
  PYTHON_BIN="${VIRTUAL_ENV}/bin/python"
elif [ -x "$API_ROOT/.venv/bin/python" ]; then
  # #4199: this env is routinely a partial install whose placeholder version
  # poisons info.version. Kept in the chain (it is correct on some machines)
  # but never silently — the version guard below is the actual gate.
  PYTHON_BIN="$API_ROOT/.venv/bin/python"
  echo "⚠️  Using fichero-engine/.venv — if the engine is not installed there," >&2
  echo "   set FICHERO_PYTHON_BIN to the venv holding the editable install." >&2
elif [ -x "$REPO_ROOT/.venv/bin/python" ]; then
  PYTHON_BIN="$REPO_ROOT/.venv/bin/python"
else
  PYTHON_BIN="python3"
fi

cd "$REPO_ROOT"

NEW_SCHEMA="$API_ROOT/tests/contracts/openapi.json"

# The export rewrites NEW_SCHEMA in place, so the committed version has to be
# captured BEFORE it runs — and restored if the guard trips, or the abort
# would leave behind exactly the corruption it exists to prevent.
PREV_SCHEMA=""
if [ -f "$NEW_SCHEMA" ]; then
  PREV_SCHEMA="$(mktemp -t openapi-prev)"
  cp "$NEW_SCHEMA" "$PREV_SCHEMA"
  trap 'rm -f "$PREV_SCHEMA"' EXIT
fi

PYTHONPATH="$API_ROOT/src" FICHERO_FEATURE_TIER=dev "$PYTHON_BIN" "$API_ROOT/scripts/export_openapi_schema.py"

if [ -n "$PREV_SCHEMA" ]; then
  if ! "$PYTHON_BIN" "$SCRIPT_DIR/check_openapi_version_regression.py" \
      --previous "$PREV_SCHEMA" --current "$NEW_SCHEMA"; then
    cp "$PREV_SCHEMA" "$NEW_SCHEMA"
    echo "↩︎  Restored the previous schema; nothing was copied downstream." >&2
    exit 1
  fi
fi

PYTHONPATH="$API_ROOT/src" "$PYTHON_BIN" "$API_ROOT/scripts/generate_openapi_cli.py"
DEST_SCHEMA="$REPO_ROOT/fichero/fichero-api-client/Sources/FicheroAPIClient/openapi.json"
DOCS_SCHEMA="$REPO_ROOT/docs/contributor/api-reference/openapi.json"

# Keep the PUBLISHED API-reference schema fresh, independently of the Swift
# fast path below. The docs copy has no generator/build step, so nothing else
# refreshes it — and the Swift bindings can be current while it has silently
# drifted (it was ~11 KB stale before this). Do it unconditionally, before the
# fast-path exit, so a no-op Swift sync still refreshes the docs copy.
# ponytail: plain cmp+cp, no build.
if [ ! -f "$DOCS_SCHEMA" ] || ! cmp -s "$NEW_SCHEMA" "$DOCS_SCHEMA"; then
  cp "$NEW_SCHEMA" "$DOCS_SCHEMA"
  echo "↻ Refreshed published API-reference schema (docs/contributor/api-reference/openapi.json)"
fi

# Fast path: if the freshly-exported schema is byte-identical to what the
# Swift package already has, the OpenAPIGenerator output is current too —
# no copy, no swift build. Saves ~2-3 minutes on the common no-op case.
# Slow path runs only when the engine routes actually changed.
#
# This makes the sync safe to run on EVERY build (no --skip-openapi-sync
# flag needed), eliminating the silent-stale-bindings class of bug that
# 31fc4141 and the page_content decode bug (today) both stemmed from.
dest_changed=0
if [ ! -f "$DEST_SCHEMA" ] || ! cmp -s "$NEW_SCHEMA" "$DEST_SCHEMA"; then
  dest_changed=1
fi

if [ "$dest_changed" -eq 0 ]; then
  echo "✅ OpenAPI schema unchanged — Swift bindings already current (fast path)"
  exit 0
fi

if [ "$dest_changed" -eq 1 ]; then
  echo "↻ OpenAPI schema changed — regenerating Swift + Python bindings"
  cp "$NEW_SCHEMA" "$DEST_SCHEMA"
fi

cd "$REPO_ROOT/fichero/fichero-api-client"
# Keep output compact while surfacing generation/build signal lines.
swift build 2>&1 | grep -E "error|warning: Schema|Writing data|Build complete" | head -30 || true

echo "✅ Synced backend OpenAPI schema into Swift client package (fichero-api-client)"
