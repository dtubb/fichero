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

# Liveness = can we actually connect and get an HTTP reply over the socket?
# (lsof on a UDS path is unreliable — esp. with uvicorn --reload's worker
# subprocess — and a bare `[ -S ]` can't tell a live socket from a stale file
# left by a crash.) Any HTTP status, incl. 401/404, means alive; only a refused
# connection (curl exit 7) means not.
engine_alive() {
  [ -S "$SOCK" ] || return 1
  curl -s -o /dev/null --max-time 2 --unix-socket "$SOCK" http://localhost/health
  [ "$?" -ne 7 ]
}

# Already serving? -> reuse, do nothing.
if engine_alive; then
  echo "dev-uds-engine: reusing warm engine on $SOCK"
  exit 0
fi

echo "dev-uds-engine: starting engine on $SOCK (reload on) -> $LOG"
# Fully detach: the ( ... & ) subshell exits immediately, so the engine is
# reparented to launchd and survives Xcode terminating the pre-action's process
# group. nohup ignores the SIGHUP Xcode sends on pre-action teardown.
( FICHERO_UDS_PATH="$SOCK" nohup "$SCRIPT_DIR/start_backend.sh" --uds --reload >"$LOG" 2>&1 & )

# Wait (bounded) for the socket to be bound before returning, so the app
# launches into a listening engine and adopts on the first try instead of
# hitting the connection screen + Retry. ~30s covers a cold boot; a warm run
# never reaches here.
for _ in $(seq 1 60); do
  engine_alive && break
  sleep 0.5
done
exit 0
