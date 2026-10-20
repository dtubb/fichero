"""A pause waits for the pages still reading and keeps what they read; Resume reads each page once (#5919,
`activity.durable.paused-stays-paused`, `activity.durable.nothing-twice`).

Pages 2 and 3 are only waiting for the lane when the pause lands (they raise the pause at once); page 1 is mid-read. Raised at
once, the fan-out aborted and page 1's paid read was lost, so Resume read it again. Driven by events, no sleeps for ordering.
"""
# ruff: noqa: F811 -- pytest fixtures imported from the sibling test module
from __future__ import annotations

import asyncio

import pytest

from fichero_server.execution.cancellation import WorkflowPaused
from fichero_server.workflows import registry
from fichero_server.workflows.builder import build_graph
from fichero_server.workflows.checkpointer import AsyncDuckDBCheckpointer
from tests.unit.workflows.test_parallel_checkpointer_resume import (  # noqa: F401
    _build_workflow,
    _drive,
    _install_fake_tools,
    _three_pages,
    page_paths,
    temp_db,
)


@pytest.mark.asyncio
async def test_a_page_reading_when_the_pause_lands_is_kept_and_read_once(temp_db, page_paths, monkeypatch):
    files, documents = _three_pages(page_paths)
    _install_fake_tools(monkeypatch, files, documents, [])
    started: list[str] = []
    finished: list[str] = []
    paused_now = {"on": True}
    page_one_may_finish = asyncio.Event()

    async def transcribe(*, inputs=None, state=None, llm_config=None, **_kw):
        doc_id = (inputs["documents"][0] or {}).get("id")
        started.append(doc_id)
        if paused_now["on"]:
            if doc_id == "page-1":
                await page_one_may_finish.wait()  # mid-read when the pause lands
            else:
                asyncio.get_running_loop().call_later(0.05, page_one_may_finish.set)  # the read ends after the others raised
                raise WorkflowPaused("t-pause")  # only waiting for the lane: withdrawn with the run's pause
        finished.append(doc_id)
        return {"text": f"transcribed::{doc_id}", "artifacts": []}

    monkeypatch.setitem(registry.TOOLS, "transcribe", transcribe)
    checkpointer = AsyncDuckDBCheckpointer.from_db_path(temp_db)
    workflow = _build_workflow()
    config = {"configurable": {"thread_id": "t-pause", "checkpoint_ns": ""}}
    initial = {"workflow_id": "wf-parallel-regression", "library_path": "", "inputs": {}, "selected_doc_ids": []}

    with pytest.raises(WorkflowPaused):
        await _drive(build_graph(workflow, enable_parallel=True, checkpointer=checkpointer, skip_cache=True), initial, config)
    assert finished == ["page-1"], f"the page reading when the pause landed finished and was kept: {finished}"

    paused_now["on"] = False  # Resume
    await _drive(build_graph(workflow, enable_parallel=True, checkpointer=checkpointer, skip_cache=True), None, config)

    assert started.count("page-1") == 1, f"page 1 was read again on Resume: started={started}"
    assert sorted(finished) == ["page-1", "page-2", "page-3"], f"every page read once: finished={finished}"
