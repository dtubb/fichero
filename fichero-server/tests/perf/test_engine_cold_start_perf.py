"""Perf benchmark for engine cold start (#4441).

NOT part of the default unit gate — lives under tests/perf/ so
`pytest tests/unit/` skips it. Run explicitly:

    PYTHONPATH=fichero-server/src .venv/bin/pytest fichero-server/tests/perf/ -q -s

Why this matters: the langchain/langgraph/MCP-tools import deferral in
`api/main.py` (see the comment starting "langchain / langgraph / MCP / the
~60 tools / Quartz are no longer" around line 756) moved heavy imports off
the request path specifically to keep boot fast. Nothing stops the NEXT
module-level import creeping back onto the interpreter-start-to-serving
path — this measurement is the tripwire, held to its best-ever time via the
same ratchet as every other perf test in this directory
(tests/perf_ratchet.py, #4439/#4443/#4444/#4446).

Measures wall-clock from interpreter start (subprocess launch) to the first
successful `GET /api/health` — the number a user actually waits through
during a real launch, not a microbenchmark of one import. Spawns a FRESH
`uvicorn` subprocess (real interpreter start, real import cost) rather than
importing `fichero_server.api.main` in-process: importing it once already
pays — and then permanently hides — the cost this test exists to catch. A
warm interpreter (module already in sys.modules) would measure nothing.

This is the Python HALF of #4441 only. The Swift half (app pre-main time,
#3980 measured ~2.9s in Dev with a 1.69s debug-dylib map that would swamp
any real signal) needs a RELEASE build to mean anything and belongs to
#4442 — this suite cannot produce one (build ownership stays with the
manager, see AGENTS.md "Serialize builds").
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from perf_ratchet import record  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]
VENV_UVICORN = Path(sys.executable).parent / "uvicorn"

# Generous ceiling — a regression tripwire, not a microbenchmark. A blown
# budget means a real import crept onto the boot path (or the machine is
# badly overloaded), not ordinary jitter. The RATCHET (below) is what
# actually holds this to account release over release; this is the backstop
# that fails loudly even on a from-scratch baseline.
COLD_START_BUDGET_S = 20.0

# Poll fast: this measures hundreds-of-ms boot time, so a coarse poll
# interval (e.g. the 0.3s used by the CLI-contract live-engine fixture,
# which times out over 30s and doesn't care about precision) would itself
# be a meaningful fraction of the number being measured.
POLL_INTERVAL_S = 0.01


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_for_health(
    url: str,
    budget_s: float,
    poll_interval_s: float,
    get,
    *,
    now=time.monotonic,
    sleep=time.sleep,
) -> bool:
    """Poll `url` until `get` returns a 200, or `budget_s` elapses.

    `get`/`now`/`sleep` are injected so this loop — the one piece of logic
    between "the engine crashed on boot" and "false green" — is unit-
    testable without a real subprocess or real wall-clock time (see
    fichero-server/tests/unit/perf/test_engine_cold_start_wait_for_health.py,
    which synthesizes both the healthy and the never-healthy case directly).
    """
    deadline = now() + budget_s
    while now() < deadline:
        try:
            if get(url).status_code == 200:
                return True
        except httpx.HTTPError:
            pass
        sleep(poll_interval_s)
    return False


def test_engine_cold_start(tmp_path):
    if not VENV_UVICORN.exists():
        pytest.skip(f"venv uvicorn not found at {VENV_UVICORN}")

    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    env = {
        **os.environ,
        # Keep startup library discovery/recovery inside the temp harness,
        # matching tests/integration/_cli_live.py's live-engine fixture —
        # otherwise this can walk real ~/Documents libraries and stall
        # before /api/health ever responds, corrupting the measurement.
        "HOME": str(tmp_path),
        "PYTHONPATH": str(REPO_ROOT / "fichero-server" / "src"),
        "FICHERO_DISABLE_AUTH": "1",
        "FICHERO_FEATURE_TIER": "dev",
        "FICHERO_SKIP_DEFAULT_WORKFLOWS": "1",
        "FICHERO_BASE_PATH": str(tmp_path / "base"),
        "FICHERO_PARENT_PID": str(os.getpid()),
    }
    log_path = tmp_path / "engine.log"

    with open(log_path, "w") as log_handle:
        start = time.perf_counter()
        process = subprocess.Popen(
            # `tcp_transport:app`, not the bare `main:app`. Two reasons and
            # both matter: a TCP listener on the bare app exposes the
            # local-only control surface to remote callers (#4222), and a
            # cold-start budget measured against an app production never
            # serves over TCP is measuring the wrong thing.
            [str(VENV_UVICORN), "fichero_server.api.tcp_transport:app",
             "--host", "127.0.0.1", "--port", str(port)],
            env=env, stdout=subprocess.DEVNULL, stderr=log_handle,
        )
        try:
            healthy = wait_for_health(
                f"{base_url}/api/health", COLD_START_BUDGET_S, POLL_INTERVAL_S,
                get=lambda u: httpx.get(u, timeout=1.0),
            )
            elapsed_s = time.perf_counter() - start

            if not healthy:
                # BLIND: could not measure at all — the engine never came up,
                # so there is nothing to hold to a bar. Distinct from the
                # ratchet's own AssertionError below (a real regression) and
                # from the pytest.skip above (no venv uvicorn — not armed).
                tail = log_path.read_text(errors="replace")[-4000:]
                pytest.fail(
                    f"BLIND: engine never became healthy within {COLD_START_BUDGET_S}s "
                    f"— nothing was measured, this is not a timing result.\n"
                    f"--- engine stderr (tail) ---\n{tail}"
                )

            record("engine.cold_start", elapsed_s * 1000)  # raises on regression
            assert elapsed_s < COLD_START_BUDGET_S, (
                f"engine cold start took {elapsed_s:.2f}s > {COLD_START_BUDGET_S}s budget "
                f"— something heavy is on the boot path"
            )
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
