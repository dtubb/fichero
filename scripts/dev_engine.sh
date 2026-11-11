#!/bin/bash
# Dev Local engine, long-lived in tmux session f_engine: scripts/dev_engine.sh start|stop|restart|status
# The engine exits when its launcher dies (FICHERO_PARENT_PID), so tmux is the launcher.
# State is the scratch library, never the real app state. 'stop' is manual: the Run pre-action only calls 'start'.
set -u
# Xcode runs pre-actions with a minimal PATH: tmux lives in Homebrew.
PATH="/Volumes/Fichero Development/tools/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SESSION=f_engine
# Own tmux server (socket fichero_engine): the engine joins the tmux server of whoever calls start. Called by Xcode, that server
# lives in the desktop session, where the login keychain works; joining a worker's shared server put it in a Background
# session (keychain: "User interaction is not allowed", #6492).
tmx() { tmux -L fichero_engine "$@"; }
SOCK="${FICHERO_UDS_PATH:-$HOME/Library/Containers/app.fichero.fichero/Data/tmp/fichero.sock}"
LOGDIR="$HOME/.local/state/fichero-dev-engine"
LOG="$LOGDIR/engine.log"
PY="${FICHERO_PYTHON_BIN:-}"
# integration .venv first: ~/code/fichero/.venv has a scipy macOS 27 dyld refuses (every Kraken page fails)
for p in "$HOME/code/fichero-worktrees/integration/.venv/bin/python" "$ROOT/.venv/bin/python"; do
  [ -n "$PY" ] && [ -x "$PY" ] && break; PY="$p"
done

alive() { [ -S "$SOCK" ] || return 1; curl -s -o /dev/null --max-time 2 --unix-socket "$SOCK" http://localhost/api/health; [ $? -ne 7 ]; }
up()    { tmx has-session -t "$SESSION" 2>/dev/null; }

# start [nowait]: nowait is for Xcode's pre-action, which must not hold the build up while a loaded Mac starts the engine.
start() {
  nowait="${1:-}"
  if alive; then echo "dev-engine: already answering on $SOCK"; return 0; fi
  [ -x "$PY" ] || { echo "dev-engine: no python at $PY (set FICHERO_PYTHON_BIN)" >&2; return 1; }
  # A session that exists means the engine process is still running (the session ends when it exits): it is starting, slowly
  # on a loaded Mac. Never kill it: the old kill-and-restart on every call meant a slow start never finished.
  if up; then echo "dev-engine: already starting"; [ "$nowait" = nowait ] && return 0
  else
  mkdir -p "$LOGDIR" "$(dirname "$SOCK")" "$HOME/Fichero Dev Test/state"
  # Launch-secret file the Debug app reads once (see dev-uds-engine.sh).
  SECRET="$(dirname "$SOCK")/launch-secret"
  ( umask 077; openssl rand -hex 32 | tr -d '\n' > "$SECRET" )
  tmx new-session -d -s "$SESSION" -c "$ROOT" \
    "FICHERO_BASE_PATH='$HOME/Fichero Dev Test/state' FICHERO_UDS_PATH='$SOCK' FICHERO_PYTHON_BIN='$PY' FICHERO_ENV=development FICHERO_DEV_LAUNCH_SECRET_FILE='$SECRET' exec '$ROOT/fichero-server/scripts/start_fichero_server.sh' --uds >>'$LOG' 2>&1"
  fi
  [ "$nowait" = nowait ] && { echo "dev-engine: starting, log $LOG"; return 0; }
  for _ in $(seq 1 360); do alive && { echo "dev-engine: up on $SOCK, log $LOG"; return 0; }; sleep 0.5; done
  echo "dev-engine: no health after 180 s, see $LOG" >&2; return 1
}
stop() { up && tmx kill-session -t "$SESSION"; echo "dev-engine: stopped"; }

case "${1:-status}" in
  start) start "${2:-}" ;;
  stop) stop ;;
  restart) stop; start ;;
  status) if alive; then echo "dev-engine: healthy on $SOCK (tmux: $(up && echo yes || echo no)), log $LOG"; else echo "dev-engine: not answering on $SOCK"; exit 1; fi ;;
  *) echo "usage: $0 start|stop|restart|status" >&2; exit 2 ;;
esac
