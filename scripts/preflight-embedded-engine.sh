#!/usr/bin/env bash
set -euo pipefail

# Ensure a manual Xcode embedded-macOS build has its Briefcase engine input.
# Normal use is a fast no-op; pass --rebuild after changing engine sources.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENGINE_DIR="$ROOT_DIR/fichero-engine"
ENGINE_APP="$ENGINE_DIR/build/engine/macos/app/Fichero Engine.app"

case "${1:-}" in
  "") ;;
  --rebuild) rebuild=true ;;
  --check)
    if [ -d "$ENGINE_APP" ]; then
      echo "Embedded engine ready: $ENGINE_APP"
      exit 0
    fi
    echo "error: embedded engine missing: $ENGINE_APP" >&2
    exit 1
    ;;
  *)
    echo "usage: $0 [--check|--rebuild]" >&2
    exit 2
    ;;
esac

if [ -d "$ENGINE_APP" ] && [ "${rebuild:-false}" = false ]; then
  echo "Embedded engine ready: $ENGINE_APP"
  exit 0
fi

if [ -x "$ENGINE_DIR/.briefcase-venv/bin/briefcase" ]; then
  BRIEFCASE="$ENGINE_DIR/.briefcase-venv/bin/briefcase"
elif [ -x "$ROOT_DIR/.venv/bin/briefcase" ]; then
  BRIEFCASE="$ROOT_DIR/.venv/bin/briefcase"
elif BRIEFCASE="$(command -v briefcase 2>/dev/null)"; then
  :
else
  echo "error: briefcase is not installed; activate the project virtualenv first" >&2
  exit 1
fi

echo "Building embedded engine with Briefcase"
(
  cd "$ENGINE_DIR"
  if [ ! -d "$ENGINE_DIR/build/engine/macos/app" ]; then
    "$BRIEFCASE" create macOS --app engine
  fi
  "$BRIEFCASE" update macOS --app engine
  "$BRIEFCASE" build macOS --app engine
)

if [ ! -x "$ENGINE_APP/Contents/MacOS/Fichero Engine" ]; then
  echo "error: Briefcase did not produce an executable engine at $ENGINE_APP" >&2
  exit 1
fi

echo "Embedded engine ready: $ENGINE_APP"
