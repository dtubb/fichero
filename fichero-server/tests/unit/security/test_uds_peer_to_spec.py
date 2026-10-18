"""multiuser.first-connection-asks-the-person (slice 6b, #2403): the Unix socket says who connected.

`api/uds_peer.py` reads the peer's user, pid and kernel audit token when a connection is made and stamps them on every
request of that connection as `fichero.peer`. The program's identity is read from the audit token, never from the pid.
"""

import json
import os
import socket
import sys
import tempfile
import threading
import time

import pytest

from fichero_server.api import uds_peer


def test_a_connected_socket_names_this_process():
    left, right = socket.socketpair(socket.AF_UNIX)
    try:
        peer = uds_peer.peer_of_socket(left)
    finally:
        left.close()
        right.close()
    assert peer["pid"] == os.getpid() and peer["uid"] == os.getuid() and peer["token"]


@pytest.mark.skipif(sys.platform != "darwin", reason="the audit token and Security.framework are macOS")
def test_identity_comes_from_the_audit_token_and_names_the_executable():
    left, right = socket.socketpair(socket.AF_UNIX)
    try:
        shown = uds_peer.identify(uds_peer.peer_of_socket(left))
    finally:
        left.close()
        right.close()
    assert shown["pid"] == os.getpid()
    assert os.path.realpath(shown["exe"]).startswith(os.path.realpath(sys.prefix)) or shown["exe"].endswith("Python")


def test_a_peer_that_already_names_its_program_is_shown_as_is():
    peer = {"uid": 1, "pid": 2, "token": "00", "exe": "/x", "signer": "S (T)"}
    assert uds_peer.identify(peer) == {"pid": 2, "exe": "/x", "signer": "S (T)"}


def test_the_real_uvicorn_server_stamps_each_connection_with_its_peer():
    uvicorn = pytest.importorskip("uvicorn")

    async def echo(scope, receive, send):
        if scope["type"] == "lifespan":
            while True:
                message = await receive()
                if message["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif message["type"] == "lifespan.shutdown":
                    await send({"type": "lifespan.shutdown.complete"})
                    return
        body = json.dumps(scope.get("fichero.peer")).encode()
        await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"application/json")]})
        await send({"type": "http.response.body", "body": body})

    folder = tempfile.mkdtemp(prefix="fp", dir="/tmp")
    path = os.path.join(folder, "s.sock")
    config = uvicorn.Config(app=echo, uds=path, http=uds_peer.peer_aware_http_protocol(), log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        for _ in range(100):
            if os.path.exists(path):
                break
            time.sleep(0.1)
        client = socket.socket(socket.AF_UNIX)
        client.connect(path)
        client.sendall(b"GET / HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n")
        raw = b""
        while chunk := client.recv(4096):
            raw += chunk
        client.close()
        peer = json.loads(raw.split(b"\r\n\r\n", 1)[1])
        assert peer["pid"] == os.getpid() and peer["uid"] == os.getuid()
    finally:
        server.should_exit = True
        thread.join(timeout=5)
