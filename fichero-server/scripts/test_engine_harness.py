#!/usr/bin/env python
"""ONE spawn-per-run engine harness for every live test consumer (2026-08-04).

Swift unit suites, XCUITest, the scripted UX smoke, CLI tests and MCP tests all
provision their engine through THIS script — one implementation, so "how a live
test gets an engine" cannot drift per consumer (#4250, #4241). It:

1. seeds a fresh synthetic library (``seed_test_library.py --full`` — the same
   deterministic fixture everywhere) into a per-run temp dir,
2. spawns the engine on a temp Unix-domain socket (owner-trusted, no TLS), with
   ``HOME`` pointed at a disposable app-home so NOTHING touches real container
   paths (the #4537 class rule),
3. waits — bounded — until ``/api/health`` answers over the socket, and FAILS
   LOUDLY with the engine's stderr tail if it does not (never a silent green),
4. prints one ready-JSON line to stdout and keeps running,
5. tears down on SIGTERM/SIGINT, when the engine dies, or when the consumer
   that launched it dies (double parent-pid accountability: the engine watches
   this script via FICHERO_PARENT_PID (#4400), and this script watches ITS
   parent) — no orphans, socket unlinked, temp dir removed.

Usage:
    PYTHONPATH=fichero-server/src python fichero-server/scripts/test_engine_harness.py
        [--socket PATH] [--seed-mode full|with-files|plain] [--timeout SECS]
        [--keep-dir]
    PYTHONPATH=fichero-server/src python fichero-server/scripts/test_engine_harness.py --self-test

Ready line (single JSON object, then a flush):
    {"socket": ..., "library": ..., "app_home": ..., "engine_pid": ...,
     "harness_pid": ..., "expected": {...}, "keys": {...}, "full_ids": {...}}

Consumers: read stdout until the first line, parse it, run, then SIGTERM this
process. If this process exits before printing the ready line, the engine
never became usable — treat that as a FAILURE, not a skip.

Exit codes: 0 clean stop · 2 usage · 3 engine never became ready ·
4 engine died while serving · 5 self-test failure.
"""

from __future__ import annotations

import argparse
import http.client
import importlib.util
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SERVER_SRC = REPO / "fichero-server" / "src"
_SEEDER_PATH = Path(__file__).resolve().parent / "seed_test_library.py"

READY_TIMEOUT_DEFAULT = 90.0
STOP_GRACE_SECONDS = 5.0


