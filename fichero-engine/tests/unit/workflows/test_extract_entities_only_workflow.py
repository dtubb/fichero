from __future__ import annotations

import asyncio
from pathlib import Path

from tests.integration._seedlib import seed

from fichero.db import db_manager
from fichero.knowledge_models import EntityType, KnowledgeEntity
from fichero.models import Artifact, DocType, Document, FileType, Workflow
from fichero.workflows.builder import build_graph
from fichero.workflows.default_workflows import _load_preset_files
from fichero.workflows.runtime import build_initial_state, to_workflow_def

import fichero.workflows.tools  # noqa: F401


FIXTURE_TEXT = "Ada signed the ledger in Mockton."


def test_extract_entities_preset_persists_entities_and_is_idempotent(tmp_path: Path):
    library_path, parent_doc_id, page_doc_ids = _seed_importable_pdf_library(tmp_path)
    db = db_manager.get_database(library_path)

    import_workflow = _load_workflow("1 · Import → Artifacts")
    extract_workflow = _load_workflow("2 · Extract Entities", provider_name="mock")

    first_import = asyncio.run(
        build_graph(import_workflow, skip_cache=True).ainvoke(
            _workflow_state(library_path, parent_doc_id, task_id="import-artifacts-first")
        )
    )
    assert not first_import.get("error")

    for page_doc_id in page_doc_ids:
        page = db.get(Document, page_doc_id)
        assert page is not None
        metadata = dict(page.metadata or {})
        metadata["transcription"] = ""
        page.metadata = metadata
        page.page_content = ""
        db.save(page)

    first = asyncio.run(
        build_graph(extract_workflow, skip_cache=True).ainvoke(
            _workflow_state(library_path, parent_doc_id, task_id="extract-entities-first")
        )
    )
    assert not first.get("error")
    first_summary = first["outputs"]["extract-entities"]["summary"]
    assert first_summary == {
        "documents_processed": 2,
        "entity_mentions_processed": 4,
        "entities_created": 2,
        "entities_reused": 2,
        "entities_suppressed": 0,
    }

    second = asyncio.run(
        build_graph(extract_workflow, skip_cache=True).ainvoke(
            _workflow_state(library_path, parent_doc_id, task_id="extract-entities-second")
        )
    )
    assert not second.get("error")
    second_summary = second["outputs"]["extract-entities"]["summary"]
    assert second_summary == {
        "documents_processed": 2,
        "entity_mentions_processed": 4,
        "entities_created": 0,
        "entities_reused": 4,
        "entities_suppressed": 0,
    }

    entities = db.query(KnowledgeEntity)
    persisted = {
        (entity.canonical_name, entity.entity_type): entity
        for entity in entities
        if entity.canonical_name in {"Ada Mock", "Mockton"}
    }
    assert set(persisted) == {
        ("Ada Mock", EntityType.person),
        ("Mockton", EntityType.location),
    }
    assert len(persisted[("Ada Mock", EntityType.person)].source_document_ids) == 2
    assert len(persisted[("Mockton", EntityType.location)].source_document_ids) == 2

    transcription_artifacts = [
        artifact
        for artifact in db.query(Artifact)
        if artifact.document_id in set(page_doc_ids)
        and artifact.artifact_type == "transcription"
    ]
    assert len(transcription_artifacts) == 2


def _seed_importable_pdf_library(tmp_path: Path) -> tuple[Path, str, list[str]]:
    library_path = tmp_path / "extract-entities-stage.fichero"
    seed(library_path)
    db = db_manager.get_database(library_path)

    source_file = tmp_path / "marshall-imported.pdf"
    source_file.write_bytes(b"%PDF-1.4\n% extract entities fixture\n")

    parent_doc = Document(
        id="marshall-import-root",
        name="Marshall import root",
        path=str(source_file),
        doc_type=DocType.file,
        file_type=FileType.pdf,
        metadata={"canonical_external_id": "marshall-import-root"},
    )
    pages = [
        Document(
            id="marshall-import-page-1",
            parent_id=parent_doc.id,
            name="Marshall import page 1",
            doc_type=DocType.page,
            sequence=1,
            page_content=FIXTURE_TEXT,
            metadata={
                "canonical_external_id": "marshall-import-root__page_001",
                "page_label": "001",
                "page_number": 1,
                "transcription": FIXTURE_TEXT,
                "images": [{"role": "enhanced"}],
            },
        ),
        Document(
            id="marshall-import-page-2",
            parent_id=parent_doc.id,
            name="Marshall import page 2",
            doc_type=DocType.page,
            sequence=2,
            page_content=FIXTURE_TEXT,
            metadata={
                "canonical_external_id": "marshall-import-root__page_002",
                "page_label": "002",
                "page_number": 2,
                "transcription": FIXTURE_TEXT,
                "images": [{"role": "enhanced"}],
            },
        ),
    ]
    db.save(parent_doc)
    for page in pages:
        db.save(page)

    return library_path, parent_doc.id, [page.id for page in pages]


def _load_workflow(name: str, *, provider_name: str | None = None):
    preset = next(p for p in _load_preset_files() if p["name"] == name)
    if provider_name is not None:
        preset = {
            **preset,
            "nodes": [
                {
                    **node,
                    "config": {
                        **node.get("config", {}),
                        **({"provider_name": provider_name} if node["tool"] != "files" else {}),
                    },
                }
                for node in preset["nodes"]
            ],
        }
    return to_workflow_def(
        Workflow(
            id=f"default-{name.lower().replace(' ', '-')}-regression-harness",
            name=preset["name"],
            description=preset.get("description", ""),
            nodes=preset["nodes"],
            edges=preset["edges"],
            config=preset.get("config", {}),
            folder_path=preset.get("folder_path", "/"),
        )
    )


def _workflow_state(library_path: Path, selected_doc_id: str, *, task_id: str) -> dict:
    state = build_initial_state(
        {"selected_doc_ids": [selected_doc_id]},
        library_path=str(library_path),
    )
    state["workflow_id"] = "default-extract-entities-regression-harness"
    state["task_id"] = task_id
    return state
