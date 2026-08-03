"""Preflight and `requires_vision` must see the CHILDREN too (#3804).

The engine's model preflight stopped at the parent's own nodes. A workflow
that delegates everything to a ``sub_workflow`` child therefore passed every
check unconditionally — including the checks that exist to catch a model pick
the run cannot honour — and then failed mid-run, which is the failure mode
preflight was built to remove.

The same blindness produced the second defect: the app derived "does this need
a vision model?" from the parent's node list, so a delegating parent reported
"needs nothing" while the run it starts cannot start without vision. That
answer is now computed by the engine and served, so surfaces read it.

Population assertions below (#4487): a shipped-preset sweep that passes
because it examined zero presets is worse than no sweep.
"""

from __future__ import annotations

import json

import pytest

from fichero_server.llm import LLMConfig
from fichero_server.workflows.preset_manifest import PRESET_DIR
from fichero_server.workflows.types import NodeDef, WorkflowDef
from fichero_server.workflows.validation import (
    validate_workflow_llm_preflight,
    workflow_requires_vision,
)


def _sub_node(node_id: str, ref: str, label: str = "") -> NodeDef:
    return NodeDef(
        id=node_id,
        tool="sub_workflow",
        label=label,
        config={
            "workflow_ref": ref,
            "input_contract": [{"id": "files", "data_type": "files"}],
            "output_contract": [],
        },
    )


def _resolver(children: dict[str, WorkflowDef]):
    return lambda ref: children.get(ref)


# =============================================================================
# 1. The descent catches a bad model pick that lives only in a child
# =============================================================================


def test_bad_model_pick_in_child_is_caught_for_delegating_parent(monkeypatch):
    """The whole point: the parent has no LLM nodes of its own, so the ONLY
    place a wrong model can be named is the child. Before the descent this
    returned [] — a clean bill of health for a run that cannot work."""
    monkeypatch.setenv("FICHERO_LOCAL_ONLY", "1")

    child = WorkflowDef(
        id="child",
        name="Child",
        nodes=[
            NodeDef(
                id="vision",
                tool="transcribe",
                label="Transcribe Page",
                provider_name="openai",
                model_name="gpt-4o",
            )
        ],
    )
    parent = WorkflowDef(
        id="parent",
        name="Parent",
        nodes=[_sub_node("delegate", "child", label="Pages")],
    )

    errors = validate_workflow_llm_preflight(
        parent,
        LLMConfig(provider="", model=""),
        workflow_resolver=_resolver({"child": child}),
    )

    assert len(errors) == 1, errors
    # The message names the path, not just the leaf: "which node" is useless
    # when the node lives in a workflow the user did not open.
    assert errors[0].startswith("Node 'Pages' (sub_workflow) -> Node 'Transcribe Page'")
    assert "Local-only AI mode is enabled" in errors[0]


def test_delegating_parent_with_a_good_child_still_passes(monkeypatch):
    """The descent must not turn every delegating workflow into an error."""
    monkeypatch.delenv("FICHERO_LOCAL_ONLY", raising=False)

    child = WorkflowDef(
        id="child",
        name="Child",
        nodes=[
            NodeDef(
                id="vision",
                tool="transcribe",
                provider_name="ollama",
                model_name="llava",
            )
        ],
    )
    parent = WorkflowDef(
        id="parent", name="Parent", nodes=[_sub_node("delegate", "child")]
    )

    assert (
        validate_workflow_llm_preflight(
            parent,
            LLMConfig(provider="", model=""),
            workflow_resolver=_resolver({"child": child}),
        )
        == []
    )


def test_child_is_checked_against_its_own_workflow_model_not_the_parents(monkeypatch):
    """``sub_workflow`` builds the child graph from the CHILD's provider/model.
    Checking it against the parent's would report refusals for a resolution the
    run never performs — and miss the one it does."""
    monkeypatch.setenv("FICHERO_LOCAL_ONLY", "1")

    child = WorkflowDef(
        id="child",
        name="Child",
        provider="openai",
        model="gpt-4o",
        nodes=[NodeDef(id="text", tool="summarize_file", label="Summarize")],
    )
    parent = WorkflowDef(
        id="parent",
        name="Parent",
        provider="ollama",
        model="llama3",
        nodes=[_sub_node("delegate", "child", label="Summaries")],
    )

    errors = validate_workflow_llm_preflight(
        parent,
        workflow_resolver=_resolver({"child": child}),
    )

    assert len(errors) == 1, errors
    assert "openai/gpt-4o" in errors[0]


def test_unresolvable_child_is_not_an_llm_error():
    """A missing child is a REFERENCE problem, reported by
    ``validate_sub_workflow_references``. Reporting it twice, once as a bogus
    model error, is the duplicate-mechanism defect this work exists to avoid."""
    parent = WorkflowDef(
        id="parent", name="Parent", nodes=[_sub_node("delegate", "nope")]
    )

    assert (
        validate_workflow_llm_preflight(parent, workflow_resolver=lambda _ref: None)
        == []
    )


# =============================================================================
# 2. A cycle must not hang
# =============================================================================


