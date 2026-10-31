"""Shared helpers to boot the Fichero engine on a plain-HTTP UDS (and TCP).

The engine can bind a plaintext Unix-domain-socket ASGI server when
``FICHERO_UDS_PATH`` is set — the ``fichero_server.api.uds_transport:app``
wrapper stamps ``scope["fichero.transport"] = "uds"`` so
``_is_loopback_request`` trusts the connection as loopback-owner (TLS is
exempt on the UDS path; there is no network listener). This module knows how
to launch that server headlessly.

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
(``fichero_server.api.uds_transport``) are missing from site-packages. We
prepend the real engine ``src`` onto ``PYTHONPATH`` for the subprocess,
derived from this file's own location so it works in ANY worktree — never a
machine-specific absolute path (#4227 rename post-mortem: the pre-rename
version of this harness hardcoded one checkout). Override with
``FICHERO_ENGINE_SRC`` if the engine lives elsewhere.
"""

from __future__ import annotations

import atexit
import os
import secrets
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

# This file lives in fichero-server/scripts/, so src/ is a sibling of its
# parent — worktree-relative, not one machine's checkout path.
DEFAULT_ENGINE_SRC = str(Path(__file__).resolve().parent.parent / "src")


def engine_src() -> str:
    return os.environ.get("FICHERO_ENGINE_SRC", DEFAULT_ENGINE_SRC)


def _child_env(*, base_path: str, token: str, uds_path: str | None = None) -> dict[str, str]:
    env = dict(os.environ)
    src = engine_src()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{src}:{existing}" if existing else src
    env["FICHERO_MULTIUSER"] = "0"
    from fichero_server.security.real_data_guard import refuse_real_base

    refuse_real_base(base_path)  # a probe engine never writes into the owner's real libraries
    env["FICHERO_BASE_PATH"] = base_path
    # The model stores follow the base path unless told otherwise (#5530); a probe engine keeps
    # using the models this Mac already has, as it did before.
    env.setdefault(
        "FICHERO_MODEL_STORE_ROOT", str(Path.home() / "Library" / "Application Support" / "Fichero")
    )
    # CRITICAL: token adoption WRITES .api-key. Without an isolated token
    # dir a probe engine rewrites the USER'S container key and every live
    # app session starts failing sign-in (the 2026-08-24 pathology —
    # reproduced live 2026-08-27 by this very harness. Sorry, Daniel).
    env["FICHERO_TOKEN_DIR"] = base_path
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


#: The engines this process started and has not stopped: ended at exit, on SIGTERM/SIGINT/SIGHUP, whatever the script
#: that started them did. Four of them were found on the Air on 2026-10-30, left by check scripts that died: 1.5-1.7 GB
#: each, 6.4 GB of an 8 GB Mac, since Oct 24.
_LIVE: "set[EngineProcess]" = set()
_LIVE_LOCK = threading.Lock()
_HOOKS_INSTALLED = False


def _stop_every_engine(*_args) -> None:
    with _LIVE_LOCK:
        engines = list(_LIVE)
    for engine in engines:
        try:
            engine.stop()
        except Exception:  # noqa: BLE001 -- nothing to do about it at exit
            pass


def _install_hooks() -> None:
    """Once: stop every live engine at interpreter exit and on the signals that kill a script outright. A handler is set
    only where none is (a test runner's own stays), and the default action follows so the signal still ends the process.
    SIGINT is not here: Python turns it into KeyboardInterrupt, which ends the script through atexit."""
    global _HOOKS_INSTALLED
    if _HOOKS_INSTALLED:
        return
    _HOOKS_INSTALLED = True
    atexit.register(_stop_every_engine)
    if threading.current_thread() is not threading.main_thread():
        return
    for sig in (signal.SIGTERM, signal.SIGHUP):
        if signal.getsignal(sig) not in (signal.SIG_DFL, None):
            continue

        def ended(signum, _frame):
            _stop_every_engine()
            signal.signal(signum, signal.SIG_DFL)
            os.kill(os.getpid(), signum)

        signal.signal(sig, ended)


