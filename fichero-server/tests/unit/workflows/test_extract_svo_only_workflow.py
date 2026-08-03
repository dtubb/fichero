from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

from tests.integration._seedlib import seed

from fichero_server.db import db_manager
from fichero_server.models.knowledge import EntityType, KnowledgeClaim
from fichero_server.models import Artifact, DocType, Document, FileType, Workflow
from fichero_server.workflows.builder import build_graph
from fichero_server.workflows.default_workflows import _load_preset_files
from fichero_server.workflows.runtime import build_initial_state, to_workflow_def
from fichero_server.workflows.tools._entity_writer import upsert_entity

import fichero_server.workflows.tools  # noqa: F401


FIXTURE_TEXT = "Ada signed the ledger in Mockton."


def test_extract_svo_preset_persists_claims_and_is_idempotent(tmp_path: Path):
    library_path, parent_doc_id, page_doc_ids = _seed_extractable_library(tmp_path)
    db = db_manager.get_database(library_path)
    workflow = _load_workflow("3 · Extract SVO → Claims", provider_name="mock")

    async def fake_extract_claims_for_entity(
        chunk_text: str,
        entity_name: str,
        entity_type: str,
        llm_config,
        instructions: str,
        extraction_sem,
    ) -> list[dict]:
        del entity_type, llm_config, instructions, extraction_sem
        assert FIXTURE_TEXT in chunk_text
        if entity_name == "Ada Mock":
            return [{
                "name": entity_name,
                "verb": "signed",
                "object": "the ledger",
                "source_text": FIXTURE_TEXT,
                "epistemic_status": "confirmed",
                "claim_type": "fact",
            }]
        if entity_name == "Mockton":
            return [{
                "name": entity_name,
                "verb": "is",
                "object": "the town where Ada signed the ledger",
                "source_text": FIXTURE_TEXT,
                "epistemic_status": "confirmed",
                "claim_type": "fact",
            }]
        return []

    with patch(
        "fichero_server.workflows.tools.extract_svo_only._extract_claims_for_entity",
        new=fake_extract_claims_for_entity,
    ):
        first = asyncio.run(
            build_graph(workflow, skip_cache=True).ainvoke(
                _workflow_state(library_path, parent_doc_id, task_id="extract-svo-first")
            )
        )
        assert not first.get("error")
        first_summary = first["outputs"]["extract-svo"]["summary"]
        # #2092: the run reports which language each document was extracted in.
        assert first_summary.pop("languages_used") == {"English": 2}
        assert first_summary == {
            "documents_processed": 2,
            "entities_processed": 4,
            "claims_extracted": 4,
            "claims_created": 4,
            "claims_reused": 0,
        }

        second = asyncio.run(
            build_graph(workflow, skip_cache=True).ainvoke(
                _workflow_state(library_path, parent_doc_id, task_id="extract-svo-second")
            )
        )
        assert not second.get("error")
        second_summary = second["outputs"]["extract-svo"]["summary"]
        assert second_summary.pop("languages_used") == {"English": 2}
        assert second_summary == {
            "documents_processed": 2,
            "entities_processed": 4,
            "claims_extracted": 4,
            "claims_created": 0,
            "claims_reused": 4,
        }

    claims = [
        claim
        for claim in db.query(KnowledgeClaim)
        if claim.source_document_id in set(page_doc_ids)
    ]
    assert len(claims) == 4
    assert {claim.subject_canonical for claim in claims} == {"Ada Mock", "Mockton"}
    assert {claim.predicate_verb for claim in claims} == {"signed", "is"}
    assert all(claim.source_page_label in {"001", "002"} for claim in claims)

    transcription_artifacts = [
        artifact
        for artifact in db.query(Artifact)
        if artifact.document_id in set(page_doc_ids)
        and artifact.artifact_type == "transcription"
    ]
    assert len(transcription_artifacts) == 2


def _seed_extractable_library(tmp_path: Path) -> tuple[Path, str, list[str]]:
    library_path = tmp_path / "extract-svo-stage.fichero"
    seed(library_path)
    db = db_manager.get_database(library_path)

    source_file = tmp_path / "marshall-imported.pdf"
    source_file.write_bytes(b"%PDF-1.4\n% extract svo fixture\n")

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
            page_content="",
            metadata={
                "canonical_external_id": "marshall-import-root__page_001",
                "page_label": "001",
                "page_number": 1,
                "transcription": "",
                "images": [{"role": "enhanced"}],
            },
        ),
        Document(
            id="marshall-import-page-2",
            parent_id=parent_doc.id,
            name="Marshall import page 2",
            doc_type=DocType.page,
            sequence=2,
            page_content="",
            metadata={
                "canonical_external_id": "marshall-import-root__page_002",
                "page_label": "002",
                "page_number": 2,
                "transcription": "",
                "images": [{"role": "enhanced"}],
            },
        ),
    ]
    db.save(parent_doc)
    for page in pages:
        db.save(page)
        db.save(
            Artifact(
                document_id=page.id,
                artifact_type="transcription",
                content=FIXTURE_TEXT,
                data={"source": "manifest-import"},
                provider="manifest-importer",
                model="fixture",
                step_name="import_artifacts",
                confidence=1.0,
            )
        )
        upsert_entity(
            db,
            canonical_name="Ada Mock",
            entity_type=EntityType.person,
            source_document_id=page.id,
        )
        upsert_entity(
            db,
            canonical_name="Mockton",
            entity_type=EntityType.location,
            source_document_id=page.id,
        )

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
    state["workflow_id"] = "default-extract-svo-regression-harness"
    state["task_id"] = task_id
    return state
