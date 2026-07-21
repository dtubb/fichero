"""Review Queue API Routes

Claim review workflow endpoints for managing curation state transitions.
Provides queue views and batch transition operations.
"""

from __future__ import annotations

import logging
from copy import deepcopy
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator

from fichero.api.auth import action_context
from fichero.api.main import get_library_database, get_library_database_for_write
from fichero.db import Database
from fichero.kg._common import is_trivial_claim
from fichero.knowledge_models import (
    ClaimCurationState,
    ClaimMergeAudit,
    ClaimMergeOperationType,
    ClaimRelationType,
    ClaimSuppressionRule,
    ClaimSuppressionRuleAction,
    KnowledgeClaim,
    KnowledgeClaimLink,
    KnowledgeEntity,
    MutationLog,
    MutationOperationType,
)
from fichero.models import DocType, Document

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/claims", tags=["review-queue"])
kg_claims_router = APIRouter(
    prefix="/kg/claims", tags=["knowledge-graph", "claim-curation"]
)


# =============================================================================
# Request/Response Models
# =============================================================================


class ClaimTransitionRequest(BaseModel):
    """Request to transition a claim's curation state."""

    to_state: str = Field(
        ...,
        description="Target curation state: unreviewed, shortlisted, curated, rejected",
    )
    reason: str | None = Field(None, description="Optional reason for transition")
    reviewed_by: str = Field(default="human", description="Who performed the review")


class BatchClaimTransitionRequest(BaseModel):
    """Request to transition multiple claims."""

    claim_ids: list[str] = Field(
        ..., description="List of claim IDs to transition", min_length=1
    )
    to_state: str = Field(..., description="Target curation state")
    reason: str | None = Field(None, description="Optional reason for transition")
    reviewed_by: str = Field(default="human", description="Who performed the review")


class ClaimTransitionResponse(BaseModel):
    """Response from claim transition operation."""

    claim_id: str
    success: bool
    from_state: str
    to_state: str
    transitioned_at: str
    error: str | None = None


class BatchClaimTransitionResponse(BaseModel):
    """Response from batch claim transition operation."""

    results: list[ClaimTransitionResponse]
    total: int
    succeeded: int
    failed: int


class BatchClaimCurationRequest(BaseModel):
    claim_ids: list[str] = Field(min_length=1, description="Claim IDs to update.")
    curation_state: ClaimCurationState = Field(
        description="New curation state for every listed claim."
    )


class BatchClaimCurationResponse(BaseModel):
    updated: int
    claim_ids: list[str] = Field(
        default_factory=list, description="Claim IDs whose state actually changed."
    )


class ClaimMergeRequest(BaseModel):
    surviving_claim_id: str = Field(
        description="Claim that remains canonical after the merge."
    )
    absorbed_claim_ids: list[str] = Field(
        min_length=1,
        description="Duplicate claims absorbed into the survivor.",
    )


class ClaimUnmergeRequest(BaseModel):
    audit_id: str = Field(
        description="ClaimMergeAudit.id from the merge being reversed."
    )


class ClaimAuditResponse(BaseModel):
    id: str
    operation_type: ClaimMergeOperationType
    source_claim_ids: list[str]
    target_claim_id: str
    merge_details: dict[str, Any] = Field(default_factory=dict)
    reversal_id: str | None
    created_by: str
    created_at: datetime


class PruneTrivialClaimsRequest(BaseModel):
    document_id: str | None = Field(
        default=None,
        description="Single document/page scope. Only claims directly attached to this document are checked.",
    )
    folder_id: str | None = Field(
        default=None,
        description="Folder scope. The folder and every descendant document are checked.",
    )
    library_wide: bool = Field(
        default=False,
        description="When true, scan the whole library and persist a global trivial-copula suppression rule.",
    )
    reason: str = Field(
        default="Prune trivial is-a copula claims",
        description="Audit note stored on any generated suppression rule.",
    )
    created_by: str = Field(
        default="human",
        description="Actor recorded on any generated suppression rule.",
    )

    @model_validator(mode="after")
    def _validate_scope(self) -> "PruneTrivialClaimsRequest":
        scopes = (
            int(bool(self.document_id))
            + int(bool(self.folder_id))
            + int(self.library_wide)
        )
        if scopes != 1:
            raise ValueError(
                "Exactly one of document_id, folder_id, or library_wide=true is required"
            )
        return self


class PruneTrivialClaimsResponse(BaseModel):
    scope_type: str
    scope_document_ids: list[str] = Field(default_factory=list)
    identified_count: int
    suppressed_count: int
    suppressed_claim_ids: list[str] = Field(default_factory=list)
    rules_written: int


class QueueClaimItem(BaseModel):
    """A claim in a review queue."""

    claim_id: str
    text: str
    curation_state: str
    claim_type: str | None
    epistemic_status: str | None
    confidence: float
    source_document_id: str | None
    entity_ids: list[str]
    entity_names: list[str]  # Resolved entity names
    created_at: str
    review_history: list[dict[str, Any]] = Field(default_factory=list)


class QueueListResponse(BaseModel):
    """Response from queue list endpoint."""

    queue: str  # unreviewed, shortlisted, etc.
    claims: list[QueueClaimItem]
    total: int
    limit: int
    offset: int


