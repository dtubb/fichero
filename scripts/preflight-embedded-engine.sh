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

# "Ready" must mean CURRENT, not merely present. This used to be `[ -d
# "$ENGINE_APP" ]` alone: a staging directory created once was "ready" forever,
# so the script printed success and re-staged nothing. That is the mechanism
# behind #3956 — an engine staged at 14:21 shipped inside an app built at 22:02,
# eight hours stale, past a fully green test suite. Xcode's Embed phase is a
# plain `cp -R` of whatever is here, and `briefcase build`/`package` do not
# re-copy source (only `briefcase update` does), so nothing else would catch it.
#
# Now: present AND staged source byte-identical to src AND bytecode
# present. Any of those failing falls through to a real rebuild.
engine_is_current() {
  [ -d "$ENGINE_APP" ] || return 1
  local staged="$ENGINE_APP/Contents/Resources/app/fichero/api/main.py"
  [ -f "$staged" ] || return 1
  # Content, not mtime: git checkouts/merges bump mtimes without changing bytes,
  if ! diff -rq --exclude=__pycache__ "$ENGINE_DIR/src/fichero" "$ENGINE_APP/Contents/Resources/app/fichero" >/dev/null 2>&1; then
    echo "Embedded engine is STALE (engine sources are newer than the staged copy) — rebuilding"
    return 1
  fi
  # A staged engine with no bytecode is a 3-5x slower engine (#3940).
  if [ -z "$(find "$ENGINE_APP/Contents/Resources" -name '*.pyc' -print -quit 2>/dev/null)" ]; then
    echo "Embedded engine has NO bytecode — precompiling"
    "$ROOT_DIR/scripts/clean-embedded-engine.sh" "$ENGINE_APP"
  fi
  return 0
}

if [ "${rebuild:-false}" = false ] && engine_is_current; then
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

# Briefcase ships .py with NO .pyc, so every import pays a full compile. This is
# not a micro-optimisation — measured on this exact bundle, same binary, only
# bytecode differing (#3940):
#
#              0 .pyc      14,530 .pyc
#   cold →     12.81s        4.37s      (-66%)
#   warm →      3.97s        0.80s      (-80%)
#
# clean-embedded-engine.sh already does the compileall AND hard-fails on zero
# .pyc; it simply was never called from here, so only build-release.sh got the
# fast engine and every preflight-built engine was 3-5x slower. Whether you got
# bytecode depended on which script you happened to run.
"$ROOT_DIR/scripts/clean-embedded-engine.sh" "$ENGINE_APP"

echo "Embedded engine ready: $ENGINE_APP"
