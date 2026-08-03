from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

from tests.integration._seedlib import seed

from fichero_server.db import db_manager
from fichero_server.models.knowledge import EntityType, KnowledgeEntity
from fichero_server.models import Artifact, DocType, Document, FileType, Workflow
from fichero_server.workflows.builder import build_graph
from fichero_server.workflows.default_workflows import _load_preset_files
from fichero_server.workflows.runtime import build_initial_state, to_workflow_def
from fichero_server.workflows.tools.extract_all import _EntitiesOnly, _EntityOnly
from fichero_server.workflows.tools.extract_entities_only import extract_entities_only
from fichero_server.llm import LLMConfig

import fichero_server.workflows.tools  # noqa: F401


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
    # #2092: the run reports which language each document was extracted in.
    # Popped so the counts below stay the subject of this assertion.
    assert first_summary.pop("languages_used") == {"English": 2}
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
    assert second_summary.pop("languages_used") == {"English": 2}
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


def test_extract_entities_tool_accepts_singleton_document_payload_without_unpack_error(
    tmp_path: Path,
):
    library_path, parent_doc_id, page_doc_ids = _seed_importable_pdf_library(tmp_path)
    db = db_manager.get_database(library_path)

    page = db.get(Document, page_doc_ids[0])
    assert page is not None

    async def fake_entities(**kwargs):
        del kwargs
        return _EntitiesOnly(
            people=[_EntityOnly(name="Ada Mock", aliases=[])],
            places=[_EntityOnly(name="Mockton", aliases=[])],
            organizations=[],
            dates=[],
            events=[],
        )

    with patch(
        "fichero_server.workflows.tools.extract_entities_only.chat_structured_with_fallback",
        new=fake_entities,
    ):
        result = asyncio.run(
            extract_entities_only(
                inputs={"documents": {"id": page.id}},
                state={
                    "library_path": str(library_path),
                    "selected_doc_ids": [parent_doc_id],
                    "task_id": "extract-entities-singleton-doc",
                },
                llm_config=LLMConfig(provider="mock", model="mock"),
            )
        )

    assert result["count"] == 1
    assert result["summary"].pop("languages_used") == {"English": 1}
    assert result["summary"] == {
        "documents_processed": 1,
        "entity_mentions_processed": 2,
        "entities_created": 2,
        "entities_reused": 0,
        "entities_suppressed": 0,
    }


def test_extract_entities_only_emits_per_document_workflow_changes(tmp_path: Path, monkeypatch):
    library_path, parent_doc_id, page_doc_ids = _seed_importable_pdf_library(tmp_path)
    events: list[tuple[str, dict]] = []

    async def fake_entities(**kwargs):
        del kwargs
        return _EntitiesOnly(
            people=[_EntityOnly(name="Ada Mock", aliases=[])],
            places=[_EntityOnly(name="Mockton", aliases=[])],
            organizations=[],
            dates=[],
            events=[],
        )

    def _spy_emit(library_path: str, **kwargs) -> None:
        events.append((library_path, kwargs))

    monkeypatch.setattr(
        "fichero_server.workflows.tools.extract_entities_only.chat_structured_with_fallback",
        fake_entities,
    )
    monkeypatch.setattr(
        "fichero_server.workflows.tools._workflow_change_emit.emit_change",
        _spy_emit,
    )

    result = asyncio.run(
        extract_entities_only(
            inputs={},
            state={
                "library_path": str(library_path),
                "selected_doc_ids": [parent_doc_id],
                "task_id": "extract-entities-emit-per-document",
            },
            llm_config=LLMConfig(provider="mock", model="mock"),
        )
    )

    assert result["count"] == 2
    # 2 docs × {entity.updated, claim.updated, document.updated} = 6 emits.
    assert len(events) == 6
    assert all(event[0] == str(library_path) for event in events)
    assert all(event[1]["actor"] == "workflow" for event in events)

    entity_events = [event[1] for event in events if event[1]["type"] == "entity.updated"]
    claim_events = [event[1] for event in events if event[1]["type"] == "claim.updated"]
    document_events = [event[1] for event in events if event[1]["type"] == "document.updated"]
    assert len(entity_events) == 2
    assert len(claim_events) == 2
    assert len(document_events) == 2
    assert all(event["entity_ids"] for event in entity_events)
    assert all(event["claim_ids"] == [] for event in claim_events)


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