# =============================================================================
# Helper Functions
# =============================================================================


def _validate_curation_state(state: str) -> ClaimCurationState:
    """Validate and convert string to ClaimCurationState enum."""
    try:
        return ClaimCurationState(state)
    except ValueError:
        valid_states = [s.value for s in ClaimCurationState]
        raise HTTPException(
            status_code=400,
            detail=f"Invalid curation state '{state}'. Must be one of: {valid_states}",
        )


def _get_entity_names(entity_ids: list[str], db: Database) -> list[str]:
    """Resolve entity IDs to canonical names."""
    names = []
    for entity_id in entity_ids:
        entity = db.get(KnowledgeEntity, entity_id)
        if entity:
            names.append(entity.canonical_name)
        else:
            names.append(f"[deleted: {entity_id[:8]}...]")
    return names


def _build_queue_item(claim: KnowledgeClaim, db: Database) -> QueueClaimItem:
    """Build a queue item from a claim with enriched data."""
    # Get review history from metadata
    review_history = claim.metadata.get("review_history", [])

    return QueueClaimItem(
        claim_id=claim.id,
        text=claim.text[:500] + ("..." if len(claim.text) > 500 else ""),
        curation_state=claim.curation_state.value,
        claim_type=claim.claim_type.value if claim.claim_type else None,
        epistemic_status=claim.epistemic_status.value
        if claim.epistemic_status
        else None,
        confidence=claim.confidence,
        source_document_id=claim.source_document_id,
        entity_ids=claim.entity_ids,
        entity_names=_get_entity_names(claim.entity_ids, db),
        created_at=claim.created_at.isoformat()
        if isinstance(claim.created_at, datetime)
        else str(claim.created_at),
        review_history=review_history,
    )


def _log_claim_curation_mutation(
    *,
    db: Database,
    claim: KnowledgeClaim,
    before_state: dict[str, Any],
) -> None:
    db.save(
        MutationLog(
            entity_type="KnowledgeClaim",
            entity_id=claim.id,
            operation=MutationOperationType.update,
            before_state=before_state,
            after_state=claim.model_dump(mode="json"),
            changed_fields=["curation_state"],
        )
    )


def _claim_audit_response(audit: ClaimMergeAudit) -> ClaimAuditResponse:
    return ClaimAuditResponse(
        id=audit.id,
        operation_type=audit.operation_type,
        source_claim_ids=audit.source_claim_ids,
        target_claim_id=audit.target_claim_id,
        merge_details=audit.merge_details,
        reversal_id=audit.reversal_id,
        created_by=audit.created_by,
        created_at=audit.created_at,
    )


def _merge_unique_by_id(existing: list[Any], incoming: list[Any]) -> list[Any]:
    seen = {getattr(item, "id", None) for item in existing}
    merged = list(existing)
    for item in incoming:
        item_id = getattr(item, "id", None)
        if item_id not in seen:
            merged.append(item)
            seen.add(item_id)
    return merged


def _claim_support_key(
    support: Any,
) -> tuple[str | None, str | None, int | None, int | None]:
    return (
        getattr(support, "source_document_id", None),
        getattr(support, "source_page_label", None),
        getattr(support, "source_char_start", None),
        getattr(support, "source_char_end", None),
    )


def _merge_claim_provenance(
    db: Database,
    survivor: KnowledgeClaim,
    absorbed_claims: list[KnowledgeClaim],
) -> dict[str, Any]:
    """Conservatively fold corroborating claim evidence into the survivor.

    The survivor keeps its existing scalar source fields so its primary citation
    remains stable, while the absorbed claims contribute only the additive,
    multi-source provenance fields that can safely union without ambiguity.
    """
    from fichero.workflows.tools._entity_writer import _weighted_corroboration_count

    existing_support_keys = {
        _claim_support_key(support) for support in survivor.source_supports
    }
    added_support_ids: list[str | None] = []
    for claim in absorbed_claims:
        for support in claim.source_supports:
            key = _claim_support_key(support)
            if key in existing_support_keys:
                continue
            survivor.source_supports.append(support)
            existing_support_keys.add(key)
            added_support_ids.append(getattr(support, "id", None))

    source_ids = {
        sid
        for sid in [
            survivor.source_document_id,
            *survivor.source_ids,
            *survivor.corroborating_source_ids,
            *(support.source_document_id for support in survivor.source_supports),
        ]
        if sid
    }
    for claim in absorbed_claims:
        source_ids.update(
            sid
            for sid in [
                claim.source_document_id,
                *claim.source_ids,
                *claim.corroborating_source_ids,
                *(support.source_document_id for support in claim.source_supports),
            ]
            if sid
        )

    page_labels = {
        label
        for label in [
            survivor.source_page_label,
            *survivor.source_page_labels,
            *(claim.source_page_label for claim in absorbed_claims),
            *(label for claim in absorbed_claims for label in claim.source_page_labels),
        ]
        if label
    }
    languages = {
        lang
        for lang in [
            survivor.language,
            survivor.source_language,
            *survivor.source_languages,
            *(claim.language for claim in absorbed_claims),
            *(claim.source_language for claim in absorbed_claims),
            *(lang for claim in absorbed_claims for lang in claim.source_languages),
        ]
        if lang
    }
    translation_chain = {
        step
        for step in [
            *survivor.translation_chain,
            *(step for claim in absorbed_claims for step in claim.translation_chain),
        ]
        if step
    }
    entity_ids = {
        entity_id
        for entity_id in [
            *survivor.entity_ids,
            *(entity_id for claim in absorbed_claims for entity_id in claim.entity_ids),
        ]
        if entity_id
    }

    survivor.source_ids = sorted(source_ids - {survivor.source_document_id})
    survivor.corroborating_source_ids = sorted(source_ids)
    survivor.corroboration_count = (
        len(source_ids) if source_ids else survivor.corroboration_count
    )
    if source_ids:
        survivor.weighted_corroboration_count = _weighted_corroboration_count(
            db, set(source_ids)
        )
    survivor.source_page_labels = sorted(page_labels)
    survivor.source_languages = sorted(languages)
    survivor.translation_chain = sorted(translation_chain)
    survivor.entity_ids = sorted(entity_ids)
    survivor.date_values = _merge_unique_by_id(
        survivor.date_values,
        [value for claim in absorbed_claims for value in claim.date_values],
    )
    survivor.place_values = _merge_unique_by_id(
        survivor.place_values,
        [value for claim in absorbed_claims for value in claim.place_values],
    )
    survivor.attribution_chain = _merge_unique_by_id(
        survivor.attribution_chain,
        [value for claim in absorbed_claims for value in claim.attribution_chain],
    )
    survivor.confidence = max(
        [survivor.confidence, *(claim.confidence for claim in absorbed_claims)]
    )
    evidential_values = [
        value
        for value in [
            survivor.evidential_confidence,
            *(claim.evidential_confidence for claim in absorbed_claims),
        ]
        if value is not None
    ]
    if evidential_values:
        survivor.evidential_confidence = max(evidential_values)

    return {
        "added_source_support_ids": [
            support_id for support_id in added_support_ids if support_id
        ],
        "source_ids": survivor.corroborating_source_ids,
        "entity_ids": survivor.entity_ids,
    }


