"""A page withdrawn from the lane because its run was paused raises WorkflowPaused even when the run's pause flag is
already cleared (`activity.durable.paused-stays-paused`): else it is recorded as the page's error and Resume never reads it."""
from __future__ import annotations

from types import SimpleNamespace

from fichero_server.execution import jobs
from fichero_server.execution.cancellation import WorkflowPaused


def test_a_waiter_withdrawn_for_a_pause_is_paused_when_the_flag_is_gone(db, monkeypatch):
    jobs._ensure(db)
    db.execute("INSERT INTO jobs (id, kind, subject, state, reason, created_at) "
               "VALUES ('page-1', 'read-a-page', 'p1', 'cancelled', 'Paused with its run', now())")
    monkeypatch.setattr(jobs, "_pause_requested", lambda run_id: False)  # the run settled: its flag is cleared
    monkeypatch.setattr(jobs, "_stop_requested", lambda run_id: False)
    raised = jobs._withdrawn(db, SimpleNamespace(job_id="page-1"), "run-1")
    assert isinstance(raised, WorkflowPaused)
