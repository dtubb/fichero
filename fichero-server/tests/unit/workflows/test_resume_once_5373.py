"""Resuming a run that is already running is refused, so two clicks never start two workers on one checkpoint
thread (#5373, `activity.run.resume-once`). Through the routes, with a real run paused on a review step."""
# ruff: noqa: F811
from __future__ import annotations

from langgraph.types import interrupt

from fichero_server.execution import runner
from fichero_server.models import Workflow
from fichero_server.workflows.registry import register_tool
from tests.unit.jobs.test_runs_are_jobs import _status, _wait_for, no_embedding_model  # noqa: F401


async def _asks(*args, **kwargs):
    return {"answer": interrupt({"kind": "human_review", "question": "Which grouping?"})}


def test_a_second_resume_of_a_running_run_is_refused(client, db, request):
    from fichero_server.workflows import registry, validation

    registry._ensure_tools_loaded()
    register_tool(name="asks", display_name="Asks", input_ports=[], output_ports=[])(_asks)
    request.addfinalizer(lambda: (registry._TOOLS.pop("asks", None), registry._TOOL_DEFS.pop("asks", None)))
    validation_stub = lambda *a, **k: []  # noqa: E731
    original = validation.validate_workflow_llm_preflight
    validation.validate_workflow_llm_preflight = validation_stub
    request.addfinalizer(lambda: setattr(validation, "validate_workflow_llm_preflight", original))
    db.save(Workflow(id="wf-resume-once", name="Resume once", nodes=[
        {"id": "ask", "tool": "asks", "label": "Ask", "inputs": {}, "config": {}}], edges=[]))
    thread_id = client.post("/api/workflow-execution/execute", json={"workflow_id": "wf-resume-once", "skip_cache": True}).json()["thread_id"]
    assert _wait_for(lambda: _status(client, thread_id) == "paused")

    runner._running_workflows[thread_id]["status"] = "running"  # a first resume is under way
    r = client.post(f"/api/workflow-execution/threads/{thread_id}/resume", json={"answer": "split"})

    assert r.status_code == 409, r.text
    assert "already running" in r.text
