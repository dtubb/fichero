"""A refusal that holds for every page (Apple Vision cannot read the project's language here) fails the node at once:
the pages not yet started do not try (owner, 2026-10-19; `source.read.vision-locale`). Before, every page tried and
failed, then the run said '5 consecutive failures' with the first page's words."""
from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from fichero_server.workflows import page_retry
from fichero_server.workflows.builder import SystemicErrorDetected, build_graph
from tests.unit.workflows.test_parallel_fanout_no_semaphore_deadlock import (
    PAGE_COUNT,
    _fan_out_workflow,
    _fresh_vision_semaphore,  # noqa: F401 -- the autouse fixture
    _library,
)

REFUSAL = "Apple Vision can't read Spanish on this Mac. Choose another reader for this step."


def test_the_refusal_is_known_to_hold_for_every_page_and_a_passing_cause_is_not():
    assert page_retry.is_refusal_for_every_page(REFUSAL)
    assert not page_retry.is_refusal_for_every_page("the model server is not ready")
    assert not page_retry.is_passing_cause(REFUSAL)  # and no second read of the page is ever made for it


@pytest.mark.asyncio
async def test_pages_not_yet_started_do_not_try_after_a_refusal_for_every_page(tmp_path):
    calls: list[int] = []

    async def refuses(**kwargs):
        calls.append(1)
        await asyncio.sleep(0)
        raise ValueError(REFUSAL)

    library_path, _pdf, db = _library(tmp_path)
    graph = build_graph(_fan_out_workflow(), skip_cache=True)
    state = {"selected_doc_ids": ["pdf-1"], "library_path": library_path, "task_id": "run-refused",
             "workflow_id": "wf-4553", "input_files": [], "outputs": {}, "completed_nodes": []}
    with (
        patch("fichero_server.workflows.tools.sources.db_manager.get_database", return_value=db),
        patch("fichero_server.db.db_manager.get_database", return_value=db),
        patch("fichero_server.workflows.tools.transcribe.process_vision", new=refuses),
    ):
        with pytest.raises(SystemicErrorDetected) as stopped:
            await asyncio.wait_for(graph.ainvoke(state), timeout=60)
    assert REFUSAL in str(stopped.value)
    assert len(calls) < PAGE_COUNT, f"{len(calls)} of {PAGE_COUNT} pages tried after the first refusal"
