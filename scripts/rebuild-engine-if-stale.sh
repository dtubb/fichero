#!/usr/bin/env bash
# Rebuild the embedded engine bundle IF the engine source is newer than the
# bundle (or the bundle is missing).
#
# WHY: the Xcode "Embed Fichero Server" build phase only `cp -R`s the pre-built
# bundle from fichero-server/build/fichero_server/macos/app/ — it does NOT rebuild it.
# So a ⌘R Dev Embedded silently embeds a STALE engine after any engine-source
# change (the stale-bundle trap: the app connects to an old engine and can miss
# fixes like the SIGPIPE/auth ones). Wire this as a Run Script phase BEFORE
# "Embed Fichero Server" so ⌘R always embeds a fresh engine — while skipping the
# ~10-min briefcase build when the bundle is already current.
#
# Manual use (before a ⌘R): ./scripts/rebuild-engine-if-stale.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUNDLE="$ROOT/fichero-server/build/fichero_server/macos/app/Fichero Server.app"
SRC="$ROOT/fichero-server/src"
STAMP="$BUNDLE/Contents/Info.plist"   # written by build_backend_bundle.sh each build

# Everything that can change what the bundle CONTAINS — not just the Python.
#
# This checked `*.py` under src/ only, so a change to the dependency list or to
# the packaging recipe left the bundle "up to date" and the build silently
# skipped. Found 2026-08-04: the pdfium fix edited pyproject.toml (adding
# pypdfium2) and build_backend_bundle.sh (placing the dylib before signing), the
# staleness check saw no new .py, and ⌘R re-embedded the SAME stale engine —
# Daniel kept getting the Gatekeeper dialog for a bug that was already fixed.
#
# A staleness check that cannot see a change reports "fresh", which is the same
# class of lie as an error that names no cause: the answer is confident and
# wrong, and it costs a build cycle each time to discover it.
DEPS="$ROOT/fichero-server/pyproject.toml"
RECIPE="$ROOT/fichero-server/scripts/build_backend_bundle.sh"
PLACE_PDFIUM="$ROOT/scripts/place_pdfium_for_kreuzberg.py"

need_rebuild=0
reason=""
if [ ! -d "$BUNDLE" ] || [ ! -f "$STAMP" ]; then
  need_rebuild=1; reason="bundle missing"
elif [ -n "$(find "$SRC" -type f -name '*.py' -newer "$STAMP" -print -quit 2>/dev/null)" ]; then
  need_rebuild=1; reason="engine source newer than bundle"
else
  for watched in "$DEPS" "$RECIPE" "$PLACE_PDFIUM"; do
    if [ -f "$watched" ] && [ "$watched" -nt "$STAMP" ]; then
      need_rebuild=1; reason="$(basename "$watched") newer than bundle"
      break
    fi
  done
fi

if [ "$need_rebuild" = 1 ]; then
  echo "note: rebuilding embedded engine ($reason)"
  "$ROOT/fichero-server/scripts/build_backend_bundle.sh"
else
  echo "note: embedded engine bundle is up to date with source — skipping rebuild"
fi
