"""Unit tests for the `aggregate` tool — the user-facing fan-in node
that combines parallel transcribe / extract results into a single text
payload for downstream nodes (catalogue, extract_all, etc.).

These tests pin every code path that's been involved in the multi-day
empty-text bug chase (#837): normal-input, resolver-before-parallel
race, cache-hit-fast-path race, multi-page ordering, error handling.

The aggregate tool is at fichero-server/src/fichero_server/workflows/tools/aggregate.py.
"""

from __future__ import annotations

import pytest

from fichero_server.workflows.tools.aggregate import (
    aggregate,
    _records_from_state_outputs,
    _wait_for_parallel_completion,
)
from fichero_server.llm import LLMConfig


@pytest.fixture
def llm_config():
    return LLMConfig(provider="apple", model="apple-intelligence")


# ---------------------------------------------------------------------------
# Normal path — resolver-supplied inputs.text is present and good
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_aggregate_concatenates_string_input(llm_config):
    """The simplest case: text input is a single string, no parallel
    sources at all. Returns the text directly with count=1."""
    inputs = {"text": "hello world", "documents": []}
    state = {}
    result = await aggregate(inputs, state, llm_config)
    assert result["text"] == "hello world"
    assert result["count"] == 1


@pytest.mark.asyncio
async def test_aggregate_concatenates_list_input(llm_config):
    """Multiple texts via list, default concat mode joins with the
    standard separator. Order preserved."""
    inputs = {
        "text": ["page 1", "page 2", "page 3"],
        "documents": [],
    }
    state = {}
    result = await aggregate(inputs, state, llm_config)
    assert "page 1" in result["text"]
    assert "page 2" in result["text"]
    assert "page 3" in result["text"]
    assert result["count"] == 3
    assert result["text"].index("page 1") < result["text"].index("page 2")


# ---------------------------------------------------------------------------
# Stale-resolver path: inputs.text empty but state.outputs has data
# (auto-aggregator fired AFTER the resolver but BEFORE this tool ran)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_aggregate_recovers_from_stale_resolver(llm_config):
    """The resolver ran before parallel completion, so inputs.text is
    empty/missing. But state.outputs[transcribe] now has real text.
    The tool should re-derive records from state.outputs and produce a
    real payload — not return empty silently."""
    inputs = {"text": None, "documents": []}
    state = {
        "outputs": {
            "transcribe": {"text": "real transcribed page text"},
        },
    }
    result = await aggregate(inputs, state, llm_config)
    assert "real transcribed page text" in result["text"], (
        f"expected stale-resolver fallback to recover real text, got: {result!r}"
    )


# ---------------------------------------------------------------------------
# Cache-hit-fast-path: inputs.text empty, state.outputs missing,
# state.parallel_results has the cached result
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_aggregate_recovers_from_cache_hit_parallel_results(llm_config):
    """Cache hit returned instantly — state.parallel_results[transcribe]
    has the cached result, but the auto-aggregator hasn't run yet so
    state.outputs is empty. inputs.text is also empty (resolver saw
    nothing). The tool must walk parallel_results to find the cached
    text. This is the actual #837 case."""
    inputs = {"text": None, "documents": []}
    state = {
        "outputs": {},
        "parallel_results": {
            "transcribe": [
                {
                    "file": "page1.jpeg",
                    "index": 0,
                    "total": 1,
                    "result": {"text": "cached page text"},
                    "success": True,
                    "cached": True,
                },
            ],
        },
    }
    result = await aggregate(inputs, state, llm_config)
    assert "cached page text" in result["text"], (
        f"expected cache-hit fast-path to surface cached text, got: {result!r}"
    )
    assert result["count"] >= 1


@pytest.mark.asyncio
async def test_aggregate_orders_parallel_results_by_index(llm_config):
    """When parallel_results arrive out-of-order (LangGraph Send fan-out
    doesn't guarantee order), aggregate sorts by `index` so multi-page
    folders come back in page order — important for catalogue narrative
    coherence."""
    inputs = {"text": None, "documents": []}
    state = {
        "outputs": {},
        "parallel_results": {
            "transcribe": [
                # Intentionally out of index order:
                {"file": "p3.jpeg", "index": 2, "total": 3,
                 "result": {"text": "third page"}, "success": True},
                {"file": "p1.jpeg", "index": 0, "total": 3,
                 "result": {"text": "first page"}, "success": True},
                {"file": "p2.jpeg", "index": 1, "total": 3,
                 "result": {"text": "second page"}, "success": True},
            ],
        },
    }
    result = await aggregate(inputs, state, llm_config)
    text = result["text"]
    assert text.index("first page") < text.index("second page"), (
        f"first page should precede second page in: {text!r}"
    )
    assert text.index("second page") < text.index("third page"), (
        f"second page should precede third page in: {text!r}"
    )


