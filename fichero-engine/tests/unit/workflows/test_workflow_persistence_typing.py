"""
Tests for the typed persistence boundary on ``Workflow.nodes`` / ``Workflow.edges`` (#2537).

Before this change the persisted ``nodes``/``edges`` columns were untyped
``list[dict]``: a malformed node (missing ``tool``) or edge surfaced as a
runtime ``KeyError``/``None`` deep in the LangGraph builder instead of a clean
validation error at save/load time, and the ``source_port`` vs ``source_port_id``
(and ``source`` vs ``source_node_id``) drift was handled ad-hoc in several readers.

These tests pin:
  * a well-formed workflow round-trips (save -> load -> same nodes/edges) and
    storage strips ports (re-hydrated from the registry on read);
  * a malformed node/edge raises a Pydantic ``ValidationError`` at the boundary;
  * an edge using the OLD ``*_id`` field spelling still loads and normalizes to
    the canonical field (back-compat, no migration);
  * the shipped preset JSON all still load + validate.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from fichero.models import Workflow
from fichero.workflows.types import EdgeDef, NodeDef


# ---------------------------------------------------------------------------
# Well-formed round-trip + port stripping
# ---------------------------------------------------------------------------


def test_wellformed_workflow_stores_minimal_nodes_without_ports():
    """A node carrying ports is accepted, but ports are NOT persisted — they are
    registry-owned and re-hydrated on read."""
    wf = Workflow(
        name="w",
        nodes=[
            {
                "id": "a",
                "tool": "files",
                "input_ports": [{"id": "p", "name": "P", "port_type": "input"}],
                "output_ports": [{"id": "o", "name": "O", "port_type": "output"}],
            }
        ],
        edges=[{"source": "a", "target": "b", "source_port": "files", "target_port": "files"}],
    )
    stored_node = wf.nodes[0]
    assert "input_ports" not in stored_node
    assert "output_ports" not in stored_node
    assert stored_node["tool"] == "files"


def test_edges_normalized_to_canonical_fields():
    wf = Workflow(
        name="w",
        edges=[{"source": "a", "target": "b", "source_port": "files", "target_port": "text"}],
    )
    edge = wf.edges[0]
    assert edge["source"] == "a"
    assert edge["target"] == "b"
    assert edge["source_port"] == "files"
    assert edge["target_port"] == "text"


def test_model_dump_reload_roundtrips_identically():
    """save -> model_dump (DB write) -> reconstruct (DB read) yields the same
    nodes/edges, ports still stripped."""
    wf = Workflow(
        name="w",
        nodes=[
            {"id": "a", "tool": "files", "input_ports": [{"id": "p", "name": "P", "port_type": "input"}]},
            {"id": "b", "tool": "transcribe"},
        ],
        edges=[{"source": "a", "target": "b", "source_port": "files", "target_port": "files"}],
    )
    dumped = wf.model_dump()
    reloaded = Workflow(**dumped)
    assert reloaded.nodes == wf.nodes
    assert reloaded.edges == wf.edges
    assert "input_ports" not in reloaded.nodes[0]


def test_nodedef_instances_accepted_and_stripped():
    """create_workflow_impl passes NodeDef/EdgeDef objects in — they must be
    accepted and reduced to storage dicts."""
    wf = Workflow(
        name="w",
        nodes=[NodeDef(id="a", tool="files", input_ports=[])],
        edges=[EdgeDef(source="a", target="b", source_port="files", target_port="files")],
    )
    assert wf.nodes[0]["tool"] == "files"
    assert "input_ports" not in wf.nodes[0]
    assert wf.edges[0]["source"] == "a"


# ---------------------------------------------------------------------------
# Malformed input fails at the boundary (not at runtime)
# ---------------------------------------------------------------------------


def test_malformed_node_missing_tool_raises_validation_error():
    with pytest.raises(ValidationError):
        Workflow(name="bad", nodes=[{"id": "x"}])  # no required `tool`


def test_malformed_node_wrong_type_raises_validation_error():
    with pytest.raises(ValidationError):
        Workflow(name="bad", nodes=[{"id": "x", "tool": "files", "position_x": "not-a-float"}])


def test_malformed_edge_wrong_type_raises_validation_error():
    with pytest.raises(ValidationError):
        Workflow(name="bad", edges=[{"source": "a", "source_port": 123}])


def test_node_must_be_dict_or_nodedef():
    with pytest.raises(ValidationError):
        Workflow(name="bad", nodes=["not-a-node"])


def test_edge_must_be_dict_or_edgedef():
    with pytest.raises(ValidationError):
        Workflow(name="bad", edges=[42])


# ---------------------------------------------------------------------------
# Back-compat: old *_id field spelling still loads + normalizes
# ---------------------------------------------------------------------------


def test_legacy_edge_id_spelling_loads_and_normalizes():
    """Already-stored workflows using source_node_id/source_port_id must keep
    loading and normalize onto source/source_port — no migration, no data loss."""
    wf = Workflow(
        name="legacy",
        edges=[
            {
                "source_node_id": "a",
                "target_node_id": "b",
                "source_port_id": "out",
                "target_port_id": "in",
            }
        ],
    )
    edge = wf.edges[0]
    assert edge["source"] == "a"
    assert edge["target"] == "b"
    assert edge["source_port"] == "out"
    assert edge["target_port"] == "in"
    # legacy keys are consumed, not left as stray data
    assert "source_node_id" not in edge
    assert "source_port_id" not in edge


def test_canonical_wins_over_legacy_when_both_present():
    edge = EdgeDef.model_validate(
        {
            "source": "real",
            "source_node_id": "stale",
            "source_port": "p",
            "source_port_id": "stale_p",
            "target": "t",
            "target_port": "tp",
        }
    )
    assert edge.source == "real"
    assert edge.source_port == "p"


def test_edgedef_model_validate_preserves_route_map():
    """The route-map fields must survive the typed deserialization path
    (an explicit field-copy previously dropped them)."""
    edge = EdgeDef.model_validate(
        {"source": "classify", "route_key": "$.nodes.classify.script", "route_map": {"ts": "t1"}}
    )
    assert edge.route_key == "$.nodes.classify.script"
    assert edge.route_map == {"ts": "t1"}


def test_empty_endpoint_edges_raise_validation_error():
    """Legacy empty-endpoint edges fail loudly instead of disappearing later."""
    with pytest.raises(ValidationError):
        Workflow(
            name="legacy",
            edges=[
                {
                    "source": "",
                    "target": "",
                    "source_port": "output",
                    "target_port": "input",
                }
            ],
        )


# ---------------------------------------------------------------------------
# Shipped presets all load + validate through the boundary
# ---------------------------------------------------------------------------


def _preset_files() -> list[Path]:
    base = (
        Path(__file__).resolve().parents[3]
        / "src"
        / "fichero"
        / "resources"
        / "default_workflows"
    )
    return sorted(base.glob("*.json"))


def test_all_shipped_presets_load_and_validate():
    files = _preset_files()
    assert files, "expected packaged preset JSON to exist"
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        wf = Workflow(
            name=data["name"],
            nodes=data.get("nodes", []),
            edges=data.get("edges", []),
            format=data.get("format", "nodes"),
        )
        for node in wf.nodes:
            assert "input_ports" not in node, f"{path.name}: ports leaked into storage"
            assert node.get("tool"), f"{path.name}: node missing tool"
        for edge in wf.edges:
            # every edge has the canonical endpoint key after normalization
            assert "source" in edge
            assert "source_port" in edge


def test_all_shipped_presets_compile_to_runtime_graph():
    """Every bundled preset must also survive the runtime EdgeDef graph build.

    The seed/storage boundary above validates edges, but the executable path
    (`to_workflow_def` -> `EdgeDef`) is where a route-style edge with a missing
    `target`/`route_map` blows up with
    'EdgeDef.target is required for non-route_map edges' (#2720). Sweep every
    preset through that path so a malformed route edge can never ship again.
    """
    from fichero.workflows.runtime import to_workflow_def

    files = _preset_files()
    assert files, "expected packaged preset JSON to exist"
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not data.get("name"):
            continue
        wf = Workflow(
            name=data["name"],
            nodes=data.get("nodes", []),
            edges=data.get("edges", []),
            format=data.get("format", "nodes"),
        )
        wd = to_workflow_def(wf)
        for edge in wd.edges:
            # A route edge declares route_map; a plain edge must name a target.
            assert edge.route_map is not None or edge.target, (
                f"{path.name}: edge {edge.id!r} has neither target nor route_map"
            )
