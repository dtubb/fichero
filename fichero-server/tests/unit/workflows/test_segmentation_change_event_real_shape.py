"""segment.overlay.refreshes-when-segmentation-finishes (#4890): prove the
FIX against a REAL final_state, not a hand-built dict.

test_finalize_run_documents.py's TestArtifactChangeEmission/TestCollectCreated
ArtifactIds pin the CONTRACT with hand-built final_state dicts and direct
complete_run_documents() calls -- fast, but they assume the shape
collect_created_artifact_ids reads (`outputs[node_id]["artifacts"]` /
top-level `artifacts`) actually exists on a state a real graph run produces.
This file runs the SHIPPED "Detect Segments (Kraken)" preset through the
real builder (`build_graph(...).ainvoke(...)`) and the real runner
(`_run_workflow_in_background`) in a temp library, stubbing only the lowest
seam -- Kraken's own model/binary call (`kraken_runtime.segment_to_geometry`,
exactly as test_kraken_segmenter_node.py already does) -- never
`process_vision` and never `finalize_run_documents` itself.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.integration._seedlib import seed

from fichero_server.db import db_manager
from fichero_server.models import Artifact, DocType, Document, FileType, Workflow


def _make_png(path: Path) -> None:
    from PIL import Image

    Image.new("RGB", (16, 16), (255, 255, 255)).save(str(path), format="PNG")


def _kraken_geometry():
    from fichero_server.media.ocr_geometry import (
        OCRGeometryBox,
        OCRGeometryLevel,
        OCRGeometryResult,
    )

    return OCRGeometryResult(
        text="",
        provider="kraken",
        model="blla",
        source="kraken-blla",
        boxes=[
            OCRGeometryBox(
                text="",
                bbox=[0.1, 0.1, 0.8, 0.05],
                level=OCRGeometryLevel.LINE,
                provider="kraken",
                model="blla",
                source="kraken-blla",
                metadata={"baseline_px": [[100.0, 300.0], [900.0, 300.0]]},
            )
        ],
    )


def _seed_png_library(tmp_path: Path) -> tuple[Path, str]:
    library_path = tmp_path / "segment-real-shape.fichero"
    seed(library_path)
    db = db_manager.get_database(library_path)

    png_path = tmp_path / "hand.png"
    _make_png(png_path)
    doc = Document(
        name="hand.png", doc_type=DocType.file, file_type=FileType.image,
        path=str(png_path),
    )
    db.save(doc)
    return library_path, doc.id


def _load_detect_regions_kraken_workflow() -> Workflow:
    """Raw `Workflow` -- for `_run_workflow_in_background`, which converts
    to a `WorkflowDef` internally (`runner.py:1221`, `to_workflow_def
    (workflow)`) and expects the untyped model, not a pre-converted one."""
    from fichero_server.workflows.default_workflows import _load_preset_files

    preset = next(
        p for p in _load_preset_files() if p["name"] == "Detect Segments (Kraken)"
    )
    return Workflow(
        id="detect-regions-kraken-real-shape-harness",
        name=preset["name"],
        description=preset.get("description", ""),
        nodes=preset["nodes"],
        edges=preset["edges"],
        config=preset.get("config", {}),
        folder_path=preset.get("folder_path", "/"),
    )


def _load_detect_regions_kraken_workflow_def():
    """`WorkflowDef` -- for a DIRECT `build_graph(...)` call, which needs the
    typed conversion `test_default_workflow_e2e_harness.py::_load_catalogue_
    workflow` also applies before invoking the graph."""
    from fichero_server.workflows.runtime import to_workflow_def

    return to_workflow_def(_load_detect_regions_kraken_workflow())


@pytest.fixture(autouse=True)
def _stub_kraken_segmenter(monkeypatch):
    """The lowest seam: Kraken's own model/binary call, never process_vision."""
    import fichero_server.llm.kraken_runtime as kraken_runtime

    def _fake_segment(image_path, rendition_id=None, home=None):
        return _kraken_geometry()

    monkeypatch.setattr(kraken_runtime, "segment_to_geometry", _fake_segment)


@pytest.mark.asyncio
async def test_builder_path_real_final_state_carries_the_artifact_id(tmp_path):
    """`build_graph(...).ainvoke(state)` -- the same call the e2e harness
    (test_default_workflow_e2e_harness.py) uses -- run for real on the
    shipped Kraken preset. `collect_created_artifact_ids` on the REAL
    resulting final_state must name the artifact `detect_regions` actually
    saved."""
    from fichero_server.workflows.builder import build_graph
    from fichero_server.workflows.runtime import build_initial_state
    from fichero_server.workflows.completion import collect_created_artifact_ids

    library_path, doc_id = _seed_png_library(tmp_path)
    db = db_manager.get_database(library_path)
    workflow = _load_detect_regions_kraken_workflow_def()

    state = build_initial_state(
        {"selected_doc_ids": [doc_id]}, library_path=str(library_path)
    )
    state["workflow_id"] = workflow.id
    state["task_id"] = "test-real-shape-builder"

    final_state = await build_graph(workflow, skip_cache=True).ainvoke(state)

    saved = db.query(Artifact, document_id=doc_id, artifact_type="regions")
    assert len(saved) == 1, "detect_regions did not persist a regions artifact"
    real_artifact_id = saved[0].id

    found_ids = collect_created_artifact_ids(final_state)
    assert real_artifact_id in found_ids, (
        f"collect_created_artifact_ids({sorted(found_ids)!r}) did not contain "
        f"the real saved artifact id {real_artifact_id!r} -- the real graph "
        f"state shape does not match what the hand-built tests assumed."
    )


