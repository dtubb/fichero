"""One engine per Unix-domain socket: a live engine's socket is never taken over (2026-09-28).

WHY: two engines ended up on one container socket and one `.api-key`. Starting an engine unlinked
whatever was at its socket path and bound its own (asyncio's `create_unix_server` does the same
silently), and its startup rewrote the bootstrap token -- so the engine the app had been talking
to kept running, unreachable, and the app's token no longer matched: 401s on some requests. Now an
engine claims its socket path first:

- something is LISTENING there (a `connect()` succeeds): another engine is live. Refuse to start,
  naming it (its `/api/health` pid and owner, when it answers). A successful connect, not an HTTP
  answer, is the test: a live engine too busy to answer within the probe's wait must not be
  mistaken for a dead one and have its socket unlinked.
- a socket file nobody listens on (`ECONNREFUSED`): a crashed engine's leftover. Reclaim it.
- a path that is not a socket: refuse; it is never unlinked.
- a socket this very process already holds (the embedded launcher binds before startup; uvicorn
  `--reload` binds in its supervisor): ours, nothing to do.

The claim runs before the bind and before `.api-key` is written, so a refused engine changes
nothing on disk.
"""

from __future__ import annotations

import errno
import json
import logging
import os
import socket
import stat
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

#: How long to wait for a live engine to say who it is. Only the NAMING waits on this; whether it
#: is live was already decided by the connect.
_PROBE_TIMEOUT_S = 2.0


class EngineAlreadyServing(RuntimeError):
    """Another engine is live on this socket path; this one must not start."""


def engine_owner() -> str:
    """Which app this engine belongs to: the `.app` bundle its interpreter lives in, or
    "dev external" (a venv or system Python, started by a script). The OUTERMOST `.app` not inside
    a `.framework` -- the embedded interpreter can sit in a Python.app within Fichero.app, and a
    Homebrew Python is itself a Python.app inside Python.framework."""
    parts = Path(sys.executable).absolute().parts
    for index, part in enumerate(parts):
        if part.endswith(".framework"):
            break
        if part.endswith(".app"):
            return str(Path(*parts[: index + 1]))
    return "dev external"


def _held_by_this_process(path: str) -> bool:
    wanted = {path, os.path.realpath(path)}
    for fd in range(3, 1024):
        try:
            if not stat.S_ISSOCK(os.fstat(fd).st_mode):
                continue
            probe = socket.socket(fileno=os.dup(fd))
        except OSError:
            continue
        try:
            if probe.family == socket.AF_UNIX and probe.getsockname() in wanted:
                return True
        except OSError:
            pass
        finally:
            probe.close()
    return False


def _who_is_there(connected: socket.socket) -> str:
    """Ask the live engine for /api/health, to NAME it in the refusal. Best effort."""
    try:
        connected.settimeout(_PROBE_TIMEOUT_S)
        connected.sendall(b"GET /api/health HTTP/1.0\r\nHost: localhost\r\n\r\n")
        raw = b""
        while chunk := connected.recv(65536):
            raw += chunk
        body = json.loads(raw.split(b"\r\n\r\n", 1)[1])
        return f"pid {body.get('engine_pid')}, owner {body.get('engine_owner') or 'not reported'}"
    except (OSError, ValueError, IndexError):
        return "it did not answer /api/health in time"


def claim_uds_path(path: str) -> None:
    """Make `path` free for this engine to bind, or raise `EngineAlreadyServing`."""
    try:
        mode = os.lstat(path).st_mode
    except FileNotFoundError:
        return
    if not stat.S_ISSOCK(mode):
        raise EngineAlreadyServing(
            f"refusing to start: {path} exists and is not a socket; it was left alone"
        )
    if _held_by_this_process(path):
        return
    probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        probe.settimeout(_PROBE_TIMEOUT_S)
        probe.connect(path)
    except OSError as exc:
        probe.close()
        if exc.errno in (errno.ECONNREFUSED, errno.ENOENT):
            Path(path).unlink(missing_ok=True)
            logger.info("reclaimed a stale engine socket at %s (nothing was listening)", path)
            return
        raise EngineAlreadyServing(f"refusing to start: cannot tell whether {path} is live ({exc})") from exc
    try:
        who = _who_is_there(probe)
    finally:
        probe.close()
    raise EngineAlreadyServing(
        f"refusing to start: another engine is live on {path} ({who}). Quit it first; its socket "
        "and the bootstrap token (.api-key) were left untouched."
    )


def uds_path_of_this_process() -> str | None:
    """The socket this engine was asked to serve: `FICHERO_UDS_PATH` (the embedded launcher and
    start_fichero_server.sh), else uvicorn's `--uds <path>` (the harnesses)."""
    env = (os.environ.get("FICHERO_UDS_PATH") or "").strip()
    if env:
        return env
    argv = sys.argv
    for index, arg in enumerate(argv):
        if arg == "--uds" and index + 1 < len(argv):
            return argv[index + 1]
        if arg.startswith("--uds="):
            return arg.split("=", 1)[1]
    return None