def _link_signature(link: KnowledgeClaimLink) -> tuple[Any, ...]:
    return (
        link.claim_id,
        link.related_claim_id,
        link.relation_type.value,
        link.evidence,
        tuple(sorted((link.metadata or {}).items())),
    )


def _repoint_claim_links(
    *,
    db: Database,
    survivor_id: str,
    absorbed_ids: set[str],
) -> dict[str, Any]:
    touched_before: dict[str, dict[str, Any]] = {}
    duplicates_deleted: list[str] = []

    links = list(db.query(KnowledgeClaimLink))
    signatures: dict[tuple[Any, ...], str] = {}
    for link in links:
        touched = link.claim_id in absorbed_ids or link.related_claim_id in absorbed_ids
        if touched:
            touched_before[link.id] = link.model_dump(mode="json")
            if link.claim_id in absorbed_ids:
                link.claim_id = survivor_id
            if link.related_claim_id in absorbed_ids:
                link.related_claim_id = survivor_id

        should_delete = (
            link.claim_id == link.related_claim_id
            and link.relation_type == ClaimRelationType.duplicate_of
        )
        signature = _link_signature(link)
        if (
            not should_delete
            and signature in signatures
            and signatures[signature] != link.id
        ):
            should_delete = True

        if should_delete:
            duplicates_deleted.append(link.id)
            db.delete(link)
            continue

        signatures[signature] = link.id
        if touched:
            db.save(link)

    return {
        "before_by_id": touched_before,
        "deleted_link_ids": duplicates_deleted,
    }


def _restore_claim_snapshot(db: Database, snapshot: dict[str, Any]) -> None:
    db.save(KnowledgeClaim.model_validate(snapshot))


def _restore_link_snapshot(db: Database, snapshot: dict[str, Any]) -> None:
    db.save(KnowledgeClaimLink.model_validate(snapshot))


def _scope_doc_ids(
    db: Database, request: PruneTrivialClaimsRequest
) -> tuple[str, set[str]]:
    if request.document_id is not None:
        document = db.get(Document, request.document_id)
        if document is None:
            raise HTTPException(
                status_code=404, detail=f"Document not found: {request.document_id}"
            )
        return "document", {request.document_id}

    if request.folder_id is not None:
        folder = db.get(Document, request.folder_id)
        if folder is None:
            raise HTTPException(
                status_code=404, detail=f"Folder not found: {request.folder_id}"
            )
        if folder.doc_type != DocType.folder:
            raise HTTPException(
                status_code=400, detail=f"Document {request.folder_id} is not a folder"
            )
        from fichero.api.routes.claim.claims import _descendant_doc_ids

        return "folder", _descendant_doc_ids(db, request.folder_id)

    return "library", set()


def _ensure_library_wide_trivial_claim_rule(
    db: Database,
    *,
    reason: str,
    created_by: str,
) -> bool:
    for rule in db.query(ClaimSuppressionRule):
        if not rule.suppress_is_a_copulas:
            continue
        if rule.match_subject_name is not None:
            continue
        if rule.match_predicate_verb is not None:
            continue
        if rule.match_object_phrase is not None:
            continue
        return False

    db.save(
        ClaimSuppressionRule(
            action=ClaimSuppressionRuleAction.prune,
            suppress_is_a_copulas=True,
            reason=reason,
            created_by=created_by,
        )
    )
    return True


