"""The spawn-per-run engine harness, driven exactly as consumers drive it.

``scripts/test_engine_harness.py`` is the ONE way live tests provision an
engine (2026-08-04 decisions; #4250, #4241). This suite launches it as a real
subprocess — the same contract the Swift harness, the scripted UX smoke, and
CLI/MCP fixtures use — and proves the three properties that make it trustworthy:

1. it becomes ready and serves the seeded synthetic library over UDS,
2. stopping it leaves NO engine process, no socket, no temp dir (#4400),
3. a harness that cannot become ready FAILS LOUDLY (exit 3 + stderr), because
   a live plan with no engine must never read as green.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
HARNESS = REPO_ROOT / "fichero-server" / "scripts" / "test_engine_harness.py"
SERVER_SRC = REPO_ROOT / "fichero-server" / "src"


def _launch(*extra: str, timeout_line: float = 120.0) -> tuple[subprocess.Popen, dict]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SERVER_SRC)
    proc = subprocess.Popen(
        [sys.executable, str(HARNESS), *extra],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    # The contract: first stdout line is the ready JSON. No line = failure.
    deadline = time.monotonic() + timeout_line
    line = ""
    while time.monotonic() < deadline:
        line = proc.stdout.readline()
        if line:
            break
        if proc.poll() is not None:
            stderr = proc.stderr.read()
            raise AssertionError(
                f"harness exited {proc.returncode} before ready line; stderr:\n{stderr}"
            )
    if not line:
        proc.kill()
        raise AssertionError("harness printed no ready line in time")
    return proc, json.loads(line)


def _stop(proc: subprocess.Popen) -> int:
    proc.send_signal(signal.SIGTERM)
    try:
        return proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()
        raise


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


@pytest.fixture(scope="module")
def spawned_engine():
    """The reusable consumer-side fixture: one harness engine per module."""
    proc, ready = _launch()
    yield ready
    _stop(proc)


class TestSpawnPerRunHarness:
    def test_ready_payload_names_everything_a_consumer_needs(self, spawned_engine):
        for key in ("socket", "library", "app_home", "engine_pid", "expected",
                    "keys", "full_ids"):
            assert spawned_engine.get(key), f"ready payload missing {key!r}"
        assert spawned_engine["library"].endswith(".fichero")
        assert Path(spawned_engine["socket"]).exists()

    def test_live_round_trip_serves_the_seeded_library(self, spawned_engine):
        sys.path.insert(0, str(HARNESS.parent))
        try:
            from test_engine_harness import http_get
        finally:
            sys.path.pop(0)

        status, _ = http_get(spawned_engine["socket"], "/api/health")
        assert status == 200

        status, body = http_get(
            spawned_engine["socket"],
            "/api/documents",
            headers={"X-Fichero-Library-Path": spawned_engine["library"]},
        )
        assert status == 200
        listed = json.loads(body)
        rows = listed["items"] if isinstance(listed, dict) and "items" in listed else listed
        ids = {r["id"] for r in rows}
        # The deterministic full-seed rows are visible over the wire.
        assert spawned_engine["full_ids"]["folder-inbox"] in ids

    def test_stop_leaves_no_orphan_engine_no_socket(self):
        proc, ready = _launch()
        engine_pid = ready["engine_pid"]
        assert _pid_alive(engine_pid)
        rc = _stop(proc)
        assert rc == 0
        # give the reap a moment on a loaded machine
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and _pid_alive(engine_pid):
            time.sleep(0.2)
        assert not _pid_alive(engine_pid), "engine survived harness SIGTERM (#4400)"
        assert not Path(ready["socket"]).exists(), "socket file survived teardown"
        assert not Path(ready["app_home"]).exists(), "temp app-home survived teardown"

    def test_unready_engine_fails_loudly_not_green(self):
        # Break the engine on purpose: an unimportable app module. The harness
        # must exit 3 with a diagnostic, never print a ready line.
        env = dict(os.environ)
        env["PYTHONPATH"] = str(SERVER_SRC)
        proc = subprocess.Popen(
            [sys.executable, str(HARNESS), "--timeout", "10",
             "--socket", "/tmp/fih-selftest-unbindable/nested/no.sock"],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        out, err = proc.communicate(timeout=120)
        assert proc.returncode == 3, f"expected loud exit 3, got {proc.returncode}"
        assert "HARNESS FAILED" in err
        assert out.strip() == "", "no ready line may be printed on failure"
