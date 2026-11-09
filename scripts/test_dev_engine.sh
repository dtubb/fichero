#!/bin/bash
# Engine-free check: with a fake health server on a temp socket, 'start' is a no-op and 'status' is healthy; with none, status fails.
D="$(mktemp -d /tmp/devengXXXX)"; export FICHERO_UDS_PATH="$D/s.sock"; H="$(dirname "$0")/dev_engine.sh"
"$H" status >/dev/null && { echo FAIL: status healthy with no socket; exit 1; }
python3 -c "
import socket,sys
s=socket.socket(socket.AF_UNIX); s.bind(sys.argv[1]); s.listen(5)
while True:
    c,_=s.accept(); c.recv(4096); c.sendall(b'HTTP/1.1 200 OK\r\nContent-Length: 0\r\nConnection: close\r\n\r\n'); c.close()
" "$FICHERO_UDS_PATH" & P=$!
for _ in 1 2 3 4 5 6 7 8 9 10; do [ -S "$FICHERO_UDS_PATH" ] && break; sleep 0.2; done
"$H" start | grep -q "already answering" || { kill $P; echo FAIL: start not a no-op; exit 1; }
"$H" status >/dev/null || { kill $P; echo FAIL: status not healthy; exit 1; }
kill $P; rm -rf "$D"; echo ok
