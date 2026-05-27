"""End-to-end default workflow regression harness (#1287).

The point is not to unit-test individual tools. It is to run the shipped
default workflow JSON through the real graph runtime and assert durable
outcomes in the seeded library: artifacts plus KG rows. This catches the
#1285 class where the graph can appear to complete while the KG handoff is
empty or disconnected.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Literal

import pytest

from tests.integration._seedlib import seed

from fichero.db import Database, db_manager
from fichero.knowledge_models import KnowledgeClaim, KnowledgeEntity
from fichero.models import Artifact, DocType, Document, FileType, Workflow
from fichero.workflows.builder import build_graph
from fichero.workflows.default_workflows import _load_preset_files
from fichero.workflows.runtime import build_initial_state, to_workflow_def

# Import workflow tools for registry side effects before build_graph().
import fichero.workflows.tools  # noqa: F401
import fichero.workflows.tools.extract_all as extract_all_module


FIXTURE_TEXT = (
    "Regression Person signed the fixture deed in Regression Place in 1842."
)


@pytest.mark.parametrize("selection_shape", ["folder", "file"])
def test_catalogue_default_workflow_lands_artifacts_and_kg_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    selection_shape: Literal["folder", "file"],
):
    """Run the unmodified default Catalogue preset for folder and file shapes."""

    _install_deterministic_workflow_stubs(monkeypatch)
    library_path, selected_doc_id, source_doc_id, catalogue_target_id = _seed_fixture_library(
        tmp_path,
        selection_shape=selection_shape,
    )
    db = db_manager.get_database(library_path)

    before_claims = len(db.all(KnowledgeClaim))
    before_entities = len(db.all(KnowledgeEntity))

    workflow = _load_catalogue_workflow()
    state = build_initial_state(
        {"selected_doc_ids": [selected_doc_id]},
        library_path=str(library_path),
    )
    state["workflow_id"] = workflow.id
    state["task_id"] = f"test-{selection_shape}-catalogue"

    final_state = asyncio.run(build_graph(workflow, skip_cache=True).ainvoke(state))

    _assert_workflow_completed(final_state)
    _assert_artifacts_landed(
        db,
        catalogue_target_id=catalogue_target_id,
        source_doc_id=source_doc_id,
    )
    _assert_kg_rows_landed(
        db,
        source_doc_id=source_doc_id,
        before_entities=before_entities,
        before_claims=before_claims,
    )


def _install_deterministic_workflow_stubs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep CI deterministic while preserving workflow data flow."""

    def resolve_alias(provider: str, model: str) -> tuple[str, str]:
        if (provider or "").startswith("$"):
            return ("fake", "fake-model")
        return (provider, model)

    async def fake_extract_all_structured(**kwargs):
        schema = kwargs.get("schema")
        if schema is not extract_all_module._Extraction:
            raise AssertionError(f"unexpected structured schema: {schema!r}")
        return extract_all_module._Extraction(
            people=[
                extract_all_module._Person(
                    name="Regression Person",
                    verb="signed",
                    object="the fixture deed",
                    source_text="Regression Person signed the fixture deed",
                )
            ],
            places=[
                extract_all_module._Place(
                    name="Regression Place",
                    verb="hosted",
                    object="the fixture signing",
                    source_text="in Regression Place",
                )
            ],
            organizations=[],
            dates=[
                extract_all_module._DateItem(
                    date="1842",
                    date_normalized="1842",
                    verb="dated",
                    object="the fixture deed",
                    source_text="in 1842",
                )
            ],
            events=[],
            quotes=[],
            keywords=["regression fixture"],
        )

    async def fake_resumen(*args, **kwargs):
        return ("Catalogue narrative for the regression fixture.", [])

    async def fake_keywords(*args, **kwargs):
        return "regression fixture; workflow harness"

    monkeypatch.setattr("fichero.llm.resolve_model_alias", resolve_alias)
    monkeypatch.setattr(
        "fichero.workflows.tools.extract_all.chat_structured_with_fallback",
        fake_extract_all_structured,
    )
    monkeypatch.setattr(
        "fichero.workflows.tools.catalogue._generate_resumen",
        fake_resumen,
    )
    monkeypatch.setattr(
        "fichero.workflows.tools.catalogue._generate_keywords",
        fake_keywords,
    )
    monkeypatch.setattr(Database, "embed", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        "fichero.kg.entity_vectors.find_similar",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        "fichero.kg.entity_vectors.index_entity",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "fichero.kg.rebuild.rebuild_kg",
        lambda *args, **kwargs: {
            "entities": 0,
            "claims": 0,
            "triples_written": 0,
        },
    )