# =============================================================================
# Claim curation/merge mutation impls — the proven business logic, extracted so
# BOTH the route handler and the audited action (EPIC #1848 / #2014) drive the
# SAME code (iterate-not-replace). Emission stays with the caller; each raises
# HTTPException on bad input exactly as the route did.
# =============================================================================


def transition_claim_impl(
    db: Database, claim_id: str, request: "ClaimTransitionRequest"
) -> ClaimTransitionResponse:
    """Transition one claim's curation state, recording review history."""
    claim = db.get(KnowledgeClaim, claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail=f"Claim not found: {claim_id}")

    target_state = _validate_curation_state(request.to_state)

    from_state = claim.curation_state
    transitioned_at = datetime.now()

    claim.curation_state = target_state
    claim.updated_at = transitioned_at

    review_entry = {
        "from_state": from_state.value,
        "to_state": target_state.value,
        "timestamp": transitioned_at.isoformat(),
        "reviewed_by": request.reviewed_by,
        "reason": request.reason,
    }
    if "review_history" not in claim.metadata:
        claim.metadata["review_history"] = []
    claim.metadata["review_history"].append(review_entry)

    db.save(claim)
    logger.info(
        f"Transitioned claim {claim_id}: {from_state.value} → {target_state.value}"
    )
    return ClaimTransitionResponse(
        claim_id=claim_id,
        success=True,
        from_state=from_state.value,
        to_state=target_state.value,
        transitioned_at=transitioned_at.isoformat(),
    )


def batch_transition_claims_impl(
    db: Database, request: "BatchClaimTransitionRequest"
) -> tuple[BatchClaimTransitionResponse, list[str]]:
    """Batch-transition many claims. Returns (response, transitioned_ids)."""
    target_state = _validate_curation_state(request.to_state)
    results = []
    succeeded = 0
    failed = 0
    transitioned_at = datetime.now()
    transitioned_ids: list[str] = []

    for claim_id in request.claim_ids:
        claim = db.get(KnowledgeClaim, claim_id)
        if not claim:
            results.append(
                ClaimTransitionResponse(
                    claim_id=claim_id,
                    success=False,
                    from_state="",
                    to_state=request.to_state,
                    transitioned_at=transitioned_at.isoformat(),
                    error="Claim not found",
                )
            )
            failed += 1
            continue

        from_state = claim.curation_state
        claim.curation_state = target_state
        claim.updated_at = transitioned_at

        review_entry = {
            "from_state": from_state.value,
            "to_state": target_state.value,
            "timestamp": transitioned_at.isoformat(),
            "reviewed_by": request.reviewed_by,
            "reason": request.reason,
        }
        if "review_history" not in claim.metadata:
            claim.metadata["review_history"] = []
        claim.metadata["review_history"].append(review_entry)

        db.save(claim)
        succeeded += 1
        transitioned_ids.append(claim_id)
        results.append(
            ClaimTransitionResponse(
                claim_id=claim_id,
                success=True,
                from_state=from_state.value,
                to_state=target_state.value,
                transitioned_at=transitioned_at.isoformat(),
            )
        )

    logger.info(f"Batch transition: {succeeded} succeeded, {failed} failed")
    return (
        BatchClaimTransitionResponse(
            results=results,
            total=len(request.claim_ids),
            succeeded=succeeded,
            failed=failed,
        ),
        transitioned_ids,
    )


def batch_set_claim_curation_state_impl(
    db: Database, request: "BatchClaimCurationRequest"
) -> tuple[BatchClaimCurationResponse, list[str]]:
    """Batch-set claim curation_state (404 if any id is unknown).

    Returns (response, updated_ids). Mirrors the entity batch-curation helper:
    claims already in the target state are skipped (idempotent no-op).
    """
    claims: list[KnowledgeClaim] = []
    for claim_id in request.claim_ids:
        claim = db.get(KnowledgeClaim, claim_id)
        if claim is None:
            raise HTTPException(status_code=404, detail=f"Claim not found: {claim_id}")
        claims.append(claim)

    now = datetime.now()
    updated_ids: list[str] = []
    for claim in claims:
        if claim.curation_state == request.curation_state:
            continue
        before_state = claim.model_dump(mode="json")
        claim.curation_state = request.curation_state
        claim.updated_at = now
        db.save(claim)
        _log_claim_curation_mutation(db=db, claim=claim, before_state=before_state)
        updated_ids.append(claim.id)

    logger.info(
        "Batch curation update: %s claims set to %s",
        len(updated_ids),
        request.curation_state.value,
    )
    return BatchClaimCurationResponse(
        updated=len(updated_ids), claim_ids=updated_ids
    ), updated_ids


