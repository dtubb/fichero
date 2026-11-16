#!/bin/bash
# Engine-free check of dev_engine.sh (the Dev Local Run pre-action): a fake engine on a temp socket whose command line
# names THIS checkout is kept ('start' a no-op); one that names another checkout is restarted (the launcher, stubbed, runs);
# with nothing answering, 'status' fails.
D="$(mktemp -d /tmp/devengXXXX)"; export FICHERO_UDS_PATH="$D/s.sock"; H="$(dirname "$0")/dev_engine.sh"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
printf 'echo launched > "%s/launched"\n' "$D" > "$D/launch.sh"; export DEV_ENGINE_LAUNCH="$D/launch.sh"
"$H" status >/dev/null && { echo FAIL: status healthy with no socket; exit 1; }
fake() {  # a health server whose argv looks like the engine's, started from checkout $1
  python3 -c "
import socket,sys
s=socket.socket(socket.AF_UNIX); s.bind(sys.argv[1]); s.listen(5)
while True:
    c,_=s.accept(); c.recv(4096); c.sendall(b'HTTP/1.1 200 OK\r\nContent-Length: 0\r\nConnection: close\r\n\r\n'); c.close()
" "$FICHERO_UDS_PATH" "$1/fichero-server/.venv/bin/python" -m uvicorn fichero_server.api.uds_transport:app --uds "$FICHERO_UDS_PATH" & P=$!
  for _ in 1 2 3 4 5 6 7 8 9 10; do [ -S "$FICHERO_UDS_PATH" ] && break; sleep 0.2; done
}
fake "$ROOT"
"$H" start | grep -q "already answering" || { kill $P; echo FAIL: this checkout\'s engine not kept; exit 1; }
[ -e "$D/launched" ] && { kill $P; echo FAIL: launched over this checkout\'s engine; exit 1; }
"$H" status >/dev/null || { kill $P; echo FAIL: status not healthy; exit 1; }
kill $P; wait $P 2>/dev/null; rm -f "$FICHERO_UDS_PATH"
fake "/tmp/another-checkout"
"$H" start >/dev/null 2>&1
[ -e "$D/launched" ] || { kill $P; echo FAIL: another checkout\'s engine not restarted; exit 1; }
kill $P; rm -rf "$D"; echo ok
