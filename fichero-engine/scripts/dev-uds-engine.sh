#!/bin/bash
# Xcode "Fichero (Dev Local)" Run pre-action: bring up the dev engine so ⌘R
# "just works" and the Debug app adopts it. Idempotent — a warm engine is
# reused (⌘R doesn't stack copies). Detaches so Xcode's pre-action shell can
# exit without killing the engine.
#
# Transport is chosen by FICHERO_DEV_TRANSPORT (default https), so there is no
# silent fallover: each mode starts exactly one transport.
#   https    — external engine on TCP :8765 (pinned loopback TLS). Sandbox-safe;
#              the Debug build adopts :8765 with no extra env. DEFAULT.
#   uds      — external engine on the app's *container* AF_UNIX socket (a /tmp
#              socket is blocked by the app sandbox). Pair with the app launched
#              with FICHERO_FORCE_UDS_PATH set to the SAME container path.
#   inmemory — nothing to start; the app runs the engine in-process (PythonKit)
#              when launched with FICHERO_FORCE_INMEMORY=1.
set -u
# Explicit transport, NO fallback: each mode starts exactly its own transport
# and nothing else. An unknown mode is a hard error, never a silent default.
MODE="${FICHERO_DEV_TRANSPORT:?FICHERO_DEV_TRANSPORT must be uds|https|inmemory}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG="${TMPDIR:-/tmp}/fichero-dev-engine.log"
# Sandboxed Debug app can only reach a socket inside its container (a /tmp
# socket is EPERM). This is the app's NSTemporaryDirectory() for uds mode.
CONTAINER_UDS="$HOME/Library/Containers/app.fichero.fichero/Data/tmp/fichero.sock"

# HTTP liveness over TCP :8765 (curl -k: the loopback cert is self-signed). Any
# HTTP reply (incl. 401) means alive; a refused connection (exit 7) means down.
https_alive() {
  curl -sk -o /dev/null --max-time 2 https://127.0.0.1:8765/health
  [ "$?" -ne 7 ]
}
uds_alive() {
  [ -S "${FICHERO_UDS_PATH:-}" ] || return 1
  curl -s -o /dev/null --max-time 2 --unix-socket "$FICHERO_UDS_PATH" http://localhost/health
  [ "$?" -ne 7 ]
}

case "$MODE" in
  inmemory)
    echo "dev-engine: inmemory mode — app runs the engine in-process, nothing to start"
    exit 0
    ;;
  uds)
    SOCK="${FICHERO_UDS_PATH:-$CONTAINER_UDS}"
    export FICHERO_UDS_PATH="$SOCK"
    mkdir -p "$(dirname "$SOCK")" 2>/dev/null
    if uds_alive; then echo "dev-engine: reusing warm UDS engine on $SOCK"; exit 0; fi
    echo "dev-engine: starting UDS engine on $SOCK (reload) -> $LOG"
    ( FICHERO_UDS_PATH="$SOCK" nohup "$SCRIPT_DIR/start_backend.sh" --uds --reload >"$LOG" 2>&1 & )
    for _ in $(seq 1 90); do uds_alive && break; sleep 0.5; done
    ;;
  https)
    if https_alive; then echo "dev-engine: reusing warm HTTPS engine on :8765"; exit 0; fi
    echo "dev-engine: starting HTTPS engine on :8765 (reload) -> $LOG"
    ( nohup "$SCRIPT_DIR/start_backend.sh" --fast --reload >"$LOG" 2>&1 & )
    for _ in $(seq 1 90); do https_alive && break; sleep 0.5; done
    ;;
  *)
    echo "dev-engine: ERROR unknown FICHERO_DEV_TRANSPORT='$MODE' (want uds|https|inmemory)" >&2
    exit 2
    ;;
esac
exit 0
