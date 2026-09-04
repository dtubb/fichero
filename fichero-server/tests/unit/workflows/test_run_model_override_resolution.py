"""The model CHOSEN must be the model USED (R-11, Daniel 2026-09-04).

Two screenshots started this: the chip read `claude-opus-5` while a
Paleographer Review ran on `gemini-flash-lite`, and a Catalogue folder run
under the same chip produced artifacts stamped `apple · apple-intelligence`.
The run-level choice reached neither an ordinary step's neighbours nor a
`sub_workflow` child.

One precedence, asserted here: **step pin > run-level explicit choice > tier
default**, with capability-compatibility as the qualifier. A choice that
cannot serve a node is not stamped onto it — the node falls back to its tier
default — which is what keeps the 2026-09-01 rule ("never claim apple-vision
will Translate") true while a deliberate choice still spreads across the steps
it fits.
"""

from __future__ import annotations

import pytest

from fichero_server.workflows.types import NodeDef, WorkflowDef
from fichero_server.workflows.validation import (
    apply_run_model_override,
    apply_run_model_override_to_def,
    model_can_serve_capability,
    node_required_capability,
    run_override_reaches_node,
)


# =============================================================================
# What a node needs of a model
# =============================================================================


def test_vision_tool_requires_vision():
    assert node_required_capability({"tool": "transcribe"}) == "vision"


def test_text_tool_requires_text():
    assert node_required_capability({"tool": "translate"}) == "text"


def test_detect_regions_is_vision_only_in_vlm_mode():
    """The config-aware answer `node_uses_llm` already gives (2026-08-27)."""
    apple = {"tool": "detect_regions", "config": {"provider": "apple"}}
    vlm = {"tool": "detect_regions", "config": {"provider": "vlm"}}
    assert node_required_capability(vlm) == "vision"
    # The Apple route calls no model at all, so no override reaches it.
    assert run_override_reaches_node(apple, "anthropic", "claude-opus-5") is False
    assert run_override_reaches_node(vlm, "anthropic", "claude-opus-5") is True


def test_unknown_tool_is_never_an_override_target():
    assert run_override_reaches_node({"tool": "no_such_tool"}, "anthropic", "x") is False


# =============================================================================
# Capability compatibility — an unknown flag is not a "no"
# =============================================================================


def test_absent_capability_metadata_counts_as_compatible():
    """A model newer than the catalog must not be silently disqualified.

    The same rule the picker follows when it greys a row rather than hiding
    it: only a positive "no" disqualifies a choice.
    """
    assert model_can_serve_capability("anthropic", "claude-opus-5", "vision") is True
    assert model_can_serve_capability("anthropic", "claude-opus-5", "text") is True


def test_recognition_only_vision_model_cannot_serve_a_text_step():
    """Apple Vision returns the page's own text and ignores the prompt."""
    assert model_can_serve_capability("apple", "apple-vision", "text") is False


def test_an_empty_choice_serves_nothing():
    assert model_can_serve_capability("", "", "text") is False


# =============================================================================
# Ordinary steps: the choice spreads within its capability class
# =============================================================================


def test_choice_reaches_every_compatible_node():
    nodes = [
        {"id": "src", "tool": "files"},
        {"id": "regions", "tool": "detect_regions", "config": {"provider": "vlm"}},
        {"id": "read", "tool": "transcribe"},
    ]
    reached = apply_run_model_override(nodes, "anthropic", "claude-opus-5")

    assert reached == ["regions", "read"], (
        "an explicit choice must reach every capability-compatible step — "
        "pinning Transcribe used to leave Detect Regions on the Settings tier"
    )
    assert nodes[1]["model_name"] == "claude-opus-5"
    assert nodes[2]["provider_name"] == "anthropic"
    assert "model_name" not in nodes[0], "a source node takes no model"


def test_an_incompatible_choice_leaves_the_node_on_its_tier_default():
    """The 2026-09-01 fix, preserved: the OCR route never lands on Translate."""
    nodes = [{"id": "translate", "tool": "translate"}]
    assert apply_run_model_override(nodes, "apple", "apple-vision") == []
    assert "model_name" not in nodes[0], (
        "an incompatible choice was stamped on — the run would promise a "
        "model the engine is about to refuse"
    )


def test_no_choice_changes_nothing():
    nodes = [{"id": "read", "tool": "transcribe", "model_name": "preset-model"}]
    assert apply_run_model_override(nodes, "", "  ") == []
    assert nodes[0]["model_name"] == "preset-model"


@pytest.mark.parametrize("shape", ["dict", "nodedef"], ids=["stored", "runtime"])
def test_both_node_shapes_answer_alike(shape):
    """The route sees stored dicts; the runtime sees NodeDefs."""
    node = (
        {"id": "read", "tool": "transcribe"}
        if shape == "dict"
        else NodeDef(id="read", tool="transcribe")
    )
    assert apply_run_model_override([node], "anthropic", "claude-opus-5") == ["read"]
    model = node["model_name"] if shape == "dict" else node.model_name
    assert model == "claude-opus-5"


# =============================================================================
# sub_workflow children: the Catalogue case
# =============================================================================


def _child() -> WorkflowDef:
    return WorkflowDef(
        id="child",
        name="2 · Extract Entities",
        nodes=[
            NodeDef(id="src", tool="files"),
            NodeDef(id="entities", tool="extract_entities", model_name="apple-intelligence"),
        ],
        edges=[],
    )


def test_the_choice_reaches_a_child_workflows_nodes():
    """A Catalogue run under a claude-opus-5 chip stamped apple-intelligence."""
    updated = apply_run_model_override_to_def(_child(), "anthropic", "claude-opus-5")

    assert updated is not None
    assert updated.nodes[1].model_name == "claude-opus-5"
    assert updated.nodes[1].provider_name == "anthropic"


def test_the_child_is_copied_not_mutated():
    """A resolved child is cached and shared — one run must not leak into the next."""
    original = _child()
    updated = apply_run_model_override_to_def(original, "anthropic", "claude-opus-5")

    assert original.nodes[1].model_name == "apple-intelligence"
    assert updated is not original


def test_a_child_with_nothing_to_override_is_returned_unchanged():
    child = WorkflowDef(id="c", name="c", nodes=[NodeDef(id="s", tool="files")], edges=[])
    assert apply_run_model_override_to_def(child, "anthropic", "claude-opus-5") is child
