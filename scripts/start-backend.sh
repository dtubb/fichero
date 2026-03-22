#!/usr/bin/env bash
set -euo pipefail

# Start the Fichero backend in development mode (hot-reload).
# Thin wrapper around fichero-api/scripts/start_backend.sh.
# Usage: scripts/start-backend.sh [--no-sync] [--fast]

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec "$ROOT_DIR/fichero-api/scripts/start_backend.sh" "$@"
