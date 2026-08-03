"""A re-run of Merge / Dedup must not regenerate over the user's corrections (#4415).

Re-running the catalogue used to redo every stage, and the extraction stages
wrote straight over hand-merged entities and hand-corrected claims. Entity
merges and corrected claims are durable statements that the extractor got
something wrong; regenerating over them destroys the human judgement that is
the most valuable data in the library.

The contract these tests pin, borrowed from #3322 step 5b:

- the stage still RUNS on curated rows — it may compute, it may not overwrite;
- the disagreement is RECORDED with the tool's full proposal, so neither the
  user's value nor the tool's candidate is silently discarded;
- an already-recorded disagreement is not rewritten on the next run, so a
  settled row is genuinely skipped rather than churned.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from fichero_server.db import db_manager
from fichero_server.models.knowledge import (
    ClaimCurationState,
    ClaimMergeAudit,
    ClaimMergeOperationType,
    EntityCurationState,
    EntityMergeAudit,
    EntityMergeOperationType,
    KnowledgeClaim,
    KnowledgeEntity,
    MutationLog,
    MutationOperationType,
)
from fichero_server.workflows.builder import build_graph
from fichero_server.workflows.curation_guard import (
    CURATION_KEY,
    CONFLICT_KEY,
    CurationSource,
    read_curation,
)

import fichero_server.workflows.tools  # noqa: F401

from tests.unit.workflows.test_merge_dedup_only_workflow import (
    _load_workflow,
    _seed_merge_dedup_library,
    _workflow_state,
)


def _run(library_path: Path, parent_doc_id: str, *, task_id: str) -> dict:
    workflow = _load_workflow("4 · Merge / Dedup")
    result = asyncio.run(
        build_graph(workflow, skip_cache=True).ainvoke(
            _workflow_state(library_path, parent_doc_id, task_id=task_id)
        )
    )
    assert not result.get("error")
    return result["outputs"]["merge-dedup"]["summary"]


def _curate(db, *, row_id: str, kind: str, actor: str = "dtubb") -> None:
    """Record that a person touched this row, the way a human route does."""
    db.save(
        MutationLog(
            entity_type=kind,
            entity_id=row_id,
            operation=MutationOperationType.update,
            created_by=actor,
        )
    )


def test_hand_corrected_claim_survives_a_rerun(tmp_path: Path):
    """The suppression rule wants this claim rejected; the user curated it.

    The user wins, and the run says so. Without the guard the rule rewrites
    curation_state to rejected and the correction is gone — silently, which is
    worse than the original bad extraction because the user believes they
    fixed it.
    """
    library_path, parent_doc_id = _seed_merge_dedup_library(tmp_path)
    db = db_manager.get_database(library_path)

    claim = db.get(KnowledgeClaim, "claim-disable")
    claim.curation_state = ClaimCurationState.curated
    claim.confidence = 0.7
    db.save(claim)
    _curate(db, row_id="claim-disable", kind="KnowledgeClaim")

    summary = _run(library_path, parent_doc_id, task_id="curation-claim")

    after = db.get(KnowledgeClaim, "claim-disable")
    assert after.curation_state == ClaimCurationState.curated, (
        "the claim-suppression rule overwrote a user-curated claim"
    )
    assert after.confidence == 0.7
    assert summary["claims_curated_preserved"] >= 1
    assert summary["claims_suppressed"] == 0


def test_hand_merged_entity_survives_a_rerun(tmp_path: Path):
    """A curator's merge decision outranks the resolution rule on re-run.

    'J. Davidson' is kept as its own entity by hand. The alias rule says to
    fold it into 'John Davidson'. The rule may not undo the human's call.
    """
    library_path, parent_doc_id = _seed_merge_dedup_library(tmp_path)
    db = db_manager.get_database(library_path)

    entity = db.get(KnowledgeEntity, "ent-jd")
    entity.curation_state = EntityCurationState.verified
    db.save(entity)
    db.save(
        EntityMergeAudit(
            operation_type=EntityMergeOperationType.merge,
            source_entity_ids=["ent-jd"],
            target_entity_id="ent-jd",
            created_by="dtubb",
        )
    )

    summary = _run(library_path, parent_doc_id, task_id="curation-entity")

    after = db.get(KnowledgeEntity, "ent-jd")
    assert after.merged_into_id is None, "a hand-curated entity was absorbed by a re-run"
    assert after.curation_state == EntityCurationState.verified
    assert summary["entities_merged"] == 0
    assert summary["entities_curated_preserved"] >= 1


def test_disagreement_is_recorded_not_silently_resolved(tmp_path: Path):
    """Both values survive: the user's stands, the tool's is kept beside it.

    Silently keeping the user's value would hide that an improved extractor
    now disagrees; silently taking the tool's would destroy the correction.
    The run records the proposal and reports the conflict so it can be decided.
    """
    library_path, parent_doc_id = _seed_merge_dedup_library(tmp_path)
    db = db_manager.get_database(library_path)

    claim = db.get(KnowledgeClaim, "claim-disable")
    claim.curation_state = ClaimCurationState.curated
    db.save(claim)
    _curate(db, row_id="claim-disable", kind="KnowledgeClaim")

    summary = _run(library_path, parent_doc_id, task_id="conflict-first")
    assert summary["conflicts_recorded"] >= 1

    after = db.get(KnowledgeClaim, "claim-disable")
    conflict = after.metadata[CURATION_KEY][CONFLICT_KEY]

    # The tool's candidate is preserved in full, with why it wanted it.
    assert conflict["proposal"]["curation_state"] == ClaimCurationState.rejected.value
    assert "suppression" in conflict["reason"]
    assert conflict["found_at"]

    # …and the user's value is untouched beside it.
    assert after.curation_state == ClaimCurationState.curated
    assert read_curation(after).source is CurationSource.user


def test_a_settled_conflict_is_not_rewritten_on_the_next_run(tmp_path: Path):
    """Second run over settled rows changes nothing — the skip is real.

    If re-recording the same disagreement bumped `updated_at`, every run would
    look like it did work, and "already complete" would be unobservable.
    """
    library_path, parent_doc_id = _seed_merge_dedup_library(tmp_path)
    db = db_manager.get_database(library_path)

    claim = db.get(KnowledgeClaim, "claim-disable")
    claim.curation_state = ClaimCurationState.curated
    db.save(claim)
    _curate(db, row_id="claim-disable", kind="KnowledgeClaim")

    _run(library_path, parent_doc_id, task_id="settle-first")
    settled = db.get(KnowledgeClaim, "claim-disable")
    stamped_at = settled.updated_at
    conflict_at = settled.metadata[CURATION_KEY][CONFLICT_KEY]["found_at"]

    _run(library_path, parent_doc_id, task_id="settle-second")

    again = db.get(KnowledgeClaim, "claim-disable")
    assert again.updated_at == stamped_at, "a settled curated row was written again"
    assert again.metadata[CURATION_KEY][CONFLICT_KEY]["found_at"] == conflict_at
    assert again.curation_state == ClaimCurationState.curated


def test_the_tools_own_merge_is_not_mistaken_for_curation(tmp_path: Path):
    """A workflow-actor audit row must not protect the row it describes.

    `merge_dedup_only` drives the merge ROUTES, which write merge audits. Those
    audits used to hardcode created_by="human", so the tool's own output read
    back as a user's correction — after one run the stage would refuse to touch
    anything it had itself produced and would report it as curated.
    """
    library_path, parent_doc_id = _seed_merge_dedup_library(tmp_path)
    db = db_manager.get_database(library_path)

    db.save(
        ClaimMergeAudit(
            operation_type=ClaimMergeOperationType.merge,
            source_claim_ids=["claim-disable"],
            target_claim_id="claim-disable",
            created_by="workflow",
        )
    )

    summary = _run(library_path, parent_doc_id, task_id="machine-actor")

    after = db.get(KnowledgeClaim, "claim-disable")
    assert after.curation_state == ClaimCurationState.rejected, (
        "a workflow-written audit row was treated as a user correction"
    )
    assert summary["claims_suppressed"] == 1
    assert summary["claims_curated_preserved"] == 0