def _load_seeder():
    spec = importlib.util.spec_from_file_location("seed_test_library", _SEEDER_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load seeder at {_SEEDER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class UDSHTTPConnection(http.client.HTTPConnection):
    """stdlib HTTP client over an AF_UNIX socket — no third-party dependency."""

    def __init__(self, uds_path: str, timeout: float = 5.0) -> None:
        super().__init__("localhost", timeout=timeout)
        self.uds_path = uds_path

    def connect(self) -> None:  # noqa: D102 — http.client contract
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        sock.connect(self.uds_path)
        self.sock = sock


def http_get(uds_path: str, url_path: str, headers: dict | None = None,
             timeout: float = 5.0) -> tuple[int, bytes]:
    conn = UDSHTTPConnection(uds_path, timeout=timeout)
    try:
        conn.request("GET", url_path, headers=headers or {})
        resp = conn.getresponse()
        return resp.status, resp.read()
    finally:
        conn.close()


def default_socket_path() -> str:
    """A short socket path under the AF_UNIX sun_path (~104 byte) limit."""
    short = uuid.uuid4().hex[:10]
    return str(Path(tempfile.gettempdir()) / f"fih-{short}.sock")


class EngineHarness:
    """Seed + spawn + wait + teardown. The whole lifecycle in one place."""

    def __init__(self, socket_path: str | None = None, seed_mode: str = "full",
                 timeout: float = READY_TIMEOUT_DEFAULT, keep_dir: bool = False):
        self.socket_path = socket_path or default_socket_path()
        self.seed_mode = seed_mode
        self.timeout = timeout
        self.keep_dir = keep_dir
        self.temp_dir: Path | None = None
        self.library: Path | None = None
        self.app_home: Path | None = None
        self.engine: subprocess.Popen | None = None
        self._stderr_file = None
        self.summary: dict = {}

    # -- lifecycle ----------------------------------------------------------

    def start(self) -> dict:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="fichero-harness-"))
        self.library = self.temp_dir / "Seed.fichero"
        self.app_home = self.temp_dir / "AppHome"
        self.app_home.mkdir()

        seeder = _load_seeder()
        self.summary = seeder.seed(
            self.library,
            with_files=self.seed_mode in ("with-files", "full"),
            full=self.seed_mode == "full",
        )

        Path(self.socket_path).unlink(missing_ok=True)
        env = dict(os.environ)
        env["PYTHONPATH"] = str(SERVER_SRC)
        env["FICHERO_UDS_PATH"] = self.socket_path
        env["FICHERO_MULTIUSER"] = "0"
        env["FICHERO_FEATURE_TIER"] = "dev"
        env["FICHERO_DISABLE_AUTH"] = "1"
        # #4537 class rule: the engine's own dotfiles/state land in the
        # disposable app-home, never the real container or real $HOME.
        env["HOME"] = str(self.app_home)
        # #4400: the engine self-terminates if THIS process dies.
        env["FICHERO_PARENT_PID"] = str(os.getpid())

        self._stderr_file = open(self.temp_dir / "engine-stderr.log", "wb")  # noqa: SIM115 — outlives this frame; closed in stop()
        self.engine = subprocess.Popen(
            [
                sys.executable, "-m", "uvicorn",
                "fichero_server.api.uds_transport:app",
                "--uds", self.socket_path,
                "--ws", "websockets-sansio",
            ],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=self._stderr_file,
        )
        self._wait_ready()
        return self.ready_payload()

    def ready_payload(self) -> dict:
        assert self.engine is not None
        return {
            "socket": self.socket_path,
            "library": str(self.library),
            "app_home": str(self.app_home),
            "engine_pid": self.engine.pid,
            "harness_pid": os.getpid(),
            "seed_mode": self.seed_mode,
            "expected": self.summary.get("expected", {}),
            "keys": self.summary.get("keys", {}),
            "full_ids": self.summary.get("full_ids", {}),
        }

    def _stderr_tail(self, limit: int = 4000) -> str:
        try:
            if self._stderr_file:
                self._stderr_file.flush()
            log = self.temp_dir / "engine-stderr.log" if self.temp_dir else None
            if log and log.is_file():
                return log.read_bytes()[-limit:].decode("utf-8", "replace")
        except OSError:
            pass
        return "<no stderr captured>"

    def _wait_ready(self) -> None:
        """Bounded wait for /api/health over the socket. Loud on failure."""
        deadline = time.monotonic() + self.timeout
        last_error = "socket never appeared"
        while time.monotonic() < deadline:
            if self.engine is not None and self.engine.poll() is not None:
                self.stop()
                raise RuntimeError(
                    f"engine exited (status {self.engine.returncode}) before "
                    f"becoming ready; stderr tail:\n{self._stderr_tail()}"
                )
            if Path(self.socket_path).exists():
                try:
                    status, _ = http_get(self.socket_path, "/api/health", timeout=2.0)
                    if status == 200:
                        return
                    last_error = f"/api/health answered {status}"
                except OSError as exc:
                    last_error = f"connect/health failed: {exc}"
            time.sleep(0.25)
        tail = self._stderr_tail()
        self.stop()
        raise RuntimeError(
            f"engine not ready within {self.timeout:.0f}s ({last_error}); "
            f"stderr tail:\n{tail}"
        )

    def stop(self) -> None:
        """Kill + reap the engine, unlink the socket, remove the temp dir."""
        if self.engine is not None and self.engine.poll() is None:
            self.engine.terminate()
            try:
                self.engine.wait(timeout=STOP_GRACE_SECONDS)
            except subprocess.TimeoutExpired:
                self.engine.kill()
                self.engine.wait(timeout=STOP_GRACE_SECONDS)
        if self._stderr_file:
            self._stderr_file.close()
            self._stderr_file = None
        Path(self.socket_path).unlink(missing_ok=True)
        if self.temp_dir and not self.keep_dir:
            shutil.rmtree(self.temp_dir, ignore_errors=True)


