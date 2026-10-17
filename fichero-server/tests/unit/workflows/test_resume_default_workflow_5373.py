"""A paused run of a shipped default workflow resumes: the workflow is found as /execute finds it, not in the
library's store only (#5373, `activity.run.resume-default-workflow`)."""
# ruff: noqa: F811
from __future__ import annotations

from tests.unit.jobs.test_runs_are_jobs import _status, _wait_for, no_embedding_model  # noqa: F401
from tests.unit.workflows.test_resume_once_5373 import _paused_run


def test_a_paused_run_of_a_default_workflow_resumes(client, db, request, monkeypatch):
    thread_id, workflow = _paused_run(client, db, request, "wf-a-default")
    db.execute("DELETE FROM workflows WHERE id = ?", [workflow.id])  # a default lives in the global library, not here
    monkeypatch.setattr("fichero_server.workflows.default_workflows.resolve_default_workflow",
                        lambda wf_id: workflow if wf_id == workflow.id else None)

    r = client.post(f"/api/workflow-execution/threads/{thread_id}/resume", json={"answer": "split"})

    assert r.status_code == 200, r.text
    assert _wait_for(lambda: _status(client, thread_id) in ("completed", "failed"))
    assert _status(client, thread_id) == "completed"
