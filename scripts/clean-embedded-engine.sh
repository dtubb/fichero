#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CHECK_VERSION=false
if [ "${1:-}" = "--check-version" ]; then
  CHECK_VERSION=true
  shift
fi
ENGINE_APP="${1:-$ROOT_DIR/fichero-server/build/server/macos/app/Fichero Server.app}"
SIGN_IDENTITY="${FICHERO_CODESIGN_IDENTITY:-}"
REQUIRED_AUTHORITY="${FICHERO_REQUIRED_CODESIGN_AUTHORITY:-}"
PRUNE_PACKAGES=(
  "PyObjCTest"
)

if [ ! -d "$ENGINE_APP" ]; then
  echo "error: embedded engine bundle not found at $ENGINE_APP" >&2
  exit 1
fi

EXPECTED_VERSION="$(grep -m1 '^version = "' "$ROOT_DIR/fichero-server/pyproject.toml" | sed -E 's/^version = "([^"]+)".*/\1/')"
BUNDLE_VERSION="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$ENGINE_APP/Contents/Info.plist" 2>/dev/null || true)"
METADATA_PATH="$(find "$ENGINE_APP/Contents/Resources/app" -maxdepth 2 -path '*/server-*.dist-info/METADATA' -print -quit 2>/dev/null || true)"
PACKAGE_VERSION="$(awk -F': ' '$1 == "Version" { print $2; exit }' "$METADATA_PATH" 2>/dev/null || true)"
if [ -z "$EXPECTED_VERSION" ] || [ "$BUNDLE_VERSION" != "$EXPECTED_VERSION" ] || [ "$PACKAGE_VERSION" != "$EXPECTED_VERSION" ]; then
  echo "error: embedded engine version mismatch (expected=$EXPECTED_VERSION bundle=$BUNDLE_VERSION package=$PACKAGE_VERSION)" >&2
  exit 1
fi
echo "  Embedded engine version: $EXPECTED_VERSION"
[ "$CHECK_VERSION" = false ] || exit 0

remove_tree_if_present() {
  local path="$1"
  if [ -e "$path" ]; then
    rm -rf "$path"
    return 0
  fi
  return 1
}

sign_target() {
  local target="$1"
  codesign --force --sign "$SIGN_IDENTITY" --timestamp=none "$target" >/dev/null 2>&1
}

verify_authority() {
  local target="$1"
  codesign -dv --verbose=4 "$target" 2>&1 | grep -Fq "Authority=$REQUIRED_AUTHORITY"
}

dsym_count="$(find "$ENGINE_APP" -name '*.dSYM' -prune | wc -l | tr -d ' ')"
if [ "$dsym_count" -gt 0 ]; then
  find "$ENGINE_APP" -name '*.dSYM' -prune -exec rm -rf {} +
fi

removed_packages=0
for package in "${PRUNE_PACKAGES[@]}"; do
  if remove_tree_if_present "$ENGINE_APP/Contents/Resources/app_packages/$package"; then
    removed_packages=$((removed_packages + 1))
  fi
done

appledouble_count="$(find "$ENGINE_APP" -name '._*' | wc -l | tr -d ' ')"
if [ "$appledouble_count" -gt 0 ]; then
  find "$ENGINE_APP" -name '._*' -delete
fi

echo "  Embedded engine cleanup: removed $dsym_count .dSYM bundles, pruned $removed_packages test packages, deleted $appledouble_count AppleDouble files"

bad_bundle_ids="$(mktemp)"
find "$ENGINE_APP" -name Info.plist -print0 | while IFS= read -r -d '' plist; do
  bundle_id=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$plist" 2>/dev/null || true)
  if [[ "$bundle_id" == com.apple.* ]]; then
    printf '%s\t%s\n' "$bundle_id" "$plist"
  fi
done > "$bad_bundle_ids"
if [ -s "$bad_bundle_ids" ]; then
  echo "error: embedded engine still contains reserved com.apple.* bundle identifiers:" >&2
  cat "$bad_bundle_ids" >&2
  rm -f "$bad_bundle_ids"
  exit 1
fi
rm -f "$bad_bundle_ids"
echo "  Embedded engine cleanup: no reserved com.apple.* bundle identifiers found"

# Bytecode magic is per MINOR version: a .pyc compiled by the wrong minor is
# silently ignored by the runtime, which recompiles on first launch — the #3940
# slow start. So detect the BUNDLE's own CPython minor and compile with EXACTLY
# that (the bundle has shipped both 3.12 and 3.13). This precompile is an
# OPTIMISATION, not a correctness requirement — never fail the build on it: a
# missing/wrong .pyc only costs a one-time runtime recompile.
BUNDLE_PYVER=""
for v in "$ENGINE_APP/Contents/Frameworks/Python.framework/Versions/"3.[0-9]*; do
  [ -d "$v" ] || continue
  BUNDLE_PYVER=$(basename "$v"); break
