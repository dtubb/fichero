"""#2529: typed human-in-the-loop contract.

The payload a paused workflow surfaces must be one stable JSON-safe Pydantic
shape (the SSE/Activity surface and the resume endpoint both depend on it),
and ask_human() must round-trip whatever the resume call feeds back.
"""

from __future__ import annotations

import sys
import types

import pytest

from fichero_server.workflows.human_review import HumanReviewRequest, ask_human


def test_request_is_json_safe_and_has_defaults():
    req = HumanReviewRequest(question="Which reading is correct?")
    dumped = req.model_dump()
    # JSON-safe primitives only — survives the interrupt boundary + SSE.
    assert dumped["kind"] == "human_review"
    assert dumped["question"] == "Which reading is correct?"
    assert dumped["context"] == {}
    assert dumped["options"] is None
    assert dumped["node_id"] is None


def test_request_carries_context_and_options():
    req = HumanReviewRequest(
        kind="bbox_htr",
        question="What does this region say?",
        context={"bbox": [1, 2, 3, 4], "draft": "ilegible"},
        options=["accept", "edit"],
        node_id="n-7",
    )
    d = req.model_dump()
    assert d["kind"] == "bbox_htr"
    assert d["context"]["bbox"] == [1, 2, 3, 4]
    assert d["options"] == ["accept", "edit"]
    assert d["node_id"] == "n-7"


def test_ask_human_passes_typed_payload_and_returns_answer(monkeypatch):
    """ask_human wraps interrupt() with the typed payload and returns its value."""
    captured = {}

    def _fake_interrupt(value):
        captured["value"] = value
        return "user typed answer"  # what Command(resume=...) would feed back

    # langgraph.types.interrupt is imported lazily inside ask_human.
    fake_mod = types.ModuleType("langgraph.types")
    fake_mod.interrupt = _fake_interrupt
    monkeypatch.setitem(sys.modules, "langgraph.types", fake_mod)

    answer = ask_human(
        "Confirm this entity?",
        kind="entity_confirm",
        context={"entity": "Bogotá"},
        options=["yes", "no"],
        node_id="n1",
    )

    assert answer == "user typed answer"
    # The payload that crossed the boundary is the typed contract, as a dict.
    assert captured["value"] == {
        "kind": "entity_confirm",
        "question": "Confirm this entity?",
        "context": {"entity": "Bogotá"},
        "options": ["yes", "no"],
        "node_id": "n1",
    }


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
