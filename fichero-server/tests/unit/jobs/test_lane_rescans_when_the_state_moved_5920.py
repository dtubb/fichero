"""`activity.lane.one-model-at-a-time` (#5920): a lane scan that ran while another job finished is not acted on.

The lane has several threads; one scans (loaded model: Kraken, a person's VLM job running, the lane full) while that job
finishes and its model becomes the loaded one. The scan chose the old model's page, and `may_start` then passed on the
now-empty lane: A's pages ran before B's queued ones. No threads or timers: the test makes the straddle itself.
"""
from __future__ import annotations

import time

from fichero_server.execution import jobs

KRAKEN, VLM = "kraken-page-rs", "vlm-page-rs"


def test_a_scan_that_straddles_a_finish_is_made_again(db, monkeypatch):
    monkeypatch.setattr(jobs._scheduler, "wake", lambda key: None)  # no lane thread of its own: the test claims by hand
    monkeypatch.setenv("FICHERO_JOB_THROTTLE", "0")
    monkeypatch.setattr(jobs, "SWITCH_AFTER_QUIET_SECONDS", 0.05)
    noop = lambda db_, subject: None  # noqa: E731
    monkeypatch.setitem(jobs.KINDS, KRAKEN, jobs.Kind(run=noop, model="kraken:blla", lane="local-ml", name="Read a page"))
    monkeypatch.setitem(jobs.KINDS, VLM, jobs.Kind(run=noop, model="omlx:big-vlm", lane="local-ml", name="VLM page"))
    jobs.enqueue(db, KRAKEN, "a2")
    jobs.enqueue(db, VLM, "b1")
    lane = jobs._scheduler.lanes["local-ml"]
    lane.libraries.add(jobs._key(db))
    lane.running["person-b"] = "omlx:big-vlm"  # the person's job, running; the lane is full
    lane.loaded_model = "kraken:blla"  # its _run has not yet made the VLM the loaded model
    lane.loaded_used_at = time.monotonic()

    real_next, straddled = jobs._Scheduler._next, []

    def next_beside_a_finish(self, lane_, **kw):
        found = real_next(self, lane_, **kw)  # decided for loaded=Kraken, lane full: Kraken's page
        if not straddled:
            straddled.append(found[2][2] if found else None)
            lane_.running.clear()  # the person's job finished while the scan ran ...
            lane_.loaded_model = "omlx:big-vlm"  # ... and its model is the loaded one
            lane_.loaded_used_at = time.monotonic()
        return found

    monkeypatch.setattr(jobs._Scheduler, "_next", next_beside_a_finish)
    claimed = jobs._scheduler._claim_one(lane)

    assert straddled == ["a2"], "the straddled scan chose the old model's page, as in the M4 picks"
    assert claimed is not None and claimed[2][2] == "b1", f"the lane acted on the stale choice: {claimed and claimed[2][2]}"


def test_a_scan_that_straddles_a_kraken_page_taking_up_is_made_again(db, monkeypatch):
    """The page gate is part of what a hold is worked out from (## 983): a scan that saw no Kraken page in flight, and finished
    after a run took one up, chose from an idle state that no longer holds, so it is made again and the heavy model waits."""
    from fichero_server.workflows.tools import vision_base

    monkeypatch.setattr(jobs._scheduler, "wake", lambda key: None)
    monkeypatch.setenv("FICHERO_JOB_THROTTLE", "0")
    monkeypatch.setattr(jobs, "SWITCH_AFTER_QUIET_SECONDS", 0.0)
    monkeypatch.setattr(vision_base._KrakenPageGate, "in_flight", 0)
    noop = lambda db_, subject: None  # noqa: E731
    monkeypatch.setitem(jobs.KINDS, "t-heavy", jobs.Kind(run=noop, model="omlx:heavy", lane="local-ml", name="Heavy"))
    monkeypatch.setitem(jobs.KINDS, "t-light", jobs.Kind(run=noop, model=None, lane="local-ml", name="Light"))
    jobs.enqueue(db, "t-heavy", "h1")
    jobs.enqueue(db, "t-light", "l1")
    lane = jobs._scheduler.lanes["local-ml"]
    lane.libraries.add(jobs._key(db))
    lane.loaded_model = "kraken:blla"
    lane.loaded_used_at = time.monotonic()

    real_next, straddled = jobs._Scheduler._next, []

    def next_beside_a_page_taken_up(self, lane_, **kw):
        found = real_next(self, lane_, **kw)  # no page in flight: the heavy job is the oldest, and not held
        if not straddled:
            straddled.append(found[2][1] if found else None)
            monkeypatch.setattr(vision_base._KrakenPageGate, "in_flight", 1)  # the run took its next page up meanwhile
        return found

    monkeypatch.setattr(jobs._Scheduler, "_next", next_beside_a_page_taken_up)
    claimed = jobs._scheduler._claim_one(lane)

    assert straddled == ["t-heavy"], "the first scan chose the heavy job from the idle state"
    assert claimed is not None and claimed[2][1] == "t-light", f"acted on the stale idle choice: {claimed and claimed[2][1]}"
