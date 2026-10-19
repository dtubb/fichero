"""A refusal of the RUN's language (the project's or the node's: Apple Vision cannot read it here) holds for every page, so
the node fails at the first and the pages not yet started do not try; a refusal of one PAGE's own language (a Latin page
among Spanish ones) stops that page alone (owner, 2026-10-19; review 359; `source.read.vision-locale`)."""
from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from fichero_server.workflows.builder import SystemicErrorDetected, build_graph
from fichero_server.workflows.tools import vision_base
from tests.unit.workflows.test_parallel_fanout_no_semaphore_deadlock import (
    PAGE_COUNT,
    _fan_out_workflow,
    _fresh_vision_semaphore,  # noqa: F401 -- the autouse fixture
    _library,
)

SPANISH = "Apple Vision can't read Spanish on this Mac. Choose another reader for this step."
LATIN = "Apple Vision can't read Latin on this Mac. Choose another reader for this step."


def test_a_refused_locale_is_typed_with_where_it_came_from(monkeypatch):
    monkeypatch.setattr(vision_base, "_supported_vision_locales", lambda: frozenset({"en-US"}))
    for source in ("page", "run"):
        vision_base._language_source.set(source)
        with pytest.raises(vision_base.VisionLocaleRefused) as caught:
            vision_base.validate_vision_language("es")
        assert (caught.value.locale, caught.value.source) == ("es-ES", source)
    vision_base._language_source.set("run")


async def _run(tmp_path, answer):
    calls: list[int] = []

    async def process_vision(**kwargs):
        calls.append(1)
        await asyncio.sleep(0)
        return answer(len(calls), kwargs)

    library_path, _pdf, db = _library(tmp_path)
    graph = build_graph(_fan_out_workflow(), skip_cache=True)
    state = {"selected_doc_ids": ["pdf-1"], "library_path": library_path, "task_id": "run-refused",
             "workflow_id": "wf-4553", "input_files": [], "outputs": {}, "completed_nodes": []}
    with (
        patch("fichero_server.workflows.tools.sources.db_manager.get_database", return_value=db),
        patch("fichero_server.db.db_manager.get_database", return_value=db),
        patch("fichero_server.workflows.tools.transcribe.process_vision", new=process_vision),
    ):
        try:
            await asyncio.wait_for(graph.ainvoke(state), timeout=60)
            return calls, None
        except SystemicErrorDetected as stopped:
            return calls, stopped


def _failure(words: str, source: str) -> dict:
    return {"text": "", "results": [{"file": "p", "text": "", "error": words, "refusal": {"locale": "x", "source": source}}]}


@pytest.mark.asyncio
async def test_the_runs_own_language_refused_stops_the_pages_not_yet_started(tmp_path):
    calls, stopped = await _run(tmp_path, lambda n, kw: _failure(SPANISH, "run"))
    assert stopped is not None and SPANISH in str(stopped)
    assert len(calls) < PAGE_COUNT, f"{len(calls)} of {PAGE_COUNT} pages tried after the first refusal"


@pytest.mark.asyncio
async def test_one_latin_page_refused_does_not_stop_the_spanish_pages(tmp_path):
    """The first page is Latin (its own language, refused); every other page is Spanish and reads."""
    def answer(n, kwargs):
        return _failure(LATIN, "page") if n == 1 else {"text": "ok", "results": [{"file": "p", "text": "ok"}]}

    calls, stopped = await _run(tmp_path, answer)
    assert stopped is None, "a page's own refused language must not stop the others"
    assert len(calls) == PAGE_COUNT, f"only {len(calls)} of {PAGE_COUNT} pages were tried"
