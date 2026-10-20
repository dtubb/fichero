"""`activity.run.stage-by-stage-no-model-juggling` (#5939; Fable runner review 2 MED 3): the lane loads a heavy model once and
finishes the pages that are waiting for it, or are handed in a moment later, before it loads the next; a page a run handed in
is held for the loaded model like a stored job. No threads: the test makes the lane's picks itself, as
test_lane_rescans_when_the_state_moved_5920.py does, and counts a swap at the decision `_run` loads on (`_heavy_switch`).
"""
from __future__ import annotations

import time
from concurrent.futures import Future

from fichero_server.execution import jobs

KRAKEN, VLM = "kraken-page-5939", "vlm-page-5939"


def _lane_with(db, monkeypatch):
    monkeypatch.setattr(jobs._scheduler, "wake", lambda key: None)
    monkeypatch.setenv("FICHERO_JOB_THROTTLE", "0")
    monkeypatch.setattr(jobs, "SWITCH_AFTER_QUIET_SECONDS", 5.0)
    noop = lambda db_, subject: None  # noqa: E731
    monkeypatch.setitem(jobs.KINDS, KRAKEN, jobs.Kind(run=noop, model="kraken:blla", lane="local-ml", name="Read a page"))
    monkeypatch.setitem(jobs.KINDS, VLM, jobs.Kind(run=noop, model="omlx:big-vlm", lane="local-ml", name="VLM page"))
    lane = jobs._scheduler.lanes["local-ml"]
    lane.libraries.add(jobs._key(db))
    lane.running.clear()
    lane.loaded_model = "kraken:blla"
    lane.loaded_used_at = time.monotonic()
    return lane


def _hand_in(db, kind, subject):
    """A page a run hands in: a waiting row the run's caller is attached to."""
    job_id = jobs.enqueue(db, kind, subject)
    jobs._scheduler.attach(job_id, lambda: None, Future(), "local-ml", None)
    return job_id


def _finish(db, job_id):
    db.execute("UPDATE jobs SET state = 'done' WHERE id = ?", [job_id])
    with jobs._scheduler._lock:
        jobs._scheduler._attached.pop(job_id, None)


def test_a_handed_in_page_of_another_model_waits_while_the_loaded_models_work_is_queued(db, monkeypatch):
    from fichero_server.workflows.tools import vision_base

    lane = _lane_with(db, monkeypatch)
    monkeypatch.setattr(vision_base._KrakenPageGate, "in_flight", 1)  # a Kraken page of a run is in the gate
    _hand_in(db, VLM, "b1")
    assert jobs._scheduler._next(lane) is None, "the VLM page was picked and the lane swapped models under Kraken's work"


def test_a_three_step_run_on_six_pages_loads_each_heavy_model_once_pages_handed_in_mid_stage_included(db, monkeypatch):
    lane = _lane_with(db, monkeypatch)
    swaps, order = [], []

    def pick() -> str | None:
        found = jobs._scheduler._next(lane)
        if found is None:
            return None
        job_id, _kind, subject, model, *_ = found[2]
        if jobs._heavy_switch(lane.loaded_model, model):
            swaps.append((lane.loaded_model, model))  # the lane would load `model` here
        lane.loaded_model, lane.loaded_used_at = model, time.monotonic()
        order.append(subject)
        _finish(db, job_id)
        return subject

    k1, k2 = _hand_in(db, KRAKEN, "k1"), _hand_in(db, KRAKEN, "k2")
    for v in ("v1", "v2", "v3"):
        _hand_in(db, VLM, v)  # the next stage's pages are already handed in and waiting
    assert (pick(), pick()) == ("k1", "k2")
    assert pick() is None, "Kraken's quiet spell has not ended: the VLM pages wait, they do not take the lane"
    _hand_in(db, KRAKEN, "k3")  # handed in mid-stage, a moment after the last page
    assert pick() == "k3"
    lane.loaded_used_at -= 10.0  # nothing more for Kraken: its quiet spell is over
    assert [pick(), pick(), pick()] == ["v1", "v2", "v3"]
    assert order == ["k1", "k2", "k3", "v1", "v2", "v3"]
    assert swaps == [("kraken:blla", "omlx:big-vlm")], f"each heavy model loads once: {swaps}"
    del k1, k2


def test_a_person_pre_empting_mid_stage_costs_exactly_one_extra_reload_661(db, monkeypatch):
    """## 661 LOW 1: a page a person is looking at goes first even mid-stage; the lane swaps to its model and back once."""
    lane = _lane_with(db, monkeypatch)
    swaps: list[tuple[str, str]] = []

    def pick() -> str | None:
        found = jobs._scheduler._next(lane)
        if found is None:
            return None
        job_id, _kind, subject, model, *_ = found[2]
        if jobs._heavy_switch(lane.loaded_model, model):
            swaps.append((lane.loaded_model, model))
        lane.loaded_model, lane.loaded_used_at = model, time.monotonic()
        _finish(db, job_id)
        return subject

    _hand_in(db, KRAKEN, "k1")
    assert pick() == "k1"
    _hand_in(db, KRAKEN, "k2")  # the stage is not over
    person = _hand_in(db, VLM, "watched page")
    db.execute("UPDATE jobs SET watched = TRUE WHERE id = ?", [person])  # a person has it open on screen
    assert pick() == "watched page"
    lane.loaded_used_at -= 10.0  # its quiet spell is over
    assert pick() == "k2"
    assert swaps == [("kraken:blla", "omlx:big-vlm"), ("omlx:big-vlm", "kraken:blla")], swaps
