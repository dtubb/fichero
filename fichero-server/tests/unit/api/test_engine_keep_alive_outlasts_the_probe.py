"""The engine keeps an idle connection open longer than the app's health probe interval (`engine.health.probe-survives-a-closed-keep-alive`, #6372).

WHY: uvicorn closes an idle keep-alive connection after 5 s, the app probes every 5 s on one pooled client, so the probe sometimes
reused a connection the engine had just closed and the heartbeat read it as the engine not responding. The engine now waits 20 s.
Runs `main()` for real on a private socket (the shipped entry point), as `test_engine_main_serves.py` does.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REQUEST = b"GET /api/health HTTP/1.1\r\nHost: localhost\r\nConnection: keep-alive\r\n\r\n"


def _read_response(conn: socket.socket) -> bytes | None:
    """One HTTP/1.1 response by its Content-Length; None if the engine closed the connection."""
    raw = b""
    while b"\r\n\r\n" not in raw:
        chunk = conn.recv(65536)
        if not chunk:
            return None
        raw += chunk
    head, _, body = raw.partition(b"\r\n\r\n")
    length = next((int(line.split(b":")[1]) for line in head.split(b"\r\n") if line.lower().startswith(b"content-length")), 0)
    while len(body) < length:
        chunk = conn.recv(65536)
        if not chunk:
            return None
        body += chunk
    return head


def test_an_idle_connection_survives_longer_than_the_default_five_seconds():
    home = tempfile.mkdtemp(prefix="fka-")
    sock_dir = tempfile.mkdtemp(dir="/tmp", prefix="fka-")          # sun_path caps near 104 bytes
    sock_path = str(Path(sock_dir) / "e.sock")
    env = {
        **{key: value for key, value in os.environ.items() if not key.startswith("FICHERO_")},
        "HOME": home, "FICHERO_BASE_PATH": home, "FICHERO_UDS_PATH": sock_path,
        "FICHERO_BOOTSTRAP_TOKEN": "test-token-keep-alive", "FICHERO_SKIP_DEFAULT_WORKFLOWS": "1",
    }
    log = open(Path(home) / "engine.log", "wb")
    process = subprocess.Popen([sys.executable, "-c", "from fichero_server.__main__ import main; main()"],
                               env=env, stdout=log, stderr=subprocess.STDOUT)
    conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    conn.settimeout(10)
    try:
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline and process.poll() is None:
            try:
                conn.connect(sock_path)
                break
            except OSError:
                time.sleep(0.25)
        conn.sendall(REQUEST)
        assert _read_response(conn) is not None, "the first probe was not answered"
        time.sleep(7)  # past uvicorn's default 5 s, inside the 20 s the engine now allows
        conn.sendall(REQUEST)
        assert _read_response(conn) is not None, "the engine closed the idle connection before the next probe"
    finally:
        conn.close()
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(15)
            except subprocess.TimeoutExpired:
                process.kill()
