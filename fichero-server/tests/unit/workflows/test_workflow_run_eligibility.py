"""The Run menu and the engine must agree about what can be run (#3804).

Two divergences, both found by auditing the menu against the engine:

1. ``config.internal`` had exactly ONE reader in the whole server — the list
   response formatter. So the SwiftUI Run menu was the only thing stopping an
   internal sub-workflow component from being executed on its own, and the
   CLI, MCP, Shortcuts and a bare POST all walked past it.

2. The menu offers a provider/model override for EVERY workflow, but the
   runner applies one only to top-level ``uses_llm`` nodes. For a workflow
   with none, the pick was discarded in silence and the run reported success
   — the #4467 shape.

Both are now decided by ``validate_run_eligibility``, which the execute path
calls and whose answers the list response publishes, so the two cannot drift.

The population tests below enumerate every shipped preset and assert the
population is non-empty first: a consistency check that passes because it
examined nothing is worse than no check (#4487).
"""

from __future__ import annotations

import json

import pytest

from fichero_server.workflows.preset_manifest import PRESET_DIR
from fichero_server.workflows.validation import (
    validate_run_eligibility,
    workflow_accepts_model_override,
    workflow_is_direct_runnable,
    workflow_override_target_tools,
    workflow_sub_workflow_refs,
)


