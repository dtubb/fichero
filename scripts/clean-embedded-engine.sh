#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENGINE_APP="${1:-$ROOT_DIR/fichero-engine/build/engine/macos/app/Fichero Engine.app}"
SIGN_IDENTITY="${FICHERO_CODESIGN_IDENTITY:-}"
REQUIRED_AUTHORITY="${FICHERO_REQUIRED_CODESIGN_AUTHORITY:-}"
PRUNE_PACKAGES=(
  "PyObjCTest"
)

if [ ! -d "$ENGINE_APP" ]; then
  echo "error: embedded engine bundle not found at $ENGINE_APP" >&2
  exit 1
fi

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
