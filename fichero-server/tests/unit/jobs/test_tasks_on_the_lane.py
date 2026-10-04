"""The task API's six kinds run as jobs (#5353, `activity.task-queue-grows-into-jobs`).

Spec: docs/contributor_manual/specs/ui/activity-and-automatic-work.md. The task queue those routes
used was never started by the engine, so every `/api/tasks` call answered 503 and none of its
workers (reindex, metrics, repair, vector repair, KG metrics, re-anchor) ever ran outside tests.
These drive the real routes and the real scheduler; only the embedder is faked.
"""
from __future__ import annotations

import time

from fichero_server.db.manager import db_manager
from fichero_server.execution import jobs


def _wait_for_status(client, task_id, status, seconds=60.0):
    deadline = time.time() + seconds
    while time.time() < deadline:
        body = client.get(f"/api/tasks/{task_id}").json()
        if body["status"] == status:
            return body
        time.sleep(0.05)
    raise AssertionError(f"task {task_id} never reached {status}: {body}")


def test_a_metrics_task_runs_as_a_job_on_the_database_lane_and_keeps_its_result(client, db):
    """WHY: these routes answered 503 for as long as they existed; a person asking for the
    library's figures got nothing. The task is a job row now, and its result outlives the run."""
    r = client.post("/api/tasks/metrics", json={"name": "Figures"})
    assert r.status_code == 200, r.text
    task_id = r.json()["task_id"]
    done = _wait_for_status(client, task_id, "completed")
    assert done["name"] == "Figures" and done["result"]["success"] is True
    result = client.get(f"/api/tasks/{task_id}/result")
    assert result.status_code == 200 and "document_count" in result.json()["details"]
    assert db.execute_fetchone("SELECT kind, model, state FROM jobs WHERE id = ?", [task_id]) == (
        "metrics", None, "done")
    assert jobs.KINDS["metrics"].lane == "database"


def test_a_reindex_waits_in_the_queue_survives_a_restart_and_runs_on_the_model_lane(
        client, test_package, monkeypatch):
    """WHY: a reindex embeds every page: it is embedder work, so it runs on the model lane, one
    heavy model at a time, and like every job it waits out a pause and survives a quit. Asking
    twice while it waits is one reindex, not two."""
    db = db_manager.get_database(test_package)
    embedded = []
    monkeypatch.setattr(type(db), "embed", lambda self, doc, *a, **k: embedded.append(doc.id) or True)
    jobs.set_paused(True)
    first = client.post("/api/tasks/reindex").json()
    again = client.post("/api/tasks/reindex").json()
    assert first["task_id"] == again["task_id"] and first["status"] == "pending"

    db_manager.close_database(test_package)  # quit
    monkeypatch.setattr(jobs, "_scheduler", jobs._Scheduler())
    db = db_manager.get_database(test_package)
    assert client.get(f"/api/tasks/{first['task_id']}").json()["status"] == "pending"
    assert db.execute_fetchone("SELECT model FROM jobs WHERE id = ?", [first["task_id"]]) == ("embedder",)

    jobs.set_paused(False)
    _wait_for_status(client, first["task_id"], "completed")


def test_cancelling_a_pending_task_stops_its_job(client):
    """WHY: the task API's cancel must reach the job, or the cancelled reindex runs anyway."""
    jobs.set_paused(True)
    task_id = client.post("/api/tasks/kg-metrics").json()["task_id"]
    r = client.post(f"/api/tasks/{task_id}/cancel")
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    jobs.set_paused(False)
    time.sleep(0.3)
    assert client.get(f"/api/tasks/{task_id}").json()["status"] == "cancelled"