def _seed_fixture_library(
    tmp_path: Path,
    *,
    selection_shape: Literal["folder", "file"],
) -> tuple[Path, str, str, str]:
    library_path = tmp_path / f"{selection_shape}.fichero"
    seed(library_path)
    db = db_manager.get_database(library_path)

    source_file = tmp_path / f"{selection_shape}-fixture.txt"
    source_file.write_text(FIXTURE_TEXT, encoding="utf-8")

    folder = Document(
        id=f"workflow-{selection_shape}-folder",
        name=f"Workflow {selection_shape} fixture",
        doc_type=DocType.folder,
    )
    source_doc = Document(
        id=f"workflow-{selection_shape}-doc",
        parent_id=folder.id,
        name=source_file.name,
        path=str(source_file),
        doc_type=DocType.file,
        file_type=FileType.text,
    )
    db.save(folder)
    db.save(source_doc)

    selected_doc_id = folder.id if selection_shape == "folder" else source_doc.id
    return library_path, selected_doc_id, source_doc.id, folder.id


def _load_catalogue_workflow():
    preset = next(p for p in _load_preset_files() if p["name"] == "Catalogue")
    return to_workflow_def(
        Workflow(
            id="default-catalogue-regression-harness",
            name=preset["name"],
            description=preset.get("description", ""),
            nodes=preset["nodes"],
            edges=preset["edges"],
            config=preset.get("config", {}),
            folder_path=preset.get("folder_path", "/"),
        )
    )


def _assert_workflow_completed(final_state: dict) -> None:
    serialized = repr(final_state)
    assert final_state.get("error") in (None, ""), final_state.get("error")
    assert "No KG payload" not in serialized

    completed = set(final_state.get("completed_nodes") or [])
    assert {
        "files-source",
        "transcribe",
        "extract_all",
        "kg_writer",
        "catalogue",
    } <= completed

    extract_output = (final_state.get("outputs") or {}).get("extract_all") or {}
    assert extract_output.get("kg_payload"), "extract_all emitted no kg_payload"
    kg_output = (final_state.get("outputs") or {}).get("kg_writer") or {}
    assert kg_output.get("value"), "kg_writer received no payload"


def _assert_artifacts_landed(
    db,
    *,
    catalogue_target_id: str,
    source_doc_id: str,
) -> None:
    source_artifacts = db.query(Artifact, document_id=source_doc_id)
    assert any(a.artifact_type == "transcription" for a in source_artifacts)
    assert any(a.artifact_type == "people" for a in source_artifacts)

    target_artifacts = db.query(Artifact, document_id=catalogue_target_id)
    assert any(a.artifact_type == "catalogue.narrative" for a in target_artifacts)

    source_doc = db.get(Document, source_doc_id)
    assert source_doc is not None
    assert source_doc.page_content == FIXTURE_TEXT

    target_doc = db.get(Document, catalogue_target_id)
    assert target_doc is not None
    assert target_doc.page_content == "Catalogue narrative for the regression fixture."


def _assert_kg_rows_landed(
    db,
    *,
    source_doc_id: str,
    before_entities: int,
    before_claims: int,
) -> None:
    entities = db.all(KnowledgeEntity)
    claims = db.all(KnowledgeClaim)
    assert len(entities) > before_entities
    assert len(claims) > before_claims

    names = {entity.canonical_name for entity in entities}
    assert {"Regression Person", "Regression Place", "regression fixture"} <= names

    fixture_claims = db.query(KnowledgeClaim, source_document_id=source_doc_id)
    claim_texts = {claim.text for claim in fixture_claims}
    assert "Regression Person signed the fixture deed." in claim_texts
    assert any(claim.entity_ids for claim in fixture_claims)
