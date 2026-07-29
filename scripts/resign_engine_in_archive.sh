#!/bin/bash
#
# resign_engine_in_archive.sh — re-sign the embedded Briefcase engine in a
# built .xcarchive (or a loose .app) with the App Store distribution identity
# and the two-key engine entitlements, BEFORE `xcodebuild -exportArchive`.
#
# Why this exists (#3952, P0, TestFlight launch blocker):
#
#   The engine is embedded by a shell-script build phase ("Embed Fichero
#   Engine"), not by the standard "Copy Files (Embed Helper Tools)" phase that
#   Xcode recognises. During `xcodebuild -exportArchive -method
#   app-store-connect`, Xcode re-signs nested code for TestFlight. A nested
#   helper that Xcode does not recognise as a "helper tool" can end up re-signed
#   with the MAIN APP's distribution entitlements, which for TestFlight include
#   `com.apple.security.get-task-allow = true`. `get-task-allow` is incompatible
#   with `com.apple.security.inherit` (Apple's Entitlement Key Reference: any
#   other App Sandbox key alongside `inherit` makes the system abort the
#   child), so the engine child is killed on launch and the app renders
#   nothing.
#
#   The build-time phase already signs the engine with exactly the two keys,
#   but with the "Apple Development" identity (`EXPANDED_CODE_SIGN_IDENTITY` at
#   archive time). The export then re-signs it with the distribution identity.
#   By re-signing the engine with the DISTRIBUTION identity + the two-key
#   entitlements BEFORE the export, the engine enters the export already
#   distribution-signed with clean entitlements, and the export's re-sign
#   preserves them (Apple's "Embedding a command-line tool in a sandboxed app"
#   doc: the re-signed tool's entitlements end up as exactly app-sandbox +
#   inherit, no get-task-allow).
#
#   This is the App-Store/TestFlight entitlement path ONLY. The DMG engine is
#   not sandboxed (no `inherit`), so `get-task-allow` on it is harmless, and
#   this script is never called from the DMG lane.
#
# Usage:
#   scripts/resign_engine_in_archive.sh <archive-or-app> <identity> <entitlements>
#
# Exits non-zero if the engine cannot be found, signing fails, or the final
# signature carries any key other than app-sandbox + inherit (get-task-allow in
# particular). Read-only with respect to the outer app — it only re-signs the
# nested engine bundle and its Mach-O contents.

set -euo pipefail

if [ "$#" -ne 3 ]; then
  echo "usage: $0 <path to Fichero.app or Fichero.xcarchive> <signing identity> <engine entitlements>" >&2
  exit 2
fi

TARGET="$1"
IDENTITY="$2"
ENGINE_ENTITLEMENTS="$3"

if [ ! -e "$TARGET" ]; then
  echo "error: not found: $TARGET" >&2
  exit 2
fi

# Accept an .xcarchive and resolve the .app inside it.
if [ -d "$TARGET" ] && [ "${TARGET##*.}" = "xcarchive" ]; then
  APP="$(find "$TARGET/Products/Applications" -maxdepth 1 -name '*.app' | head -1)"
  if [ -z "$APP" ]; then
    echo "error: no .app inside $TARGET" >&2
    exit 2
  fi
else
  APP="$TARGET"
fi

if [ ! -d "$APP" ]; then
  echo "error: not a bundle: $APP" >&2
  exit 2
fi

# Resolve to a physical path — archive products can sit behind a symlink, and
# `find` does not descend into a symlinked starting point (the R2 lesson,
# validate_mas_bundle.sh).
APP="$(cd "$APP" && pwd -P)"
ENGINE_DST="$APP/Contents/Helpers/Fichero Server.app"

if [ ! -d "$ENGINE_DST" ]; then
  echo "error: no embedded engine at: $ENGINE_DST" >&2
  echo "       (the MAS embed phase places it in Contents/Helpers — Contents/Resources is invalid)" >&2
  exit 1
fi

if [ ! -f "$ENGINE_ENTITLEMENTS" ]; then
  echo "error: engine entitlements not found: $ENGINE_ENTITLEMENTS" >&2
  exit 1
fi

# The two-key rule is the whole point. Refuse to sign with anything else.
# PlistBuddy prints the dictionary root as `Dict {`; only entitlement identifiers
# followed by `=` are keys.
PLISTBUDDY="${PLISTBUDDY:-/usr/libexec/PlistBuddy}"
ENT_KEYS="$("$PLISTBUDDY" -c "Print" "$ENGINE_ENTITLEMENTS" 2>/dev/null | awk '/^[[:space:]]*com\.apple\.[[:alnum:].-]+[[:space:]]*=/ {print $1}' | sort -u || true)"
EXPECTED_ENT_KEYS=$'com.apple.security.app-sandbox\ncom.apple.security.inherit'
if [ "$ENT_KEYS" != "$EXPECTED_ENT_KEYS" ]; then
  echo "error: $ENGINE_ENTITLEMENTS must hold exactly app-sandbox + inherit:" >&2
  printf '%s\n' "$ENT_KEYS" | sed 's/^/      /' >&2
  exit 1
