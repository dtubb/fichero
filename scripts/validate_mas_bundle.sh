#!/bin/bash
#
# validate_mas_bundle.sh — run App Store Connect's ingestion checks LOCALLY, on a
# built or archived Fichero.app, before spending an upload to learn the answer.
#
#   ./scripts/validate_mas_bundle.sh "path/to/Fichero.app"
#   ./scripts/validate_mas_bundle.sh "path/to/Fichero.xcarchive"
#
# Every rule here corresponds to a rejection this app has actually taken (#3748/#3749):
#
#   90284  a nested static archive (.a) is not signed with the distribution cert.
#          Briefcase's Python.framework ships Tcl/Tk link-time stubs. A .a cannot be
#          signed at all — it is an ar archive, not a Mach-O image — so it must not
#          ship. The embed phase deletes them; this proves it did.
#
#   90296  a nested executable lacks com.apple.security.app-sandbox. This is what
#          fm-bridge tripped: the Swift CLI the engine spawns, buried at
#          Contents/Resources/app/fichero_server/resources/bin/fm-bridge, far from any path
#          a rule was looking at. So this checks EVERY Mach-O executable in the
#          bundle, wherever it sits, rather than the places we happen to expect.
#
#   2.4.5(vii)  Sparkle, in any form, in an App Store build.
#
# Exits non-zero and names the offenders. Read-only: it inspects, never modifies.
#
# NOT a substitute for `xcrun altool`/Transporter validation — it is the fast local
# gate that catches the failures we know about, in seconds instead of an upload cycle.

set -u

# --structure-only omits the checks that need the OUTER app to be signed, so this can
# run as a build phase — where the engine is already signed (our embed phase does it)
# but Xcode has not yet reached its CodeSign step for the app itself. Everything that
# does not depend on that signature still runs, which is every rejection we have
# actually taken: .a, .dSYM, unsandboxed nested executables, engine placement, Sparkle.
STRUCTURE_ONLY=0
TARGET=""
for arg in "$@"; do
  case "$arg" in
    --structure-only) STRUCTURE_ONLY=1 ;;
    *) TARGET="$arg" ;;
  esac
done

if [ -z "$TARGET" ]; then
  echo "usage: $0 [--structure-only] <path to Fichero.app or Fichero.xcarchive>" >&2
  exit 2
fi

# Accept an .xcarchive and find the app inside it.
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

# Resolve to a PHYSICAL path. In an archive build the products dir holds a SYMLINK to
# the real bundle under DSTROOT, and `find` does not descend into a symlinked starting
# point — it silently reports zero matches, which reads exactly like a clean bundle.
# That is how a .dSYM-laden archive passed its own checks (#3797). Never `find` a path
# that might be a symlink.
APP="$(cd "$APP" && pwd -P)"

echo "Validating $APP"
FAILURES=0

fail_early() {
  echo "  ✗ $1" >&2
  echo >&2
  echo "FAILED — validation cannot be trusted." >&2
  exit 1
}

# Before believing any "found nothing", prove find is traversing at all. A bundle
# always has files in it; zero means the walk is broken, not that the bundle is clean.
if [ "$(find "$APP" -type f | head -1 | wc -l | tr -d ' ')" -eq 0 ]; then
  fail_early "find traverses nothing under $APP — every check below would vacuously pass"
fi

fail() {
  echo "  ✗ $1" >&2
  FAILURES=$((FAILURES + 1))
}

# ── 1. Static archives (90284) ────────────────────────────────────────────────
ARCHIVES="$(find "$APP" -name '*.a' -type f)"
if [ -n "$ARCHIVES" ]; then
  fail "static archives present — ingestion rejects these (90284), and a .a cannot be signed:"
  echo "$ARCHIVES" | sed 's/^/      /' >&2
else
  echo "  ✓ no static archives (.a)"
fi

# ── 1b. Debug-symbol bundles (90277/90278) ────────────────────────────────────
# Briefcase ships PyObjCTest extensions with their *.cpython-312-darwin.so.dSYM
# alongside. A .dSYM carries the bundle identifier com.apple.xcode.dsym.* — Apple's
# own, not ours, so it can never match the provisioning profile. It is not runtime
# code either: it is detached DWARF, loaded by nothing, useful only to symbolicate a
# crash log. There is nothing to fix by re-signing it; it simply must not ship.
DSYMS="$(find "$APP" -name '*.dSYM' -type d)"
if [ -n "$DSYMS" ]; then
  fail "debug-symbol bundles present — they carry com.apple.xcode.dsym identifiers (90277/90278):"
  echo "$DSYMS" | sed 's/^/      /' >&2
else
  echo "  ✓ no debug-symbol bundles (.dSYM)"
fi

# ── 2. Every nested executable is sandboxed (90296) ───────────────────────────
# By Mach-O TYPE, not by path — the whole point of the fm-bridge rejection is that
# the offender was somewhere nobody thought to look.
EXECS="$(find "$APP" -type f -exec file {} + 2>/dev/null \
  | awk -F': ' '/Mach-O/ && /executable/ && !/for architecture/ {print $1}' | sort -u)"

