"""How long to wait for a spawned engine: by its own CPU progress, not the wall clock (#5187).

No side effects on import (unlike `_cli_live`, which sets engine env defaults), so the unit tests
of this helper can import it.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import httpx


# #5187: how long to wait for a spawned engine. Its startup is ~3 CPU-seconds of work (importing the
# app ~2.1 s, the lifespan ~0.5 s; measured 2026-09-28 on this machine). Under load that work is
# STARVED, not longer: at a load average of 80 on 8 cores a process gets ~1/10 of a core, and the
# same 3 s took more than 30 s of wall time -- the "never became healthy in 30s" with an empty
# stderr (uvicorn logs nothing until the import is done). A wall-clock deadline cannot tell that
# from a hang, so the wait follows the ENGINE'S OWN PROGRESS instead:
#: CPU the engine may spend without answering: 10x the measured work. Past it, it is not load.
STARTUP_CPU_BUDGET_S = 30.0
#: Wall time with no CPU progress at all: a hang (a deadlock, a wait on the network), not load --
#: a starved but runnable process still gets slices every few seconds.
STARTUP_STALL_S = 120.0
#: A backstop so nothing waits forever.
STARTUP_WALL_CAP_S = 900.0


def _cpu_seconds(pid: int) -> float | None:
    """A process's total CPU time, from `ps` ([[dd-]hh:]mm:ss[.xx]); None once it is gone."""
    done = subprocess.run(["ps", "-o", "time=", "-p", str(pid)], capture_output=True, text=True)
    text = done.stdout.strip()
    if done.returncode != 0 or not text:
        return None
    days, _, clock = text.rpartition("-")
    seconds = 0.0
    for part in clock.split(":"):
        seconds = seconds * 60 + float(part)
    return seconds + (int(days) * 86400 if days else 0)


def wait_for_engine(is_ready, process: subprocess.Popen) -> str | None:
    """Poll `is_ready()` until it is true; None then, else WHY the engine never got there."""
    started = last_progress = time.monotonic()
    last_cpu = 0.0
    while True:
        try:
            if is_ready():
                return None
        except Exception:  # noqa: BLE001 -- not listening yet
            pass
        now = time.monotonic()
        if process.poll() is not None:
            return f"the engine exited with code {process.returncode}"
        cpu = _cpu_seconds(process.pid)
        if cpu is None:
            return "the engine is gone"
        if cpu > last_cpu:
            last_cpu, last_progress = cpu, now
        if cpu > STARTUP_CPU_BUDGET_S:
            return f"the engine used {cpu:.1f} CPU-seconds without answering (budget {STARTUP_CPU_BUDGET_S:.0f}, ~10x its work)"
        if now - last_progress > STARTUP_STALL_S:
            return f"the engine made no CPU progress for {STARTUP_STALL_S:.0f} s at {cpu:.1f} CPU-seconds: a hang, not load"
        if now - started > STARTUP_WALL_CAP_S:
            return f"the engine was not ready after {STARTUP_WALL_CAP_S:.0f} s ({cpu:.1f} CPU-seconds)"
        time.sleep(0.3)


def _wait_healthy(base_url: str, process: subprocess.Popen) -> str | None:
    """None once /api/health says healthy; else why not (see `wait_for_engine`)."""
    def healthy() -> bool:
        response = httpx.get(f"{base_url}/api/health", timeout=2.0)
        return response.status_code == 200 and response.json().get("status") == "healthy"
    return wait_for_engine(healthy, process)


def _share_real_model_cache(workdir: Path) -> Path:
    """Point the spawned engine's fake HOME at the REAL model cache (#4434).

    The fixture redirects HOME into the workdir (necessary — startup library
    discovery must stay inside the harness), but the engine's models dir
    hangs off HOME, so every integration run RE-DOWNLOADED the 2.2 GB
    e5-large ONNX embedding model into temp and then leaked it. A symlink to
    the real cache means no download and nothing to leak; if the real cache
    is absent (fresh CI), the engine downloads into the workdir as before and
    teardown reclaims it. The models tree is a shared CACHE, not library
    data — the harness's isolation rule protects Daniel's library, and this
    shares only what a real engine on this machine would populate anyway.

    Returns the model-store root to give the engine as ``FICHERO_MODEL_STORE_ROOT``: the model
    stores follow ``FICHERO_BASE_PATH`` unless told otherwise (#5530), so the engine is pointed
    back at this fake home's store, where the link is.
    """
    fake_fichero = workdir / "Library" / "Application Support" / "Fichero"
    fake_fichero.mkdir(parents=True, exist_ok=True)
    real_models = Path.home() / "Library" / "Application Support" / "Fichero" / "models"
    if real_models.is_dir():
        (fake_fichero / "models").symlink_to(real_models)
    return fake_fichero
