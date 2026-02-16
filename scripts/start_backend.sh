#!/bin/bash
#
# Start the Fichero backend with automatic OpenAPI sync.
#
# Usage:
#   ./scripts/start_backend.sh           # Sync OpenAPI, validate, then start (default)
#   ./scripts/start_backend.sh --no-sync # Skip OpenAPI regeneration (faster)
#   ./scripts/start_backend.sh --fast    # Skip sync AND validation (fastest, production)
#
# This script:
#   1. Regenerates OpenAPI spec from Python models (unless --no-sync)
#   2. Validates Python/Swift model sync (unless --fast)
#   3. Starts the FastAPI backend on port 8765
#

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

# Parse arguments - sync is ON by default
SYNC_OPENAPI=true
SKIP_VALIDATION=false

for arg in "$@"; do
    case $arg in
        --no-sync)
            SYNC_OPENAPI=false
            ;;
        --fast)
            SYNC_OPENAPI=false
            SKIP_VALIDATION=true
            ;;
        --help|-h)
            echo "Usage: $0 [--no-sync] [--fast]"
            echo ""
            echo "Options:"
            echo "  --no-sync   Skip OpenAPI regeneration (faster startup)"
            echo "  --fast      Skip sync AND validation (fastest, for production)"
            echo ""
            exit 0
            ;;
    esac
done

# Step 1: Regenerate OpenAPI spec (default behavior)
if [ "$SYNC_OPENAPI" = true ]; then
    echo "🔄 Syncing OpenAPI spec (Python → Swift)..."
    ./scripts/sync_openapi_schema.sh
    echo ""
fi

# Step 2: Validate model sync (unless skipped)
if [ "$SKIP_VALIDATION" = false ]; then
    echo "🔍 Validating Python/Swift model sync..."
    if ! python3 "$SCRIPT_DIR/validate_model_sync.py"; then
        echo ""
        echo "⚠️  Model sync validation failed!"
        echo "   Run './scripts/sync_openapi_schema.sh' to regenerate OpenAPI spec."
        echo "   Or run with --no-check to skip validation."
        exit 1
    fi
    echo ""
fi

# Step 3: Start the backend
echo "🚀 Starting Fichero backend on port 8765..."
echo ""

# Enable model validation in Python startup as well (logs warning if out of sync)
export FICHERO_VALIDATE_MODELS=1

PYTHONPATH=fichero-api/src .venv/bin/uvicorn fichero.api.main:app --port 8765 --reload
