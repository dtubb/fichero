"""A chained step is judged by the project it was started in, and a refused step says why (#6354, #5368).

Met 2026-11-13: on a page of a project, Detect Segments then Read Lines (a vision model on a cloud provider) was refused
with "No project is open for this call", and Activity said only "No reason was recorded". Two faults:

- the chain runs on its own thread and loop, which held none of the request's project, so the cloud-consent gate
  (`ai.where.one-egress-gate`) saw no project; the chain now binds the library it was started in;
- a step refused before it ran left no run row, so nothing carried the refusal; it now has a failed row whose error (and
  Activity reason) are the refusal's words (`activity.run.never-fails-silently`).

Driven through the real `_run_chain_steps`; the step's validation is the gate's own check (`llm._enforce_local_only_provider`,
which is what the preflight's model build reaches), the project's answer is its saved Set Up, and the rows are read from the
library's run record and jobs table.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from fichero_server import llm
from fichero_server.api.routes.workflow import chains as chain_routes
from fichero_server.execution.chaining import ChainExecutionResult, ChainStep, ChainStepStatus, WorkflowChain
from fichero_server.recipes import places
from fichero_server.recipes.project import write_project_setup
from fichero_server.workflows.activity import get_activity_tracker

CLOUD = llm.LLMConfig(provider="openrouter", model="google/gemini-3.1-flash-lite")


@pytest.fixture(autouse=True)
def _only_the_projects_rule(monkeypatch):
    monkeypatch.delenv("FICHERO_LOCAL_ONLY", raising=False)
    monkeypatch.setattr(places, "get_places", lambda: None)


def _project(tmp_path, *, cloud_allowed: bool) -> str:
    library = tmp_path / "p.fichero"
    library.mkdir()
    write_project_setup(library, {"purposes": ["transcribe"], "cloud_allowed": cloud_allowed}, None)
    return str(library)


def _validates_like_the_preflight(workflow, request, db) -> None:
    """The preflight's model build reaches the gate; a refusal arrives as the validation error the route reports."""
    from fastapi import HTTPException

    try:
        llm._enforce_local_only_provider(CLOUD, kind="vision")
    except llm.EgressRefusedError as refused:
        raise HTTPException(status_code=400, detail=f"Workflow validation failed: Node 'Read' (transcribe): {refused}") from refused


def _run_chain(db, library: str):
    chain = WorkflowChain(name="Segments then read", steps=[
        ChainStep(id="s1", workflow_id="wf-detect", name="Detect Segments (Kraken)"),
        ChainStep(id="s2", workflow_id="wf-read", name="Read Lines (Kraken lines, vision model)"),
    ])
    threads = [(step, f"thread-{step.id}") for step in chain.steps]
    chain_routes._running_executions["exec-1"] = ChainExecutionResult(
        chain_id=chain.id, execution_id="exec-1", status=ChainStepStatus.PENDING, step_results=[])
    result = chain_routes._running_executions["exec-1"]
    from fichero_server.execution.chaining import ChainStepResult

    result.step_results = [ChainStepResult(step_id=s.id, workflow_id=s.workflow_id, status=ChainStepStatus.PENDING)
                           for s, _ in threads]
    seams = [
        patch.object(chain_routes, "_acquire_chain_db", return_value=db),
        patch.object(chain_routes, "_load_step_workflow", side_effect=lambda _db, wid: type("W", (), {
            "name": wid, "nodes": [], "edges": []})()),
        patch.object(chain_routes, "_validate_step_workflow", side_effect=_validates_like_the_preflight),
        patch.object(chain_routes, "_record_step_run_accepted", new_callable=AsyncMock),
        patch.object(chain_routes, "_run_step_workflow", new_callable=AsyncMock),
        patch.object(chain_routes, "_step_run_outcome", return_value=("completed", None)),
    ]
    for seam in seams:
        seam.start()
    try:
        asyncio.run(chain_routes._run_chain_steps("exec-1", chain, threads, {}, library, chain_routes._ChainStepsCanceller()))
    finally:
        for seam in seams:
            seam.stop()
    return result


@pytest.fixture(autouse=True)
def _clean():
    yield
    chain_routes._running_executions.clear()


def test_a_chain_on_a_project_that_allows_cloud_models_passes_validation_at_every_step(db, tmp_path):
    result = _run_chain(db, _project(tmp_path, cloud_allowed=True))
    assert [r.status for r in result.step_results] == [ChainStepStatus.COMPLETED, ChainStepStatus.COMPLETED]


def test_a_chain_on_a_project_that_keeps_pages_here_is_still_refused_and_says_why(db, tmp_path):
    result = _run_chain(db, _project(tmp_path, cloud_allowed=False))
    first, second = result.step_results
    assert first.status == ChainStepStatus.FAILED  # both steps meet the gate here (the stand-in judges every step)
    assert "keeps its pages on this Mac" in (first.error or "") and second.status == ChainStepStatus.SKIPPED
    # The refusal reaches the run row Activity and the step's popover read, and the job row's reason.
    run = asyncio.run(get_activity_tracker(str(db.path)).store.get_workflow_run("thread-s1"))
    assert run.status == "failed" and "keeps its pages on this Mac" in (run.error or "")
    reason = db.execute_fetchone("SELECT state, reason FROM jobs WHERE subject = ?", ["thread-s1"])
    assert reason[0] == "failed" and "keeps its pages on this Mac" in (reason[1] or "")


def test_the_chain_names_no_project_open_only_when_it_truly_has_none(db):
    result = _run_chain(db, "")  # a chain started with no library at all: the old answer, still in words
    assert "No project is open" in (result.step_results[0].error or "")


def test_a_refusal_that_cannot_be_recorded_says_so_to_the_chain(db):
    """`_record_step_run_refused` never raises (the chain's row carries the reason) but answers False when the run row
    cannot be written, so the step's error says Activity could not record it (#6354)."""
    step = ChainStep(id="s1", workflow_id="wf", name="Read Lines")
    with patch.object(chain_routes, "get_activity_tracker", side_effect=RuntimeError("store down"), create=True), \
            patch("fichero_server.workflows.activity.get_activity_tracker", side_effect=RuntimeError("store down")):
        recorded = asyncio.run(chain_routes._record_step_run_refused(db, "thread-x", step, None, None, "refused"))
    assert recorded is False
