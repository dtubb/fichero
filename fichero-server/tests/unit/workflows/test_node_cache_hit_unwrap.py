"""Cache-hit unwrap regression (2026-09-02, Marshall sample).

``NodeCache.get`` returns a ``CacheEntry`` WRAPPER whose tool result lives in
``entry.result``. The parallel fan-out fed the wrapper straight into
``parallel_results`` as the item's ``result``; the aggregation barrier's
``isinstance(result, dict)`` then missed every field, so a cache HIT
"completed" with empty text and the next node died with "No text provided".
The worth-caching guard was equally blind: ``bool(entry)`` is always True, so
poisoned empty entries sailed through on both the parallel and sequential
paths.

This runs the shipped Transcribe preset TWICE on the same file with the cache
enabled. The second run must hit the cache and still hand downstream the same
non-empty text the first run produced.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from tests.unit.workflows.test_default_workflow_e2e_harness import (
    FIXTURE_TEXT,
    _install_deterministic_workflow_stubs,
    _load_workflow_by_name,
    _seed_fixture_library,
)

from fichero_server.workflows.builder import build_graph
from fichero_server.workflows.runtime import build_initial_state

import fichero_server.workflows.tools  # noqa: F401  registers everything


def _run_transcribe(workflow, library_path: Path, doc_id: str, task_id: str) -> dict:
    state = build_initial_state(
        {"selected_doc_ids": [doc_id]},
        library_path=str(library_path),
    )
    state["workflow_id"] = workflow.id
    state["task_id"] = task_id
    return asyncio.run(build_graph(workflow).ainvoke(state))


def test_second_run_cache_hit_still_emits_text(tmp_path, monkeypatch):
    _install_deterministic_workflow_stubs(monkeypatch)
    library_path, selected_doc_id, source_doc_id, _ = _seed_fixture_library(
        tmp_path, selection_shape="file"
    )
    workflow = _load_workflow_by_name("Transcribe")

    first = _run_transcribe(workflow, library_path, selected_doc_id, "cache-run-1")
    first_out = (first.get("outputs") or {}).get("transcribe") or {}
    first_text = first_out.get("text") or ""
    assert FIXTURE_TEXT.split()[0] in first_text, (
        "first (uncached) run produced no usable transcribe text — "
        f"got: {first_text!r}"
    )

    second = _run_transcribe(workflow, library_path, selected_doc_id, "cache-run-2")
    second_out = (second.get("outputs") or {}).get("transcribe") or {}
    second_text = second_out.get("text") or ""
    # The cache HIT must hand downstream the RESULT dict, not the CacheEntry
    # wrapper: with the wrapper, aggregation emitted text="" while reporting
    # success, and every downstream text node failed with "No text provided".
    assert second_text == first_text, (
        "cache-hit run lost the transcribe text — the CacheEntry wrapper "
        f"leaked into parallel_results (got: {second_text!r})"
    )
