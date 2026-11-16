"""`workflows.defaults.every-preset-proven-on-both-axes`, `workflows.preset-validated` (docs/contributor_manual/specs/ui/workflows.md,
Step 3.1, #4369, #4501): the STRUCTURE axis of every shipped preset, and the rule that only a validated preset loses "(Untested)".

WHY: a preset is two claims, that its graph is sound and that its model calls give what it says. The first is checked here for ALL
shipped presets, with no model call: it is a real workflow definition, its connections are legal, its graph builds, every tool it names
can execute, and a scope it declares is one of the two. The second needs real calls and real output (#4496 passed "green" while storing
commentary as a transcription); it is not claimed here, so a preset that has not been so validated stays labelled "(Untested)".
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fichero_server.workflows.builder import build_graph
from fichero_server.workflows.registry import is_tool_executable
from fichero_server.workflows.types import WorkflowDef
from fichero_server.workflows.validation import SCOPES, validate_workflow_connections

PRESET_DIR = Path(__file__).resolve().parents[3] / "src" / "fichero_server" / "resources" / "default_workflows"
PRESETS = sorted(PRESET_DIR.glob("*.json"))


def _definition(path: Path) -> WorkflowDef:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return WorkflowDef.model_validate({k: raw[k] for k in ("name", "description", "nodes", "edges") if k in raw})


def test_the_retired_translate_presets_are_not_shipped_and_translate_double_checks():
    """Step 3.3 (#4705): one Translate, which cross-checks by default; the two presets it replaced are no longer shipped, so no
    preset is proven twice for the same job (the old names still resolve to Translate: `test_translate_and_extraction_checks_to_spec`)."""
    names = {p.stem for p in PRESETS}
    assert not names & {"translate_review", "translate_deepl"}, sorted(names & {"translate_review", "translate_deepl"})
    tools = [n.tool for n in _definition(PRESET_DIR / "translate.json").nodes]
    assert tools[-1] == "text_translate_review" and "text_translate" in tools, tools


def test_preset_discovery_is_not_blind():
    assert len(PRESETS) > 40, f"found {len(PRESETS)} shipped presets"


@pytest.mark.parametrize("path", PRESETS, ids=lambda p: p.stem)
def test_each_preset_has_a_sound_graph(path):
    definition = _definition(path)
    assert definition.nodes, "a preset with no steps"
    assert validate_workflow_connections(definition) == []
    build_graph(definition, enable_parallel=True)  # raises ValueError for a graph that cannot be built


@pytest.mark.parametrize("path", PRESETS, ids=lambda p: p.stem)
def test_each_preset_names_only_tools_that_can_execute(path):
    missing = sorted({n.tool for n in _definition(path).nodes if not is_tool_executable(n.tool)})
    assert missing == [], f"{path.stem} names tools nothing runs: {missing}"


@pytest.mark.parametrize("path", PRESETS, ids=lambda p: p.stem)
def test_a_declared_scope_is_one_of_the_two(path):
    config = json.loads(path.read_text(encoding="utf-8")).get("config") or {}
    assert config.get("scope", "per_file") in SCOPES


def test_only_a_validated_preset_loses_the_untested_label(client):
    """`tested: true` is the one switch: the served flag follows it, for every preset (`_workflow_untested`)."""
    from fichero_server.api.routes.workflow.workflows import _workflow_untested
    from types import SimpleNamespace

    for path in PRESETS:
        config = json.loads(path.read_text(encoding="utf-8")).get("config") or {}
        wf = SimpleNamespace(is_system=True, config=config)
        assert _workflow_untested(wf) is (not config.get("tested", False)), path.stem