def test_mutually_referencing_workflows_do_not_hang(monkeypatch):
    """A -> B -> A. The reference validator is what REPORTS the cycle; this
    function only has to terminate — and still check both workflows' nodes on
    the way round."""
    monkeypatch.setenv("FICHERO_LOCAL_ONLY", "1")

    a = WorkflowDef(
        id="a",
        name="A",
        nodes=[
            _sub_node("to_b", "b", label="To B"),
            NodeDef(
                id="a_llm",
                tool="summarize_file",
                label="A Text",
                provider_name="openai",
                model_name="gpt-4o",
            ),
        ],
    )
    b = WorkflowDef(
        id="b",
        name="B",
        nodes=[
            _sub_node("to_a", "a", label="To A"),
            NodeDef(
                id="b_llm",
                tool="summarize_file",
                label="B Text",
                provider_name="openai",
                model_name="gpt-4o",
            ),
        ],
    )

    errors = validate_workflow_llm_preflight(
        a,
        LLMConfig(provider="", model=""),
        workflow_resolver=_resolver({"a": a, "b": b}),
    )

    # Both nodes reported exactly once — the guard bounds the walk, it does not
    # abandon the branch it was already on.
    assert len(errors) == 2, errors
    assert any("A Text" in e for e in errors)
    assert any("B Text" in e for e in errors)


def test_self_referencing_workflow_does_not_hang(monkeypatch):
    monkeypatch.setenv("FICHERO_LOCAL_ONLY", "1")

    workflow = WorkflowDef(
        id="loop",
        name="Loop",
        nodes=[
            _sub_node("me", "loop", label="Itself"),
            NodeDef(
                id="llm",
                tool="summarize_file",
                label="Text",
                provider_name="openai",
                model_name="gpt-4o",
            ),
        ],
    )

    errors = validate_workflow_llm_preflight(
        workflow,
        LLMConfig(provider="", model=""),
        workflow_resolver=lambda ref: workflow if ref == "loop" else None,
    )

    assert len(errors) == 1, errors


def test_a_child_shared_by_two_parents_is_checked_once(monkeypatch):
    """Shared components are the normal case, not a cycle. One error, not two."""
    monkeypatch.setenv("FICHERO_LOCAL_ONLY", "1")

    child = WorkflowDef(
        id="shared",
        name="Shared",
        nodes=[
            NodeDef(
                id="llm",
                tool="summarize_file",
                label="Shared Text",
                provider_name="openai",
                model_name="gpt-4o",
            )
        ],
    )
    parent = WorkflowDef(
        id="parent",
        name="Parent",
        nodes=[
            _sub_node("first", "shared", label="First"),
            _sub_node("second", "shared", label="Second"),
        ],
    )

    errors = validate_workflow_llm_preflight(
        parent,
        LLMConfig(provider="", model=""),
        workflow_resolver=_resolver({"shared": child}),
    )

    assert len(errors) == 1, errors


# =============================================================================
# 3. requires_vision, computed where the rule lives
# =============================================================================


def test_requires_vision_true_when_the_requirement_lives_only_in_a_child():
    """The case the client-side copy got wrong: the parent's own nodes contain
    no vision tool at all."""
    child = WorkflowDef(
        id="child",
        name="Child",
        nodes=[NodeDef(id="vision", tool="transcribe")],
    )
    parent_nodes = [_sub_node("delegate", "child")]

    assert workflow_requires_vision(
        parent_nodes, workflow_resolver=_resolver({"child": child})
    ) is True
    # Without the descent the same nodes answer "no" — which is exactly what
    # the app was showing.
    assert workflow_requires_vision(parent_nodes, workflow_resolver=lambda _r: None) is False


def test_requires_vision_false_for_a_text_only_chain():
    child = WorkflowDef(
        id="child",
        name="Child",
        nodes=[NodeDef(id="text", tool="summarize_file")],
    )

    assert (
        workflow_requires_vision(
            [_sub_node("delegate", "child")],
            workflow_resolver=_resolver({"child": child}),
        )
        is False
    )


def test_requires_vision_reads_stored_node_dicts_as_well_as_nodedefs():
    """The API serves stored rows, whose nodes are dicts — the same answer must
    come out of both shapes or the served field depends on the caller."""
    assert workflow_requires_vision([{"tool": "transcribe"}]) is True
    assert workflow_requires_vision([NodeDef(id="v", tool="transcribe")]) is True
    assert workflow_requires_vision([{"tool": "summarize_file"}]) is False


def test_requires_vision_terminates_on_a_cycle():
    a_nodes = [_sub_node("to_b", "b")]
    b = WorkflowDef(id="b", name="B", nodes=[_sub_node("to_a", "a")])
    a = WorkflowDef(id="a", name="A", nodes=a_nodes)

    assert (
        workflow_requires_vision(a_nodes, workflow_resolver=_resolver({"a": a, "b": b}))
        is False
    )


# =============================================================================
# 4. The shipped presets, swept
# =============================================================================


def _shipped_presets() -> list[dict]:
    presets = []
    for path in sorted(PRESET_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("name"):
            presets.append(data)
    return presets


PRESETS = _shipped_presets()


def test_delegating_presets_exist_and_report_their_real_vision_requirement():
    """The Spanish Script parent is the concrete instance of the bug: it
    delegates transcription to a child and the app called it text-only."""
    delegating = [
        preset
        for preset in PRESETS
        if any(
            (node or {}).get("tool") == "sub_workflow"
            for node in preset.get("nodes") or []
        )
    ]
    assert delegating, "no delegating preset shipped — this sweep examined nothing"

    resolved = {
        preset["name"]: workflow_requires_vision(preset.get("nodes"))
        for preset in delegating
    }
    # Non-vacuous in the direction that matters: at least one shipped
    # delegating preset genuinely needs vision, and says so.
    assert any(resolved.values()), resolved


@pytest.mark.parametrize("preset", PRESETS, ids=lambda p: p["name"])
def test_requires_vision_is_answerable_for_every_shipped_preset(preset):
    """No preset makes the computation throw or hang — including the ones whose
    children resolve through the shipped-JSON fallback."""
    assert isinstance(workflow_requires_vision(preset.get("nodes")), bool)
