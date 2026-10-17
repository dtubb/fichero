"""A review step pauses a real run and its answer reaches the tool, through the routes (#5429,
`activity.run.review-step-pauses`): started with `POST /api/workflow-execution/execute`, settled as paused
`awaiting_review` with the question, resumed with `POST .../threads/{id}/resume` and an answer. Only the
asking tool is a stub (it calls LangGraph's interrupt(), as `ask_human` does)."""
# ruff: noqa: F811
from __future__ import annotations

from langgraph.types import interrupt

from fichero_server.workflows.registry import register_tool

from fichero_server.models import DocType, Document, FileType, Status, Workflow
from tests.unit.jobs.test_runs_are_jobs import _status, _wait_for, no_embedding_model  # noqa: F401


async def _asks(*args, **kwargs):
    answer = interrupt({"kind": "human_review", "question": "Which grouping?"})
    return {"answer": answer}


def test_a_review_step_pauses_the_run_and_the_answer_reaches_the_tool_on_resume(client, db, monkeypatch, request):
    from fichero_server.workflows import registry, validation

    registry._ensure_tools_loaded()
    register_tool(name="asks", display_name="Asks", input_ports=[], output_ports=[])(_asks)
    request.addfinalizer(lambda: (registry._TOOLS.pop("asks", None), registry._TOOL_DEFS.pop("asks", None)))

    monkeypatch.setattr(validation, "validate_workflow_llm_preflight", lambda *a, **k: [])
    page = Document(name="p", doc_type=DocType.file, file_type=FileType.text, status=Status.completed, page_content="x")
    db.save(page)
    db.save(Workflow(id="wf-review-routes", name="Review", nodes=[
        {"id": "ask", "tool": "asks", "label": "Ask", "inputs": {}, "config": {}}], edges=[]))

    r = client.post("/api/workflow-execution/execute", json={"workflow_id": "wf-review-routes", "skip_cache": True})
    assert r.status_code == 202, r.text
    thread_id = r.json()["thread_id"]

    assert _wait_for(lambda: _status(client, thread_id) in ("paused", "failed", "completed"))
    status = client.get(f"/api/workflow-execution/threads/{thread_id}/status").json()
    assert status["status"] == "paused", status

    assert client.post(f"/api/workflow-execution/threads/{thread_id}/resume", json={"answer": "split"}).status_code in (200, 202)
    assert _wait_for(lambda: _status(client, thread_id) in ("completed", "failed"))
    assert _status(client, thread_id) == "completed"
    assert "split" in str(client.get(f"/api/workflow-execution/threads/{thread_id}/status").json()), "the answer reached the tool"