class _FakeActivityStore:
    async def save_workflow_run(self, **_kwargs):
        return None

    async def update_workflow_run(self, **_kwargs):
        return None


class _FakeActivityTracker:
    def __init__(self):
        self.store = _FakeActivityStore()

    def __getattr__(self, _name):
        return lambda **_kwargs: None


@pytest.mark.asyncio
async def test_runner_path_emits_one_artifact_updated_event_naming_it(
    monkeypatch, tmp_path
):
    """The REAL runner (`_run_workflow_in_background`), with the REAL builder
    and REAL compiled graph -- only `get_activity_tracker` and the
    thread-local `db_manager.get_database` redirect are mocked (same as
    test_finalize_run_documents.py's own runner-integration tests), so
    `build_graph`/`create_compiled_app` run unmodified. Asserts ONE
    `artifact.updated` ChangeEvent fires, naming the real artifact and its
    document -- not a hand-built one."""
    from fichero_server.execution import runner
    from fichero_server.api.routes.workflow_execution.schemas import (
        ExecuteWorkflowRequest,
    )
    from fichero_server.api import change_stream

    library_path, doc_id = _seed_png_library(tmp_path)
    db = db_manager.get_database(library_path)
    workflow = _load_detect_regions_kraken_workflow()

    monkeypatch.setattr(
        runner, "get_activity_tracker", lambda _p: _FakeActivityTracker()
    )
    monkeypatch.setattr(
        "fichero_server.db.manager.db_manager.get_database",
        lambda _library_path: db,
    )
    monkeypatch.setattr(
        "fichero_server.db.manager.db_manager.close_current_thread", lambda: None
    )

    captured = []
    monkeypatch.setattr(
        change_stream._change_hub,
        "emit",
        lambda library_path, event: captured.append(event),
    )

    thread_id = "test-real-shape-runner"
    events = runner.WorkflowEventHub()
    state = {"events": events}
    runner._set_workflow_state(thread_id, state)

    await runner._run_workflow_in_background(
        thread_id,
        workflow,
        ExecuteWorkflowRequest(workflow_id=workflow.id, inputs={"selected_doc_ids": [doc_id]}),
        db,
    )

    saved = db.query(Artifact, document_id=doc_id, artifact_type="regions")
    assert len(saved) == 1, "detect_regions did not persist a regions artifact"
    real_artifact_id = saved[0].id

    artifact_events = [e for e in captured if e.type == "artifact.updated"]
    assert len(artifact_events) == 1, (
        f"expected exactly one artifact.updated event, got "
        f"{[e.type for e in captured]!r}"
    )
    assert artifact_events[0].artifact_ids == [real_artifact_id]
    assert artifact_events[0].document_ids == [doc_id]


def test_batch_snapshot_values_shape_also_carries_the_artifact_id(tmp_path):
    """The batch path (`execution/batch.py`) reads
    `collect_created_artifact_ids(getattr(snapshot, "values", None))` off a
    LangGraph checkpoint snapshot rather than an `ainvoke` return value.
    Cheap check (no full BatchManager run): re-use the SAME real final_state
    the builder-path test above proves is correct, wrapped the way
    `compiled_graph.aget_state(config).values` actually shapes it (a plain
    dict, same keys) -- `collect_created_artifact_ids` doesn't care which
    LangGraph call produced the dict, only that the keys are there, so this
    is the real shape rather than a hand-built stand-in."""
    from fichero_server.workflows.builder import build_graph
    from fichero_server.workflows.runtime import build_initial_state
    from fichero_server.workflows.completion import collect_created_artifact_ids

    library_path, doc_id = _seed_png_library(tmp_path)
    db = db_manager.get_database(library_path)
    workflow = _load_detect_regions_kraken_workflow_def()

    state = build_initial_state(
        {"selected_doc_ids": [doc_id]}, library_path=str(library_path)
    )
    state["workflow_id"] = workflow.id
    state["task_id"] = "test-real-shape-batch"

    final_state = asyncio.run(build_graph(workflow, skip_cache=True).ainvoke(state))
    saved = db.query(Artifact, document_id=doc_id, artifact_type="regions")
    assert len(saved) == 1
    real_artifact_id = saved[0].id

    # snapshot.values IS final_state's own shape (LangGraph's checkpoint
    # values are the same channel dict ainvoke returns) -- wrap it exactly
    # as batch.py's own `getattr(snapshot, "values", None)` line reads it.
    snapshot = SimpleNamespace(values=final_state)
    found_ids = collect_created_artifact_ids(getattr(snapshot, "values", None))
    assert real_artifact_id in found_ids
