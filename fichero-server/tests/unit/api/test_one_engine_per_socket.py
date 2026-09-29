"""One engine per socket: a live engine's socket is refused, a stale one reclaimed (2026-09-28).

WHY: two engines ended up on one container socket and one `.api-key`. A starting engine unlinked
the socket path and bound its own, and its startup rewrote the bootstrap token; the engine the app
had been using ran on unreachable, and the app's token no longer matched -- 401s on some requests.
If this regresses, a second launch silently steals the socket and the token again.

Real Unix-domain sockets throughout: a live stand-in engine answering /api/health, one that
listens but never answers (busy is not dead), a crashed engine's leftover file, and a plain file.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import tempfile
from pathlib import Path

import pytest

from fichero_server.api import uds_claim
from fichero_server.api.uds_claim import EngineAlreadyServing, claim_uds_path, engine_owner


@pytest.fixture
def sock_path():
    folder = tempfile.mkdtemp(dir="/tmp", prefix="fsk-")      # sun_path caps near 104 bytes
    yield str(Path(folder) / "e.sock")
    shutil.rmtree(folder, ignore_errors=True)


_STAND_IN = r"""
import json, socket, sys, time
path, answer = sys.argv[1], sys.argv[2] == "1"
server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
server.bind(path)
server.listen(4)
body = json.dumps({"status": "healthy", "engine_pid": 4242, "engine_owner": "/Applications/Fichero.app"}).encode()
while True:
    conn, _ = server.accept()
    try:
        if not conn.recv(4096):
            continue                      # a probe that only connected
        if answer:
            conn.sendall(b"HTTP/1.0 200 OK\r\nContent-Type: application/json\r\n\r\n" + body)
        else:
            time.sleep(5)                 # busy: never answers in time
    except OSError:
        pass                              # a client that hung up must not kill the engine
    finally:
        conn.close()
"""


class _LiveEngine:
    """Another engine -- another PROCESS -- listening on `path`, answering /api/health like the real
    one (or not). A same-process stand-in would read as this engine's own socket."""

    def __init__(self, path: str, *, answer: bool = True):
        import subprocess
        import sys
        import time

        self.process = subprocess.Popen([sys.executable, "-c", _STAND_IN, path, "1" if answer else "0"])
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                probe.connect(path)
                probe.close()
                return
            except OSError:
                probe.close()
                time.sleep(0.05)
        self.close()
        raise RuntimeError("the stand-in engine never listened")

    def close(self):
        self.process.kill()
        self.process.wait(10)


def _live_engine(path: str, *, answer: bool = True) -> _LiveEngine:
    return _LiveEngine(path, answer=answer)


def test_a_live_engine_is_refused_and_named_and_its_socket_is_left(sock_path):
    server = _live_engine(sock_path)
    try:
        before = os.stat(sock_path).st_ino
        with pytest.raises(EngineAlreadyServing) as refusal:
            claim_uds_path(sock_path)
        assert "another engine is live" in str(refusal.value)
        assert "pid 4242, owner /Applications/Fichero.app" in str(refusal.value)
        assert os.stat(sock_path).st_ino == before              # its socket was not touched
    finally:
        server.close()


def test_a_busy_engine_that_does_not_answer_is_still_refused(sock_path, monkeypatch):
    """Listening is the test, not answering: a live engine slow under load must never be taken for
    a dead one and have its socket unlinked."""
    monkeypatch.setattr(uds_claim, "_PROBE_TIMEOUT_S", 0.3)
    server = _live_engine(sock_path, answer=False)
    try:
        with pytest.raises(EngineAlreadyServing, match="did not answer /api/health in time"):
            claim_uds_path(sock_path)
        assert Path(sock_path).exists()
    finally:
        server.close()


def test_a_stale_socket_nobody_listens_on_is_reclaimed(sock_path):
    crashed = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    crashed.bind(sock_path)
    crashed.close()                                             # the file stays; nobody listens
    assert Path(sock_path).exists()
    claim_uds_path(sock_path)
    assert not Path(sock_path).exists()


def test_a_path_that_is_not_a_socket_is_refused_and_left_alone(sock_path):
    Path(sock_path).write_text("not a socket")
    with pytest.raises(EngineAlreadyServing, match="is not a socket"):
        claim_uds_path(sock_path)
    assert Path(sock_path).read_text() == "not a socket"


