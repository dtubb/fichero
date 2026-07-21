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
  --check) check_only=true ;;
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
  if ! "$ROOT_DIR/scripts/clean-embedded-engine.sh" --check-version "$ENGINE_APP"; then
    echo "Embedded engine has STALE version metadata — rebuilding"
    return 1
  fi
  # Content, not mtime: git checkouts/merges bump mtimes without changing bytes.
  # The App Store signer changes fm-bridge's signature bytes, so compare its
  # stable Mach-O UUID separately instead of forcing a rebuild after signing.
  local source_bridge="$ENGINE_DIR/src/fichero/resources/bin/fm-bridge"
  local staged_bridge="$ENGINE_APP/Contents/Resources/app/fichero/resources/bin/fm-bridge"
  if ! diff -rq --exclude=__pycache__ --exclude=.DS_Store --exclude=fm-bridge \
      "$ENGINE_DIR/src/fichero" "$ENGINE_APP/Contents/Resources/app/fichero" >/dev/null 2>&1 \
      || [ ! -f "$source_bridge" ] || [ ! -f "$staged_bridge" ] \
      || [ "$(dwarfdump --uuid "$source_bridge" | awk 'NR == 1 { print $2 }')" \
           != "$(dwarfdump --uuid "$staged_bridge" | awk 'NR == 1 { print $2 }')" ]; then
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

if [ "${check_only:-false}" = true ]; then
  if engine_is_current; then
    echo "Embedded engine ready: $ENGINE_APP"
    exit 0
  fi
  echo "error: embedded engine is missing or stale: $ENGINE_APP" >&2
  exit 1
fi

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

# Briefcase update refreshes code and dependencies, but not the generated app
# template (including Info.plist). Recreate only when the stamped version has
# changed; otherwise keep the much faster update/build path.
if [ -d "$ENGINE_APP" ] && ! "$ROOT_DIR/scripts/clean-embedded-engine.sh" --check-version "$ENGINE_APP" >/dev/null 2>&1; then
  echo "Recreating Briefcase app template for the stamped engine version"
  # rm -rf can hit a transient "Directory not empty" race when a concurrent
  # indexer or Briefcase subprocess has a handle open in the Python.xcframework
  # tree. A 1s pause lets the handle release; retry before treating it as a real
  # failure (a genuinely stuck file is rare, and aborting a 40-min release on a
  # one-off FS race is the kind of babysit this script exists to avoid).
  _rm_ok=0
  for _ in 1 2 3; do
    if rm -rf "$ENGINE_DIR/build/engine/macos/app"; then _rm_ok=1; break; fi
    [ "$_" = 3 ] || sleep 1
  done
  [ "$_rm_ok" = 1 ] || { echo "error: could not remove $ENGINE_DIR/build/engine/macos/app after 3 tries" >&2; exit 1; }
fi
(
  cd "$ENGINE_DIR"
  # When this preflight runs as an xcodebuild BUILD PHASE (a direct
  # `xcodebuild -scheme "Fichero (App Store)"`, vs release-all.sh which runs it
  # standalone), xcodebuild injects SWIFT_* build settings into the environment.
  # Briefcase's dylib arch-detection subprocess then emits
  # "Warning: unknown environment variable SWIFT_DEBUG_INFORMATION_FORMAT" onto
  # stdout, which Briefcase mis-parses as arch output → "Unable to determine
  # architectures in …/libmupdf.dylib". Briefcase's own Python build needs none
  # of these, so clear them.
  for _v in $(env | sed -n 's/^\(SWIFT_[A-Z0-9_]*\)=.*/\1/p'); do unset "$_v"; done
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
