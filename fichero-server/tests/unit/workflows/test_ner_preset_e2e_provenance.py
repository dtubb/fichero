"""End-to-end proof that the two shipped NER presets actually extract
entities, and that what they land is traceable back to the run (#4379, #4369).

The existing broad smoke test
(``test_all_default_workflows_complete_with_deterministic_tool_stubs``) stubs
*every* tool in the graph, including the extraction tool itself — so it proves
the graph completes but proves nothing about extraction. The direct unit tests
(``test_extract_entities_only_workflow``) call the tool as a function and never
traverse the preset graph. Between them sits the gap #4379 fell into: run the
REAL preset graph with only the model call stubbed, and assert durable
outcomes.

Both presets are covered:
  * ``NER per-page (local)``  → files → aggregate → extract_all(persist_kg)
  * ``2 · Extract Entities``  → files → extract_entities_only

Asserted:
  * entity artifacts / KnowledgeEntity rows land in the seeded library,
  * artifacts carry the full #4313 provenance trio — ``run_id``,
    ``step_name``, ``sequence`` — so a run's output is attributable,
  * the run reports no error.

Nothing here skips. If a preset, tool, or fixture is missing the test FAILS
(#4365): a NER test that quietly skips is exactly how a broken NER surface
stays green.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from tests.integration._seedlib import seed
from tests.unit.workflows.test_default_workflow_e2e_harness import (
    FIXTURE_TEXT,
    _install_deterministic_workflow_stubs,
    _load_workflow_by_name,
)

from fichero_server.db import Database, db_manager
from fichero_server.models import Artifact, DocType, Document, FileType
from fichero_server.models.knowledge import KnowledgeEntity
from fichero_server.workflows.builder import build_graph

import fichero_server.workflows.tools  # noqa: F401
import fichero_server.workflows.tools.extract_all as extract_all_module
from fichero_server.workflows.runtime import build_initial_state

# Artifact types extract_all writes for the entity sections. These are the
# durable NER output — if extraction runs but writes none of these, the user
# got nothing.
ENTITY_ARTIFACT_TYPES = {"people", "places", "dates"}


def _seed_text_corpus(tmp_path: Path, name: str, pages: int = 2):
    """A folder of plain-text documents with real page_content.

    Both NER presets read text, not images: extract_all via the aggregate
    node, extract_entities_only via page_content / transcription artifacts.
    """
    library_path = tmp_path / f"{name}.fichero"
    seed(library_path)
    db = db_manager.get_database(library_path)

    folder = Document(id=f"{name}-folder", name=f"{name} folder", doc_type=DocType.folder)
    db.save(folder)

    doc_ids: list[str] = []
    for index in range(pages):
        source_file = tmp_path / f"{name}-{index + 1}.txt"
        source_file.write_text(FIXTURE_TEXT, encoding="utf-8")
        doc = Document(
            id=f"{name}-doc-{index + 1}",
            parent_id=folder.id,
            name=source_file.name,
            path=str(source_file),
            doc_type=DocType.file,
            file_type=FileType.text,
            page_content=FIXTURE_TEXT,
            metadata={"transcription": FIXTURE_TEXT},
        )
        db.save(doc)
        doc_ids.append(doc.id)

    return library_path, folder.id, doc_ids


def _run_preset(preset_name: str, library_path: Path, selected_doc_id: str, task_id: str):
    workflow = _load_workflow_by_name(preset_name)
    state = build_initial_state(
        {"selected_doc_ids": [selected_doc_id]},
        library_path=str(library_path),
    )
    state["workflow_id"] = workflow.id
    state["task_id"] = task_id
    final_state = asyncio.run(build_graph(workflow, skip_cache=True).ainvoke(state))
    assert not final_state.get("error"), (preset_name, final_state.get("error"))
    return workflow, final_state


def test_ner_per_page_local_lands_entity_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """The local NER preset must produce per-document entity artifacts."""
    _install_deterministic_workflow_stubs(monkeypatch)
    library_path, folder_id, doc_ids = _seed_text_corpus(tmp_path, "ner-local")
    db = db_manager.get_database(library_path)
    before_entities = len(db.all(KnowledgeEntity))

    run_id = "ner-local-run-1"
    workflow, final_state = _run_preset(
        "NER per-page (local)", library_path, folder_id, run_id
    )

    completed = set(final_state.get("completed_nodes") or [])
    assert {node.id for node in workflow.nodes} <= completed, (
        f"NER preset left nodes unrun: "
        f"{sorted({n.id for n in workflow.nodes} - completed)}"
    )

    run_artifacts = [a for a in db.all(Artifact) if a.run_id == run_id]
    landed_types = {a.artifact_type for a in run_artifacts}
    assert ENTITY_ARTIFACT_TYPES & landed_types, (
        f"NER run produced no entity artifacts (got {sorted(landed_types)})"
    )
    # persist_kg=true on the extract_all node: KG rows must land inline.
    assert len(db.all(KnowledgeEntity)) > before_entities, (
        "NER per-page declares persist_kg=true but wrote no KnowledgeEntity rows"
    )
    names = {entity.canonical_name for entity in db.all(KnowledgeEntity)}
    assert "Regression Person" in names, (
        f"extracted entity names did not reach the KG: {sorted(names)}"
    )


def test_ner_entity_artifacts_carry_the_full_provenance_trio(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """#4313 provenance trio — run_id AND step_name AND sequence.

    KNOWN FAILING against the current code (reported, not weakened).

    ``save_artifact`` in ``llm_base`` stamps all three: ``run_id`` from
    ``state["task_id"]``, ``step_name``/``workflow_id`` from the builder's
    node-context contextvar, and ``sequence`` from a per-run monotonic
    counter. ``extract_all`` does NOT go through ``save_artifact`` — it
    constructs ``Artifact(...)`` inline for every entity section and passes
    only ``run_id``. So every people/places/dates artifact a NER run
    produces has ``step_name=None``, ``workflow_id=None`` and
    ``sequence=None``.

    Consequence: NER output cannot be attributed to the node that produced
    it, and cannot be ordered within its run — which is exactly the
    forensics you need when a NER run dies mid-way (#4379) and you have to
    reconstruct how far it got. ``list_all_artifacts``'s run/step filter
    (covered by test_run_artifact_provenance) returns nothing for a NER run.

    The fix belongs in the product (lane-4379): route extract_all's entity
    artifacts through ``save_artifact``, or stamp the same three fields.
    """
    _install_deterministic_workflow_stubs(monkeypatch)
    library_path, folder_id, _doc_ids = _seed_text_corpus(tmp_path, "ner-provenance")
    db = db_manager.get_database(library_path)

    run_id = "ner-provenance-run-1"
    workflow, _final_state = _run_preset(
        "NER per-page (local)", library_path, folder_id, run_id
    )
    node_ids = {node.id for node in workflow.nodes}

    run_artifacts = [a for a in db.all(Artifact) if a.run_id == run_id]
    assert run_artifacts, "NER run wrote no artifacts at all"

    unattributed = sorted(
        {a.artifact_type for a in run_artifacts if a.step_name not in node_ids}
    )
    assert unattributed == [], (
        f"NER artifacts with no producing-node step_name: {unattributed} "
        f"(preset nodes: {sorted(node_ids)})"
    )

    unordered = sorted(
        {a.artifact_type for a in run_artifacts if not isinstance(a.sequence, int)}
    )
    assert unordered == [], (
        f"NER artifacts with no per-run sequence: {unordered} — a partial run "
        "cannot be replayed in order"
    )

    sequences = [a.sequence for a in run_artifacts]
    assert len(set(sequences)) == len(sequences), (
        f"sequence numbers repeat within one run: {sequences}"
    )


def test_catalogue_stage_2_extract_entities_persists_entities_through_the_graph(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """Stage 2 of the discrete catalogue pipeline, run as a real graph."""

    async def fake_entities_only(**kwargs):
        schema = kwargs.get("schema")
        if schema is not extract_all_module._EntitiesOnly:
            raise AssertionError(f"unexpected schema: {schema!r}")
        return extract_all_module._EntitiesOnly(
            people=[
                extract_all_module._EntityOnly(
                    name="Regression Person", entity_type="person"
                )
            ],
            places=[
                extract_all_module._EntityOnly(
                    name="Regression Place", entity_type="place"
                )
            ],
            organizations=[],
            dates=[],
            events=[],
        )

    monkeypatch.setattr(
        "fichero_server.llm.resolve_model_alias",
        lambda provider, model: ("fake", "fake-model"),
    )
    monkeypatch.setattr(
        "fichero_server.workflows.tools.extract_entities_only.chat_structured_with_fallback",
        fake_entities_only,
    )
    monkeypatch.setattr(Database, "embed", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        "fichero_server.knowledge.entity_vectors.find_similar", lambda *a, **k: []
    )
    monkeypatch.setattr(
        "fichero_server.knowledge.entity_vectors.index_entity", lambda *a, **k: None
    )

    library_path, folder_id, doc_ids = _seed_text_corpus(tmp_path, "ner-stage2")
    db = db_manager.get_database(library_path)
    before_entities = len(db.all(KnowledgeEntity))

    workflow, final_state = _run_preset(
        "2 · Extract Entities", library_path, folder_id, "ner-stage2-run-1"
    )

    extract_node_id = next(
        node.id for node in workflow.nodes if node.tool == "extract_entities_only"
    )
    summary = ((final_state.get("outputs") or {}).get(extract_node_id) or {}).get(
        "summary"
    ) or {}
    assert summary.get("documents_processed") == len(doc_ids), (
        f"stage-2 NER reported {summary.get('documents_processed')!r} documents "
        f"processed for {len(doc_ids)} seeded documents — silent under-processing"
    )
    assert summary.get("entities_created", 0) > 0, (
        f"stage-2 NER created no entities while reporting success: {summary}"
    )

    entities = db.all(KnowledgeEntity)
    assert len(entities) > before_entities
    names = {entity.canonical_name for entity in entities}
    assert {"Regression Person", "Regression Place"} <= names, (
        f"stage-2 NER did not persist the extracted names: {sorted(names)}"
    )
