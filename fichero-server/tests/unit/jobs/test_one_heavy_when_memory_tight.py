"""While memory is busy, heavy work runs one job at a time (#5622, `activity.throttle.one-heavy-when-memory-tight`).

Spec: docs/contributor_manual/specs/ui/activity-and-automatic-work.md. The maintainer saw two projects'
"Processing imported pages" running together (thumbnails on the images lane, embeds on the model lane)
at memory pressure warn and 312% CPU, while the rows read "Waiting: you're using the Mac". Pressure warn
does not hold work (#5524); it stops heavy work running side by side, in any project, whatever started it.

Through the real scheduler and `GET /api/activity/jobs`; memory pressure is faked at the throttle's
reading, the stages are faked so no model loads.
"""
from __future__ import annotations

import threading
import time

import pytest

from fichero_server.execution import jobs, throttle


@pytest.fixture
def pressure(monkeypatch):
    state = {"level": 2}  # warn
    monkeypatch.setenv("FICHERO_JOB_THROTTLE", "1")
    monkeypatch.setattr(jobs, "THROTTLE_LOOK_AGAIN_SECONDS", 0.05)
    monkeypatch.setattr(throttle, "memory_pressure_level", lambda: state["level"])
    monkeypatch.setattr(throttle, "PROBES", [])  # nothing else holds
    return state


@pytest.fixture
def lanes(monkeypatch):
    """A heavy kind on each heavy lane whose job runs until released; records when each ran."""
    release = threading.Event()
    running: list[str] = []
    together: list[int] = []

    def work(db, subject):
        running.append(subject)
        together.append(len(running))
        release.wait(30)
        running.remove(subject)

    monkeypatch.setitem(jobs.KINDS, "t-model", jobs.Kind(run=work, model="embedder"))
    monkeypatch.setitem(jobs.KINDS, "t-image", jobs.Kind(run=work, model=None, lane="images"))
    yield release, running, together
    release.set()


def _wait_for(predicate, seconds=30.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def test_two_heavy_lanes_run_one_job_between_them_while_memory_is_busy(db, client, pressure, lanes):
    """WHY (#5622): a thumbnail and an embed ran side by side at pressure warn. Now the second waits, and
    says why, naming what runs; it starts when the first ends."""
    release, running, together = lanes
    jobs.enqueue(db, "t-image", "thumb-1")
    assert _wait_for(lambda: running == ["thumb-1"])
    jobs.enqueue(db, "t-model", "embed-1")
    jobs.enqueue(db, "t-image", "thumb-2")
    time.sleep(0.3)
    assert running == ["thumb-1"]
    rows = {j["task_type"]: j for j in client.get("/api/activity/jobs").json()["jobs"] if j["state"] == "waiting"}
    assert rows["t-model"]["reason"].startswith(jobs.ONE_HEAVY_REASON)
    # One row per kind (`activity.window.one-row-per-kind`): thumb-1 is running, so the t-image row reads Running and the
    # waiting thumbnail is a line in the row's pages (`activity.window.expands-to-pages`).
    [(waiting_id, created)] = db.execute_fetchall(
        "SELECT id, created_at FROM jobs WHERE subject = 'thumb-2' AND state = 'waiting'")
    assert jobs.waiting_reason(db, waiting_id, "t-image", created_at=created).startswith(jobs.ONE_HEAVY_REASON)
    release.set()
    assert _wait_for(lambda: db.execute_fetchone(
        "SELECT count(*) FROM jobs WHERE state = 'done'")[0] == 3)
    assert max(together) == 1


def test_with_memory_normal_the_lanes_run_side_by_side(db, pressure, lanes):
    """Pressure normal: the images lane keeps its two slots and runs beside the model lane (no needless wait)."""
    release, running, _together = lanes
    pressure["level"] = 1
    jobs.enqueue(db, "t-image", "thumb-1")
    jobs.enqueue(db, "t-image", "thumb-2")
    jobs.enqueue(db, "t-model", "embed-1")
    assert _wait_for(lambda: len(running) == 3)
    release.set()


def test_start_does_not_lift_it(db, pressure, lanes):
    """WHY (ruled 2026-10-09): forcing work never runs two heavy jobs at once under memory pressure."""
    release, running, together = lanes
    jobs.set_mode("started")
    jobs.enqueue(db, "t-image", "thumb-1")
    assert _wait_for(lambda: running == ["thumb-1"])
    jobs.enqueue(db, "t-model", "embed-1")
    time.sleep(0.3)
    assert running == ["thumb-1"]
    release.set()
    assert _wait_for(lambda: db.execute_fetchone("SELECT count(*) FROM jobs WHERE state = 'done'")[0] == 2)
    assert max(together) == 1


# `recipes-run.memory.one-heavy-model` (#6000, #6167): on a Mac of 16 GB or less the model lane never keeps two heavy models
# loaded, whatever the free-memory reading says; the release is told which model the lane switches to and why.
@pytest.mark.parametrize("loaded, wanted, freed", [("omlx:qwen-7b", "kraken:blla", "local-model"),
                                                   ("kraken:blla", "omlx:qwen-7b", "kraken")])
def test_a_small_mac_frees_the_loaded_heavy_model_before_another_loads_whatever_memory_reads(db, monkeypatch, loaded, wanted,
                                                                                            freed):
    jobs._ensure(db)
    released: list[tuple[str, str]] = []
    for family in ("kraken", "local-model"):
        monkeypatch.setitem(jobs._RELEASE, family, lambda reason="", f=family: released.append((f, reason)) or True)
    monkeypatch.setattr(jobs, "_physical_memory_bytes", lambda: 16 * 1024**3)
    monkeypatch.setattr(throttle, "memory_available_bytes", lambda: 14 * 1024**3)  # plenty free, by macOS's reading
    monkeypatch.setattr(jobs, "_kraken_busy", lambda queued=0: False)
    monkeypatch.setitem(jobs.KINDS, "t-heavy", jobs.Kind(run=lambda db, subject: None, model=wanted))
    job_id = jobs._insert(db, "t-heavy", "page-1", wanted, "automatic")
    lane = jobs._Lane("local-ml", 1)
    lane.loaded_model = loaded

    jobs._scheduler._run(lane, jobs._key(db), db, (job_id, "t-heavy", "page-1", wanted), None)

    assert [f for f, _ in released] == [freed]
    assert "one heavy model at a time" in released[0][1] and f"switches to {jobs._family(wanted)}" in released[0][1]
    assert lane.loaded_model == wanted