def _shipped_presets() -> list[dict]:
    presets = []
    for path in sorted(PRESET_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("name"):
            presets.append(data)
    return presets


PRESETS = _shipped_presets()


def _eligibility(preset: dict, **overrides) -> list[str]:
    return validate_run_eligibility(
        name=preset["name"],
        config=preset.get("config"),
        nodes=preset.get("nodes"),
        **overrides,
    )


# =============================================================================
# The population is real
# =============================================================================


def test_shipped_preset_population_is_not_empty():
    """Guard the guard: every test below iterates PRESETS."""
    assert len(PRESETS) >= 30, f"only {len(PRESETS)} presets loaded from {PRESET_DIR}"


# =============================================================================
# 1. Internal components cannot be run on their own
# =============================================================================


def test_internal_components_exist_and_are_refused():
    """At least one shipped component is internal, and it is refused."""
    internal = [p for p in PRESETS if not workflow_is_direct_runnable(p.get("config"))]
    assert internal, "no internal preset in the shipped set — this test proves nothing"

    for preset in internal:
        errors = _eligibility(preset)
        assert errors, f"{preset['name']} is internal but was accepted for a top-level run"
        assert "internal component" in errors[0]
        assert "sub_workflow" in errors[0]


def test_direct_runnable_presets_are_not_refused():
    """The other side of the same rule — no preset is wrongly blocked."""
    runnable = [p for p in PRESETS if workflow_is_direct_runnable(p.get("config"))]
    assert len(runnable) >= 30

    for preset in runnable:
        assert _eligibility(preset) == [], f"{preset['name']} was wrongly refused"


@pytest.mark.parametrize(
    "config",
    [
        {"internal": True},
        {"input_contract": [{"id": "files", "data_type": "files"}]},
    ],
    ids=["internal-flag", "input-contract"],
)
def test_either_marker_blocks_a_top_level_run(config):
    """#4324's flag and the contract marker each exclude on their own."""
    assert workflow_is_direct_runnable(config) is False
    assert _eligibility({"name": "Component", "config": config, "nodes": []})


def test_absent_config_is_runnable():
    """A user workflow carries no config at all and must stay runnable."""
    assert workflow_is_direct_runnable(None) is True
    assert workflow_is_direct_runnable({}) is True


# =============================================================================
# 2. A provider/model override that changes nothing is refused, not dropped
# =============================================================================


def test_presets_without_llm_nodes_refuse_an_override():
    """The 'Default and OpenRouter do the same thing' class of dead control."""
    no_llm = [
        p
        for p in PRESETS
        if workflow_is_direct_runnable(p.get("config"))
        and not workflow_override_target_tools(p.get("nodes"))
    ]
    assert no_llm, "no override-less preset found — this test proves nothing"

    for preset in no_llm:
        assert workflow_accepts_model_override(preset.get("nodes")) is False
        errors = _eligibility(preset, provider_override="openrouter")
        assert errors, f"{preset['name']} silently accepted a no-op override"
        assert "cannot apply the requested provider/model override" in errors[0]


def test_presets_with_llm_nodes_accept_an_override():
    with_llm = [
        p
        for p in PRESETS
        if workflow_is_direct_runnable(p.get("config"))
        and workflow_override_target_tools(p.get("nodes"))
    ]
    assert len(with_llm) >= 20

    for preset in with_llm:
        assert workflow_accepts_model_override(preset.get("nodes")) is True
        assert _eligibility(preset, provider_override="openrouter", model_override="x") == []


def test_no_override_requested_is_never_refused():
    """Running 'Default' on an image workflow must keep working."""
    for preset in PRESETS:
        if not workflow_is_direct_runnable(preset.get("config")):
            continue
        assert _eligibility(preset) == []
        assert _eligibility(preset, provider_override="", model_override="  ") == []


# =============================================================================
# 3. The sub_workflow blind spot is named, not glossed
# =============================================================================


def test_delegating_parent_names_the_child_it_delegates_to():
    """Transcribe Spanish Script is vision work the parent cannot override.

    Its two nodes are `files` and `sub_workflow`; all three vision nodes live
    in the child. The runner's override loop and the LLM preflight both stop
    at the parent, so the menu offered text-only models for vision-only work
    and the engine validated none of it. The refusal has to say WHY, or the
    user just sees a workflow that refuses everything.
    """
    parents = [p for p in PRESETS if workflow_sub_workflow_refs(p.get("nodes"))]
    assert parents, "no delegating preset found — this test proves nothing"

    for preset in parents:
        if workflow_override_target_tools(preset.get("nodes")):
            continue  # a parent that also does its own model work is fine
        errors = _eligibility(preset, model_override="gpt-4o-mini")
        assert errors
        assert "sub-workflow" in errors[0]
        for ref in workflow_sub_workflow_refs(preset.get("nodes")):
            assert ref in errors[0], "the refusal must name the child"


def test_no_llm_refusal_says_no_model_is_used():
    """The two reasons are distinguishable — a user can act on each."""
    errors = validate_run_eligibility(
        name="Rotate / Auto-Orient Images",
        config={},
        nodes=[{"tool": "files"}, {"tool": "rotate_images"}],
        provider_override="apple",
    )
    assert errors
    assert "none of its nodes use a language or vision model" in errors[0]
    assert "sub-workflow" not in errors[0]


# =============================================================================
# Shape-agnostic helpers: stored dicts and NodeDefs must answer alike
# =============================================================================


def test_override_targets_read_both_node_shapes():
    """The route sees stored dicts; the runtime sees NodeDefs."""
    from fichero_server.workflows.types import NodeDef

    dicts = [{"tool": "files"}, {"tool": "transcribe"}]
    defs = [NodeDef(id="a", tool="files"), NodeDef(id="b", tool="transcribe")]

    assert workflow_override_target_tools(dicts) == ["transcribe"]
    assert workflow_override_target_tools(defs) == ["transcribe"]


def test_unknown_tool_contributes_no_override_target():
    """A registry miss must not be counted as an overridable node."""
    assert workflow_override_target_tools([{"tool": "no_such_tool"}]) == []


# =============================================================================
# The ENGINE enforces it, not the menu — every client inherits the rule
# =============================================================================


def _save_workflow(db, *, config: dict | None = None, nodes: list | None = None):
    """A minimal VALID graph: a lone `files` source has no required inputs, so
    connection validation and preflight both pass and only the #3804 rules
    can reject the run."""
    from uuid import uuid4

    from fichero_server.models import Workflow

    workflow = Workflow(
        name=f"Eligibility {uuid4().hex[:8]}",
        description="",
        format="nodes",
        config=config or {},
        nodes=nodes or [{"id": "files-source", "tool": "files", "inputs": {}, "config": {}}],
        edges=[],
    )
    db.save(workflow)
    return workflow


def test_execute_refuses_an_internal_component(client, db):
    """The Swift menu hides it; the CLI, MCP and a bare POST did not."""
    workflow = _save_workflow(db, config={"internal": True})

    response = client.post(
        "/api/workflow-execution/execute",
        json={"workflow_id": workflow.id},
    )

    assert response.status_code == 400
    assert "internal component" in response.json()["detail"]


def test_execute_refuses_an_override_no_node_would_accept(client, db):
    """Not a warning and not a silent drop — the run does not start."""
    workflow = _save_workflow(db)

    response = client.post(
        "/api/workflow-execution/execute",
        json={"workflow_id": workflow.id, "provider_override": "openrouter"},
    )

    assert response.status_code == 400
    assert "cannot apply the requested provider/model override" in response.json()["detail"]


def test_execute_without_an_override_still_runs(client, db):
    """The refusal is scoped to the override — Default must be unaffected."""
    workflow = _save_workflow(db)

    response = client.post(
        "/api/workflow-execution/execute",
        json={"workflow_id": workflow.id},
    )

    assert response.status_code == 202


def test_list_publishes_the_same_answer_the_engine_enforces(client, db):
    """The menu reads this field; drift between the two is the whole bug."""
    workflow = _save_workflow(db)

    response = client.get("/api/workflows")
    assert response.status_code == 200
    item = next(i for i in response.json()["items"] if i["id"] == workflow.id)

    assert item["accepts_model_override"] is False
    assert item["direct_runnable"] is True
