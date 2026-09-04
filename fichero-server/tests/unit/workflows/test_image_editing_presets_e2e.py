"""Every shipped image-editing preset, run end to end (Daniel, 2026-09-03).

The per-tool tests call the tool function directly with a hand-built input
dict. That is not the same thing as RUNNING the preset: the preset also has to
name a registered tool, wire its ports so the `files` source actually reaches
it, and survive the graph runtime — and a preset can be broken in any of those
ways while its tool's own test stays green.

Apple-free and model-free by construction: these tools do arithmetic on
pixels. `uses_llm` is asserted below precisely so that stays true — a preset
that quietly grew a model step would start costing money on a run the workflow
bar describes as free.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from tests.unit.workflows.test_default_workflow_e2e_harness import _load_workflow_by_name

from fichero_server.db import db_manager
from fichero_server.models import Document, FileType, ImageEditChain, Rendition
from fichero_server.workflows.builder import build_graph
from fichero_server.workflows.registry import get_tool_def
from fichero_server.workflows.runtime import build_initial_state

pytest.importorskip("PIL")

from PIL import Image, ImageDraw  # noqa: E402

# name → (the tool the preset must run, does it append to the edit chain?)
IMAGE_PRESETS = {
    "Enhance Images": ("enhance_images", True),
    "Fuzzy Clean Images": ("fuzzy_clean_images", True),
    "Remove Background Images": ("remove_background_images", True),
    "Rotate / Auto-Orient Images": ("rotate_images", True),
    "Segment Images": ("segment_images", False),
    "Split Images": ("split_images", False),
    "Prepare Images for OCR": ("prepare_images", False),
}


def _scratch_library(tmp_path: Path) -> tuple[Path, object, Document]:
    """A library with one real scanned-looking page. No fixtures, no network."""
    library_path = tmp_path / "Library.fichero"
    (library_path / "lance").mkdir(parents=True)
    (library_path / "storage").mkdir()
    db = db_manager.get_database(library_path)

    source = library_path / "storage" / "scan.png"
    image = Image.new("RGB", (240, 320), color=(18, 18, 18))
    draw = ImageDraw.Draw(image)
    # A light block on a dark ground: background removal, segmentation and
    # auto-contrast all need something to FIND, or they honestly do nothing
    # and the test would be asserting against a no-op.
    draw.rectangle([40, 60, 200, 260], fill=(235, 232, 225))
    draw.rectangle([70, 100, 170, 130], fill=(30, 30, 30))
    image.save(source)

    doc = Document(name="scan.png", path=str(source), file_type=FileType.image)
    db.save(doc)
    return library_path, db, doc


def _run(preset_name: str, library_path: Path, doc_id: str) -> dict:
    workflow = _load_workflow_by_name(preset_name)
    state = build_initial_state(
        {"selected_doc_ids": [doc_id]}, library_path=str(library_path)
    )
    state["workflow_id"] = workflow.id
    state["task_id"] = f"test-image-preset-{workflow.id}"
    return asyncio.run(build_graph(workflow, skip_cache=True).ainvoke(state))


@pytest.mark.parametrize("preset_name", sorted(IMAGE_PRESETS))
def test_preset_runs_its_tool_and_finishes_clean(preset_name, tmp_path):
    library_path, _db, doc = _scratch_library(tmp_path)
    tool_name, _ = IMAGE_PRESETS[preset_name]

    final_state = _run(preset_name, library_path, doc.id)

    assert final_state.get("error") in (None, ""), final_state.get("error")
    completed = set(final_state.get("completed_nodes") or [])
    assert completed, f"{preset_name} completed no nodes at all"
    # The tool node itself ran — not just the `files` source, which would
    # "succeed" while doing nothing to the image.
    assert any(tool_name in node for node in completed), (
        f"{preset_name} never reached {tool_name}; completed={sorted(completed)}"
    )


@pytest.mark.parametrize("preset_name", sorted(IMAGE_PRESETS))
def test_preset_actually_changes_something(preset_name, tmp_path):
    """A green tick with nothing persisted is absence read as success.

    Each of these tools reports `no_effect` when it wrote no output or could
    place none of it in the library; that field is the honest answer to "did
    the run do anything", and a preset run on a real image must never set it.
    """
    library_path, db, doc = _scratch_library(tmp_path)
    tool_name, _ = IMAGE_PRESETS[preset_name]

    final_state = _run(preset_name, library_path, doc.id)

    node_output = (final_state.get("outputs") or {}).get(tool_name) or {}
    assert node_output, f"{preset_name} produced no output for {tool_name}"
    assert node_output.get("error") in (None, ""), node_output.get("error")
    assert not node_output.get("no_effect"), node_output.get("no_effect")
    # And the bytes it wrote are real files, not paths it merely named.
    written = node_output.get("output_files") or node_output.get("files") or []
    assert written, f"{preset_name} wrote no image"
    assert all(Path(path).exists() for path in written), written


@pytest.mark.parametrize("preset_name", sorted(IMAGE_PRESETS))
def test_preset_result_is_reachable_from_the_library(preset_name, tmp_path):
    """The user's half of the contract: a run leaves something the app can
    SHOW — a rendition of the page, or child nodes cut from it. A file in
    $TMPDIR is not a result; the temp sweep takes it and the library never
    knew about it."""
    library_path, db, doc = _scratch_library(tmp_path)

    _run(preset_name, library_path, doc.id)

    renditions = list(db.query(Rendition, document_id=doc.id))
    children = [child for child in db.all(Document) if child.parent_id == doc.id]
    assert renditions or children, (
        f"{preset_name} left nothing in the library — no rendition, no child node"
    )
    for rendition in renditions:
        assert Path(rendition.path).exists(), rendition.path
        # Under library storage, never the swept temp dir.
        assert str(library_path) in str(Path(rendition.path).resolve()), rendition.path


@pytest.mark.parametrize("preset_name", sorted(IMAGE_PRESETS))
def test_preset_leaves_the_source_file_untouched(preset_name, tmp_path):
    """Non-destructive is the whole contract: the original bytes never move."""
    library_path, _db, doc = _scratch_library(tmp_path)
    before = Path(doc.path).read_bytes()

    _run(preset_name, library_path, doc.id)

    assert Path(doc.path).read_bytes() == before


@pytest.mark.parametrize(
    "preset_name",
    sorted(name for name, (_, chains) in IMAGE_PRESETS.items() if chains),
)
def test_chain_preset_lands_a_step_the_editor_can_see(preset_name, tmp_path):
    """A workflow edit and a hand edit are the SAME chain.

    This is what makes "run Enhance Images, then open the Edits facet" show a
    step you can re-open, re-tune, or revert — rather than an invisible change
    to the pixels with no recipe behind it.
    """
    library_path, db, doc = _scratch_library(tmp_path)

    _run(preset_name, library_path, doc.id)

    chains = list(db.query(ImageEditChain, document_id=doc.id))
    assert len(chains) == 1, f"{preset_name} saved {len(chains)} chains"
    assert chains[0].operations, f"{preset_name} saved an empty chain"


@pytest.mark.parametrize("preset_name", sorted(IMAGE_PRESETS))
def test_preset_needs_no_model(preset_name, tmp_path):
    """The claim the workflow bar makes about these: no model, no cost."""
    tool_name, _ = IMAGE_PRESETS[preset_name]
    tool_def = get_tool_def(tool_name)
    assert tool_def is not None, f"{tool_name} is not registered"
    assert tool_def.uses_llm is False
