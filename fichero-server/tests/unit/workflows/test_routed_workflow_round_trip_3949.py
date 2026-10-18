"""A workflow with a route_map edge survives save and read-back (#3949).

Spec: docs/contributor_manual/specs/ui/workflows.md, `workflows.defaults.routed-workflow-survives-round-trip`.
WHY: seed_default_workflows logged "cannot list workflows ... EdgeDef.target is required for non-route_map
edges" on every launch: a routed workflow came back from the store as a plain edge with an empty target.
Through the real store and a real temporary database.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from fichero_server.db import Database
from fichero_server.models import Workflow
from fichero_server.workflows.workflow_store import WorkflowStore

# scripts/ is not a package: load the repo's scan helper by path (see test_scan_files_skips_nested_worktrees).
_SCAN = Path(__file__).resolve().parents[4] / "scripts" / "_scan_files.py"
_spec = importlib.util.spec_from_file_location("_scan_files", _SCAN)
assert _spec and _spec.loader
scan_files = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scan_files)

_ROUTE_EDGE = {
    "id": "edge-route",
    "source": "classify",
    "target": "",
    "route_key": "$.nodes.classify.script_type",
    "route_map": {"print": "read_print", "hand": "read_hand"},
}


@pytest.fixture
def store(tmp_path):
    return WorkflowStore(Database(tmp_path / "test.duckdb"))


def _routed() -> Workflow:
    return Workflow(
        name="Routed",
        format="nodes",
        nodes=[
            {"id": "classify", "tool": "classify_script", "label": "Classify"},
            {"id": "read_print", "tool": "transcribe", "label": "Print"},
            {"id": "read_hand", "tool": "transcribe", "label": "Hand"},
        ],
        edges=[{"id": "edge-0", "source": "classify", "target": "read_print"}, dict(_ROUTE_EDGE)],
    )


def _route_edge(workflow: Workflow) -> dict:
    edges = [e if isinstance(e, dict) else e.model_dump() for e in workflow.edges]
    return next(e for e in edges if e.get("id") == "edge-route")


def test_route_map_and_route_key_survive_save_and_get(store):
    saved = _routed()
    store.save(saved)
    back = _route_edge(store.get(saved.id))
    assert back["route_map"] == _ROUTE_EDGE["route_map"]
    assert back["route_key"] == _ROUTE_EDGE["route_key"]


def test_a_routed_workflow_is_listed_without_a_validation_error(store):
    store.save(_routed())
    assert [w.name for w in store.list_all()] == ["Routed"]


def test_the_shipped_auto_detect_default_round_trips(store):
    preset = next(scan_files.scan_rglob(Path(__file__).resolve().parents[3], "transcribe_auto_detect.json"))
    data = json.loads(preset.read_text(encoding="utf-8"))
    workflow = Workflow(
        name=data["name"], format="nodes", nodes=data["nodes"], edges=data["edges"]
    )
    store.save(workflow)
    back = store.get(workflow.id)
    assert [_route_edge_keys(e) for e in back.edges] == [_route_edge_keys(e) for e in workflow.edges]


def _route_edge_keys(edge) -> tuple:
    d = edge if isinstance(edge, dict) else edge.model_dump()
    return (d.get("source"), d.get("target"), d.get("route_key"), json.dumps(d.get("route_map"), sort_keys=True))
