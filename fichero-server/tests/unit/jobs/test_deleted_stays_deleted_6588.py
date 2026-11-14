"""A deleted row stays deleted, whatever a lane writes late (#6594).

Spec: docs/contributor_manual/specs/ui/activity-pane.md, `activity.engine.deleted-stays-deleted`.
WHY: the scheduler's end write for a deferred job (`state = waiting`) revived a row Delete had cancelled, and a second
Delete re-stamped `deleted_at`, so a later Undo no longer restored it.
"""
from __future__ import annotations

import pytest

from fichero_server.execution import jobs

KIND = "t-stays-deleted"


@pytest.fixture
def held(db, monkeypatch):
    monkeypatch.setitem(jobs.KINDS, KIND, jobs.Kind(run=lambda db, subject: None, model=None, name="A job"))
    monkeypatch.setattr(jobs, "_scheduler", jobs._Scheduler())
    jobs.set_paused(True)
    yield db
    jobs.set_paused(False)


def test_a_deferred_end_on_a_deleted_row_leaves_it_deleted_and_not_waiting(held):
    job_id = jobs.enqueue(held, KIND, "s:1")
    held.execute("UPDATE jobs SET state = 'running' WHERE id = ?", [job_id])
    jobs._scheduler.running_ids = lambda: [job_id]
    jobs.delete_jobs(held, [job_id], stop_running=True)

    # The lane's end write when the job's run was deferred (`waiting`) or out of reach (`running`), arriving after the delete.
    for state in ("waiting", "running"):
        jobs._write_unfinished_end(held, job_id, state, "Waiting for a model")
        row = held.execute_fetchone("SELECT state, deleted_at IS NOT NULL FROM jobs WHERE id = ?", [job_id])
        assert row == ("cancelled", True), f"a late {state} end revived a deleted row: {row}"


def test_a_double_delete_then_one_undelete_restores_the_row(held):
    job_id = jobs.enqueue(held, KIND, "s:2")
    assert jobs.delete_jobs(held, [job_id])[0] == [job_id]
    stamp = held.execute_fetchone("SELECT deleted_at FROM jobs WHERE id = ?", [job_id])[0]
    jobs.delete_jobs(held, [job_id])
    assert held.execute_fetchone("SELECT deleted_at FROM jobs WHERE id = ?", [job_id])[0] == stamp, "not re-stamped"

    assert jobs.undelete_jobs(held, [job_id]) == [job_id]
    assert held.execute_fetchone("SELECT state, deleted_at IS NOT NULL FROM jobs WHERE id = ?", [job_id]) == ("waiting", False)
