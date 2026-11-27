"""The engine's launch budget: first `/api/health` 200 within 8 s of the spawn and under 4 s of engine CPU (#7105).

NOT part of the unit gate: it lives under tests/perf/, which the perf rung and the nightly run on a check runner
(`scripts/perf_engine_run.py`). A loaded machine fails it; that is a measurement of the machine, so read the two figures
it prints beside the load before reading the red.

WHY BOTH FIGURES: wall is what the person waits through, and it moves with whatever else the machine is doing. CPU is the
engine's own work to reach health (interpreter start, the app import, the lifespan up to its yield) and moves only when
something is added to that path. #7105 measured 6.4 s of CPU on an M4: the lifespan imported the whole workflow tool
stack before it yielded.

Runs `main()` for real on a private socket with a scratch home and base, as `test_engine_keep_alive_outlasts_the_probe.py`
does: the shipped entry point, never the owner's libraries.
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from perf_ratchet import record  # noqa: E402

SRC = str(Path(__file__).resolve().parents[2] / "src")
HEALTH_WALL_BUDGET_S = 8.0
HEALTH_CPU_BUDGET_S = 4.0
GIVE_UP_S = 180.0  # how long to wait for a figure at all; the budgets above are what is asserted
REQUEST = b"GET /api/health HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n"


def cpu_seconds(pid: int) -> float:
    """The process's user + system CPU so far, from `ps -o time=` (`[hh:]mm:ss.cc`)."""
    out = subprocess.run(["ps", "-o", "time=", "-p", str(pid)], capture_output=True, text=True, check=True).stdout.strip()
    seconds = 0.0
    for part in out.split(":"):
        seconds = seconds * 60 + float(part)
    return seconds


def health_answers(sock_path: str) -> bool:
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
            conn.settimeout(30)
            conn.connect(sock_path)
            conn.sendall(REQUEST)
            return b" 200 " in conn.recv(65536).split(b"\r\n", 1)[0]
    except OSError:
        return False


def test_cpu_seconds_reads_ps_time():
    assert cpu_seconds(os.getpid()) >= 0.0


def test_health_within_8_s_and_under_4_s_of_engine_cpu_on_a_scratch_base():
    home = tempfile.mkdtemp(prefix="flb-")
    sock_dir = tempfile.mkdtemp(dir="/tmp", prefix="flb-")  # sun_path caps near 104 bytes
    sock_path = str(Path(sock_dir) / "e.sock")
    env = {
        **{key: value for key, value in os.environ.items() if not key.startswith("FICHERO_")},
        "HOME": home, "FICHERO_BASE_PATH": home, "FICHERO_UDS_PATH": sock_path, "PYTHONPATH": SRC,
        "FICHERO_BOOTSTRAP_TOKEN": "test-token-launch-budget", "FICHERO_SKIP_DEFAULT_WORKFLOWS": "1",
        "FICHERO_PARENT_PID": str(os.getpid()),
    }
    log_path = Path(home) / "engine.log"
    with open(log_path, "wb") as log:
        started = time.monotonic()
        process = subprocess.Popen([sys.executable, "-c", "from fichero_server.__main__ import main; main()"],
                                   env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            healthy = False
            while time.monotonic() - started < GIVE_UP_S and process.poll() is None:
                if health_answers(sock_path):
                    healthy = True
                    break
                time.sleep(0.02)
            wall = time.monotonic() - started
            if not healthy:
                pytest.fail(f"BLIND: the engine never answered health in {GIVE_UP_S:.0f} s; nothing was measured.\n"
                            + log_path.read_text(errors="replace")[-4000:])
            cpu = cpu_seconds(process.pid)
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(15)
                except subprocess.TimeoutExpired:
                    process.kill()
            shutil.rmtree(sock_dir, ignore_errors=True)
            shutil.rmtree(home, ignore_errors=True)

    load = os.getloadavg()[0]
    print(f"\n[perf] engine launch: health after {wall:.2f} s wall, {cpu:.2f} s engine CPU (1-minute load {load:.1f})")
    assert cpu < HEALTH_CPU_BUDGET_S, (
        f"the engine spent {cpu:.2f} s of CPU before its first health answer, budget {HEALTH_CPU_BUDGET_S} s: "
        f"something was added to the path before the lifespan yields (#7105). Load was {load:.1f}.")
    assert wall <= HEALTH_WALL_BUDGET_S, (
        f"the first health answer took {wall:.2f} s, budget {HEALTH_WALL_BUDGET_S} s (#7105). Load was {load:.1f}.")
    record("engine.launch.health_cpu", cpu * 1000)  # held to its best: raises on a regression
    record("engine.launch.health_wall", wall * 1000)
