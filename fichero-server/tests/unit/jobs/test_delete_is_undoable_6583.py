"""Undo of Delete brings a row back as it was, never as a phantom (#6594).

Spec: docs/contributor_manual/specs/ui/activity-pane.md, `activity.engine.undelete-running-is-a-phantom`
and `activity.pane.archive-old-runs`.
WHY: Delete on a running row is Stop then Delete; its remembered state was `running`, and Undo wrote `running` back with
no thread behind it. A row Delete stopped comes back paused ("Stopped by you"); the others come back as they were.
"""
from __future__ import annotations

import pytest

from fichero_server.execution import jobs

KIND = "t-undo-delete"


@pytest.fixture
def held(db, monkeypatch):
    monkeypatch.setitem(jobs.KINDS, KIND, jobs.Kind(run=lambda db, subject: None, model=None, name="A job",
                                                     cancel=lambda db, job_id: "stopping"))
    monkeypatch.setattr(jobs, "_scheduler", jobs._Scheduler())
    jobs.set_paused(True)
    yield db
    jobs.set_paused(False)


def _row(db, subject, state, reason=None, parent=None):
    job_id = jobs.enqueue(db, KIND, subject)
    db.execute("UPDATE jobs SET state = ?, reason = ?, parent_id = ?, finished_at = CASE WHEN ? IN ('done', 'failed', 'cancelled') "
               "THEN now() ELSE NULL END WHERE id = ?", [state, reason, parent, state, job_id])
    return job_id


def _now(db, job_id):
    return db.execute_fetchone("SELECT state, reason, deleted_at IS NOT NULL FROM jobs WHERE id = ?", [job_id])


def test_a_running_row_deleted_with_stop_comes_back_paused_stopped_by_you(held, client):
    running = _row(held, "u:running", "running")
    child = _row(held, "u:running:child", "running", parent=running)
    jobs._scheduler.running_ids = lambda: [running]

    deleted = client.post("/api/activity/jobs/delete", json={"ids": [running], "stop_running": True}).json()
    assert deleted["deleted_ids"] == [running]
    assert client.post("/api/activity/jobs/undelete", json={"ids": [running]}).json()["ids"] == [running]

    assert _now(held, running) == ("paused", "Stopped by you", False), "never `running` with no thread"
    assert _now(held, child) == ("paused", "Stopped by you", False)


def test_the_other_states_come_back_in_their_own_state(held, client):
    waiting = _row(held, "u:waiting", "waiting")
    paused = _row(held, "u:paused", "paused", jobs.PAUSED_REASON)
    failed = _row(held, "u:failed", "failed", "the model is not downloaded")
    done = _row(held, "u:done", "done")
    ids = [waiting, paused, failed, done]
    assert sorted(client.post("/api/activity/jobs/delete", json={"ids": ids}).json()["deleted_ids"]) == sorted(ids)

    assert sorted(client.post("/api/activity/jobs/undelete", json={"ids": ids}).json()["ids"]) == sorted(ids)

    assert _now(held, waiting)[0] == "waiting"
    assert _now(held, paused) == ("paused", jobs.PAUSED_REASON, False)
    assert _now(held, failed) == ("failed", "the model is not downloaded", False)
    assert _now(held, done)[0] == "done"
