"""Archive hides and keeps; Put Back restores; Delete removes from every list and Undo brings the row back as it was (#6583).

Spec: docs/contributor_manual/specs/ui/activity-pane.md, `activity.pane.archive-old-runs`. WHY (owner 2026-11-13, 23:30): old
runs must leave the table but keep their results, cost and history, be shown on request, and come back; a deleted row is gone
from every list, Retry's included. Through the routes and the real jobs table; the lane is held.
"""
from __future__ import annotations

import pytest

from fichero_server.execution import jobs

KIND = "t-archive"


@pytest.fixture
def held(db, monkeypatch):
    monkeypatch.setitem(jobs.KINDS, KIND, jobs.Kind(run=lambda db, subject: None, model=None, name="Run a thing"))
    monkeypatch.setattr(jobs, "_scheduler", jobs._Scheduler())
    jobs.set_paused(True)
    yield db
    jobs.set_paused(False)


def _row(db, subject, state, reason=None, parent=None, days_ago=0):
    job_id = jobs.enqueue(db, KIND, subject)
    db.execute("UPDATE jobs SET state = ?, reason = ?, parent_id = ?, finished_at = CASE WHEN ? IN ('done', 'failed', 'cancelled') "
               "THEN now() - INTERVAL (?) DAY ELSE NULL END WHERE id = ?", [state, reason, parent, state, days_ago, job_id])
    return job_id


def _listed(client, archived=False):
    return {j["id"]: j for j in client.get("/api/activity/jobs", params={"archived": archived}).json()["jobs"]}


def _row_in_table(db, job_id):
    return db.execute_fetchone("SELECT state, reason, cleared_at IS NOT NULL, deleted_at IS NOT NULL FROM jobs WHERE id = ?", [job_id])


def test_archive_hides_a_finished_run_and_keeps_everything__put_back_lists_it_again(held, client):
    run = _row(held, "a:run", "failed", "2 pages were not read")
    page = _row(held, "a:run:page", "failed", "timed out", parent=run)
    assert run in _listed(client)

    r = client.post("/api/activity/jobs/archive", json={"ids": [run]})

    assert r.status_code == 200, r.text
    assert r.json() == {"archived_ids": [run], "skipped_ids": [], "count": 1}
    assert run not in _listed(client), "archived: out of the table"
    archived = _listed(client, archived=True)
    assert run in archived and archived[run]["state"] == "failed" and archived[run]["reason"] == "2 pages were not read"
    assert _row_in_table(held, page) == ("failed", "timed out", True, False), "the rows under it are kept, marked with it"

    assert client.post("/api/activity/jobs/unarchive", json={"ids": [run]}).json() == {"ids": [run], "count": 1}
    assert run in _listed(client) and run not in _listed(client, archived=True)
    assert _row_in_table(held, page)[2] is False


def test_archive_finished_takes_ended_rows_by_state_and_age_and_refuses_what_still_goes(held, client):
    old_done = _row(held, "b:old", "done", days_ago=10)
    new_done = _row(held, "b:new", "done", days_ago=1)
    failed = _row(held, "b:failed", "failed", "no model", days_ago=3)
    waiting = _row(held, "b:waiting", "waiting")
    paused = _row(held, "b:paused", "paused", jobs.PAUSED_REASON)

    r = client.post("/api/activity/jobs/archive", json={"states": ["done", "failed", "cancelled"], "older_than_days": 2})
    assert sorted(r.json()["archived_ids"]) == sorted([old_done, failed]), r.json()
    assert new_done not in r.json()["archived_ids"], "ended yesterday: younger than the asked age"

    r = client.post("/api/activity/jobs/archive", json={"ids": [waiting, paused, f"waiting:{KIND}"]})
    assert r.json()["archived_ids"] == [] and sorted(r.json()["skipped_ids"]) == sorted([waiting, paused, f"waiting:{KIND}"])
    assert _row_in_table(held, waiting)[0] == "waiting" and _row_in_table(held, paused)[0] == "paused"


def test_delete_removes_the_row_from_the_table_the_archive_and_retry__undo_restores_its_former_state(held, client):
    archived = _row(held, "c:archived", "failed", "no credit")
    client.post("/api/activity/jobs/archive", json={"ids": [archived]})
    paused = _row(held, "c:paused", "paused", jobs.PAUSED_REASON)

    r = client.post("/api/activity/jobs/delete", json={"ids": [archived, paused]})

    assert sorted(r.json()["deleted_ids"]) == sorted([archived, paused])
    assert archived not in _listed(client, archived=True) and archived not in _listed(client)
    assert paused not in _listed(client)
    assert _row_in_table(held, paused) == ("cancelled", "Deleted by you", True, True), "stopped, so no lane picks it"
    retry = client.post(f"/api/activity/jobs/{archived}/retry")
    assert retry.status_code != 200, "a deleted row is in no Retry list"
    assert "deleted" in retry.text

    undone = client.post("/api/activity/jobs/undelete", json={"ids": [archived, paused]}).json()
    assert sorted(undone["ids"]) == sorted([archived, paused])
    assert _row_in_table(held, paused) == ("paused", jobs.PAUSED_REASON, False, False), "back as it was"
    assert _row_in_table(held, archived) == ("failed", "no credit", True, False), "back as it was: archived"
    assert archived in _listed(client, archived=True) and paused in _listed(client)


def test_undo_of_delete_keeps_an_archive_mark_a_row_under_it_had_before(held, client):
    """Review 2026-11-14: Undo of Delete lifted `cleared_at` from every row under the deleted one, so a row archived before
    the delete came back unarchived. Only the mark the delete set comes off."""
    run = _row(held, "d:run", "failed", "1 page was not read")
    page = _row(held, "d:run:page", "failed", "timed out", parent=run)
    fresh = _row(held, "d:run:fresh", "done", parent=run)
    client.post("/api/activity/jobs/archive", json={"ids": [page]})

    client.post("/api/activity/jobs/delete", json={"ids": [run]})
    assert client.post("/api/activity/jobs/undelete", json={"ids": [run]}).json()["ids"] == [run]

    assert _row_in_table(held, run) == ("failed", "1 page was not read", False, False)
    assert _row_in_table(held, fresh)[2:] == (False, False), "the delete's mark is lifted"
    assert _row_in_table(held, page) == ("failed", "timed out", True, False), "archived before the delete: still archived"


def test_archive_and_delete_are_undoable_audited_actions(held):
    from fichero_server.actions.registry import registry

    assert {"job.archive", "job.unarchive", "job.delete", "job.undelete"} <= set(registry.names())
