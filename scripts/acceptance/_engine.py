"""Shared plumbing for the acceptance run: ONE private engine, ONE test library.

`engine()` starts an engine from THIS worktree's source on its own Unix socket, with its
own state directory and key file, so it shares nothing with the maintainer's app or its
engine: not the socket, not `app.duckdb`, not `.api-key`. It is a context manager, and
its `finally` stops the engine on every path -- normal exit, exception, Ctrl-C, SIGTERM,
SIGHUP -- then removes the socket. A previous attempt left its engine running
unattended; that is what this file exists to prevent.

Everything talks to the engine through `fichero_cli.FicheroClient` (the CLI's own HTTP
client) or the MCP tool functions in `fichero_mcp.server` (one client call each).
Nothing here opens a `.duckdb` file or writes SQL.

    ACCEPTANCE_OUT   where results, the engine log and the engine's state go
                     (default: acceptance-out/ at the repo root; never committed)
"""

from __future__ import annotations

import contextlib
import json
import os
import signal
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Iterator

REPO = Path(__file__).resolve().parents[2]
PYTHON = "/Users/danieltubb/code/fichero/.venv/bin/python"
CORPUS = Path.home() / "Fichero Test Corpus"
LIBRARY_ROOT = Path.home() / "Fichero Test Library"
LIBRARY = LIBRARY_ROOT / "Acceptance 2026-09-27.fichero"
# A Unix socket path is limited to 104 bytes on macOS, so the socket sits in /tmp under a
# name that says whose it is.
SOCKET = Path("/tmp/fichero-acceptance.sock")
OUT = Path(os.environ.get("ACCEPTANCE_OUT", REPO / "acceptance-out"))
STATE = OUT / "engine-state"

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp", ".jp2", ".gif", ".bmp"}

for _sub in ("fichero-cli/src", "fichero-server/src", "fichero-mcp/src"):
    if str(REPO / _sub) not in sys.path:
        sys.path.insert(0, str(REPO / _sub))


def engine_env() -> dict[str, str]:
    env = dict(os.environ)
    env.update(
        {
            "PYTHONPATH": os.pathsep.join(str(REPO / s) for s in ("fichero-server/src", "fichero-cli/src")),
            "FICHERO_UDS_PATH": str(SOCKET),
            # Own state dir: app.duckdb, thumbnails, global library -- never the maintainer's.
            "FICHERO_BASE_PATH": str(STATE),
            # Own key file (api/auth.py: FICHERO_TOKEN_DIR is "for TEST engines only").
            "FICHERO_TOKEN_DIR": str(STATE),
            "FICHERO_LIBRARY_ALLOWED_ROOTS": str(LIBRARY_ROOT),
            "FICHERO_BACKEND_STABLE_MODE": "1",
            "FICHERO_SKIP_EMBEDDINGS_PREWARM": "1",
            "FICHERO_SKIP_DERIVATIVE_RESUME": "1",
            # The engine exits when this process does (#4400), so a crashed or killed
            # acceptance script can never leave its engine running unattended.
            "FICHERO_PARENT_PID": str(os.getpid()),
        }
    )
    for leak in ("FICHERO_TCP_TLS_ALSO", "FICHERO_API_URL", "FICHERO_BOOTSTRAP_TOKEN", "FICHERO_UDS"):
        env.pop(leak, None)
    return env


def client_env() -> None:
    """Point this process's FicheroClient (CLI and MCP alike) at OUR engine and library."""
    os.environ["FICHERO_UDS"] = str(SOCKET)
    os.environ["FICHERO_LIBRARY_PATH"] = str(LIBRARY)
    os.environ.pop("FICHERO_API_URL", None)
    key = STATE / ".api-key"
    if key.exists():
        os.environ["FICHERO_API_KEY"] = key.read_text().strip()


def guard() -> None:
    """Refuse to run against anything but the acceptance library + socket."""
    lib = os.environ.get("FICHERO_LIBRARY_PATH", "")
    if not lib.startswith(str(LIBRARY_ROOT) + "/"):
        raise SystemExit(f"refusing: FICHERO_LIBRARY_PATH={lib!r} is not the test library")
    if os.environ.get("FICHERO_UDS", "") != str(SOCKET):
        raise SystemExit("refusing: FICHERO_UDS is not the acceptance engine's socket")


