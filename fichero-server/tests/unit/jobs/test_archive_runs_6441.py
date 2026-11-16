"""A workflow run archives too, never by a delete: it leaves the runs list, keeps everything, and Undo or Put Back lists it again (#6441).

Spec: docs/contributor_manual/specs/ui/activity-pane.md, `activity.pane.archive-old-runs`. WHY (owner, via the manager
2026-11-14): Archive on a run row was the soft delete; Archive must keep the run. Through the routes and the real tables.
"""
from __future__ import annotations

import pytest

from fichero_server.core.timeutil import utc_now
from fichero_server.execution import jobs
from fichero_server.models.activity_records import WorkflowRunRecord

KIND = "t-run-archive"


@pytest.fixture
def held(db, monkeypatch):
    monkeypatch.setitem(jobs.KINDS, KIND, jobs.Kind(run=lambda db, subject: None, model=None, name="Run a recipe"))
    monkeypatch.setattr(jobs, "_scheduler", jobs._Scheduler())
    jobs.set_paused(True)
    yield db
    jobs.set_paused(False)


def _run(db, status, state):
    """A run: its record and its row in `jobs` share the id, as the engine writes them."""
    run_id = jobs.enqueue(db, KIND, f"run:{status}")
    db.execute("UPDATE jobs SET state = ? WHERE id = ?", [state, run_id])
    db.save(WorkflowRunRecord(id=run_id, workflow_id="w", workflow_name="Read", status=status, started_at=utc_now()))
    return run_id


def _runs(client, archived=False):
    return {r["thread_id"] for r in client.get("/api/workflow-execution/runs", params={"archived": archived}).json()["items"]}


def test_archive_takes_an_ended_run_out_of_the_list_and_keeps_it__undo_puts_it_back(held, client):
    done = _run(held, "completed", "done")
    going = _run(held, "paused", "paused")  # not swept as stale, and not ended
    assert {done, going} <= _runs(client)

    r = client.post("/api/workflow-execution/runs/archive", json={"thread_ids": [done, going, "nope"]})

    assert r.status_code == 200, r.text
    assert r.json() == {"archived_ids": [done], "skipped_ids": [going, "nope"], "count": 1}
    assert done not in _runs(client) and going in _runs(client)
    assert _runs(client, archived=True) == {done}
    assert held.execute_fetchone("SELECT status FROM workflowrunrecords WHERE id = ?", [done])[0] == "completed", "kept"

    assert client.post("/api/activity/jobs/unarchive", json={"ids": [done]}).json() == {"ids": [done], "count": 1}
    assert done in _runs(client) and not _runs(client, archived=True)


def test_the_run_archive_is_an_undoable_action_whose_undo_is_put_back(held, client):
    from fichero_server.actions import registry

    spec = registry.get("workflow_run.archive")
    assert spec.undoable
    assert spec.invert(None, {"archived_ids": ["r1"]}, None) == ("job.unarchive", {"ids": ["r1"]})
