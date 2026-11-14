#!/bin/bash
# The Dev Local engine on the app's container socket: scripts/dev_engine.sh start|stop|restart|status
# `start` is what the "Fichero (Dev Local)" Run pre-action calls: it keeps an engine that answers AND was started from
# THIS checkout, else (none, or another checkout's) it (re)starts one from this checkout through
# start_dev_local_engine.sh (scratch library, its own session, so it outlives the pre-action). No tmux.
set -u
PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"   # Xcode runs pre-actions with a minimal PATH
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SOCK="${FICHERO_UDS_PATH:-$HOME/Library/Containers/app.fichero.fichero/Data/tmp/fichero.sock}"
LAUNCH="${DEV_ENGINE_LAUNCH:-$ROOT/scripts/start_dev_local_engine.sh}"   # the test stubs it
PATTERN="uvicorn fichero_server.api.uds_transport:app --uds $SOCK"

pid()   { pgrep -f "$PATTERN" | head -1; }
alive() { [ -S "$SOCK" ] && curl -s -o /dev/null --max-time 2 --unix-socket "$SOCK" http://localhost/api/health; }
ours()  { local p; p=$(pid); [ -n "$p" ] && ps -o command= -p "$p" | grep -qF "$ROOT/"; }

start() {
  if alive && ours; then echo "dev-engine: already answering on $SOCK from $ROOT"; return 0; fi
  [ -n "$(pid)" ] && echo "dev-engine: the engine on $SOCK is another checkout's or not answering; restarting from $ROOT"
  zsh "$LAUNCH"
  alive || { echo "dev-engine: no health on $SOCK; see ~/code/fichero-worktrees/.devlogs/dev_engine.log" >&2; return 1; }
}
stop() { local p; p=$(pid); [ -n "$p" ] && kill "$p"; echo "dev-engine: stopped"; }

case "${1:-status}" in
  start) start ;;
  stop) stop ;;
  restart) stop; sleep 2; start ;;
  status) if alive; then echo "dev-engine: healthy on $SOCK ($(ours && echo "this checkout" || echo "another checkout"))"; else echo "dev-engine: not answering on $SOCK"; exit 1; fi ;;
  *) echo "usage: $0 start|stop|restart|status" >&2; exit 2 ;;
esac