done

ENGINE_PYTHON=""
if [ -n "$BUNDLE_PYVER" ]; then
  PYMAJ="${BUNDLE_PYVER%%.*}"; PYMIN="${BUNDLE_PYVER#*.}"
  for candidate in \
    "$ENGINE_APP/Contents/Frameworks/Python.framework/Versions/$BUNDLE_PYVER/bin/python$BUNDLE_PYVER" \
    "${FICHERO_PYTHON_BIN:-}" \
    "$(command -v "python$BUNDLE_PYVER" 2>/dev/null || true)" \
    "/opt/homebrew/bin/python$BUNDLE_PYVER" \
    "/opt/homebrew/opt/python@$BUNDLE_PYVER/bin/python$BUNDLE_PYVER" \
    "/usr/local/bin/python$BUNDLE_PYVER" \
    "/Library/Frameworks/Python.framework/Versions/$BUNDLE_PYVER/bin/python$BUNDLE_PYVER"; do
    [ -n "$candidate" ] && [ -x "$candidate" ] || continue
    if "$candidate" -c "import sys; raise SystemExit(sys.version_info[:2] != ($PYMAJ, $PYMIN))" 2>/dev/null; then
      ENGINE_PYTHON="$candidate"; break
    fi
  done
fi

if [ -n "$ENGINE_PYTHON" ]; then
  echo "  Embedded engine: precompiling bytecode with $ENGINE_PYTHON (bundle Python ${BUNDLE_PYVER:-unknown})"
  if "$ENGINE_PYTHON" -m compileall -q -j 8 \
       "$ENGINE_APP/Contents/Resources/app" \
       "$ENGINE_APP/Contents/Resources/app_packages"; then
    pyc_count="$(find "$ENGINE_APP/Contents/Resources" -name '*.pyc' 2>/dev/null | wc -l | tr -d ' ')"
    echo "  Embedded engine cleanup: precompiled $pyc_count Python files"
  else
    echo "  warning: bytecode precompile reported errors; runtime will recompile as needed (non-fatal)" >&2
  fi
else
  echo "  warning: no python${BUNDLE_PYVER:-3.x} interpreter found to precompile bytecode — the engine will compile on first launch (#3940 slow start)." >&2
  echo "           Install a matching python (e.g. 'brew install python@${BUNDLE_PYVER:-3.13}') or make briefcase produce the pyproject-pinned 3.12." >&2
fi

if [ -n "$SIGN_IDENTITY" ]; then
  macho_list="$(mktemp)"
  find "$ENGINE_APP" -type f -exec file {} + 2>/dev/null \
    | awk -F': ' '/Mach-O/ && !/\(for architecture/ {print $1}' \
    | sort -u > "$macho_list"
  macho_count=$(wc -l < "$macho_list" | tr -d ' ')
  echo "  Embedded engine cleanup: signing $macho_count Mach-O files with $SIGN_IDENTITY"
  while IFS= read -r macho; do
    sign_target "$macho"
  done < "$macho_list"
  rm -f "$macho_list"

  bundle_list="$(mktemp)"
  find "$ENGINE_APP" -type d \( -name '*.framework' -o -name '*.app' -o -name '*.xpc' \) \
    | awk '{print length, $0}' | sort -rn | cut -d' ' -f2- > "$bundle_list"
  while IFS= read -r bundle; do
    sign_target "$bundle"
  done < "$bundle_list"
  rm -f "$bundle_list"

  if ! codesign --verify --deep --strict "$ENGINE_APP" >/dev/null 2>&1; then
    echo "error: embedded engine codesign verification failed after re-sign" >&2
    exit 1
  fi
  echo "  Embedded engine cleanup: re-signed and verified bundle"
fi

if [ -n "$REQUIRED_AUTHORITY" ]; then
  artifact_list="$(mktemp)"
  find "$ENGINE_APP" -type f \( -name '*.so' -o -name '*.dylib' \) | sort > "$artifact_list"
  bad_signatures=()
  while IFS= read -r artifact; do
    if ! (verify_authority "$artifact"); then
      bad_signatures+=("$artifact")
    fi
  done < "$artifact_list"
  rm -f "$artifact_list"

  if [ "${#bad_signatures[@]}" -gt 0 ]; then
    echo "error: embedded engine has nested libraries not signed by '$REQUIRED_AUTHORITY':" >&2
    printf '%s\n' "${bad_signatures[@]}" >&2
    exit 1
  fi
  echo "  Embedded engine cleanup: all nested .so/.dylib files signed by $REQUIRED_AUTHORITY"
fi
