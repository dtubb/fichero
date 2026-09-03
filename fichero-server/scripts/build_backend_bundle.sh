#!/bin/bash
set -e

# Build backend bundle with Briefcase.
# Run from repo root: ./fichero-server/scripts/build_backend_bundle.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
echo "🔨 Building Fichero Backend with Briefcase"
cd "$API_ROOT"

if ! command -v briefcase >/dev/null 2>&1; then
  echo "❌ Briefcase not found. Installing..."
  pip install briefcase
fi

if [ -d "build/server" ]; then
  chmod -R u+w build/server 2>/dev/null || true
  rm -rf build/server || /bin/rm -rf build/server
fi

# One owner for the fm-bridge build, shared with
# scripts/preflight-embedded-engine.sh — the entry point the release actually
# uses. When only this script built it, every release shipped without it.
"$API_ROOT/scripts/build_fm_bridge.sh"

SIGNING_IDENTITY=$(security find-identity -v -p codesigning | grep "Apple Development" | head -1 | awk -F'"' '{print $2}')
if [ -z "$SIGNING_IDENTITY" ]; then
  echo "❌ No Apple Development signing identity found"
  exit 1
fi

BACKEND_APP_SOURCE="build/fichero_server/macos/app/Fichero Server.app"

# ── Version metadata is written by `create`, not `update` ───────────────────
#
# `briefcase update` refreshes app code and (with -r) requirements, but it
# NEVER re-renders the generated app template — Info.plist included. Confirmed
# in briefcase 0.4.2: `UpdateCommand.update_app` calls install_app_code /
# install_app_requirements / install_app_resources (icons) / support / stub, and
# nothing that runs the cookiecutter. Only `briefcase create` writes
# CFBundleShortVersionString.
#
# So a version bump in pyproject.toml used to leave the staged bundle labelled
# with whatever version was current the last time `create` ran — 2026-09-01:
# ~/code/fichero held THREE versions at once (Info.plist 2026.8.27, dist-info
# 2026.8.31b1, pyproject 2026.9.1b2) and the Dev Embedded build printed the
# oldest of the three as "Embedded engine version". A staging step whose version
# label is a fossil of an earlier build is the same class of lie as a staleness
# check that cannot see a change.
#
# Recreate ONLY when the stamped version has drifted (the full create is slow);
# otherwise keep the fast update/build path. Mirrors the identical guard in
# scripts/preflight-embedded-engine.sh so both restage entry points agree.
if [ -d "$BACKEND_APP_SOURCE" ] \
   && ! "$API_ROOT/../scripts/clean-embedded-engine.sh" --check-version "$API_ROOT/$BACKEND_APP_SOURCE" >/dev/null 2>&1; then
  echo "♻️  Recreating Briefcase app template — the staged engine's version metadata has drifted"
  rm -rf "build/fichero_server/macos/app"
fi
if [ ! -d "build/fichero_server/macos/app" ]; then
  briefcase create macOS --app fichero_server
fi
# Build and SIGN as two steps, so there is a seam between them.
#
# `briefcase package` does both at once, leaving nowhere to stand between "the
# bundle exists" and "the bundle is sealed". The release needs that seam:
# libpdfium.dylib is placed beside kreuzberg's binding after the build and
# before signing (scripts/release-all.sh), so the codesign pass covers it.
#
# -r: refresh requirements too. Without it a dependency change in pyproject.toml
# was staged by NOBODY — this is the documented full rebuild, and it was the one
# path that skipped requirements.
briefcase update macOS --app fichero_server -r
briefcase build macOS --app fichero_server
briefcase package macOS --app fichero_server --identity "$SIGNING_IDENTITY"
STAGED_BRIDGE="$BACKEND_APP_SOURCE/Contents/Resources/app/fichero_server/resources/bin/fm-bridge"
if [ -d "$BACKEND_APP_SOURCE" ] && [ ! -x "$STAGED_BRIDGE" ]; then
  echo "❌ Staged engine has no executable fm-bridge at $STAGED_BRIDGE"
  echo "   Apple Intelligence and search refinement would be dead in this build."
  exit 1
fi
if [ -d "$BACKEND_APP_SOURCE" ]; then
  echo "✅ Backend bundle ready: $BACKEND_APP_SOURCE"
else
  echo "❌ Build failed - $BACKEND_APP_SOURCE not found"
  exit 1
fi
