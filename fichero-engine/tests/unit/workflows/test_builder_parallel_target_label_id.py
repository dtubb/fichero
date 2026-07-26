"""
Regression tests for #2483: builder must use node id (not label) when wiring
non-parallel edges whose target is a parallel-target node.

Root cause: when a node has label != id (e.g. id="transcribe",
label="Transcribe Capture"), LangGraph registers it as "{label}_process" /
"{label}_aggregate".  Any non-SOURCE_TOOL edge pointing at that node was
wired to bare "{label}" — a node name that never existed — producing:
  ValueError: Found edge ending at unknown node 'Transcribe Capture'

Fix: _target_graph_name() appends "_process" when the target node id is in
parallel_target_node_ids.
"""

from __future__ import annotations

import json
import pathlib


from fichero.workflows.builder import build_graph
from fichero.workflows.types import WorkflowDef, NodeDef, EdgeDef


# ---------------------------------------------------------------------------
# 1. Actual preset round-trip (the original failure)
# ---------------------------------------------------------------------------

def _load_preset(name: str) -> WorkflowDef:
    preset_dir = (
        pathlib.Path(__file__).parents[3]
        / "src" / "fichero" / "resources" / "default_workflows"
    )
    data = json.loads((preset_dir / name).read_text())
    return WorkflowDef(**data)


def test_capture_ocr_transcribe_preset_builds_without_error():
    """#2483: 'Capture OCR + Transcribe' must build a LangGraph without ValueError."""
    workflow = _load_preset("capture_ocr_transcribe.json")
    app = build_graph(workflow, enable_parallel=True)
    assert app is not None


# ---------------------------------------------------------------------------
# 2. Minimal unit test: label != id + non-source edge to parallel target
# ---------------------------------------------------------------------------

def test_non_source_edge_to_parallel_target_builds():
    """A non-SOURCE_TOOL node wired to a parallel-target node must not crash.

    Topology:
      files-source (SOURCE_TOOL) ──files──▶ transcribe   ← parallel fan-out edge
      enhance      (not SOURCE_TOOL) ──▶ transcribe      ← this edge was broken

    'transcribe' has label="Transcribe Capture" (differs from its id).
    Before the fix, graph.add_edge("Enhance Images", "Transcribe Capture")
    raised ValueError because the registered node name is "Transcribe Capture_process".
    """
    workflow = WorkflowDef(
        name="Label Id Mismatch",
        nodes=[
            NodeDef(id="files-source", tool="files", label="Files", config={}),
            NodeDef(id="enhance", tool="enhance_images", label="Enhance Images", config={}),
            NodeDef(
                id="transcribe",
                tool="transcribe",
                label="Transcribe Capture",   # label differs from id
                config={},
            ),
        ],
        edges=[
            # parallel edge: files-source (SOURCE_TOOL) → transcribe (PARALLEL_TOOL)
            EdgeDef(
                source="files-source",
                target="transcribe",
                source_port="files",
                target_port="files",
            ),
            # non-parallel edge to the same parallel-target node
            EdgeDef(
                source="files-source",
                target="enhance",
                source_port="files",
                target_port="files",
            ),
            EdgeDef(
                source="enhance",
                target="transcribe",
                source_port="output_files",
                target_port="files",
            ),
        ],
    )

    # Must not raise ValueError: Found edge ending at unknown node 'Transcribe Capture'
    app = build_graph(workflow, enable_parallel=True)
    assert app is not None
