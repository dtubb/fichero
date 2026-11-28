"""The engine's launch budget: first `/api/health` 200 within 8 s of the spawn, at under 1.6 times the CPU its app import cost (#7105).

NOT part of the unit gate: it lives under tests/perf/, which the perf rung and the nightly run on a check runner
(`scripts/perf_engine_run.py`).

WHY BOTH FIGURES: wall is what the person waits through, and it moves with whatever else the machine is doing. CPU is the
engine's own work to reach health (interpreter start, the app import, the lifespan up to its yield, and whatever the
lifespan put on the event loop ahead of the first answer) and moves when something is added to that path.

WHY THE CPU BUDGET IS A RATIO AND NOT SECONDS: the same engine reads 2 to 3 times the CPU seconds at a load average near
100 that it reads on a quiet machine, so a budget in seconds was red for the fixed engine on a loaded worker and green for
the unfixed one on a quiet runner. The reference is the same process's CPU at the moment its app import ended, read by a
thread the launcher starts (`LAUNCH`); the engine's own code is not changed for the measurement. Measured at load averages
of 114 to 142, nine launches each: 1.73 to 2.08 before #7105's fixes, 1.36 to 1.47 after them.

ponytail: an app import that grows raises the reference and so loosens this budget; the app-import module budget is what
holds the import. If that proves too loose, hold the CPU after the import against a fixed calibration workload instead.

The scratch base has one saved, enabled MCP server that never answers. Before #7105 the lifespan imported the workflow
tool stack before it yielded and began the MCP load, on the event loop, as it yielded; both were paid before the first
health answer.

Runs `main()` on a private socket with a scratch home and base, as `test_engine_keep_alive_outlasts_the_probe.py` does:
the shipped entry point, never the owner's libraries.
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
HEALTH_CPU_BUDGET_APP_IMPORTS = 1.6
GIVE_UP_S = 180.0  # how long to wait for a figure at all; the budgets above are what is asserted
REQUEST = b"GET /api/health HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n"
LAUNCHES = 2
SAVE_SILENT_MCP_SERVER = """
from fichero_server.db.app import get_app_db
from fichero_server.models import MCPServer
get_app_db().save_mcp_server(MCPServer(name="silent", transport="stdio", command="python3",
                                       args=["-c", "import sys; sys.stdin.read()"]))
"""
# `main()` with one thread beside it that writes the process's CPU once the app module `main()` serves has its `app`.
LAUNCH = """
import os, sys, threading, time
def note_app_import_cpu():
    while getattr(sys.modules.get("fichero_server.api.uds_transport"), "app", None) is None:
        time.sleep(0.005)
    with open(os.environ["FLB_APP_IMPORT_CPU"], "w") as out:
        out.write(repr(time.process_time()))
threading.Thread(target=note_app_import_cpu, daemon=True).start()
from fichero_server.__main__ import main
main()
"""


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


def launch_to_health() -> tuple[float, float, float]:
    """One engine on a scratch base with a saved MCP server: wall seconds and engine CPU seconds at its first health 200,
    and the CPU seconds it had used when its app import ended."""
    home = tempfile.mkdtemp(prefix="flb-")
    sock_dir = tempfile.mkdtemp(dir="/tmp", prefix="flb-")  # sun_path caps near 104 bytes
    sock_path = str(Path(sock_dir) / "e.sock")
    env = {
        **{key: value for key, value in os.environ.items() if not key.startswith("FICHERO_")},
        "HOME": home, "FICHERO_BASE_PATH": home, "FICHERO_UDS_PATH": sock_path, "PYTHONPATH": SRC,
        "FICHERO_BOOTSTRAP_TOKEN": "test-token-launch-budget", "FICHERO_SKIP_DEFAULT_WORKFLOWS": "1",
        "FICHERO_PARENT_PID": str(os.getpid()), "FLB_APP_IMPORT_CPU": str(Path(home) / "app-import-cpu"),
    }
    log_path = Path(home) / "engine.log"
    try:
        with open(log_path, "wb") as log:
            subprocess.run([sys.executable, "-c", SAVE_SILENT_MCP_SERVER], env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
            started = time.monotonic()
            process = subprocess.Popen([sys.executable, "-c", LAUNCH], env=env, stdout=log, stderr=subprocess.STDOUT)
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
                return wall, cpu, float(Path(env["FLB_APP_IMPORT_CPU"]).read_text())
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(15)
                    except subprocess.TimeoutExpired:
                        process.kill()
    finally:
        shutil.rmtree(sock_dir, ignore_errors=True)
        shutil.rmtree(home, ignore_errors=True)


def test_cpu_seconds_reads_ps_time():
    assert cpu_seconds(os.getpid()) >= 0.0


def test_health_within_8_s_and_under_1_6_app_imports_of_engine_cpu_with_a_saved_mcp_server():
    launches = [launch_to_health() for _ in range(LAUNCHES)]
    wall = min(wall for wall, _cpu, _app_import in launches)
    cpu, app_import = min(((cpu, app_import) for _wall, cpu, app_import in launches), key=lambda pair: pair[0] / pair[1])
    load = os.getloadavg()[0]
    print(f"\n[perf] engine launch: health after {wall:.2f} s wall; {cpu:.2f} s engine CPU, {cpu / app_import:.2f} times the "
          f"{app_import:.2f} s of its app import (the lower of {LAUNCHES} launches each, 1-minute load {load:.1f})")
    assert cpu < HEALTH_CPU_BUDGET_APP_IMPORTS * app_import, (
        f"the engine spent {cpu:.2f} s of CPU before its first health answer, {cpu / app_import:.2f} times the {app_import:.2f} s "
        f"of its app import, budget {HEALTH_CPU_BUDGET_APP_IMPORTS}: something was added between the app import and the first "
        f"answer (#7105). Load was {load:.1f}.")
    assert wall <= HEALTH_WALL_BUDGET_S, (
        f"the first health answer took {wall:.2f} s, budget {HEALTH_WALL_BUDGET_S} s (#7105). Load was {load:.1f}.")
    record("engine.launch.health_cpu", cpu * 1000)  # held to its best: raises on a regression
    record("engine.launch.health_wall", wall * 1000)
