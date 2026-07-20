"""Shared helpers to boot the Fichero engine on a plain-HTTP UDS (and TCP).

The engine can bind a plaintext Unix-domain-socket ASGI server when
``FICHERO_UDS_PATH`` is set — the ``fichero.api.uds_transport:app`` wrapper
stamps ``scope["fichero.transport"] = "uds"`` so ``_is_loopback_request`` trusts
the connection as loopback-owner (TLS is exempt on the UDS path; there is no
network listener). This module knows how to launch that server headlessly.

Why the extra env:
  * ``FICHERO_BASE_PATH``      -> point app.duckdb / global.fichero at a fresh
                                  temp dir so we do NOT fight a live engine for
                                  the ``app.duckdb`` lock.
  * ``FICHERO_BOOTSTRAP_TOKEN``-> pin the bootstrap secret to a known value so a
                                  test/harness can present it without scraping
                                  the 0600 ``.api-key`` file.
  * ``FICHERO_MULTIUSER=0``    -> single-user mode: the loopback bootstrap token
                                  IS the owner credential.

Engine source: the venv here is a STALE non-editable copy, so newer modules
(``fichero.api.uds_transport``) are missing from site-packages. We prepend the
real engine ``src`` onto ``PYTHONPATH`` for the subprocess. Override with
``FICHERO_ENGINE_SRC`` if the engine lives elsewhere.
"""

from __future__ import annotations

import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

DEFAULT_ENGINE_SRC = "/Users/danieltubb/code/fichero/fichero-engine/src"


def engine_src() -> str:
    return os.environ.get("FICHERO_ENGINE_SRC", DEFAULT_ENGINE_SRC)


def _child_env(*, base_path: str, token: str, uds_path: str | None = None) -> dict[str, str]:
    env = dict(os.environ)
    src = engine_src()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{src}:{existing}" if existing else src
    env["FICHERO_MULTIUSER"] = "0"
    env["FICHERO_BASE_PATH"] = base_path
    env["FICHERO_BOOTSTRAP_TOKEN"] = token
    if uds_path is not None:
        env["FICHERO_UDS_PATH"] = uds_path
    else:
        env.pop("FICHERO_UDS_PATH", None)
    return env


def _short_sock_path() -> str:
    # UDS sun_path is ~104 bytes on macOS — keep it in /tmp and short.
    return f"/tmp/fich_uds_{secrets.token_hex(4)}.sock"


def _free_tcp_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class EngineProcess:
    """A uvicorn subprocess bound to a UDS or a TCP loopback port."""

    def __init__(self, proc: subprocess.Popen, *, token: str, base_path: str,
                 uds_path: str | None = None, port: int | None = None,
                 log_path: str | None = None):
        self.proc = proc
        self.token = token
        self.base_path = base_path
        self.uds_path = uds_path
        self.port = port
        self.log_path = log_path

    # --- httpx transport helpers -------------------------------------------
    def httpx_kwargs(self) -> dict:
        import httpx

        if self.uds_path is not None:
            return dict(
                transport=httpx.HTTPTransport(uds=self.uds_path),
                base_url="http://localhost",
            )
        return dict(base_url=f"http://127.0.0.1:{self.port}")

    def stop(self) -> None:
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=10)
        if self.uds_path:
            Path(self.uds_path).unlink(missing_ok=True)


def start_engine(*, transport: str = "uds", token: str | None = None,
                 log_dir: str | None = None, ready_timeout: float = 60.0) -> EngineProcess:
    """Launch uvicorn on a UDS ('uds') or plain-HTTP TCP loopback ('tcp').

    Blocks until ``/api/health`` returns 200 or ``ready_timeout`` elapses.
    The TCP path here is PLAIN HTTP for profiling convenience only — the real
    engine mandates TLS on TCP; health is unauthenticated so no token is needed.
    """
    import httpx

    token = token or secrets.token_urlsafe(24)
    base_path = tempfile.mkdtemp(prefix="fich_base_")
    log_dir = log_dir or tempfile.gettempdir()
    log_path = os.path.join(log_dir, f"uv_{transport}_{secrets.token_hex(3)}.log")
    logf = open(log_path, "w")

    if transport == "uds":
        uds_path = _short_sock_path()
        Path(uds_path).unlink(missing_ok=True)
        cmd = [
            sys.executable, "-m", "uvicorn",
            "fichero.api.uds_transport:app",
            "--uds", uds_path,
            "--log-level", "warning",
        ]
        env = _child_env(base_path=base_path, token=token, uds_path=uds_path)
        port = None
    elif transport == "tcp":
        uds_path = None
        port = _free_tcp_port()
        cmd = [
            sys.executable, "-m", "uvicorn",
            "fichero.api.main:app",
            "--host", "127.0.0.1",
            "--port", str(port),
            "--log-level", "warning",
        ]
        env = _child_env(base_path=base_path, token=token, uds_path=None)
    else:
        raise ValueError(f"unknown transport {transport!r}")

    proc = subprocess.Popen(cmd, env=env, stdout=logf, stderr=subprocess.STDOUT)
    ep = EngineProcess(proc, token=token, base_path=base_path,
                       uds_path=uds_path, port=port, log_path=log_path)

    # Poll for readiness via an actual health request.
    deadline = time.time() + ready_timeout
    last_err: Exception | None = None
    with httpx.Client(timeout=5, **ep.httpx_kwargs()) as client:
        while time.time() < deadline:
            if proc.poll() is not None:
                logf.flush()
                tail = Path(log_path).read_text()[-2000:]
                raise RuntimeError(
                    f"engine ({transport}) exited early rc={proc.returncode}\n--- log ---\n{tail}"
                )
            try:
                r = client.get("/api/health")
                if r.status_code == 200:
                    return ep
            except Exception as exc:  # not ready yet
                last_err = exc
            time.sleep(0.25)

    ep.stop()
    logf.flush()
    tail = Path(log_path).read_text()[-2000:]
    raise TimeoutError(
        f"engine ({transport}) not ready in {ready_timeout}s; last_err={last_err}\n--- log ---\n{tail}"
    )
