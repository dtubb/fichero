#!/bin/bash
set -e

# Start backend with optional OpenAPI sync/validation.
# Run from repo root: ./fichero-api/scripts/start_backend.sh [--no-sync|--fast]

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
API_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$API_ROOT/.." && pwd)"

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
  python3 "$API_ROOT/scripts/validate_model_sync.py"
fi

export FICHERO_VALIDATE_MODELS=1
PYTHONPATH="$API_ROOT/src" "$REPO_ROOT/.venv/bin/uvicorn" fichero.api.main:app --port 8765 --reload
