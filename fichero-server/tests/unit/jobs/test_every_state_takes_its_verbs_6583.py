"""Every state of a job row takes exactly the verbs the states table allows (#6583, #6584).

Spec: docs/contributor_manual/specs/ui/activity-pane.md, "States and what a person may do in each",
`activity.pane.row-actions-on-the-table`. WHY (owner 2026-11-13): create/read/update/delete, Pause and Stop must be rock
solid in every state. Through the routes and the real jobs table; the lane is held (background work paused) so a row's
state is what the test set, except the one row a thread runs.
"""
from __future__ import annotations

import pytest

from fichero_server.execution import jobs

KIND = "t-verbs"


@pytest.fixture
def held(db, monkeypatch):
    monkeypatch.setitem(jobs.KINDS, KIND, jobs.Kind(run=lambda db, subject: None, model=None, name="Read a page"))
    monkeypatch.setattr(jobs, "_scheduler", jobs._Scheduler())
    jobs.set_paused(True)
    yield db
    jobs.set_paused(False)


def _row(db, subject, state, reason=None):
    job_id = jobs.enqueue(db, KIND, subject)
    db.execute("UPDATE jobs SET state = ?, reason = ?, finished_at = CASE WHEN ? IN ('done', 'failed', 'cancelled') "
               "THEN now() ELSE NULL END WHERE id = ?", [state, reason, state, job_id])
    return job_id


def _state(db, job_id):
    return db.execute_fetchone("SELECT state FROM jobs WHERE id = ?", [job_id])[0]


def _pause(client, job_id, paused=True):
    return client.put(f"/api/activity/jobs/{job_id}/paused", json={"paused": paused}).json()["state"]


def _stop(client, job_id):
    return client.post(f"/api/activity/jobs/{job_id}/cancel").json()["state"]


def _retry(client, job_id):
    r = client.post(f"/api/activity/jobs/{job_id}/retry")
    return r.json()["state"] if r.status_code == 200 else f"refused {r.status_code}"


def _delete(client, job_id):
    body = client.post("/api/activity/jobs/delete", json={"ids": [job_id]}).json()
    return "deleted" if job_id in body["deleted_ids"] else "skipped"


def test_queued__pause_holds_it_stop_ends_it_retry_leaves_it_delete_takes_it(held, client):
    a, b, c, d = (_row(held, f"q:{i}", "waiting") for i in range(4))
    assert _pause(client, a) == "paused" and _state(held, a) == "paused"
    assert _stop(client, b) == "cancelled" and _state(held, b) == "cancelled"
    assert _retry(client, c) == "waiting", "Retry on a queued row changes nothing"
    assert _delete(client, d) == "deleted" and _state(held, d) == "cancelled", "a deleted queued row is cancelled, never picked"


def test_paused__continue_queues_it_stop_ends_it_pause_again_is_nothing_delete_takes_it(held, client):
    a, b, c, d = (_row(held, f"p:{i}", "paused", jobs.PAUSED_REASON) for i in range(4))
    assert _pause(client, a, paused=False) == "waiting" and _state(held, a) == "waiting"
    assert _stop(client, b) == "cancelled"
    assert _pause(client, c) == "paused", "a paused row paused again stays paused, no error"
    assert _delete(client, d) == "deleted" and _state(held, d) == "cancelled"


def test_stopped_when_fichero_quit__continue_queues_it_and_it_is_no_longer_listed_as_stopped(held, client):
    a = _row(held, "quit:1", "running")
    jobs.resume(held)
    assert _state(held, a) == "paused"
    assert [i["id"] for i in client.get("/api/activity/stopped-at-quit").json()["items"]] == [a]
    assert _pause(client, a, paused=False) == "waiting", "Continue on the row itself works like the alert's"
    assert client.get("/api/activity/stopped-at-quit").json()["items"] == []


def test_failed__retry_queues_it_stop_ends_it_pause_is_nothing_delete_keeps_it_failed_and_hidden(held, client):
    a, b, c, d = (_row(held, f"f:{i}", "failed", "Out of credit on OpenRouter") for i in range(4))
    assert _retry(client, a) == "waiting" and _state(held, a) == "waiting"
    assert _stop(client, b) == "cancelled", "Stop on a failed row ends it, so it offers nothing more"
    assert _pause(client, c) == "failed", "Pause on a failed row changes nothing"
    assert _delete(client, d) == "deleted" and _state(held, d) == "failed", "a deleted failure keeps its state and reason"
    listed = {j["id"] for j in client.get("/api/activity/jobs").json()["jobs"]}
    assert d not in listed and a in listed


def test_done_and_stopped__retry_runs_a_stopped_one_again_a_done_one_is_left_delete_takes_both(held, client):
    done, stopped = _row(held, "d:1", "done"), _row(held, "s:1", "cancelled", "Stopped by you")
    assert _retry(client, done) == "done", "nothing to do again"
    assert _retry(client, stopped) == "waiting", "Retry on a stopped row runs it again"
    assert _pause(client, done) == "done" and _stop(client, done) == "done"
    assert _delete(client, done) == "deleted" and _delete(client, stopped) == "deleted"


def test_running__pause_and_stop_are_asked_of_it_delete_is_skipped_and_said(held, client):
    a = _row(held, "r:1", "running")
    jobs._scheduler.running_ids = lambda: [a]  # a lane thread runs it now
    assert _state(held, a) == "running"
    assert _pause(client, a) in ("running", "paused"), "a plain running row finishes its item; its answer is its state"
    assert _retry(client, a) == "running", "Retry on a running row changes nothing"
    assert _delete(client, a) == "skipped" and _state(held, a) == "running"
    assert _stop(client, a) in ("running", "stopping", "cancelled")
