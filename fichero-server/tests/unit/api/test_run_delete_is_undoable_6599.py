"""A run's Delete is undoable like a job's (`activity.pane.one-undo-per-action`, #6599, #6588).

Spec: `docs/contributor_manual/specs/ui/activity-pane.md`. `workflow_run.delete` was not undoable: a person deleting a run
and a job together got the job back on Undo and the run stayed gone. The delete now keeps each run's status
(`deleted_from`); its inverse, `workflow_run.undelete`, puts the run back as it was, events and all.
"""
from __future__ import annotations

from tests.unit.api.test_routes_workflow_execution import _seed_run


def _invoke(client, name, params):
    answer = client.post("/api/actions/invoke", json={"name": name, "params": params})
    assert answer.status_code == 200, answer.text
    return answer.json()


def _listed(client):
    return {i["thread_id"]: i["status"] for i in client.get("/api/workflow-execution/runs").json()["items"]}


def test_undo_of_a_run_delete_puts_it_back_as_it_was(client, db):
    _seed_run(db, "thread-undo-failed", status="failed")
    _seed_run(db, "thread-undo-done", status="completed")
    done = _invoke(client, "workflow_run.delete", {"thread_ids": ["thread-undo-failed", "thread-undo-done"]})
    assert sorted(done["result"]["deleted_ids"]) == ["thread-undo-done", "thread-undo-failed"]
    assert "thread-undo-failed" not in _listed(client)

    undone = client.post("/api/actions/audit/undo", json={"audit_ids": [done["audit_id"]]})
    assert undone.status_code == 200, undone.text
    listed = _listed(client)
    assert listed.get("thread-undo-failed") == "failed" and listed.get("thread-undo-done") == "completed"


def test_undelete_leaves_a_run_not_deleted_alone(client, db):
    _seed_run(db, "thread-undo-live", status="failed")
    put_back = _invoke(client, "workflow_run.undelete", {"thread_ids": ["thread-undo-live", "thread-nowhere"]})
    assert put_back["result"]["undeleted_ids"] == []
    assert _listed(client).get("thread-undo-live") == "failed"
