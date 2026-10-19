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
    # A venv or uv python resolves to its base interpreter, so only say it is a real executable on disk.
    assert os.path.isabs(shown["exe"]) and os.access(shown["exe"], os.X_OK)


def test_a_peer_that_already_names_its_program_is_shown_as_is():
    peer = {"uid": 1, "pid": 2, "token": "00", "exe": "/x", "signer": "S (T)"}
    assert uds_peer.identify(peer) == {"pid": 2, "exe": "/x", "signer": "S (T)"}


def _serve_once_and_get_peer():
    """Run the real uvicorn on a UDS with the peer-aware protocol; return (status line, parsed body) of one GET."""
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
        headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]
        await send({"type": "http.response.start", "status": 200, "headers": headers})
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
        return raw.split(b"\r\n", 1)[0], json.loads(raw.split(b"\r\n\r\n", 1)[1])
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def test_the_real_uvicorn_server_stamps_each_connection_with_its_peer():
    _status, peer = _serve_once_and_get_peer()
    assert peer["pid"] == os.getpid() and peer["uid"] == os.getuid()


def test_a_failing_peer_lookup_never_drops_the_connection(monkeypatch):
    # Review 140: a surprise while stamping must serve the request without a peer, not close the socket.
    def boom(_sock):
        raise TypeError("surprise")

    monkeypatch.setattr(uds_peer, "peer_of_socket", boom)
    status, peer = _serve_once_and_get_peer()
    assert status.endswith(b"200 OK") and peer is None


def test_a_missing_security_symbol_gives_no_identity_not_an_error(monkeypatch):
    monkeypatch.setattr(uds_peer, "_code_identity_of", lambda *a: (_ for _ in ()).throw(AttributeError("no symbol")))
    if sys.platform != "darwin":
        pytest.skip("Security.framework is macOS")
    assert uds_peer._code_identity("00" * 32) == ("", None)