def merge_claims_impl(db: Database, request: "ClaimMergeRequest") -> ClaimMergeAudit:
    """The proven claim-merge algorithm — provenance fold + link repoint + audit.

    Extracted verbatim from the ``/merge`` route so BOTH the route and the
    ``claim.merge`` action drive the same code (iterate-not-replace). Returns the
    persisted ``ClaimMergeAudit`` whose ``merge_details`` carry the reversible
    snapshots ``unmerge`` restores. Raises ``HTTPException`` on bad ids exactly
    as before.
    """
    survivor = db.get(KnowledgeClaim, request.surviving_claim_id)
    if survivor is None:
        raise HTTPException(
            status_code=404,
            detail=f"Surviving claim not found: {request.surviving_claim_id}",
        )
    if survivor.merged_into_id is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Claim {survivor.id} was already merged into {survivor.merged_into_id}",
        )

    absorbed_ids = list(dict.fromkeys(request.absorbed_claim_ids))
    if survivor.id in absorbed_ids:
        raise HTTPException(
            status_code=400, detail="Surviving claim cannot also be absorbed"
        )

    absorbed_claims: list[KnowledgeClaim] = []
    for claim_id in absorbed_ids:
        claim = db.get(KnowledgeClaim, claim_id)
        if claim is None:
            raise HTTPException(
                status_code=404, detail=f"Absorbed claim not found: {claim_id}"
            )
        if claim.merged_into_id is not None:
            raise HTTPException(
                status_code=409,
                detail=f"Claim {claim_id} was already merged into {claim.merged_into_id}",
            )
        absorbed_claims.append(claim)

    now = datetime.now()
    survivor_before = survivor.model_dump(mode="json")
    absorbed_before = {
        claim.id: claim.model_dump(mode="json") for claim in absorbed_claims
    }

    provenance_changes = _merge_claim_provenance(db, survivor, absorbed_claims)
    link_changes = _repoint_claim_links(
        db=db,
        survivor_id=survivor.id,
        absorbed_ids={claim.id for claim in absorbed_claims},
    )

    for claim in absorbed_claims:
        claim.merged_into_id = survivor.id
        claim.curation_state = ClaimCurationState.rejected
        claim.updated_at = now
        db.save(claim)

    survivor.updated_at = now
    db.save(survivor)

    audit = ClaimMergeAudit(
        operation_type=ClaimMergeOperationType.merge,
        source_claim_ids=[claim.id for claim in absorbed_claims],
        target_claim_id=survivor.id,
        merge_details={
            "survivor_before": survivor_before,
            "absorbed_before": absorbed_before,
            "provenance_changes": provenance_changes,
            "link_changes": link_changes,
        },
        created_by="human",
        created_at=now,
    )
    db.save(audit)
    audit.reversal_id = audit.id
    db.save(audit)
    return audit


def unmerge_claims_impl(
    db: Database, request: "ClaimUnmergeRequest"
) -> ClaimMergeAudit:
    """Reverse a recorded claim merge from its audit snapshots.

    Extracted from the ``/unmerge`` route so the ``claim.merge`` action's
    ``invert`` reuses the exact same proven reversal. Returns the undo audit.
    Raises ``HTTPException`` on missing/non-merge/already-unmerged records.
    """
    audit = db.get(ClaimMergeAudit, request.audit_id)
    if audit is None:
        raise HTTPException(
            status_code=404, detail=f"Claim merge audit not found: {request.audit_id}"
        )
    if audit.operation_type != ClaimMergeOperationType.merge:
        raise HTTPException(status_code=409, detail="Only merge audits can be unmerged")
    if audit.reversal_id != audit.id:
        raise HTTPException(status_code=409, detail="This merge was already unmerged")

    merge_details = deepcopy(audit.merge_details or {})
    survivor_snapshot = merge_details.get("survivor_before")
    absorbed_snapshots = merge_details.get("absorbed_before", {})
    link_snapshots = (merge_details.get("link_changes") or {}).get("before_by_id", {})
    if not survivor_snapshot or not absorbed_snapshots:
        raise HTTPException(
            status_code=409, detail="Merge audit is missing reversible snapshots"
        )

    _restore_claim_snapshot(db, survivor_snapshot)
    for snapshot in absorbed_snapshots.values():
        _restore_claim_snapshot(db, snapshot)
    for snapshot in link_snapshots.values():
        _restore_link_snapshot(db, snapshot)

    now = datetime.now()
    undo = ClaimMergeAudit(
        operation_type=ClaimMergeOperationType.unmerge,
        source_claim_ids=audit.source_claim_ids,
        target_claim_id=audit.target_claim_id,
        merge_details={"reversed_audit_id": audit.id},
        reversal_id=audit.id,
        created_by="human",
        created_at=now,
    )
    db.save(undo)
    audit.reversal_id = undo.id
    db.save(audit)
    return undo