fi

echo "Re-signing embedded engine for TestFlight/App Store distribution:"
echo "  app bundle: $APP"
echo "  engine:     $ENGINE_DST"
echo "  identity:   $IDENTITY"
echo "  entitlements: $ENGINE_ENTITLEMENTS"

# Sign inside-out, mirroring the MAS embed phase. Libraries take no entitlements
# and sign plain; executables and executable bundles (.app/.xpc) carry the
# two-key sandbox set. Frameworks sign plain.
is_macho_executable() {
  file -b "$1" 2>/dev/null | grep -q "Mach-O.*executable"
}

sign_mas() {
  local target="$1"
  case "$target" in
    *.framework)
      codesign --force --sign "$IDENTITY" "$target" >/dev/null 2>&1
      return $?
      ;;
  esac
  if [ -d "$target" ] || is_macho_executable "$target"; then
    codesign --force --sign "$IDENTITY" --entitlements "$ENGINE_ENTITLEMENTS" "$target" >/dev/null 2>&1
  else
    codesign --force --sign "$IDENTITY" "$target" >/dev/null 2>&1
  fi
}

# Mach-Os first.
macho_list="$(mktemp)"
find "$ENGINE_DST" -type f -exec file {} + 2>/dev/null \
  | awk -F': ' '/Mach-O/ && !/for architecture/ {print $1}' | sort -u > "$macho_list"
echo "  signing $(wc -l < "$macho_list" | tr -d ' ') Mach-O binaries in the engine"

sign_fails=0
while IFS= read -r macho; do
  if ! sign_mas "$macho"; then
    echo "  error: failed to sign Mach-O: $macho" >&2
    sign_fails=$((sign_fails + 1))
  fi
done < "$macho_list"
rm -f "$macho_list"
if [ "$sign_fails" -gt 0 ]; then
  echo "error: $sign_fails Mach-O binaries failed to re-sign" >&2
  exit 1
fi

# Re-seal bundles innermost-first so a parent's seal hashes a correct child.
bundle_list="$(mktemp)"
find "$ENGINE_DST" -type d -name '*.app' -o -type d -name '*.framework' -o -type d -name '*.xpc' > "$bundle_list.raw"
awk '{print length, $0}' "$bundle_list.raw" | sort -rn | cut -d' ' -f2- > "$bundle_list"
rm -f "$bundle_list.raw"
bundle_fails=0
while IFS= read -r bundle; do
  if ! sign_mas "$bundle"; then
    echo "  error: failed to re-seal bundle: $bundle" >&2
    bundle_fails=$((bundle_fails + 1))
  fi
done < "$bundle_list"
rm -f "$bundle_list"
if [ "$bundle_fails" -gt 0 ]; then
  echo "error: $bundle_fails bundles failed to re-seal" >&2
  exit 1
fi

# Verify the signature, and the two-key rule. The get-task-allow check is the
# load-bearing one for #3952: the engine child is aborted at runtime if this key
# is present alongside inherit, and TestFlight export is the path that injects
# it. Fail here, before the upload, rather than at launch on a tester's Mac.
if ! codesign --verify --strict "$ENGINE_DST" >/dev/null 2>&1; then
  echo "error: embedded engine signature is invalid after re-signing" >&2
  exit 1
fi
if ! codesign --display --entitlements - "$ENGINE_DST" 2>&1 | grep -q "com.apple.security.inherit"; then
  echo "error: embedded engine is missing com.apple.security.inherit after re-signing" >&2
  exit 1
fi
if codesign --display --entitlements - "$ENGINE_DST" 2>&1 | grep -q "com.apple.security.get-task-allow"; then
  echo "error: embedded engine carries com.apple.security.get-task-allow after re-signing" >&2
  echo "       get-task-allow is incompatible with com.apple.security.inherit (Apple Entitlement" >&2
  echo "       Key Reference) and aborts the sandboxed engine child on launch (#3952)." >&2
  echo "       The TestFlight export re-signs nested code with the parent's distribution" >&2
  echo "       entitlements; this re-sign must have stripped it. Investigate the export" >&2
  echo "       pipeline before uploading." >&2
  exit 1
fi

echo "  engine re-signed for distribution: app-sandbox + inherit, no get-task-allow"