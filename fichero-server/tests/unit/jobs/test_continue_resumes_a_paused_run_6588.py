"""A paused workflow run's Continue resumes it (#6588, `activity.pane.row-actions-on-the-table`): the row's one Continue
(`PUT /api/activity/jobs/{id}/paused` with `paused: false`) reaches the run's own Resume from its checkpoint. It answered 409
"A paused run is resumed with its Resume", so Continue on a paused run did nothing in the app but say so."""
from __future__ import annotations

from fichero_server.execution import jobs


def test_continue_on_a_paused_run_resumes_it_from_its_checkpoint(client, db, monkeypatch):
    from fichero_server.api.routes.workflow_execution import core

    jobs._ensure(db)
    jobs._record(db, "run-1", kind="workflow", subject="run-1", parent_id=None, state="paused", reason="Paused by you",
                 name="Read the letters")
    resumed = []

    async def resume(thread_id, _http, request=None, db=None, library_path=None):
        resumed.append(thread_id)

    monkeypatch.setattr(core, "resume_workflow", resume)
    answer = client.put("/api/activity/jobs/run-1/paused", json={"paused": False})
    assert answer.status_code == 200, answer.text
    assert answer.json()["state"] == "running"
    assert resumed == ["run-1"]


def test_a_paused_job_of_its_own_still_goes_back_to_waiting(client, db):
    jobs._ensure(db)
    job_id = jobs.enqueue(db, "thumbnail", "doc-1")
    db.execute("UPDATE jobs SET state = 'paused', reason = ? WHERE id = ?", [jobs.PAUSED_REASON, job_id])
    assert client.put(f"/api/activity/jobs/{job_id}/paused", json={"paused": False}).json()["state"] == "waiting"
