"""A resumed run uses the provider and model the person chose when it started, not the stored workflow's
(#5373, `activity.run.resume-keeps-model`)."""
# ruff: noqa: F811
from __future__ import annotations

from tests.unit.jobs.test_runs_are_jobs import _status, _wait_for, no_embedding_model  # noqa: F401
from tests.unit.workflows.test_resume_once_5373 import _paused_run


def test_a_resume_carries_the_runs_provider_and_model_override(client, db, request, monkeypatch):
    from fichero_server.api.routes.workflow_execution import core

    thread_id, workflow = _paused_run(client, db, request, "wf-keeps-model", provider_override="ollama", model_override="llama3")
    seen = {}
    real = core._run_workflow_in_background

    async def spy(*, request, **kwargs):
        seen["provider"], seen["model"] = request.provider_override, request.model_override
        return await real(request=request, **kwargs)

    monkeypatch.setattr(core, "_run_workflow_in_background", spy)
    assert client.post(f"/api/workflow-execution/threads/{thread_id}/resume", json={"answer": "split"}).status_code == 200
    assert _wait_for(lambda: _status(client, thread_id) in ("completed", "failed"))

    assert seen == {"provider": "ollama", "model": "llama3"}
