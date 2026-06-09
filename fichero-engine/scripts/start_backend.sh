#!/bin/bash
set -e

# Start backend with optional OpenAPI sync/validation.
# Run from repo root: ./fichero-engine/scripts/start_backend.sh [--no-sync|--fast]

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
API_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$API_ROOT/.." && pwd)"

if [ -n "${FICHERO_PYTHON_BIN:-}" ] && [ -x "${FICHERO_PYTHON_BIN}" ]; then
  PYTHON_BIN="${FICHERO_PYTHON_BIN}"
elif [ -x "$API_ROOT/.venv/bin/python" ]; then
  # Prefer project-local venv over any externally activated environment.
  PYTHON_BIN="$API_ROOT/.venv/bin/python"
elif [ -x "$REPO_ROOT/.venv/bin/python" ]; then
  PYTHON_BIN="$REPO_ROOT/.venv/bin/python"
elif [ -n "${VIRTUAL_ENV:-}" ] && [ -x "${VIRTUAL_ENV}/bin/python" ]; then
  PYTHON_BIN="${VIRTUAL_ENV}/bin/python"
else
  PYTHON_BIN="python3"
fi

SYNC_OPENAPI=true
SKIP_VALIDATION=false

for arg in "$@"; do
  case $arg in
    --no-sync) SYNC_OPENAPI=false ;;
    --fast) SYNC_OPENAPI=false; SKIP_VALIDATION=true ;;
    --help|-h)
      echo "Usage: $0 [--no-sync] [--fast]"
      exit 0
      ;;
  esac
done

if [ "$SYNC_OPENAPI" = true ]; then
  "$API_ROOT/scripts/sync_openapi_schema.sh"
fi

if [ "$SKIP_VALIDATION" = false ]; then
  "$PYTHON_BIN" "$API_ROOT/scripts/validate_model_sync.py"
fi

export FICHERO_VALIDATE_MODELS=1
# Scope --reload to the engine source ONLY. A bare --reload watches the CWD (repo
# root), which includes agent worktrees under .claude/worktrees/ — every worker
# edit then triggers a reload storm + RAM blowup. --reload-dir fixes that.
PYTHONPATH="$API_ROOT/src" "$PYTHON_BIN" -m uvicorn fichero.api.main:app --port 8765 \
  --reload --reload-dir "$API_ROOT/src"
