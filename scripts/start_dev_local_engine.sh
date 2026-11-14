#!/bin/zsh
# Start (or restart) the dev engine the "Fichero (Dev Local)" Xcode scheme dials, from THIS checkout.
# The scheme runs the app only; Debug never spawns an engine. UDS only, on the container socket.
#
#   scripts/start_dev_local_engine.sh            # restart on the current checkout's code
#   curl -s --unix-socket "$SOCK" http://localhost/api/health
#
# Base state is a scratch folder (~/Fichero Dev Test/state), never the real libraries. Allowed project
# roots: Dev Test, Test Corpus, and ~/Fichero Projects (real data: read-only habits). Model store is the
# shared ~/Library/Application Support/Fichero. Log: ~/code/fichero-worktrees/.devlogs/dev_engine.log
set -u
ROOT=${0:A:h:h}
SOCK="$HOME/Library/Containers/app.fichero.fichero/Data/tmp/fichero.sock"
PY="${FICHERO_PYTHON_BIN:-$ROOT/fichero-server/.venv/bin/python}"
LOG="$HOME/code/fichero-worktrees/.devlogs/dev_engine.log"; mkdir -p "${LOG:h}"
old=$(pgrep -f "uvicorn fichero_server.api.uds_transport:app --uds $SOCK" | head -1)  # this socket only, not other lanes' engines
if [ -n "$old" ]; then
  kill "$old"; for i in {1..15}; do kill -0 "$old" 2>/dev/null || break; sleep 1; done
  kill -0 "$old" 2>/dev/null && { kill -9 "$old"; sleep 2; }   # SIGTERM can be ignored while it drains
fi
rm -f "$SOCK"
BASE="$HOME/Fichero Dev Test/state"
PYTHONPATH="$ROOT/fichero-server/src" "$PY" -m fichero_server.security.real_data_guard "$BASE" || exit 1  # never real data
cd "$ROOT" && env OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES FICHERO_APP_BUNDLE_ID=app.fichero.fichero FICHERO_DEBUG_APP_BUNDLE_ID=app.fichero.fichero \
  FICHERO_FEATURE_TIER=dev FICHERO_MULTIUSER=0 FICHERO_PYTHON_BIN="$PY" \
  FICHERO_BASE_PATH="$BASE" FICHERO_UDS_PATH="$SOCK" \
  FICHERO_LIBRARY_ALLOWED_ROOTS="$HOME/Fichero Dev Test:$HOME/Fichero Test Corpus:$HOME/Fichero Projects" \
  FICHERO_MODEL_STORE_ROOT="$HOME/Library/Application Support/Fichero" PYTHONPATH="$ROOT/fichero-server/src" \
  "$PY" -c 'import subprocess,sys; subprocess.Popen(sys.argv[2:], stdout=open(sys.argv[1], "w"), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)' \
  "$LOG" "$PY" -m uvicorn fichero_server.api.uds_transport:app --uds "$SOCK" --ws websockets-sansio
# Its own session: it outlives whatever started it (a terminal, or Xcode's Run pre-action via dev_engine.sh).
for i in {1..60}; do curl -s -o /dev/null --max-time 2 --unix-socket "$SOCK" http://localhost/api/health && break; sleep 1; done
curl -s --max-time 5 --unix-socket "$SOCK" http://localhost/api/health | cut -c1-160; echo
