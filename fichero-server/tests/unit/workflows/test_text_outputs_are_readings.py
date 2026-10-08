"""Text outputs are readings; the catalogue never overwrites a folder's text (#5599).

Spec: `docs/contributor_manual/specs/source/source-model.md`, "Extracted data, integrated (review
2026-10-07)":

- `source.extract.catalogue-never-overwrites-text`: the catalogue's narrative is a reading of kind
  description on the folder, never written into its `page_content`.
- `source.extract.text-outputs-are-readings`: a translation, modernisation or regest is a reading of
  its kind; the historical presets stop filing a translation as `analysis`.

Each shipped preset runs through the REAL background runner (`_run_workflow_in_background`, as
`POST /execute` does) with only the model stubbed, and the result is looked for where a person would
look: the document's readings (`GET /api/content-representations/document/{id}`).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from PIL import Image

from tests.integration._seedlib import seed
from tests.unit.workflows.test_catalogue_real_preset_run_e2e import (
    _run_through_the_runner,
    two_folder_library,  # noqa: F401 — fixture re-export
)
from tests.unit.workflows.test_default_workflow_e2e_harness import (
    _install_deterministic_workflow_stubs,
)

import fichero_server.llm as llm_module
from fichero_server.api.routes.document.content_representations import list_representations
from fichero_server.api.routes.workflow_execution.schemas import ExecuteWorkflowRequest
from fichero_server.db import db_manager
from fichero_server.execution import runner
from fichero_server.models import Artifact, DocType, Document, FileType, ProvenanceKind, Workflow
from fichero_server.workflows.default_workflows import _load_preset_files
from fichero_server.workflows.selection import SelectionKind, WorkflowSelection

import fichero_server.workflows.tools  # noqa: F401

FOLDER_OWN_TEXT = "Caja 3: notas del archivero, escritas a mano en la carpeta."


@pytest.fixture(autouse=True)
def _no_seeding(monkeypatch):
    monkeypatch.setenv("FICHERO_SKIP_DEFAULT_WORKFLOWS", "1")


def _readings(library_path: Path, document_id: str):
    """The document's readings, read through the route a person's window reads."""
    db = db_manager.get_database(library_path)
    return asyncio.run(list_representations(document_id, db=db)).items


def _live(rows, kind: str):
    return [row for row in rows if row.kind == kind and row.retracted_at is None]


# ── source.extract.catalogue-never-overwrites-text ──────────────────────────


def _catalogue_run(library_path: Path, thread_id: str) -> None:
    _run_through_the_runner(
        library_path, thread_id, WorkflowSelection(kind=SelectionKind.folder, ids=["caja-3"])
    )


def test_the_catalogue_narrative_is_a_description_reading_of_the_folder(
    two_folder_library, monkeypatch  # noqa: F811
):
    _install_deterministic_workflow_stubs(monkeypatch)
    library_path, db = two_folder_library

    _catalogue_run(library_path, "catalogue-description-reading")

    db = db_manager.get_database(library_path)
    narrative = next(
        a for a in db.query(Artifact, document_id="caja-3") if a.artifact_type == "catalogue.narrative"
    )
    described = _live(_readings(library_path, "caja-3"), "description")
    assert len(described) == 1, f"expected one description reading on the folder, got {described!r}"
    reading = described[0]
    assert reading.content == narrative.content
    assert reading.segment_id is None
    assert reading.derived_from_artifact_id == narrative.id
    assert reading.producer_run_id == narrative.run_id
    assert reading.producer_run_id.startswith("catalogue-description-reading")
    assert reading.provenance_kind is ProvenanceKind.workflow, "a machine's description, never a person's"


def test_the_folders_own_text_stays_what_it_was(two_folder_library, monkeypatch):  # noqa: F811
    _install_deterministic_workflow_stubs(monkeypatch)
    library_path, db = two_folder_library
    folder = db.get(Document, "caja-3")
    db.save(folder.model_copy(update={"page_content": FOLDER_OWN_TEXT}))

    _catalogue_run(library_path, "catalogue-keeps-folder-text")

    db = db_manager.get_database(library_path)
    assert db.get(Document, "caja-3").page_content == FOLDER_OWN_TEXT, (
        "the catalogue wrote its narrative over the folder's own text"
    )
    assert _live(_readings(library_path, "caja-3"), "description"), "and the narrative went nowhere"


def test_a_folder_with_no_text_is_not_given_the_narrative_as_text(
    two_folder_library, monkeypatch  # noqa: F811
):
    _install_deterministic_workflow_stubs(monkeypatch)
    library_path, db = two_folder_library
    before = db.get(Document, "caja-3").page_content

    _catalogue_run(library_path, "catalogue-empty-folder-text")

    db = db_manager.get_database(library_path)
    assert db.get(Document, "caja-3").page_content == before


def test_a_rerun_describes_the_folder_once_not_once_per_run(
    two_folder_library, monkeypatch  # noqa: F811
):
    _install_deterministic_workflow_stubs(monkeypatch)
    library_path, _db = two_folder_library

    _catalogue_run(library_path, "catalogue-rerun-first")
    first = _live(_readings(library_path, "caja-3"), "description")
    _catalogue_run(library_path, "catalogue-rerun-second")

    rows = _readings(library_path, "caja-3")
    live = _live(rows, "description")
    assert len(live) == 1, f"a re-run doubled the folder's description: {live!r}"
    assert live[0].producer_run_id.startswith("catalogue-rerun-second")
    # The superseded one is retracted, not deleted: what was said stays on the record.
    old = next(row for row in rows if row.id == first[0].id)
    assert old.retracted_at is not None


# ── source.extract.text-outputs-are-readings: the historical presets ────────

HISTORICAL = [
    # (preset name, reading kind, the model's stubbed answer)
    ("Translate to English (Historical)", "translation", "In the town of Madrid, on the twentieth day"),
    ("Modernización (Spanish)", "normalized_text", "En la villa de Madrid, a veinte días"),
    ("Regesto (Archival Abstract)", "regest", "1601, Madrid. Escritura de venta otorgada por Juan de Ocampo."),
]


@pytest.fixture
def one_page_library(tmp_path: Path):
    library_path = tmp_path / "historical.fichero"
    seed(library_path)
    db = db_manager.get_database(library_path)
    image = tmp_path / "folio-1.png"
    Image.new("RGB", (32, 32), "white").save(image)
    db.save(
        Document(
            id="folio-1",
            name="folio-1.png",
            path=str(image),
            doc_type=DocType.file,
            file_type=FileType.image,
            page_content="En la villa de madrid a veynte dias",
        )
    )
    yield library_path, db
    db_manager.close_database(library_path)


def _run_preset(library_path: Path, preset_name: str, thread_id: str, document_id: str) -> None:
    preset = next(p for p in _load_preset_files() if p["name"] == preset_name)
    # The shipped graph and prompt, with a generative model chosen on its step, as a person does: the
    # library's factory default is Apple Vision, which this step refuses (it ignores the prompt).
    nodes = [
        {**node, "config": {**node["config"], "provider_name": "openrouter", "model_name": "google/gemini-3.1-flash-lite"}}
        if node["tool"] == "analyze"
        else node
        for node in preset["nodes"]
    ]
    workflow = Workflow(
        id=f"default-{thread_id}",
        name=preset["name"],
        description=preset.get("description", ""),
        nodes=nodes,
        edges=preset["edges"],
        config=preset.get("config", {}),
        folder_path=preset.get("folder_path", "/"),
    )
    runner._set_workflow_state(
        thread_id,
        {
            "workflow_id": workflow.id,
            "workflow_name": workflow.name,
            "status": "accepted",
            "events": runner.WorkflowEventHub(),
            "error": None,
            "final_state": None,
        },
    )
    request = ExecuteWorkflowRequest(
        workflow_id=workflow.id,
        inputs={},
        thread_id=thread_id,
        selection=WorkflowSelection(kind=SelectionKind.documents, ids=[document_id]),
        skip_cache=True,
    )
    db = db_manager.get_database(library_path)
    try:
        asyncio.run(runner._run_workflow_in_background(thread_id, workflow, request, db))
    finally:
        runner._remove_workflow_state(thread_id)


@pytest.mark.parametrize(("preset_name", "kind", "answer"), HISTORICAL)
def test_a_historical_preset_saves_a_reading_of_its_kind(
    one_page_library, monkeypatch, preset_name, kind, answer
):
    _install_deterministic_workflow_stubs(monkeypatch)
    library_path, _db = one_page_library

    async def fake_vision(*, images, prompt, config, language=None, **kwargs):
        return answer

    monkeypatch.setattr(llm_module, "vision", fake_vision)
    thread_id = f"historical-{kind}"

    _run_preset(library_path, preset_name, thread_id, "folio-1")

    readings = _live(_readings(library_path, "folio-1"), kind)
    assert [r.content for r in readings] == [answer], (
        f"{preset_name} left no {kind} reading on the page; found {_readings(library_path, 'folio-1')!r}"
    )
    reading = readings[0]
    assert reading.producer_run_id.startswith(thread_id)
    assert reading.provenance_kind is ProvenanceKind.workflow

    db = db_manager.get_database(library_path)
    artifacts = db.query(Artifact, document_id="folio-1")
    assert not [a for a in artifacts if a.artifact_type == "analysis"], (
        f"{preset_name} still files its answer as 'analysis'"
    )
    record = next(a for a in artifacts if a.id == reading.derived_from_artifact_id)
    assert record.artifact_type == kind, "the run's record carries the kind of what it made"
    page = db.get(Document, "folio-1")
    assert page.page_content == "En la villa de madrid a veynte dias", "the transcription is untouched"
    assert "analysis" not in (page.metadata or {})


def test_the_translation_preset_is_found_where_translations_are_looked_for(one_page_library, monkeypatch):
    """Whatever looks for a translation finds it: a translation reading, and the run's record typed
    `translation` (the artifact type the translate tools and the immersive view already use)."""
    _install_deterministic_workflow_stubs(monkeypatch)
    library_path, _db = one_page_library

    async def fake_vision(*, images, prompt, config, language=None, **kwargs):
        return "In the town of Madrid"

    monkeypatch.setattr(llm_module, "vision", fake_vision)
    _run_preset(library_path, "Translate to English (Historical)", "historical-found", "folio-1")

    db = db_manager.get_database(library_path)
    assert [a.content for a in db.query(Artifact, document_id="folio-1", artifact_type="translation")] == [
        "In the town of Madrid"
    ]
    assert [r.content for r in _live(_readings(library_path, "folio-1"), "translation")] == [
        "In the town of Madrid"
    ]


def test_an_analyze_node_that_names_no_reading_kind_is_still_an_analysis(tmp_path, monkeypatch):
    """The custom Analyze step is a prompt and nothing more: without a reading kind it writes no
    reading (the guard's declaration names both)."""
    from fichero_server.workflows.tools.analyze import TOOL_CONFIG, tool_config_for

    assert tool_config_for(None) is TOOL_CONFIG
    assert TOOL_CONFIG.reading_kind is None and TOOL_CONFIG.artifact_type == "analysis"
    translation = tool_config_for("translation")
    assert (translation.artifact_type, translation.reading_kind, translation.metadata_field) == (
        "translation",
        "translation",
        None,
    )


# ── the translate tools: the same seam ──────────────────────────────────────


def test_text_translate_writes_a_translation_reading(one_page_library, monkeypatch):
    from fichero_server.llm import LLMConfig
    from fichero_server.workflows.tools import text_translate as tool

    library_path, _db = one_page_library

    async def fake_chat(*args, **kwargs):
        return "In the town of Madrid on the twentieth day"

    # `process_text` imports `chat` from fichero_server.llm at call time.
    monkeypatch.setattr(llm_module, "chat", fake_chat)
    result = asyncio.run(
        tool.text_translate(
            {
                "text": "En la villa de madrid a veynte dias",
                "documents": [{"id": "folio-1", "name": "folio-1.png"}],
            },
            {"library_path": str(library_path), "task_id": "translate-run"},
            LLMConfig(provider="openrouter", model="fake-model"),
        )
    )
    assert not result.get("error"), result
    readings = _live(_readings(library_path, "folio-1"), "translation")
    assert [r.content for r in readings] == ["In the town of Madrid on the twentieth day"]
    assert readings[0].producer_run_id == "translate-run"
