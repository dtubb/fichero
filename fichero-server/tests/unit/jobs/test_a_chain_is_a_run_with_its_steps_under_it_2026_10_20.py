"""`activity.run.one-way-to-run`: a chain run shows in Activity as one run (a `chain` row) with each step's workflow run
under it, and Stop on that row reaches the chain (the steps not yet started and the run in flight)."""
from __future__ import annotations

from unittest.mock import MagicMock

from fichero_server.api.routes.workflow import chains
from fichero_server.execution import jobs


def test_a_chain_row_has_its_step_runs_as_children(db):
    jobs._ensure(db)
    jobs.record_chain(db, "exec-1", status="running", name="Bar Chain")
    for thread in ("thread-a", "thread-b"):
        jobs._record(db, thread, kind="workflow", subject=thread, parent_id=None, state="done", reason=None, name=thread)
        jobs.set_parent(db, thread, "exec-1")
    tree = jobs.tree(db, "exec-1")
    assert tree["kind"] == "chain" and tree["name"] == "Chain run"
    assert [c["id"] for c in tree["children"]] == ["thread-a", "thread-b"]


def test_stop_on_the_chain_row_reaches_the_chain(db):
    jobs._ensure(db)
    jobs.record_chain(db, "exec-2", status="running", name="Bar Chain")
    executor = MagicMock()
    chains._running_executors["exec-2"] = executor
    try:
        jobs.cancel_job(db, "exec-2")
    finally:
        chains._running_executors.pop("exec-2", None)
    executor.cancel.assert_called_once_with()


def test_a_chain_that_ends_is_done_failed_or_cancelled_on_its_row(db):
    jobs._ensure(db)
    for status, state in (("completed", "done"), ("failed", "failed"), ("cancelled", "cancelled")):
        jobs.record_chain(db, f"exec-{status}", status="running", name="C")
        jobs.record_chain(db, f"exec-{status}", status=status, name="C")
        assert jobs.read_job(db, f"exec-{status}")["state"] == state