@pytest.mark.asyncio
async def test_aggregate_skips_failed_parallel_results(llm_config):
    """Per-file failures (success=False) shouldn't contribute their
    placeholder text to the aggregate. Only successful results land."""
    inputs = {"text": None, "documents": []}
    state = {
        "outputs": {},
        "parallel_results": {
            "transcribe": [
                {"file": "p1.jpeg", "index": 0, "total": 2,
                 "result": {"text": "good page"}, "success": True},
                {"file": "p2.jpeg", "index": 1, "total": 2,
                 "error": "Vision OCR failed", "success": False},
            ],
        },
    }
    result = await aggregate(inputs, state, llm_config)
    assert "good page" in result["text"]
    assert "Vision OCR failed" not in result["text"]


# ---------------------------------------------------------------------------
# True empty path: nothing in inputs, outputs, or parallel_results
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_aggregate_returns_empty_when_no_data_anywhere(llm_config):
    """When inputs, state.outputs, AND state.parallel_results are all
    empty/missing, the tool returns an empty payload cleanly — does
    NOT raise. Downstream nodes will see an empty text and may abort
    via the systemic-error path (#839), but that's the correct chain.
    This is the path that fires on truly-broken upstream."""
    inputs = {"text": None, "documents": []}
    state = {"outputs": {}, "parallel_results": {}}
    result = await aggregate(inputs, state, llm_config)
    assert result["text"] == ""
    assert result["count"] == 0


# ---------------------------------------------------------------------------
# Direct exercise of the helpers
# ---------------------------------------------------------------------------


def test_records_from_state_outputs_prefers_outputs_over_parallel():
    """When BOTH state.outputs AND state.parallel_results have data,
    state.outputs wins (it's the canonical post-aggregation form). This
    avoids double-counting if a partially-fired auto-aggregator wrote
    state.outputs while parallel_results still has the per-Send entries."""
    state = {
        "outputs": {"transcribe": {"text": "from outputs"}},
        "parallel_results": {
            "transcribe": [
                {"index": 0, "total": 1,
                 "result": {"text": "from parallel"}, "success": True},
            ],
        },
    }
    records = _records_from_state_outputs({}, state)
    assert any("from outputs" in r["text"] for r in records)
    assert not any("from parallel" in r["text"] for r in records)


def test_records_from_state_outputs_returns_empty_when_truly_empty():
    """No outputs, no parallel_results → empty list (caller handles)."""
    records = _records_from_state_outputs({}, {})
    assert records == []


def test_records_from_state_outputs_skips_blank_text_strings():
    """state.outputs containing only empty/whitespace text shouldn't
    produce records. Otherwise we'd count blank pages as content."""
    state = {
        "outputs": {
            "transcribe": {"text": "   \n   "},
            "extract": {"text": ""},
        },
    }
    records = _records_from_state_outputs({}, state)
    assert records == []


@pytest.mark.asyncio
async def test_wait_for_parallel_completion_returns_immediately_when_complete():
    """When all parallel sources already have len >= total, the wait
    helper returns immediately without sleeping. Avoids the 250ms poll
    delay on cache-hit / single-file fast paths."""
    import time
    state = {
        "parallel_results": {
            "transcribe": [
                {"index": 0, "total": 1, "result": {"text": "done"},
                 "success": True},
            ],
        },
    }
    t0 = time.monotonic()
    await _wait_for_parallel_completion(state)
    elapsed = time.monotonic() - t0
    assert elapsed < 0.1, f"expected immediate return; took {elapsed:.3f}s"


@pytest.mark.asyncio
async def test_wait_for_parallel_completion_skipped_when_no_parallel():
    """No parallel_results in state means there are no parallel sources;
    the wait helper returns immediately without polling. Lets non-
    parallel workflows skip the barrier entirely with no overhead."""
    import time
    state = {}
    t0 = time.monotonic()
    await _wait_for_parallel_completion(state)
    assert (time.monotonic() - t0) < 0.05