def client(*, library: bool = True):
    """The CLI's own client, on our socket. `library=False` sends no library header:
    the start-up probe uses it, because a request that names a library path creates
    that package on disk (a finding of this run, see the report)."""
    from fichero_cli.client import FicheroClient

    client_env()
    guard()
    c = FicheroClient(client_name="fichero-acceptance", timeout=600.0)
    if not library:
        # `library_path=""` is documented as "explicit no library" but the constructor's
        # `library_path or os.environ[...]` turns "" back into the env value (a finding).
        c.library_path = None
        c._discover_library_path = False
    return c


def load_avg() -> float:
    return os.getloadavg()[0]


def wait_for_load(limit: float = 40.0) -> None:
    while load_avg() > limit:
        print(f"load {load_avg():.1f} > {limit}; pausing", flush=True)
        time.sleep(30)


def _socket_is_live() -> bool:
    import socket as _s

    probe = _s.socket(_s.AF_UNIX, _s.SOCK_STREAM)
    try:
        probe.connect(str(SOCKET))
        return True
    except OSError:
        return False
    finally:
        probe.close()


@contextlib.contextmanager
def engine(log_name: str = "engine.log") -> Iterator[subprocess.Popen]:
    """Start our engine; ALWAYS stop it on the way out."""
    wait_for_load()
    if SOCKET.exists():
        if _socket_is_live():
            raise SystemExit(f"{SOCKET} is live: another acceptance engine is running; stop it first")
        SOCKET.unlink()
    STATE.mkdir(parents=True, exist_ok=True)
    log = open(OUT / log_name, "ab")
    proc = subprocess.Popen(
        [PYTHON, "-m", "fichero_server"],
        cwd=str(REPO),
        env=engine_env(),
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,  # its own process group: a stop takes every child with it
    )
    (OUT / "engine.pid").write_text(str(proc.pid))

    def _on_signal(signum, _frame):
        raise KeyboardInterrupt(f"signal {signum}")

    old = {s: signal.signal(s, _on_signal) for s in (signal.SIGTERM, signal.SIGHUP)}
    try:
        deadline = time.monotonic() + 180
        while True:
            if proc.poll() is not None:
                raise RuntimeError(f"engine exited during start (code {proc.returncode}); see {OUT / log_name}")
            if _socket_is_live() and (STATE / ".api-key").exists():
                try:
                    with client(library=False) as c:
                        c.request("GET", "/api/health")
                    break
                except Exception:  # noqa: BLE001 -- still starting
                    pass
            if time.monotonic() > deadline:
                raise RuntimeError("engine did not answer within 180 s")
            time.sleep(1)
        print(f"engine {proc.pid} up on {SOCKET}", flush=True)
        yield proc
    finally:
        stop(proc)
        for s, h in old.items():
            signal.signal(s, h)
        log.close()


def stop(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGTERM)
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(proc.pid, signal.SIGKILL)
            proc.wait(timeout=10)
    # Anything left in the group (a worker that ignored SIGTERM) goes too.
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(proc.pid, signal.SIGKILL)
    SOCKET.unlink(missing_ok=True)
    (OUT / "engine.pid").unlink(missing_ok=True)
    print(f"engine {proc.pid} stopped (exit {proc.returncode})", flush=True)


def save(name: str, data: Any) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return path


def load(name: str) -> Any:
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def timed(fn: Callable[[], Any], runs: int = 5) -> tuple[Any, dict]:
    """One discarded cold run, then `runs` measured: median and max in ms, with the load."""
    fn()
    samples = []
    result = None
    for _ in range(runs):
        t0 = time.perf_counter()
        result = fn()
        samples.append((time.perf_counter() - t0) * 1000)
    return result, {
        "median_ms": round(statistics.median(samples), 1),
        "max_ms": round(max(samples), 1),
        "min_ms": round(min(samples), 1),
        "runs": runs,
        "load_1m": round(load_avg(), 1),
    }