def prune_trivial_claims_impl(
    db: Database, request: "PruneTrivialClaimsRequest"
) -> PruneTrivialClaimsResponse:
    """Suppress trivially-true (is-a copula) claims in scope. Returns the report."""
    scope_type, scoped_doc_ids = _scope_doc_ids(db, request)

    identified: list[KnowledgeClaim] = []
    for claim in db.all(KnowledgeClaim):
        if scope_type != "library" and claim.source_document_id not in scoped_doc_ids:
            continue
        if is_trivial_claim(claim):
            identified.append(claim)

    now = datetime.now()
    suppressed_ids: list[str] = []
    for claim in identified:
        next_confidence = min(claim.confidence, 0.2)
        if (
            claim.curation_state == ClaimCurationState.rejected
            and claim.confidence == next_confidence
        ):
            continue
        before_state = claim.model_dump(mode="json")
        claim.curation_state = ClaimCurationState.rejected
        claim.confidence = next_confidence
        claim.updated_at = now
        db.save(claim)
        _log_claim_curation_mutation(db=db, claim=claim, before_state=before_state)
        suppressed_ids.append(claim.id)

    rules_written = 0
    if request.library_wide and _ensure_library_wide_trivial_claim_rule(
        db,
        reason=request.reason,
        created_by=request.created_by,
    ):
        rules_written = 1

    logger.info(
        "Pruned trivial claims: scope=%s identified=%s suppressed=%s rules_written=%s",
        scope_type,
        len(identified),
        len(suppressed_ids),
        rules_written,
    )
    return PruneTrivialClaimsResponse(
        scope_type=scope_type,
        scope_document_ids=sorted(scoped_doc_ids),
        identified_count=len(identified),
        suppressed_count=len(suppressed_ids),
        suppressed_claim_ids=suppressed_ids,
        rules_written=rules_written,
    )


# =============================================================================
# Review Queue Endpoints
# =============================================================================


