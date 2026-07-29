"""Direct tests for workflows/builder.py pure helpers (#1987 Test Coverage).

These helpers shape real execution behaviour — LLM capability routing, the
cache-poisoning guard that refuses to persist empty node results, and unique
human-readable node naming — but had no direct test. Focus on the edges.
"""

from __future__ import annotations

import pytest

from fichero_server.workflows.builder import (
    _generate_node_names,
    _required_llm_capability_for_category,
    _result_worth_caching,
)
from fichero_server.workflows.types import NodeDef, WorkflowDef


# ---------------------------------------------------------------------------
# _required_llm_capability_for_category
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("category", ["vision", "audio", "video"])
def test_capability_passes_through_media_categories(category: str) -> None:
    assert _required_llm_capability_for_category(category) == category


@pytest.mark.parametrize("category", ["VISION", " Audio ", "Video"])
def test_capability_is_case_and_whitespace_insensitive(category: str) -> None:
    assert _required_llm_capability_for_category(category) == category.strip().lower()


@pytest.mark.parametrize("category", [None, "", "   ", "text", "summarize", "unknown"])
def test_capability_defaults_to_text(category) -> None:
    assert _required_llm_capability_for_category(category) == "text"


# ---------------------------------------------------------------------------
# _result_worth_caching — the empty-result cache-poisoning guard
# ---------------------------------------------------------------------------


def test_cache_keeps_non_empty_text() -> None:
    assert _result_worth_caching({"text": "real output"}) is True


def test_cache_skips_empty_or_whitespace_text() -> None:
    assert _result_worth_caching({"text": ""}) is False
    assert _result_worth_caching({"text": "   \n"}) is False
    assert _result_worth_caching({}) is False


def test_cache_value_dict_only_when_a_field_is_truthy() -> None:
    assert _result_worth_caching({"value": {"a": 1}}) is True
    assert _result_worth_caching({"value": {"a": None, "b": ""}}) is False
    assert _result_worth_caching({"value": {}}) is False


def test_cache_value_list_only_when_non_empty() -> None:
    assert _result_worth_caching({"value": [1]}) is True
    assert _result_worth_caching({"value": []}) is False


def test_cache_keeps_when_results_or_artifacts_present() -> None:
    assert _result_worth_caching({"results": [{"x": 1}]}) is True
    assert _result_worth_caching({"artifacts": ["a.png"]}) is True
    assert _result_worth_caching({"results": [], "artifacts": []}) is False


def test_cache_non_dict_uses_truthiness() -> None:
    assert _result_worth_caching("done") is True
    assert _result_worth_caching(0) is False
    assert _result_worth_caching(None) is False
    assert _result_worth_caching([]) is False


# ---------------------------------------------------------------------------
# _generate_node_names — label/tool fallback + uniqueness
# ---------------------------------------------------------------------------


def _wf(nodes: list[NodeDef]) -> WorkflowDef:
    return WorkflowDef(name="wf", nodes=nodes)


def test_node_name_uses_label_then_titlecased_tool() -> None:
    wf = _wf(
        [
            NodeDef(id="n1", tool="extract_text", label="Transcribe"),
            NodeDef(id="n2", tool="extract_text", label=""),  # empty -> tool name
        ]
    )
    names = _generate_node_names(wf)
    assert names["n1"] == "Transcribe"
    assert names["n2"] == "Extract Text"


def test_node_names_are_made_unique_with_suffixes() -> None:
    wf = _wf(
        [
            NodeDef(id="a", tool="x", label="Step"),
            NodeDef(id="b", tool="x", label="Step"),
            NodeDef(id="c", tool="x", label="Step"),
        ]
    )
    names = _generate_node_names(wf)
    assert [names["a"], names["b"], names["c"]] == ["Step", "Step 2", "Step 3"]


def test_node_names_empty_workflow() -> None:
    assert _generate_node_names(_wf([])) == {}
