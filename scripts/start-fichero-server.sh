#!/usr/bin/env bash
set -euo pipefail

# Start the Fichero backend in development mode (hot-reload).
# Thin wrapper around fichero-server/scripts/start_fichero_server.sh.
# Usage: scripts/start-fichero-server.sh [--no-sync] [--fast]

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec "$ROOT_DIR/fichero-server/scripts/start_fichero_server.sh" "$@"
