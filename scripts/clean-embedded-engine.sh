#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENGINE_APP="${1:-$ROOT_DIR/fichero-engine/build/engine/macos/app/Fichero Engine.app}"

if [ ! -d "$ENGINE_APP" ]; then
  echo "error: embedded engine bundle not found at $ENGINE_APP" >&2
  exit 1
fi

dsym_count="$(find "$ENGINE_APP" -name '*.dSYM' -prune | wc -l | tr -d ' ')"
if [ "$dsym_count" -eq 0 ]; then
  echo "  Embedded engine cleanup: no .dSYM bundles to remove"
  exit 0
fi

find "$ENGINE_APP" -name '*.dSYM' -prune -exec rm -rf {} +
echo "  Embedded engine cleanup: removed $dsym_count .dSYM bundles"
