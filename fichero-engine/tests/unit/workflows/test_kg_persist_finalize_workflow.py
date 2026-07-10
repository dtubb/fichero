from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

from tests.integration._seedlib import seed

from fichero.db import Database, db_manager
from fichero.knowledge_models import EntityType, KnowledgeClaim, KnowledgeEntity
from fichero.models import Artifact, DocType, Document, FileType, Workflow
from fichero.workflows.builder import build_graph
from fichero.workflows.default_workflows import _load_preset_files
from fichero.workflows.runtime import build_initial_state, to_workflow_def
from fichero.workflows.tools._entity_writer import upsert_entity
from fichero.workflows.tools.extract_all import _EntitiesOnly, _EntityOnly

import fichero.workflows.tools  # noqa: F401


FIXTURE_TEXT = "Ada signed the ledger in Mockton."
EMBED_DIM = 1024


def test_kg_persist_finalize_preset_recomputes_and_is_idempotent(tmp_path: Path):
    library_path, parent_doc_id, page_doc_ids = _seed_finalize_library(tmp_path)
    db = db_manager.get_database(library_path)
    workflow = _load_workflow("5 · KG Persist / Finalize")
    entity_total = len(db.query(KnowledgeEntity))
    claim_total = len(db.query(KnowledgeClaim))

    with patch.object(
        Database,
        "_embed_texts",
        side_effect=lambda texts: [[1.0] + ([0.0] * (EMBED_DIM - 1)) for _ in texts],
    ):
        first = asyncio.run(
            build_graph(workflow, skip_cache=True).ainvoke(
                _workflow_state(library_path, parent_doc_id, task_id="kg-finalize-first")
            )
        )
        assert not first.get("error")
        first_summary = first["outputs"]["kg-persist-finalize"]["summary"]
        assert first_summary["documents_scoped"] == 2
        assert first_summary["entities_total"] == entity_total
        assert first_summary["claims_total"] == claim_total
        assert first_summary["claims_updated"] >= 0
        assert 0 <= first_summary["entity_vectors_indexed"] <= entity_total
        assert 0 <= first_summary["claim_vectors_indexed"] <= claim_total
        assert first_summary["triples_written"] > 0

        second = asyncio.run(
            build_graph(workflow, skip_cache=True).ainvoke(
                _workflow_state(library_path, parent_doc_id, task_id="kg-finalize-second")
            )
        )
        assert not second.get("error")
        second_summary = second["outputs"]["kg-persist-finalize"]["summary"]
        assert second_summary == {
            "documents_scoped": 2,
            "entities_total": entity_total,
            "claims_total": claim_total,
            "claims_updated": 0,
            "entity_vectors_indexed": 0,
            "claim_vectors_indexed": 0,
            "triples_written": 0,
        }

    claims = [
        db.get(KnowledgeClaim, claim_id)
        for claim_id in ("claim-ada-page-1", "claim-ada-page-2")
    ]
    assert all(claim is not None for claim in claims)
    assert all(claim.corroboration_count == 2 for claim in claims)
    assert all(claim.weighted_corroboration_count == 2.0 for claim in claims)
    assert all(sorted(claim.corroborating_source_ids) == sorted(page_doc_ids) for claim in claims)

    assert "kg_entity_embeddings" in db._lance_tables()
    assert "kg_claim_embeddings" in db._lance_tables()
    assert db.lance.open_table("kg_entity_embeddings").count_rows() == 2
    assert db.lance.open_table("kg_claim_embeddings").count_rows() == 2
    assert (Path(db.path).parent / "kg.nt").exists()