@router.patch(
    "/{claim_id}/transition",
    response_model=ClaimTransitionResponse,
    summary="Transition claim curation state",
    description="Transition a single claim to a new curation state (unreviewed → shortlisted → curated/rejected).",
)
async def transition_claim(
    claim_id: str,
    request: ClaimTransitionRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> ClaimTransitionResponse:
    result = registry.invoke(
        db,
        "claim.transition",
        {"claim_id": claim_id, **request.model_dump(mode="json")},
        ctx,
    )
    return ClaimTransitionResponse.model_validate(result.result)


@router.post(
    "/batch/transition",
    response_model=BatchClaimTransitionResponse,
    summary="Batch transition claims",
    description="Transition multiple claims to a new curation state in one operation.",
)
async def batch_transition_claims(
    request: BatchClaimTransitionRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> BatchClaimTransitionResponse:
    result = registry.invoke(
        db,
        "claim.batch_transition",
        request.model_dump(mode="json"),
        ctx,
    )
    return BatchClaimTransitionResponse.model_validate(result.result)


@kg_claims_router.patch(
    "/batch-curation",
    response_model=BatchClaimCurationResponse,
    summary="Batch set claim curation state",
)
async def batch_set_claim_curation_state(
    request: BatchClaimCurationRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> BatchClaimCurationResponse:
    result = registry.invoke(
        db,
        "claim.batch_curation",
        request.model_dump(mode="json"),
        ctx,
    )
    return BatchClaimCurationResponse.model_validate(result.result)


@kg_claims_router.post(
    "/merge",
    response_model=ClaimAuditResponse,
    summary="Merge duplicate claims into a surviving claim",
)
async def merge_claims(
    request: ClaimMergeRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> ClaimAuditResponse:
    result = registry.invoke(
        db,
        "claim.merge",
        request.model_dump(mode="json"),
        ctx,
    )
    return ClaimAuditResponse.model_validate(result.result)


@kg_claims_router.post(
    "/unmerge",
    response_model=ClaimAuditResponse,
    summary="Reverse a recorded claim merge",
)
async def unmerge_claims(
    request: ClaimUnmergeRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> ClaimAuditResponse:
    result = registry.invoke(
        db,
        "claim.unmerge",
        request.model_dump(mode="json"),
        ctx,
    )
    return ClaimAuditResponse.model_validate(result.result)


@kg_claims_router.post(
    "/prune-trivial",
    response_model=PruneTrivialClaimsResponse,
    summary="Prune trivially-true claims",
)
async def prune_trivial_claims(
    request: PruneTrivialClaimsRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> PruneTrivialClaimsResponse:
    result = registry.invoke(
        db,
        "claim.prune_trivial",
        request.model_dump(mode="json"),
        ctx,
    )
    return PruneTrivialClaimsResponse.model_validate(result.result)


@router.get(
    "/queues/unreviewed",
    response_model=QueueListResponse,
    summary="Get unreviewed claims queue",
    description="List all claims in unreviewed state with optional filtering.",
)
async def get_unreviewed_queue(
    person: str | None = Query(None, description="Filter by entity name (person)"),
    topic: str | None = Query(None, description="Filter by topic/entity"),
    question: str | None = Query(None, description="Filter by question in text"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Database = Depends(get_library_database),
) -> QueueListResponse:
    """Get unreviewed claims queue."""
    claims = db.all(KnowledgeClaim)
    unreviewed = [
        c for c in claims if c.curation_state == ClaimCurationState.unreviewed
    ]

    # Apply filters
    if person:
        unreviewed = [
            c
            for c in unreviewed
            if any(
                person.lower() in name.lower()
                for name in _get_entity_names(c.entity_ids, db)
            )
        ]
    if topic:
        unreviewed = [
            c
            for c in unreviewed
            if any(
                topic.lower() in name.lower()
                for name in _get_entity_names(c.entity_ids, db)
            )
            or (c.text and topic.lower() in c.text.lower())
        ]
    if question:
        unreviewed = [
            c for c in unreviewed if c.text and question.lower() in c.text.lower()
        ]

    total = len(unreviewed)
    paginated = unreviewed[offset : offset + limit]

    return QueueListResponse(
        queue="unreviewed",
        claims=[_build_queue_item(c, db) for c in paginated],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/queues/shortlisted",
    response_model=QueueListResponse,
    summary="Get shortlisted claims queue",
    description="List all claims in shortlisted state with optional filtering.",
)
async def get_shortlisted_queue(
    person: str | None = Query(None, description="Filter by entity name (person)"),
    topic: str | None = Query(None, description="Filter by topic/entity"),
    question: str | None = Query(None, description="Filter by question in text"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Database = Depends(get_library_database),
) -> QueueListResponse:
    """Get shortlisted claims queue."""
    claims = db.all(KnowledgeClaim)
    shortlisted = [
        c for c in claims if c.curation_state == ClaimCurationState.shortlisted
    ]

    # Apply filters
    if person:
        shortlisted = [
            c
            for c in shortlisted
            if any(
                person.lower() in name.lower()
                for name in _get_entity_names(c.entity_ids, db)
            )
        ]
    if topic:
        shortlisted = [
            c
            for c in shortlisted
            if any(
                topic.lower() in name.lower()
                for name in _get_entity_names(c.entity_ids, db)
            )
            or (c.text and topic.lower() in c.text.lower())
        ]
    if question:
        shortlisted = [
            c for c in shortlisted if c.text and question.lower() in c.text.lower()
        ]

    total = len(shortlisted)
    paginated = shortlisted[offset : offset + limit]

    return QueueListResponse(
        queue="shortlisted",
        claims=[_build_queue_item(c, db) for c in paginated],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/queues/curated",
    response_model=QueueListResponse,
    summary="Get curated claims queue",
    description="List all claims in curated state with optional filtering.",
)
async def get_curated_queue(
    person: str | None = Query(None, description="Filter by entity name (person)"),
    topic: str | None = Query(None, description="Filter by topic/entity"),
    question: str | None = Query(None, description="Filter by question in text"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Database = Depends(get_library_database),
) -> QueueListResponse:
    """Get curated claims queue."""
    claims = db.all(KnowledgeClaim)
    curated = [c for c in claims if c.curation_state == ClaimCurationState.curated]

    # Apply filters
    if person:
        curated = [
            c
            for c in curated
            if any(
                person.lower() in name.lower()
                for name in _get_entity_names(c.entity_ids, db)
            )
        ]
    if topic:
        curated = [
            c
            for c in curated
            if any(
                topic.lower() in name.lower()
                for name in _get_entity_names(c.entity_ids, db)
            )
            or (c.text and topic.lower() in c.text.lower())
        ]
    if question:
        curated = [c for c in curated if c.text and question.lower() in c.text.lower()]

    total = len(curated)
    paginated = curated[offset : offset + limit]

    return QueueListResponse(
        queue="curated",
        claims=[_build_queue_item(c, db) for c in paginated],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/queues/rejected",
    response_model=QueueListResponse,
    summary="Get rejected claims queue",
    description="List all claims in rejected state with optional filtering.",
)
async def get_rejected_queue(
    person: str | None = Query(None, description="Filter by entity name (person)"),
    topic: str | None = Query(None, description="Filter by topic/entity"),
    question: str | None = Query(None, description="Filter by question in text"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Database = Depends(get_library_database),
) -> QueueListResponse:
    """Get rejected claims queue."""
    claims = db.all(KnowledgeClaim)
    rejected = [c for c in claims if c.curation_state == ClaimCurationState.rejected]

    # Apply filters
    if person:
        rejected = [
            c
            for c in rejected
            if any(
                person.lower() in name.lower()
                for name in _get_entity_names(c.entity_ids, db)
            )
        ]
    if topic:
        rejected = [
            c
            for c in rejected
            if any(
                topic.lower() in name.lower()
                for name in _get_entity_names(c.entity_ids, db)
            )
            or (c.text and topic.lower() in c.text.lower())
        ]
    if question:
        rejected = [
            c for c in rejected if c.text and question.lower() in c.text.lower()
        ]

    total = len(rejected)
    paginated = rejected[offset : offset + limit]

    return QueueListResponse(
        queue="rejected",
        claims=[_build_queue_item(c, db) for c in paginated],
        total=total,
        limit=limit,
        offset=offset,
    )


# =============================================================================
# Action layer registration (EPIC #1848 / #2014) — claim curation + merge.
# =============================================================================
#
# Each action WRAPS the proven ``*_impl`` above (iterate-not-replace) and routes
# through ``registry.invoke`` so chat tools / App Intents / tests / the audit
# log share ONE path with the typed routes (which stay untouched), matching the
# entity.merge pilot. Reversible pairs:
#   * claim.transition -> claim.transition (back to from_state)
#   * claim.merge      -> claim.unmerge    (via the recorded audit id)
#
# claim.batch_transition / claim.batch_curation / claim.unmerge /
# claim.prune_trivial are registered non-undoable: a partial-batch or
# already-an-undo op has no single clean inverse, but each still captures a
# before-snapshot in the audit for who-changed-what.

from fichero.actions.registry import action, ActionContext, ChangeSpec, registry  # noqa: E402


class ClaimTransitionActionParams(BaseModel):
    """Params for claim.transition — the path claim_id + the transition body."""

    claim_id: str = Field(description="Claim id to transition")
    to_state: str = Field(description="Target curation state")
    reason: str | None = Field(
        default=None, description="Optional reason for transition"
    )
    reviewed_by: str = Field(default="human", description="Who performed the review")


def _invert_transition(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    """Undo a transition by transitioning back to the recorded from_state."""
    if not before:
        return None
    claim_id = before.get("claim_id")
    from_state = before.get("from_state")
    if not claim_id or not from_state:
        return None
    return (
        "claim.transition",
        {"claim_id": claim_id, "to_state": from_state, "reason": "undo transition"},
    )


def _invert_merge_claims(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    if not after:
        return None
    audit_id = after.get("claim_merge_audit_id")
    if not audit_id:
        return None
    return ("claim.unmerge", {"audit_id": audit_id})


def _invert_unmerge_claims(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    if not after:
        return None
    target_claim_id = after.get("target_claim_id")
    source_claim_ids = after.get("source_claim_ids")
    if not target_claim_id or not source_claim_ids:
        return None
    return (
        "claim.merge",
        {
            "surviving_claim_id": target_claim_id,
            "absorbed_claim_ids": source_claim_ids,
        },
    )


@action(
    "claim.transition",
    ClaimTransitionActionParams,
    domains=["claim"],
    undoable=True,
    invert=_invert_transition,
)
def _action_transition_claim(
    db: Database, params: ClaimTransitionActionParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    request = ClaimTransitionRequest(
        to_state=params.to_state, reason=params.reason, reviewed_by=params.reviewed_by
    )
    response = transition_claim_impl(db, params.claim_id, request)
    spec = ChangeSpec(
        domains=["claim"],
        target_ids=[params.claim_id],
        before={"claim_id": params.claim_id, "from_state": response.from_state},
        after={"to_state": response.to_state},
        emit_type="claim.updated",
        claim_ids=[params.claim_id],
    )
    return response.model_dump(mode="json"), spec


@action(
    "claim.batch_transition",
    BatchClaimTransitionRequest,
    domains=["claim"],
    undoable=False,
)
def _action_batch_transition(
    db: Database, params: BatchClaimTransitionRequest, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    response, transitioned_ids = batch_transition_claims_impl(db, params)
    spec = ChangeSpec(
        domains=["claim"],
        target_ids=transitioned_ids,
        after={"to_state": params.to_state, "transitioned_ids": transitioned_ids},
        emit_type="claim.updated" if transitioned_ids else None,
        claim_ids=transitioned_ids,
    )
    return response.model_dump(mode="json"), spec


@action(
    "claim.batch_curation",
    BatchClaimCurationRequest,
    domains=["claim"],
    undoable=False,
)
def _action_batch_curation(
    db: Database, params: BatchClaimCurationRequest, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    response, updated_ids = batch_set_claim_curation_state_impl(db, params)
    spec = ChangeSpec(
        domains=["claim"],
        target_ids=updated_ids,
        after={
            "curation_state": params.curation_state.value,
            "updated_ids": updated_ids,
        },
        emit_type="claim.updated" if updated_ids else None,
        claim_ids=updated_ids,
    )
    return response.model_dump(mode="json"), spec


@action(
    "claim.merge",
    ClaimMergeRequest,
    domains=["claim"],
    undoable=True,
    invert=_invert_merge_claims,
)
def _action_merge_claims(
    db: Database, params: ClaimMergeRequest, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    audit = merge_claims_impl(db, params)
    claim_ids = [audit.target_claim_id, *audit.source_claim_ids]
    spec = ChangeSpec(
        domains=["claim"],
        target_ids=claim_ids,
        before={
            "survivor_before": audit.merge_details.get("survivor_before"),
            "absorbed_before": audit.merge_details.get("absorbed_before"),
        },
        after={"claim_merge_audit_id": audit.id},
        emit_type="claim.merged",
        claim_ids=claim_ids,
    )
    return _claim_audit_response(audit).model_dump(mode="json"), spec


@action(
    "claim.unmerge",
    ClaimUnmergeRequest,
    domains=["claim"],
    undoable=True,
    invert=_invert_unmerge_claims,
)
def _action_unmerge_claims(
    db: Database, params: ClaimUnmergeRequest, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    undo = unmerge_claims_impl(db, params)
    claim_ids = [undo.target_claim_id, *undo.source_claim_ids]
    spec = ChangeSpec(
        domains=["claim"],
        target_ids=claim_ids,
        after={
            "claim_merge_audit_id": undo.id,
            "target_claim_id": undo.target_claim_id,
            "source_claim_ids": undo.source_claim_ids,
        },
        emit_type="claim.merged",
        claim_ids=claim_ids,
    )
    return _claim_audit_response(undo).model_dump(mode="json"), spec


@action(
    "claim.prune_trivial",
    PruneTrivialClaimsRequest,
    domains=["claim"],
    undoable=False,
)
def _action_prune_trivial(
    db: Database, params: PruneTrivialClaimsRequest, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    response = prune_trivial_claims_impl(db, params)
    spec = ChangeSpec(
        domains=["claim"],
        target_ids=response.suppressed_claim_ids,
        after=response.model_dump(mode="json"),
        emit_type="claim.updated" if response.suppressed_claim_ids else None,
        claim_ids=response.suppressed_claim_ids,
    )
    return response.model_dump(mode="json"), spec
