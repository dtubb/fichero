"""A page whose work raises the run's pause is recorded as paused, not failed (#5919 sweep, ## 602): else Activity says
'failed' for a pause. (The text refinement this file also pinned was removed with `use_ai_refinement`, #5921.)"""
from __future__ import annotations

import time


from fichero_server.execution import jobs
from fichero_server.execution.cancellation import WorkflowPaused

KIND = "pausing-page-pp"


def test_work_that_raises_the_pause_leaves_a_paused_row_not_a_failed_one(db, monkeypatch):
    def work(db_, subject):
        raise WorkflowPaused("run-1")

    monkeypatch.setenv("FICHERO_JOB_THROTTLE", "0")
    monkeypatch.setitem(jobs.KINDS, KIND, jobs.Kind(run=work, model=None, lane="local-ml", name="Read a page"))
    job_id = jobs.enqueue(db, KIND, "p1")
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline and jobs.read_job(db, job_id)["state"] in ("waiting", "running"):
        time.sleep(0.02)
    row = jobs.read_job(db, job_id)
    assert row["state"] == "cancelled" and row["reason"] == "Paused with its run", row