def test_catalogue_full_pipeline_runs_1_to_5(tmp_path: Path):
    library_path, parent_doc_id, page_doc_ids = _seed_full_pipeline_library(tmp_path)
    db = db_manager.get_database(library_path)
    workflow = _load_workflow("Catalogue", provider_name="mock")

    async def fake_entities(*args, **kwargs):
        del args, kwargs
        return _EntitiesOnly(
            people=[_EntityOnly(name="Ada Mock", aliases=[], entity_type="person")],
            places=[_EntityOnly(name="Mockton", aliases=[], entity_type="place")],
            organizations=[],
            events=[],
        )

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

    with (
        patch.object(
            Database,
            "_embed_texts",
            side_effect=lambda texts: [[1.0] + ([0.0] * (EMBED_DIM - 1)) for _ in texts],
        ),
        patch(
            "fichero.workflows.tools.extract_entities_only.chat_structured_with_fallback",
            new=fake_entities,
        ),
        patch(
            "fichero.workflows.tools.extract_svo_only._extract_claims_for_entity",
            new=fake_extract_claims_for_entity,
        ),
    ):
        result = asyncio.run(
            build_graph(workflow, skip_cache=True).ainvoke(
                _workflow_state(library_path, parent_doc_id, task_id="catalogue-full-pipeline")
            )
        )

    assert not result.get("error")
    outputs = result["outputs"]
    assert outputs["import-artifacts"]["summary"]["artifacts_created"] == 4
    assert outputs["extract-entities"]["summary"]["entities_created"] == 2
    assert outputs["extract-svo"]["summary"]["claims_created"] == 4
    assert outputs["merge-dedup"]["summary"]["claims_examined"] == 4
    assert outputs["kg-persist-finalize"]["summary"]["claims_updated"] == 2

    artifacts = [
        artifact
        for artifact in db.query(Artifact)
        if artifact.document_id in set(page_doc_ids)
        and artifact.artifact_type in {"import_receipt", "transcription"}
    ]
    assert len(artifacts) == 4

    entities = [
        entity
        for entity in db.query(KnowledgeEntity)
        if entity.canonical_name in {"Ada Mock", "Mockton"}
    ]
    assert len(entities) == 2

    claims = [claim for claim in db.query(KnowledgeClaim) if claim.source_document_id in set(page_doc_ids)]
    assert len(claims) == 4
    ada_claims = [claim for claim in claims if claim.subject_canonical == "Ada Mock"]
    assert len(ada_claims) == 2
    assert all(claim.corroboration_count == 2 for claim in ada_claims)
    assert "kg_entity_embeddings" in db._lance_tables()
    assert "kg_claim_embeddings" in db._lance_tables()


def _seed_finalize_library(tmp_path: Path) -> tuple[Path, str, list[str]]:
    library_path = tmp_path / "kg-finalize-stage.fichero"
    db = db_manager.get_database(library_path)

    source_file = tmp_path / "marshall-imported.pdf"
    source_file.write_bytes(b"%PDF-1.4\n% kg finalize fixture\n")

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
            metadata={"page_label": "001"},
        ),
        Document(
            id="marshall-import-page-2",
            parent_id=parent_doc.id,
            name="Marshall import page 2",
            doc_type=DocType.page,
            sequence=2,
            metadata={"page_label": "002"},
        ),
    ]
    db.save(parent_doc)
    for page in pages:
        db.save(page)

    ada_id = upsert_entity(
        db,
        canonical_name="Ada Mock",
        entity_type=EntityType.person,
        source_document_id=pages[0].id,
    )
    upsert_entity(
        db,
        canonical_name="Ada Mock",
        entity_type=EntityType.person,
        source_document_id=pages[1].id,
    )
    upsert_entity(
        db,
        canonical_name="Mockton",
        entity_type=EntityType.location,
        source_document_id=pages[0].id,
    )

    db.save(
        KnowledgeClaim(
            id="claim-ada-page-1",
            text="Ada signed the ledger.",
            source_document_id=pages[0].id,
            source_page_label="001",
            subject_canonical="Ada Mock",
            predicate_verb="signed",
            object_phrase="the ledger",
            source_excerpt="Ada signed the ledger.",
            entity_ids=[ada_id],
            metadata={"verb": "signed", "object": "the ledger"},
        )
    )
    db.save(
        KnowledgeClaim(
            id="claim-ada-page-2",
            text="Ada signed the ledger.",
            source_document_id=pages[1].id,
            source_page_label="002",
            subject_canonical="Ada Mock",
            predicate_verb="signed",
            object_phrase="the ledger",
            source_excerpt="Ada signed the ledger.",
            entity_ids=[ada_id],
            metadata={"verb": "signed", "object": "the ledger"},
        )
    )

    return library_path, parent_doc.id, [page.id for page in pages]


def _seed_full_pipeline_library(tmp_path: Path) -> tuple[Path, str, list[str]]:
    library_path = tmp_path / "catalogue-full-pipeline-stage.fichero"
    seed(library_path)
    db = db_manager.get_database(library_path)

    source_file = tmp_path / "marshall-imported.pdf"
    source_file.write_bytes(b"%PDF-1.4\n% full pipeline fixture\n")

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
    state["workflow_id"] = "default-kg-persist-finalize-regression-harness"
    state["task_id"] = task_id
    return state
