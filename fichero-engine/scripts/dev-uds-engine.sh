#!/bin/bash
# Xcode "Fichero (Dev Local)" Run pre-action: bring up the dev engine on a UDS
# socket if it isn't already serving one, so ⌘R "just works" and the Debug app
# adopts it via FICHERO_FORCE_UDS_PATH. Idempotent: a warm engine is reused (so
# ⌘R doesn't stack copies and the engine stays hot for --reload). Detaches so
# Xcode's pre-action shell can exit without killing the engine.
set -u
SOCK="${FICHERO_UDS_PATH:-/tmp/fichero.sock}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG="${TMPDIR:-/tmp}/fichero-dev-engine.log"

# Already serving? (socket exists AND a process holds it) -> reuse, do nothing.
if [ -S "$SOCK" ] && /usr/sbin/lsof "$SOCK" >/dev/null 2>&1; then
  echo "dev-uds-engine: reusing warm engine on $SOCK"
  exit 0
fi

echo "dev-uds-engine: starting engine on $SOCK (reload on) -> $LOG"
# Fully detach: the ( ... & ) subshell exits immediately, so the engine is
# reparented to launchd and survives Xcode terminating the pre-action's process
# group. nohup ignores the SIGHUP Xcode sends on pre-action teardown.
( FICHERO_UDS_PATH="$SOCK" nohup "$SCRIPT_DIR/start_backend.sh" --uds --reload >"$LOG" 2>&1 & )
exit 0