def serve(args: argparse.Namespace) -> int:
    harness = EngineHarness(
        socket_path=args.socket,
        seed_mode=args.seed_mode,
        timeout=args.timeout,
        keep_dir=args.keep_dir,
    )

    stopping = False

    def _on_signal(signum, frame):  # noqa: ARG001
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)

    try:
        payload = harness.start()
    except RuntimeError as exc:
        print(f"HARNESS FAILED: {exc}", file=sys.stderr)
        return 3

    print(json.dumps(payload), flush=True)

    launcher_ppid = os.getppid()
    rc = 0
    while not stopping:
        if harness.engine is not None and harness.engine.poll() is not None:
            print(
                "HARNESS FAILED: engine died while serving "
                f"(status {harness.engine.returncode}); stderr tail:\n"
                f"{harness._stderr_tail()}",
                file=sys.stderr,
            )
            rc = 4
            break
        # The consumer that launched us is gone (SIGKILL, crash): tear down.
        if os.getppid() != launcher_ppid:
            break
        time.sleep(0.5)
    harness.stop()
    return rc


def self_test(args: argparse.Namespace) -> int:
    """The harness's own proof: a live round-trip, a clean teardown, and a
    demonstration that the ready-wait FAILS rather than passing vacuously."""
    harness = EngineHarness(seed_mode=args.seed_mode, timeout=args.timeout)
    try:
        payload = harness.start()
    except RuntimeError as exc:
        print(f"self-test FAILED to start: {exc}", file=sys.stderr)
        return 5

    try:
        status, body = http_get(payload["socket"], "/api/health")
        assert status == 200, f"/api/health -> {status}"

        status, body = http_get(
            payload["socket"],
            "/api/documents",
            headers={"X-Fichero-Library-Path": payload["library"]},
        )
        assert status == 200, f"/api/documents -> {status}: {body[:200]!r}"
        listed = json.loads(body)
        rows = listed["items"] if isinstance(listed, dict) and "items" in listed else listed
        assert isinstance(rows, list) and rows, f"no documents listed: {body[:200]!r}"

        engine_pid = payload["engine_pid"]
        temp_dir = harness.temp_dir
    except AssertionError as exc:
        print(f"self-test FAILED live round-trip: {exc}", file=sys.stderr)
        harness.stop()
        return 5

    harness.stop()

    # Teardown proof: engine reaped, socket gone, temp dir gone.
    try:
        os.kill(engine_pid, 0)
        alive = True
    except (ProcessLookupError, PermissionError):
        alive = False
    if alive:
        print(f"self-test FAILED: engine pid {engine_pid} survived stop()",
              file=sys.stderr)
        return 5
    if Path(payload["socket"]).exists():
        print("self-test FAILED: socket file survived stop()", file=sys.stderr)
        return 5
    if temp_dir and temp_dir.exists():
        print("self-test FAILED: temp dir survived stop()", file=sys.stderr)
        return 5

    # The guard must be able to fire (#4487): a socket nothing binds must
    # produce a loud RuntimeError, not a quiet pass.
    dud = EngineHarness(seed_mode="plain", timeout=0.1)
    dud.temp_dir = Path(tempfile.mkdtemp(prefix="fichero-harness-dud-"))
    dud.library = dud.temp_dir / "unused.fichero"
    dud.app_home = dud.temp_dir / "AppHome"
    try:
        dud._wait_ready()
        print("self-test FAILED: ready-wait passed against nothing",
              file=sys.stderr)
        return 5
    except RuntimeError:
        pass
    finally:
        shutil.rmtree(dud.temp_dir, ignore_errors=True)

    print(
        "test_engine_harness self-test: OK — seeded full library, engine ready "
        "over UDS, /api/health 200, documents listed, teardown left no engine "
        "process, no socket, no temp dir; ready-wait proven to fail loudly."
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--socket", help="AF_UNIX socket path (default: short temp path)")
    parser.add_argument("--seed-mode", choices=["full", "with-files", "plain"],
                        default="full")
    parser.add_argument("--timeout", type=float, default=READY_TIMEOUT_DEFAULT)
    parser.add_argument("--keep-dir", action="store_true",
                        help="keep the per-run temp dir for debugging")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test(args)
    return serve(args)


if __name__ == "__main__":
    raise SystemExit(main())
