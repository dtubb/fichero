"""#4324(d): route_map fan-out driven by an EXPLICIT edge declaration.

Before, the builder inferred the files source for route_map parallel targets
by walking one hop upstream of the routing node (builder.py, route-map
fan-out). ``EdgeDef.route_files_source`` makes that wiring explicit in the
workflow definition; the inference remains only as a fallback for
user-authored workflows that predate the field.
"""

from __future__ import annotations

import json
import logging
import pathlib

import pytest

from fichero_server.workflows.builder import build_graph
from fichero_server.workflows.types import EdgeDef, NodeDef, WorkflowDef


def _load_preset(name: str) -> WorkflowDef:
    preset_dir = (
        pathlib.Path(__file__).parents[3]
        / "src" / "fichero_server" / "resources" / "default_workflows"
    )
    data = json.loads((preset_dir / name).read_text())
    return WorkflowDef(**data)


def _routed_workflow(*, declare: bool, wire_source_to_classify: bool = True) -> WorkflowDef:
    """classify → route_map → transcribe branch, files from files-source."""
    edges = []
    if wire_source_to_classify:
        edges.append(
            EdgeDef(
                source="files-source",
                target="classify",
                source_port="files",
                target_port="files",
            )
        )
    edges.append(
        EdgeDef(
            id="edge-route",
            source="classify",
            target="",
            route_key="$.nodes.classify.script_type",
            route_map={"typescript": "transcribe-ts"},
            route_files_source="files-source" if declare else None,
        )
    )
    return WorkflowDef(
        name="Routed",
        nodes=[
            NodeDef(id="files-source", tool="files", label="Files", config={}),
            NodeDef(id="classify", tool="classify_script", label="Classify", config={}),
            NodeDef(
                id="transcribe-ts",
                tool="transcribe",
                label="Transcribe TS",
                config={},
                inputs={"files": "$.nodes.files-source.files"},
            ),
        ],
        edges=edges,
    )


def test_declared_route_files_source_enables_fan_out(caplog):
    workflow = _routed_workflow(declare=True)
    with caplog.at_level(logging.INFO, logger="fichero_server.workflows.builder"):
        app = build_graph(workflow, enable_parallel=True)
    assert app is not None
    assert any("Route-map fan-out declared" in rec.message for rec in caplog.records)
    assert not any("fan-out detected" in rec.message for rec in caplog.records)


def test_declaration_works_where_inference_cannot(caplog):
    """No source→classify edge exists, so one-hop inference finds nothing;
    the explicit declaration still wires the fan-out."""
    workflow = _routed_workflow(declare=True, wire_source_to_classify=False)
    with caplog.at_level(logging.INFO, logger="fichero_server.workflows.builder"):
        app = build_graph(workflow, enable_parallel=True)
    assert app is not None
    assert any("Route-map fan-out declared" in rec.message for rec in caplog.records)


def test_inference_fallback_still_detects_legacy_workflows(caplog):
    workflow = _routed_workflow(declare=False)
    with caplog.at_level(logging.INFO, logger="fichero_server.workflows.builder"):
        app = build_graph(workflow, enable_parallel=True)
    assert app is not None
    assert any("Route-map fan-out detected" in rec.message for rec in caplog.records)


def test_declared_source_must_be_a_source_tool():
    workflow = _routed_workflow(declare=True)
    for edge in workflow.edges:
        if edge.route_map:
            edge.route_files_source = "classify"  # not a SOURCE_TOOL
    with pytest.raises(ValueError, match="route_files_source"):
        build_graph(workflow, enable_parallel=True)


def test_auto_detect_preset_declares_its_fan_out_source(caplog):
    """The shipped Transcribe (Auto-Detect) preset no longer relies on
    builder inference for its per-file fan-out (#4324)."""
    workflow = _load_preset("transcribe_auto_detect.json")
    route_edges = [e for e in workflow.edges if e.route_map]
    assert route_edges, "Auto-Detect lost its route_map edge"
    assert all(e.route_files_source == "files-source" for e in route_edges)

    with caplog.at_level(logging.INFO, logger="fichero_server.workflows.builder"):
        app = build_graph(workflow, enable_parallel=True)
    assert app is not None
    assert any("Route-map fan-out declared" in rec.message for rec in caplog.records)
    assert not any("fan-out detected" in rec.message for rec in caplog.records)