EXEC_COUNT=0
UNSANDBOXED=0
MAIN_EXEC="$APP/Contents/MacOS/$(/usr/libexec/PlistBuddy -c 'Print :CFBundleExecutable' "$APP/Contents/Info.plist" 2>/dev/null)"

while IFS= read -r exe; do
  [ -n "$exe" ] || continue
  EXEC_COUNT=$((EXEC_COUNT + 1))

  # In --structure-only (build-phase) mode the OUTER app is not signed yet — Xcode's
  # CodeSign step runs after our phases — so its entitlements cannot be read. Every
  # NESTED executable is already signed by the embed phase, and those are the ones
  # that have actually been rejected, so they are still checked.
  if [ "$STRUCTURE_ONLY" -eq 1 ] && [ "$exe" = "$MAIN_EXEC" ]; then
    continue
  fi

  ENTS="$(codesign --display --entitlements - "$exe" 2>&1)"

  if ! printf '%s' "$ENTS" | grep -q "com.apple.security.app-sandbox"; then
    fail "not sandboxed (90296): ${exe#"$APP"/}"
    UNSANDBOXED=$((UNSANDBOXED + 1))
    continue
  fi

  # The main app carries the real sandbox; every OTHER executable must INHERIT it.
  # inherit is incompatible with any other App Sandbox key — the system aborts a
  # child that has one — so a nested executable with, say, network.server of its own
  # is a launch failure waiting to happen, not a harmless extra.
  if [ "$exe" != "$MAIN_EXEC" ]; then
    if ! printf '%s' "$ENTS" | grep -q "com.apple.security.inherit"; then
      fail "nested executable lacks com.apple.security.inherit: ${exe#"$APP"/}"
    fi
    # get-task-allow is also incompatible with inherit (Apple Entitlement Key
    # Reference) and aborts the sandboxed engine child on launch. TestFlight
    # export injects it into nested code when the helper is not recognised as
    # an Embed-Helper-Tools target — exactly the Fichero engine's case (#3952).
    # The build phase and scripts/resign_engine_in_archive.sh strip it; this is
    # the local gate that proves they did, on a built bundle or a .xcarchive.
    if printf '%s' "$ENTS" | grep -q "com.apple.security.get-task-allow"; then
      fail "nested executable carries get-task-allow (aborts the sandboxed child at launch, #3952): ${exe#"$APP"/}"
    fi
  fi
done <<EOF
$EXECS
EOF

if [ "$UNSANDBOXED" -eq 0 ] && [ "$EXEC_COUNT" -gt 0 ]; then
  echo "  ✓ all $EXEC_COUNT Mach-O executable(s) sandboxed"
fi
if [ "$EXEC_COUNT" -eq 0 ]; then
  fail "found no Mach-O executables at all — is this really an app bundle?"
fi

# ── 3. The engine is a nested helper in a designated code location ─────────────
if [ -d "$APP/Contents/Resources/Fichero Engine.app" ]; then
  fail "engine is in Contents/Resources — not a designated code location (invalid bundle structure)"
fi
if [ -d "$APP/Contents/Helpers/Fichero Engine.app" ]; then
  echo "  ✓ engine embedded in Contents/Helpers"
else
  fail "no engine at Contents/Helpers/Fichero Engine.app — the app would ship with no backend"
fi

# ── 4. Sparkle is absent, in every form (2.4.5(vii)) ──────────────────────────
SPARKLE="$(find "$APP" \( -name 'Sparkle.framework' -o -name 'Autoupdate' -o -name 'Updater.app' \) )"
if [ -n "$SPARKLE" ]; then
  fail "Sparkle is present in an App Store build (2.4.5(vii)):"
  echo "$SPARKLE" | sed 's/^/      /' >&2
else
  echo "  ✓ no Sparkle framework/Autoupdate/Updater"
fi

for KEY in SUFeedURL SUPublicEDKey; do
  if /usr/libexec/PlistBuddy -c "Print :${KEY}" "$APP/Contents/Info.plist" >/dev/null 2>&1; then
    fail "Info.plist still declares ${KEY} — an App Store app must not advertise a self-updater"
  fi
done

# ── 5. The signature actually verifies ────────────────────────────────────────
# --deep is used here to VERIFY (read-only, fine). It must never be used to SIGN:
# signing with --deep re-signs nested code with the PARENT's entitlements, which
# silently replaces the engine's two-key set and breaks inherit.
if [ "$STRUCTURE_ONLY" -eq 1 ]; then
  echo "  – signature check skipped (--structure-only: the app is signed after this phase)"
elif codesign --verify --deep --strict "$APP" 2>/dev/null; then
  echo "  ✓ signature verifies (--verify --deep --strict)"
else
  fail "signature does not verify: codesign --verify --deep --strict failed"
fi

echo
if [ "$FAILURES" -gt 0 ]; then
  echo "FAILED — $FAILURES problem(s). This bundle would be rejected." >&2
  exit 1
fi
echo "PASSED — no known ingestion blocker in this bundle."