#: The child's own watch (`-c`): the engine ends itself when the process that started it is gone (SIGKILL, a crash: no
#: atexit runs then). `os.getppid()` turns 1 (launchd) when the parent dies. Then it runs uvicorn's `main` in place.
_WATCH_THE_PARENT = """
import os, sys, threading, time
parent = os.getppid()
def watch():
    while os.getppid() == parent:
        time.sleep(1.0)
    os._exit(0)
threading.Thread(target=watch, daemon=True, name="parent-watch").start()
sys.argv = ["uvicorn", *sys.argv[1:]]
from uvicorn.main import main
main()
"""


class EngineProcess:
    """A uvicorn subprocess bound to a UDS or a TCP loopback port.

    Never left behind: it runs in its own process group (so its own children go with it), it ends itself when the
    process that started it is gone, and the starter stops it at exit or on a signal (`_install_hooks`).
    """

    def __init__(self, proc: subprocess.Popen, *, token: str, base_path: str,
                 uds_path: str | None = None, port: int | None = None,
                 log_path: str | None = None):
        self.proc = proc
        self.token = token
        self.base_path = base_path
        self.uds_path = uds_path
        self.port = port
        self.log_path = log_path
        with _LIVE_LOCK:
            _LIVE.add(self)

    # --- httpx transport helpers -------------------------------------------
    def httpx_kwargs(self) -> dict:
        import httpx

        if self.uds_path is not None:
            return dict(
                transport=httpx.HTTPTransport(uds=self.uds_path),
                base_url="http://localhost",
            )
        return dict(base_url=f"http://127.0.0.1:{self.port}")

    def _signal_group(self, sig: int) -> None:
        try:
            os.killpg(self.proc.pid, sig)  # the engine and anything it forked (its embedder seed, a worker)
        except ProcessLookupError:
            pass
        except PermissionError:  # not our group after all: the one process
            self.proc.send_signal(sig)

    def stop(self) -> None:
        if self.proc.poll() is None:
            self._signal_group(signal.SIGTERM)
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._signal_group(signal.SIGKILL)
                self.proc.wait(timeout=10)
        if self.uds_path:
            Path(self.uds_path).unlink(missing_ok=True)
        with _LIVE_LOCK:
            _LIVE.discard(self)


def start_engine(*, transport: str = "uds", token: str | None = None,
                 log_dir: str | None = None, ready_timeout: float = 60.0,
                 base_path: str | None = None) -> EngineProcess:
    """Launch uvicorn on a UDS ('uds') or plain-HTTP TCP loopback ('tcp').

    Blocks until ``/api/health`` returns 200 or ``ready_timeout`` elapses.
    The TCP path here is PLAIN HTTP for profiling convenience only — the real
    engine mandates TLS on TCP; health is unauthenticated so no token is needed.
    """
    import httpx

    token = token or secrets.token_urlsafe(24)
    base_path = base_path or tempfile.mkdtemp(prefix="fich_base_")
    log_dir = log_dir or tempfile.gettempdir()
    log_path = os.path.join(log_dir, f"uv_{transport}_{secrets.token_hex(3)}.log")
    logf = open(log_path, "w")

    if transport == "uds":
        uds_path = _short_sock_path()
        Path(uds_path).unlink(missing_ok=True)
        cmd = [
            sys.executable, "-c", _WATCH_THE_PARENT,
            "fichero_server.api.uds_transport:app",
            "--uds", uds_path,
            "--log-level", "warning",
        ]
        env = _child_env(base_path=base_path, token=token, uds_path=uds_path)
        port = None
    elif transport == "tcp":
        uds_path = None
        port = _free_tcp_port()
        cmd = [
            sys.executable, "-c", _WATCH_THE_PARENT,
            "fichero_server.api.main:app",
            "--host", "127.0.0.1",
            "--port", str(port),
            "--log-level", "warning",
        ]
        env = _child_env(base_path=base_path, token=token, uds_path=None)
    else:
        raise ValueError(f"unknown transport {transport!r}")

    _install_hooks()
    # Its own process group: `stop` ends the engine and whatever it forked, and a Ctrl-C to the script's group does
    # not reach it half-way (the hook stops it in order).
    proc = subprocess.Popen(cmd, env=env, stdout=logf, stderr=subprocess.STDOUT, start_new_session=True)
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
