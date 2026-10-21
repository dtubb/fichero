"""The engine's real entry point starts and serves (#5228).

WHY: the embedded app runs `fichero_server.__main__.main()`; the dev engine and every other test
start the ASGI app through uvicorn directly. So a crash in `main()` itself reached nobody but the
shipped app: on 2026-09-28 a function-local `import threading` further down `main()` made an
earlier use raise UnboundLocalError, and the bundled engine died on its first line while the whole
suite stayed green. This runs `main()` for real on a private socket and waits for /api/health.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def _health(sock_path: str) -> dict | None:
    probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    probe.settimeout(2)
    try:
        probe.connect(sock_path)
        probe.sendall(b"GET /api/health HTTP/1.0\r\nHost: localhost\r\n\r\n")
        raw = b""
        while chunk := probe.recv(65536):
            raw += chunk
        return json.loads(raw.split(b"\r\n\r\n", 1)[1])
    except (OSError, ValueError, IndexError):
        return None
    finally:
        probe.close()


def test_main_starts_and_answers_health_on_its_socket():
    home = tempfile.mkdtemp(prefix="fem-")
    sock_dir = tempfile.mkdtemp(dir="/tmp", prefix="fem-")          # sun_path caps near 104 bytes
    sock_path = str(Path(sock_dir) / "e.sock")
    # Its own state: the pytest process may hold app.duckdb at the inherited FICHERO_BASE_PATH (earlier tests open the app DB
    # in-process), and a second process cannot lock it; nothing of the shell's or the suite's FICHERO_* reaches the engine.
    env = {
        **{key: value for key, value in os.environ.items() if not key.startswith("FICHERO_")},
        "HOME": home,
        "FICHERO_BASE_PATH": home,
        "FICHERO_UDS_PATH": sock_path,
        "FICHERO_BOOTSTRAP_TOKEN": "test-token-main-serves",
        "FICHERO_SKIP_DEFAULT_WORKFLOWS": "1",
    }
    process = subprocess.Popen(
        [sys.executable, "-c", "from fichero_server.__main__ import main; main()"],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    try:
        deadline = time.monotonic() + 90
        body = None
        while time.monotonic() < deadline and process.poll() is None:
            body = _health(sock_path)
            if body is not None:
                break
            time.sleep(0.25)
        if body is None:
            process.kill()
            out = process.communicate(timeout=10)[0].decode(errors="replace")[-3000:]
            raise AssertionError(f"main() never answered /api/health (exit {process.returncode}):\n{out}")
        assert body.get("status") in {"ok", "healthy"} or "engine_pid" in body, body
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(15)
            except subprocess.TimeoutExpired:
                process.kill()


def test_main_gates_multiuser_env_without_an_owner_password_and_health_says_why():
    """`multiuser.env-without-owner-password-starts-off` (#5908), the app's own path: the embedded app starts the engine through
    `main()` with FICHERO_MULTIUSER on; with no owner password ever chosen the engine must still serve, with Multi-user off and
    the reason in health. An inherited FICHERO_GATE_MULTIUSER_ENV=0 must not turn the gate off (main() assigns it)."""
    home = tempfile.mkdtemp(prefix="fem-")
    sock_dir = tempfile.mkdtemp(dir="/tmp", prefix="fem-")
    sock_path = str(Path(sock_dir) / "e.sock")
    env = {
        **{key: value for key, value in os.environ.items() if not key.startswith("FICHERO_")},  # nothing of the shell's reaches it
        "HOME": home, "FICHERO_UDS_PATH": sock_path, "FICHERO_BOOTSTRAP_TOKEN": "test-token-main-gates",
        "FICHERO_SKIP_DEFAULT_WORKFLOWS": "1", "FICHERO_MULTIUSER": "1", "FICHERO_GATE_MULTIUSER_ENV": "0",
        "FICHERO_BASE_PATH": home,
    }
    log = open(Path(home) / "engine.log", "wb")  # a file, never an unread pipe that could fill and block the engine
    process = subprocess.Popen(
        [sys.executable, "-c", "from fichero_server.__main__ import main; main()"],
        env=env, stdout=log, stderr=subprocess.STDOUT,
    )
    try:
        deadline = time.monotonic() + 90
        body = None
        while time.monotonic() < deadline and process.poll() is None:
            body = _health(sock_path)
            if body is not None:
                break
            time.sleep(0.25)
        assert body is not None, f"main() never answered /api/health (exit {process.poll()}):\n{(Path(home) / 'engine.log').read_text(errors='replace')[-3000:]}"
        assert process.poll() is None, "the engine exited instead of starting with Multi-user off"
        assert body["dependencies"].get("multiuser") == "off: the owner has not chosen a password yet", body
    finally:
        log.close()
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(15)
            except subprocess.TimeoutExpired:
                process.kill()
