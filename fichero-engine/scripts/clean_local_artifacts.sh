#!/bin/bash
set -euo pipefail

# Remove local generated/build artifacts across the repo.
# Safe to run repeatedly; only deletes generated paths.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

TARGETS=(
  "$ROOT_DIR/.build"
  "$ROOT_DIR/build"
  "$ROOT_DIR/dist"
  "$ROOT_DIR/logs"
  "$ROOT_DIR/.pytest_cache"
  "$ROOT_DIR/fichero/derived_data"
  "$ROOT_DIR/fichero/fichero-api-client/.build"
)

echo "🧹 Cleaning local generated artifacts..."
for path in "${TARGETS[@]}"; do
  if [ -e "$path" ]; then
    echo "  - removing $path"
    rm -rf "$path"
  fi
done
echo "✅ Cleanup complete"
