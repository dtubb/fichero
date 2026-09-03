"""Guard: a fanned-out parallel tool never also takes a mid-chain edge.

Found live 2026-09-03 running the shipped "Capture OCR + Transcribe" preset:
its `transcribe` node (a PARALLEL_TOOLS member) had inbound edges from BOTH
the files source and `enhance_images`. The builder classifies any edge whose
source is a SOURCE tool as a per-file fan-out (regardless of port), so the
node was Sent every ORIGINAL file the moment the source completed — before
prepare/enhance had run — and the plain `enhance -> transcribe_process` edge
then invoked the Send-expecting _process node once more with no item payload:
`[PARALLEL] [1/1] FAILED: File not found:` (empty path). One phantom failure,
one transcription of the wrong (un-enhanced) file, and a run that still said
"completed successfully".

The legal shapes are:
  * fan-out: parallel tool fed ONLY by source-tool edges (per-file Sends); or
  * batch: parallel tool fed ONLY by non-source edges (single batch call on
    the upstream node's output files), documents via a static inputs mapping.
Mixing them is structurally broken in the current builder, so no shipped
preset may do it.
"""

import json
from pathlib import Path

from fichero_server.workflows.builder import PARALLEL_TOOLS, SOURCE_TOOLS

PRESET_DIR = (
    Path(__file__).resolve().parents[3]
    / "src"
    / "fichero_server"
    / "resources"
    / "default_workflows"
)


def _mixed_parallel_feeds(preset: dict) -> list[str]:
    """Node ids of parallel-tool nodes fed by both source and non-source edges."""
    tools_by_id = {n.get("id"): n.get("tool") for n in preset.get("nodes", [])}
    offenders: list[str] = []
    for node in preset.get("nodes", []):
        if node.get("tool") not in PARALLEL_TOOLS:
            continue
        inbound = [
            e for e in preset.get("edges", []) if e.get("target") == node.get("id")
        ]
        from_source = [
            e for e in inbound if tools_by_id.get(e.get("source")) in SOURCE_TOOLS
        ]
        from_chain = [
            e for e in inbound if tools_by_id.get(e.get("source")) not in SOURCE_TOOLS
        ]
        if from_source and from_chain:
            offenders.append(node.get("id", "?"))
    return offenders


def test_no_shipped_preset_mixes_fanout_and_chain_edges_into_a_parallel_tool():
    presets = sorted(PRESET_DIR.glob("*.json"))
    assert len(presets) > 20, f"preset discovery went blind: found {len(presets)}"
    offenders: list[str] = []
    for path in presets:
        preset = json.loads(path.read_text())
        for node_id in _mixed_parallel_feeds(preset):
            offenders.append(f"{path.name}[{node_id}]")
    assert not offenders, (
        "These parallel-tool nodes are fed by BOTH a source fan-out and a "
        "mid-chain edge; the chain edge fires the Send-expecting _process "
        "node with no payload (phantom 'File not found:' failure) and the "
        "fan-out processes the wrong (pre-chain) files. Drop the source "
        "edge(s) and map documents via inputs, or drop the chain edge:\n"
        + "\n".join(offenders)
    )


def test_guard_fires_on_the_original_capture_shape():
    """Self-test: the exact pre-fix Capture OCR + Transcribe shape is caught."""
    bad = {
        "nodes": [
            {"id": "files-source", "tool": "files"},
            {"id": "enhance", "tool": "enhance_images"},
            {"id": "transcribe", "tool": "transcribe"},
        ],
        "edges": [
            {"source": "files-source", "target": "enhance",
             "source_port": "files", "target_port": "files"},
            {"source": "files-source", "target": "transcribe",
             "source_port": "documents", "target_port": "documents"},
            {"source": "enhance", "target": "transcribe",
             "source_port": "output_files", "target_port": "files"},
        ],
    }
    assert _mixed_parallel_feeds(bad) == ["transcribe"]
