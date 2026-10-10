"""A page waiting for memory on the model lane names the model that waits and that model's own need (#5654
item 8, `activity.throttle.power-heat-memory`).

WHY: on the demo (2026-10-10), during the Paleographer Review step (Qwen2.5-VL 3B on this Mac's model server)
the waiting pages said "Kraken and the other local models need about 2.5 GB of free memory, and this Mac has
about 1.9 GB free": the lane's memory check asked Kraken's floor for every job, whatever model it was for.

The real lane and its rows; nothing reads this Mac's memory (every reading is injected).
"""
from __future__ import annotations

import threading
import time

import pytest

from fichero_server.execution import jobs, throttle
from fichero_server.llm import kraken_runtime

GB = 1024**3
MLX = "omlx:Qwen2.5-VL-3B"


def _wait_for(predicate, seconds=20.0):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


@pytest.fixture
def mac(monkeypatch):
    state = {"free": int(1.9 * GB), "pressure": 1}
    monkeypatch.setenv("FICHERO_JOB_THROTTLE", "1")
    monkeypatch.setattr(jobs, "THROTTLE_LOOK_AGAIN_SECONDS", 0.05)
    monkeypatch.setattr(kraken_runtime, "_available_memory_bytes", lambda: state["free"])
    monkeypatch.setattr(kraken_runtime, "_memory_pressure_level", lambda: state["pressure"])
    monkeypatch.setattr(throttle, "PROBES", [(throttle.memory_is_tight, True)])
    monkeypatch.setattr(jobs, "_scheduler", jobs._Scheduler())
    return state


def _reason(db, job_id):
    return jobs.read_job(db, job_id)["reason"]


def test_a_local_model_call_waiting_for_memory_names_its_model_and_need(db, mac):
    ran = threading.Event()
    call = jobs.submit(db, "ask-a-model", "Paleographer Review", model=MLX, fn=ran.set)
    assert _wait_for(lambda: _reason(db, call.job_id) not in (None, ""))

    reason = _reason(db, call.job_id)
    assert reason.startswith(throttle.MEMORY_REASON), reason
    assert "Qwen2.5-VL 3B (OCR) needs about 3.9 GB" in reason, reason
    assert "Kraken" not in reason
    assert "1.9 GB free" in reason
    # The list's reason is the same derivation.
    assert jobs.state_and_reason(db, call.job_id) == ("waiting", reason)

    mac["free"] = 8 * GB
    assert ran.wait(10)


def test_a_kraken_page_waiting_for_memory_names_kraken(db, mac):
    ran = threading.Event()
    page = jobs.submit(db, "read-a-line", "p1.png", model="kraken:kraken-mccatmus", fn=ran.set)
    assert _wait_for(lambda: _reason(db, page.job_id) not in (None, ""))

    reason = _reason(db, page.job_id)
    assert "Kraken needs about 2.5 GB" in reason, reason
    mac["free"] = 8 * GB
    assert ran.wait(10)


def test_a_call_to_the_model_already_loaded_needs_only_a_read(db, mac):
    """Loaded, its weights are already in use: another page needs only the per-read margin (1 GB)."""
    jobs._scheduler.lanes["local-ml"].loaded_model = MLX
    ran = threading.Event()
    call = jobs.submit(db, "ask-a-model", "Paleographer Review", model=MLX, fn=ran.set)
    assert ran.wait(10), _reason(db, call.job_id)