def test_a_socket_this_process_already_holds_is_ours(sock_path):
    """The embedded launcher binds before startup, and uvicorn --reload binds in its supervisor:
    the lifespan's claim then finds its OWN socket and must not refuse it."""
    mine = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    mine.bind(sock_path)
    mine.listen(1)
    try:
        claim_uds_path(sock_path)                               # no refusal, nothing unlinked
        assert Path(sock_path).exists()
    finally:
        mine.close()


def test_the_socket_the_launcher_bound_is_ours_even_past_fd_1023(sock_path):
    """#5269 follow-up: a real launch's engine refused to start, "another engine is live" -- the
    other engine was itself. The launcher binds before the lifespan's claim, and the claim's fd scan
    (3..1023) cannot see a descriptor past 1023. The launcher now records what it bound, so the
    claim recognises it however many files the engine has open."""
    from fichero_server.__main__ import _bind_uds_socket

    spare = [open(os.devnull) for _ in range(1100)]             # push the next fd past 1023
    try:
        mine = _bind_uds_socket(sock_path)
        assert mine.fileno() > 1023
        try:
            claim_uds_path(sock_path)                           # ours: no refusal
            assert Path(sock_path).exists()
        finally:
            mine.close()
    finally:
        for handle in spare:
            handle.close()
        uds_claim._BOUND_HERE.clear()


def test_no_path_at_all_is_free(sock_path):
    assert claim_uds_path(sock_path) is None                    # no refusal
    assert not Path(sock_path).exists()                         # and nothing created


def test_the_embedded_launcher_refuses_a_live_socket_and_binds_a_stale_one(sock_path):
    from fichero_server.__main__ import _bind_uds_socket, _release_uds_path

    server = _live_engine(sock_path)
    try:
        with pytest.raises(SystemExit, match="another engine is live"):
            _bind_uds_socket(sock_path)
    finally:
        server.close()
    # now only the (stale) file is left
    bound = _bind_uds_socket(sock_path)
    ino = os.stat(sock_path).st_ino
    bound.close()
    _release_uds_path(sock_path, ino)                           # still ours: removed
    assert not Path(sock_path).exists()


def test_on_exit_an_engine_never_unlinks_a_socket_someone_else_now_holds(sock_path):
    from fichero_server.__main__ import _release_uds_path

    server = _live_engine(sock_path)
    try:
        _release_uds_path(sock_path, bound_inode=-1)            # not the inode it bound
        assert Path(sock_path).exists()
    finally:
        server.close()


def test_startup_refuses_before_writing_the_bootstrap_token(sock_path, monkeypatch):
    """Through the real lifespan: a live engine on FICHERO_UDS_PATH stops startup BEFORE
    `.api-key` is written."""
    import asyncio

    from fichero_server.api import main

    written: list[bool] = []
    monkeypatch.setattr(main, "_ensure_bootstrap_token_written", lambda: written.append(True))
    monkeypatch.setenv("FICHERO_UDS_PATH", sock_path)
    server = _live_engine(sock_path)

    async def start():
        async with main.app.router.lifespan_context(main.app):
            pass

    try:
        with pytest.raises(EngineAlreadyServing):
            asyncio.run(start())
    finally:
        server.close()
    assert written == []                                        # the token was never rewritten


def test_the_owner_is_the_outermost_app_or_dev_external(monkeypatch):
    for executable, owner in (
        ("/Applications/Fichero.app/Contents/Resources/python/bin/python3", "/Applications/Fichero.app"),
        ("/Applications/Fichero.app/Contents/Frameworks/Python.framework/Versions/3.12/Resources/"
         "Python.app/Contents/MacOS/Python", "/Applications/Fichero.app"),
        ("/opt/homebrew/Cellar/python@3.12/3.12.13/Frameworks/Python.framework/Versions/3.12/"
         "Resources/Python.app/Contents/MacOS/Python", "dev external"),
        ("/Users/someone/code/fichero/.venv/bin/python", "dev external"),
    ):
        monkeypatch.setattr(uds_claim.sys, "executable", executable)
        assert engine_owner() == owner, executable


def test_health_names_the_engine_to_a_local_caller_only(monkeypatch):
    from fastapi.testclient import TestClient

    from fichero_server.api.main import app

    monkeypatch.setattr(uds_claim, "engine_owner", lambda: "/Applications/Fichero.app")
    local = TestClient(app).get("/api/health").json()
    assert (local["engine_pid"], local["engine_owner"]) == (os.getpid(), "/Applications/Fichero.app")
    remote = TestClient(app, client=("192.0.2.10", 5000)).get("/api/health").json()
    assert remote["engine_owner"] is None                       # no local path over the network
