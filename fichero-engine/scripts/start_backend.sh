#!/bin/bash
set -e

# Start backend with optional OpenAPI sync/validation.
# Run from repo root: ./fichero-engine/scripts/start_backend.sh [--no-sync|--fast|--reload]

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
RELOAD=false
UVICORN_SSL_ARGS=()

for arg in "$@"; do
  case $arg in
    --no-sync) SYNC_OPENAPI=false ;;
    --fast) SYNC_OPENAPI=false; SKIP_VALIDATION=true ;;
    --reload) RELOAD=true ;;
    --help|-h)
      echo "Usage: $0 [--no-sync] [--fast] [--reload]"
      echo
      echo "Default starts uvicorn without reload so the real app DuckDB is opened"
      echo "by one process only. Use --reload only with an isolated/test database."
      exit 0
      ;;
  esac
done

if [ -n "${FICHERO_TLS_CERTFILE:-}" ] || [ -n "${FICHERO_TLS_KEYFILE:-}" ]; then
  if [ -z "${FICHERO_TLS_CERTFILE:-}" ] || [ -z "${FICHERO_TLS_KEYFILE:-}" ]; then
    echo "FICHERO_TLS_CERTFILE and FICHERO_TLS_KEYFILE must both be set."
    exit 1
  fi
  UVICORN_SSL_ARGS+=(--ssl-certfile "$FICHERO_TLS_CERTFILE" --ssl-keyfile "$FICHERO_TLS_KEYFILE")
fi

UVICORN_BIND_HOST="$(
  PYTHONPATH="$API_ROOT/src" "$PYTHON_BIN" - <<'PY'
from fichero.bind_host import resolve_bind_host

print(resolve_bind_host())
PY
)"

if [ "$SYNC_OPENAPI" = true ]; then
  "$API_ROOT/scripts/sync_openapi_schema.sh"
fi

if [ "$SKIP_VALIDATION" = false ]; then
  "$PYTHON_BIN" "$API_ROOT/scripts/validate_model_sync.py"
fi

export FICHERO_VALIDATE_MODELS=1
if [ "$RELOAD" = true ]; then
  # Scope --reload to the engine source ONLY. A bare --reload watches the CWD
  # (repo root), which includes agent worktrees under .claude/worktrees/ — every
  # worker edit then triggers a reload storm + RAM blowup. --reload-dir fixes
  # that. Do not use reload against the real app DuckDB; the reloader parent and
  # child can contend for the same single-process DuckDB lock during app import.
  PYTHONPATH="$API_ROOT/src" "$PYTHON_BIN" -m uvicorn fichero.api.main:app --port 8765 \
    --reload --reload-dir "$API_ROOT/src" --host "$UVICORN_BIND_HOST" "${UVICORN_SSL_ARGS[@]}"
else
  PYTHONPATH="$API_ROOT/src" "$PYTHON_BIN" -m uvicorn fichero.api.main:app --port 8765 \
    --host "$UVICORN_BIND_HOST" "${UVICORN_SSL_ARGS[@]}"
fi
