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
    env = {
        **os.environ,
        "HOME": home,
        "FICHERO_UDS_PATH": sock_path,
        "FICHERO_BOOTSTRAP_TOKEN": "test-token-main-serves",
        "FICHERO_SKIP_DEFAULT_WORKFLOWS": "1",
    }
    env.pop("FICHERO_TCP_TLS_ALSO", None)
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
