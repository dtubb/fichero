from __future__ import annotations

import asyncio
from pathlib import Path

from tests.integration._seedlib import seed

from fichero_server.db import db_manager
from fichero_server.models.knowledge import (
    ClaimCurationState,
    ClaimSuppressionRule,
    ClaimSuppressionRuleAction,
    EntityResolutionRule,
    EntityResolutionRuleType,
    EntityType,
    KnowledgeClaim,
    KnowledgeEntity,
)
from fichero_server.models import DocType, Document, FileType, Workflow
from fichero_server.workflows.builder import build_graph
from fichero_server.workflows.default_workflows import _load_preset_files
from fichero_server.workflows.runtime import build_initial_state, to_workflow_def

import fichero_server.workflows.tools  # noqa: F401


def test_merge_dedup_preset_applies_rules_and_is_idempotent(tmp_path: Path):
    library_path, parent_doc_id = _seed_merge_dedup_library(tmp_path)
    db = db_manager.get_database(library_path)
    workflow = _load_workflow("4 · Merge / Dedup")

    first = asyncio.run(
        build_graph(workflow, skip_cache=True).ainvoke(
            _workflow_state(library_path, parent_doc_id, task_id="merge-dedup-first")
        )
    )
    assert not first.get("error")
    first_summary = first["outputs"]["merge-dedup"]["summary"]
    assert first_summary == {
        "documents_scoped": 2,
        "entities_examined": 2,
        "entities_merged": 1,
        "entities_reclassified": 0,
        "entities_suppressed": 0,
        "claims_examined": 4,
        "claims_suppressed": 1,
        "claims_pruned_trivial": 1,
        "claim_merges": 1,
        # #4415 curation-survival counters: nothing here was curated by a
        # person, so a re-run is free to act and preserves nothing.
        "entities_curated_preserved": 0,
        "claims_curated_preserved": 0,
        "conflicts_recorded": 0,
        "conflicts_cleared": 0,
    }

    second = asyncio.run(
        build_graph(workflow, skip_cache=True).ainvoke(
            _workflow_state(library_path, parent_doc_id, task_id="merge-dedup-second")
        )
    )
    assert not second.get("error")
    second_summary = second["outputs"]["merge-dedup"]["summary"]
    assert second_summary == {
        "documents_scoped": 2,
        "entities_examined": 1,
        "entities_merged": 0,
        "entities_reclassified": 0,
        "entities_suppressed": 0,
        "claims_examined": 3,
        "claims_suppressed": 0,
        "claims_pruned_trivial": 0,
        "claim_merges": 0,
        # #4415 curation-survival counters: nothing here was curated by a
        # person, so a re-run is free to act and preserves nothing.
        "entities_curated_preserved": 0,
        "claims_curated_preserved": 0,
        "conflicts_recorded": 0,
        "conflicts_cleared": 0,
    }

    canonical = db.get(KnowledgeEntity, "ent-john")
    absorbed = db.get(KnowledgeEntity, "ent-jd")
    assert canonical is not None
    assert absorbed is not None
    assert absorbed.merged_into_id == canonical.id
    assert "J. Davidson" in canonical.aliases

    source_claim = db.get(KnowledgeClaim, "claim-jd")
    survivor_claim = db.get(KnowledgeClaim, "claim-john")
    assert source_claim is not None
    assert survivor_claim is not None
    assert source_claim.merged_into_id == survivor_claim.id
    assert source_claim.curation_state == ClaimCurationState.rejected
    assert canonical.id in survivor_claim.entity_ids

    disabled_claim = db.get(KnowledgeClaim, "claim-disable")
    assert disabled_claim is not None
    assert disabled_claim.curation_state == ClaimCurationState.rejected
    assert disabled_claim.confidence == 0.7

    trivial_claim = db.get(KnowledgeClaim, "claim-trivial")
    assert trivial_claim is not None
    assert trivial_claim.curation_state == ClaimCurationState.rejected
    assert trivial_claim.confidence == 0.2


def _seed_merge_dedup_library(tmp_path: Path) -> tuple[Path, str]:
    library_path = tmp_path / "merge-dedup-stage.fichero"
    seed(library_path)
    db = db_manager.get_database(library_path)

    source_file = tmp_path / "marshall-merge.pdf"
    source_file.write_bytes(b"%PDF-1.4\n% merge dedup fixture\n")

    parent_doc = Document(
        id="marshall-merge-root",
        name="Marshall merge root",
        path=str(source_file),
        doc_type=DocType.file,
        file_type=FileType.pdf,
        metadata={"canonical_external_id": "marshall-merge-root"},
    )
    page_1 = Document(
        id="marshall-merge-page-1",
        parent_id=parent_doc.id,
        name="Marshall merge page 1",
        doc_type=DocType.page,
        sequence=1,
        metadata={"page_label": "001"},
    )
    page_2 = Document(
        id="marshall-merge-page-2",
        parent_id=parent_doc.id,
        name="Marshall merge page 2",
        doc_type=DocType.page,
        sequence=2,
        metadata={"page_label": "002"},
    )
    db.save(parent_doc)
    db.save(page_1)
    db.save(page_2)

    db.save(
        EntityResolutionRule(
            rule_type=EntityResolutionRuleType.alias,
            match_canonical_name="J. Davidson",
            match_entity_type=EntityType.person,
            target_canonical_name="John Davidson",
            target_entity_type=EntityType.person,
            reason="Same person",
        )
    )
    db.save(
        ClaimSuppressionRule(
            action=ClaimSuppressionRuleAction.disable,
            match_subject_name="Pedro",
            match_predicate_verb="said",
            reason="Known bad extraction",
        )
    )

    db.save(
        KnowledgeEntity(
            id="ent-john",
            canonical_name="John Davidson",
            entity_type=EntityType.person,
            source_document_ids=[page_1.id],
        )
    )
    db.save(
        KnowledgeEntity(
            id="ent-jd",
            canonical_name="J. Davidson",
            entity_type=EntityType.person,
            source_document_ids=[page_2.id],
        )
    )

    db.save(
        KnowledgeClaim(
            id="claim-john",
            text="John Davidson signed the ledger.",
            source_document_id=page_1.id,
            source_page_label="001",
            subject_canonical="John Davidson",
            predicate_verb="signed",
            object_phrase="the ledger",
            entity_ids=["ent-john"],
            confidence=0.8,
        )
    )
    db.save(
        KnowledgeClaim(
            id="claim-jd",
            text="J. Davidson signed the ledger.",
            source_document_id=page_1.id,
            source_page_label="001",
            subject_canonical="John Davidson",
            predicate_verb="signed",
            object_phrase="the ledger",
            entity_ids=["ent-jd"],
            confidence=0.8,
        )
    )
    db.save(
        KnowledgeClaim(
            id="claim-disable",
            text="Pedro said the deed was false.",
            source_document_id=page_2.id,
            source_page_label="002",
            subject_canonical="Pedro",
            predicate_verb="said",
            object_phrase="the deed was false",
            confidence=0.7,
        )
    )
    db.save(
        KnowledgeClaim(
            id="claim-trivial",
            text="Andagoya is a place.",
            source_document_id=page_2.id,
            source_page_label="002",
            subject_canonical="Andagoya",
            predicate_verb="is",
            object_phrase="a place",
            confidence=0.9,
            predicate_canonical="is_a",
        )
    )

    return library_path, parent_doc.id


def _load_workflow(name: str):
    preset = next(p for p in _load_preset_files() if p["name"] == name)
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
    state["workflow_id"] = "default-merge-dedup-regression-harness"
    state["task_id"] = task_id
    return state
