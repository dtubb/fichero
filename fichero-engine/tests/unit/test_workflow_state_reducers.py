"""Unit coverage for the pure LangGraph state reducers in
``fichero.workflows.types`` — the functions that merge outputs from parallel
workflow branches. These are exercised indirectly by executor/integration tests;
this file locks their merge semantics directly.
"""

from __future__ import annotations

import pytest

import fichero.workflows.types as wt
from fichero.workflows.types import (
    _last_value,
    _merge_completed_nodes,
    _merge_error,
    _merge_outputs,
    _merge_output_files,
    _merge_parallel_results,
    compact_output_for_state,
)


# ===========================================================================
# compact_output_for_state
# ===========================================================================


def test_compact_non_dict_passthrough():
    assert compact_output_for_state("scalar") == "scalar"
    assert compact_output_for_state([1, 2]) == [1, 2]


def test_compact_drops_bulky_lists_for_counts():
    out = compact_output_for_state({
        "text": "combined",
        "texts": ["a", "b", "c"],
        "results": [{"x": 1}],
        "values": [1, 2],
        "keep": "me",
    })
    assert out == {
        "text": "combined",
        "text_count": 3,
        "result_count": 1,
        "value_count": 2,
        "keep": "me",
    }
    assert "texts" not in out and "results" not in out and "values" not in out


def test_compact_leaves_non_list_fields_alone():
    out = compact_output_for_state({"texts": "not-a-list"})
    assert out == {"texts": "not-a-list"}  # only lists are compacted


def test_compact_raises_when_over_size_cap(monkeypatch):
    monkeypatch.setattr(wt, "_STATE_OUTPUT_MAX_BYTES", 10)
    with pytest.raises(ValueError, match="capped serialized size"):
        compact_output_for_state({"a": "x" * 100})


# ===========================================================================
# _merge_parallel_results
# ===========================================================================


def test_merge_parallel_results_none_cases():
    assert _merge_parallel_results(None, None) == {}
    assert _merge_parallel_results({"n": [1]}, None) == {"n": [1]}
    assert _merge_parallel_results(None, {"n": [1]}) == {"n": [1]}


def test_merge_parallel_results_extends_and_adds():
    merged = _merge_parallel_results({"a": [1]}, {"a": [2], "b": [3]})
    assert merged == {"a": [1, 2], "b": [3]}


# ===========================================================================
# _merge_outputs
# ===========================================================================


def test_merge_outputs_none_cases():
    assert _merge_outputs(None, None) == {}
    assert _merge_outputs({"n": {"x": 1}}, None) == {"n": {"x": 1}}


def test_merge_outputs_last_write_wins_and_compacts():
    merged = _merge_outputs(
        {"a": {"v": 1}},
        {"a": {"v": 2}, "b": {"texts": ["x", "y"]}},
    )
    assert merged["a"] == {"v": 2}                       # new overwrites existing key
    assert merged["b"] == {"text_count": 2}              # bulky list compacted on merge


# ===========================================================================
# _merge_completed_nodes / _merge_output_files (order-preserving union)
# ===========================================================================


@pytest.mark.parametrize("reducer", [_merge_completed_nodes, _merge_output_files])
def test_union_reducers(reducer):
    assert reducer(None, None) == []
    assert reducer(["a"], None) == ["a"]
    assert reducer(None, ["a"]) == ["a"]
    # Order preserved, duplicates dropped.
    assert reducer(["a", "b"], ["b", "c"]) == ["a", "b", "c"]


# ===========================================================================
# _last_value
# ===========================================================================


def test_last_value():
    assert _last_value("old", "new") == "new"   # new wins
    assert _last_value("old", None) == "old"     # None new keeps existing
    assert _last_value(None, None) == ""         # both None -> empty string


# ===========================================================================
# _merge_error
# ===========================================================================


def test_merge_error():
    assert _merge_error("old", "new") == "new"   # newest non-empty wins
    assert _merge_error("old", "") == "old"       # empty new preserves existing
    assert _merge_error("old", None) == "old"
    assert _merge_error(None, None) is None
    assert _merge_error(None, "boom") == "boom"
