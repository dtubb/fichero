#!/usr/bin/env bash
set -euo pipefail

# Build the fm-bridge Swift CLI into the engine's staged resources.
#
# ONE owner for this step (2026-09-02). There were two engine-staging entry
# points and only one of them built fm-bridge:
#
#   build_backend_bundle.sh          → ran swiftc, staged the binary
#   scripts/preflight-embedded-engine.sh → did not
#
# The release calls the PREFLIGHT one (release-all.sh: "Engine: rebuild
# current Briefcase stage"), and Xcode's embed phase calls it too. fm-bridge is
# gitignored, so a fresh worktree has no copy to stage — and briefcase happily
# staged an EMPTY resources/bin/. The shipped 2026.09.01.2 app is the witness:
# Fichero.app/…/fichero_server/resources/bin/ contains nothing, so every
# Apple Intelligence call answered "fm-bridge binary not found" and search
# refinement was dead in release builds.
#
# Both entry points now call this. Idempotent and fast: it recompiles only when
# the binary is missing or older than its source.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

FM_BRIDGE_SOURCE="$API_ROOT/bin/fm-bridge/FmBridge.swift"
FM_BRIDGE_DEST="$API_ROOT/src/fichero_server/resources/bin/fm-bridge"

if [ ! -f "$FM_BRIDGE_SOURCE" ]; then
  echo "error: fm-bridge source not found at $FM_BRIDGE_SOURCE" >&2
  exit 1
fi

if [ -x "$FM_BRIDGE_DEST" ] && [ "$FM_BRIDGE_DEST" -nt "$FM_BRIDGE_SOURCE" ]; then
  echo "  fm-bridge current: $FM_BRIDGE_DEST"
  exit 0
fi

if ! command -v swiftc >/dev/null 2>&1; then
  echo "error: swiftc not found; cannot build fm-bridge. Apple Intelligence and" >&2
  echo "       search refinement would be dead in the built app — refusing to stage" >&2
  echo "       an engine without it. Install the Xcode command line tools." >&2
  exit 1
fi

mkdir -p "$(dirname "$FM_BRIDGE_DEST")"
# -O                 release-optimized
# -parse-as-library   required for @main alongside top-level Codable structs
# -target            REQUIRED: without it the binary's minimum OS is the BUILD
#                    host's — a bridge built on macOS 27 refuses to launch on
#                    the macOS 26 Macs we ship to (minos 27.0 was found staged
#                    in a release app, 2026-09-04), silently killing every
#                    Apple Intelligence call there.
swiftc -O -parse-as-library -target arm64-apple-macos26.0 \
  -o "$FM_BRIDGE_DEST" "$FM_BRIDGE_SOURCE"
chmod 755 "$FM_BRIDGE_DEST"
MINOS="$(otool -l "$FM_BRIDGE_DEST" | grep -m1 minos | awk '{print $2}')"
if [ "$MINOS" != "26.0" ]; then
  echo "error: fm-bridge minos is $MINOS, not 26.0 — this binary would refuse" >&2
  echo "       to launch on the macOS 26 Macs we ship to. Refusing to stage it." >&2
  rm -f "$FM_BRIDGE_DEST"
  exit 1
fi
echo "  Built fm-bridge: $FM_BRIDGE_DEST (minos $MINOS)"
