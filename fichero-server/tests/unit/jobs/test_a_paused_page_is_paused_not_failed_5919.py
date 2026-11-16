"""A page whose work raises the run's pause is recorded as paused, not failed (#5919 sweep, ## 602): else Activity says
'failed' for a pause. (The text refinement this file also pinned was removed with `use_ai_refinement`, #5921.)"""
from __future__ import annotations

import asyncio
import time

from fichero_server.execution import jobs
from fichero_server.execution.cancellation import WorkflowPaused, clear_pause, request_pause
from fichero_server.llm import LLMConfig
from fichero_server.workflows.builder import _make_node_function
from fichero_server.workflows.types import NodeDef

KIND = "pausing-page-pp"


def test_work_that_raises_the_pause_leaves_a_paused_row_not_a_failed_one(db, monkeypatch):
    def work(db_, subject):
        raise WorkflowPaused("run-1")

    monkeypatch.setenv("FICHERO_JOB_THROTTLE", "0")
    monkeypatch.setitem(jobs.KINDS, KIND, jobs.Kind(run=work, model=None, lane="local-ml", name="Read a page"))
    job_id = jobs.enqueue(db, KIND, "p1")
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline and jobs.read_job(db, job_id)["state"] in ("waiting", "running"):
        time.sleep(0.02)
    row = jobs.read_job(db, job_id)
    assert row["state"] == "cancelled" and row["reason"] == "Paused with its run", row


def test_a_pause_raised_by_a_nodes_start_is_recorded_paused_and_the_nodes_call_never_ran(db, monkeypatch):
    """The workflows Step 1.4 boundary (#4402) through the job path: a pause pressed before a serial node starts is raised at the
    node's start; the page's row says paused, and the node's one long call did not run (before, it ran to the end and the row
    said done)."""
    run = "pause-before-node-start-run"
    calls: list = []

    async def one_long_call(inputs, state, llm_config):
        calls.append("ran")
        return {"text": "done"}

    node = _make_node_function(
        NodeDef(id="serial", tool="files", label="Serial", config={}), one_long_call,
        LLMConfig(provider="openai", model="gpt-4o-mini"), workflow_config={}, incoming_edges=[],
    )

    def work(db_, subject):
        asyncio.run(node({"outputs": {}, "completed_nodes": [], "task_id": run}))

    request_pause(run)
    try:
        monkeypatch.setenv("FICHERO_JOB_THROTTLE", "0")
        monkeypatch.setitem(jobs.KINDS, KIND, jobs.Kind(run=work, model=None, lane="local-ml", name="Read a page"))
        job_id = jobs.enqueue(db, KIND, "p2")
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and jobs.read_job(db, job_id)["state"] in ("waiting", "running"):
            time.sleep(0.02)
        row = jobs.read_job(db, job_id)
    finally:
        clear_pause(run)
    assert row["state"] == "cancelled" and row["reason"] == "Paused with its run", row
    assert calls == []
