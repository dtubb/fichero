"""A page a person stops alone is not a page that failed (#5935, `activity.stop.page-skips-run-stops-children`).

`process_vision`'s per-file handlers turned any `Exception` into that file's `{"error": ...}` result; `PageStopped`
(a `JobCancelled`) was caught there, so the stopped page was recorded failed. It must reach the fan-out, which skips it
(`cancelled`) while the run goes on; a real failure in the same run still reads failed.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from fichero_server.execution.jobs import PageStopped
from fichero_server.llm import LLMConfig
from fichero_server.workflows.builder import SystemicErrorDetected, build_graph
from fichero_server.workflows.tools.vision_base import VisionToolConfig, process_vision
from tests.unit.workflows.test_parallel_fanout_no_semaphore_deadlock import (
    PAGE_COUNT,
    _fan_out_workflow,
    _fresh_vision_semaphore,  # noqa: F401 -- the autouse fixture
    _library,
)


async def _read(tmp_path: Path, vision):
    image = tmp_path / "page.png"
    image.write_bytes(b"\x89PNG stub")
    with (
        patch("fichero_server.workflows.tools.vision_base.save_artifact", new=AsyncMock(return_value=None)),
        patch("fichero_server.workflows.tools.vision_base.file_to_data_uri", return_value="data:image/png;base64,AAAA"),
        patch("fichero_server.llm.vision", new=vision),
    ):
        return await process_vision(
            files=[str(image)], documents=[], prompt="Describe.",
            llm_config=LLMConfig(provider="openai", model="gpt-4o", api_key="k"), library_path="", task_id=None,
            tool_config=VisionToolConfig(artifact_type="transcription", update_page_content=False, trigger_embedding=False,
                                         supports_apple_vision=True),
            vision_mode="llm")


@pytest.mark.asyncio
async def test_the_readers_per_file_handler_lets_a_stopped_page_through(tmp_path):
    with pytest.raises(PageStopped):
        await _read(tmp_path, AsyncMock(side_effect=PageStopped("Stopped by you")))


@pytest.mark.asyncio
async def test_a_real_failure_is_still_that_files_error(tmp_path):
    result = await _read(tmp_path, AsyncMock(side_effect=RuntimeError("model fell over")))
    assert "model fell over" in str(result["results"][0]["error"])


async def _fan_out(tmp_path, answer):
    calls: list[int] = []

    async def fake_process_vision(**kwargs):
        calls.append(1)
        await asyncio.sleep(0)
        return answer(len(calls))

    library_path, _pdf, db = _library(tmp_path)
    graph = build_graph(_fan_out_workflow(), skip_cache=True)
    state = {"selected_doc_ids": ["pdf-1"], "library_path": library_path, "task_id": "run-5935",
             "workflow_id": "wf-4553", "input_files": [], "outputs": {}, "completed_nodes": []}
    with (
        patch("fichero_server.workflows.tools.sources.db_manager.get_database", return_value=db),
        patch("fichero_server.db.db_manager.get_database", return_value=db),
        patch("fichero_server.workflows.tools.transcribe.process_vision", new=fake_process_vision),
    ):
        return await asyncio.wait_for(graph.ainvoke(state), timeout=60)


def _ok(n):
    return {"text": f"t{n}", "texts": [f"t{n}"], "results": [{"file": f"p{n}", "text": f"t{n}"}], "values": [None],
            "artifact_ids": [], "output_files": [], "page_records": []}


@pytest.mark.asyncio
async def test_a_page_stopped_alone_is_skipped_cancelled_and_the_run_completes(tmp_path):
    def answer(n):
        if n == 1:
            raise PageStopped("Stopped by you")
        return _ok(n)

    try:
        final = await _fan_out(tmp_path, answer)
    except SystemicErrorDetected as exc:  # pragma: no cover -- the failure this pins
        pytest.fail(f"a stopped page aborted the run: {exc}")
    results = final["outputs"]["transcribe"]["results"]
    cancelled = [r for r in results if r.get("cancelled")]
    assert len(cancelled) == 1
    assert not [r for r in results if r.get("error") and not r.get("cancelled")], "the stopped page counted as a failure"
    assert len(results) == PAGE_COUNT


@pytest.mark.asyncio
async def test_a_real_failure_beside_a_stopped_page_still_reads_failed(tmp_path):
    def answer(n):
        if n == 1:
            raise PageStopped("Stopped by you")
        if n == 2:
            raise RuntimeError("model fell over")
        return _ok(n)

    final = await _fan_out(tmp_path, answer)
    results = final["outputs"]["transcribe"]["results"]
    assert sum(1 for r in results if r.get("cancelled")) == 1
    failed = [r for r in results if r.get("error") and not r.get("cancelled")]
    assert len(failed) == 1 and "model fell over" in failed[0]["error"]
