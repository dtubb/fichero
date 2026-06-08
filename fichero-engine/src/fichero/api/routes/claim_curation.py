"""Review Queue API Routes

Claim review workflow endpoints for managing curation state transitions.
Provides queue views and batch transition operations.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator

from fichero.api.main import get_library_database
from fichero.db import Database
from fichero.kg._common import is_trivial_claim
from fichero.knowledge_models import (
    ClaimCurationState,
    ClaimSuppressionRule,
    ClaimSuppressionRuleAction,
    KnowledgeClaim,
    KnowledgeEntity,
    MutationLog,
    MutationOperationType,
)
from fichero.models import DocType, Document

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/claims", tags=["review-queue"])
kg_claims_router = APIRouter(prefix="/kg/claims", tags=["knowledge-graph", "claim-curation"])


# =============================================================================
# Request/Response Models
# =============================================================================


class ClaimTransitionRequest(BaseModel):
    """Request to transition a claim's curation state."""

    to_state: str = Field(..., description="Target curation state: unreviewed, shortlisted, curated, rejected")
    reason: str | None = Field(None, description="Optional reason for transition")
    reviewed_by: str = Field(default="human", description="Who performed the review")


class BatchClaimTransitionRequest(BaseModel):
    """Request to transition multiple claims."""

    claim_ids: list[str] = Field(..., description="List of claim IDs to transition", min_length=1)
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
    curation_state: ClaimCurationState = Field(description="New curation state for every listed claim.")


class BatchClaimCurationResponse(BaseModel):
    updated: int
    claim_ids: list[str] = Field(default_factory=list, description="Claim IDs whose state actually changed.")


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
        scopes = int(bool(self.document_id)) + int(bool(self.folder_id)) + int(self.library_wide)
        if scopes != 1:
            raise ValueError("Exactly one of document_id, folder_id, or library_wide=true is required")
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
            detail=f"Invalid curation state '{state}'. Must be one of: {valid_states}"
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
        epistemic_status=claim.epistemic_status.value if claim.epistemic_status else None,
        confidence=claim.confidence,
        source_document_id=claim.source_document_id,
        entity_ids=claim.entity_ids,
        entity_names=_get_entity_names(claim.entity_ids, db),
        created_at=claim.created_at.isoformat() if isinstance(claim.created_at, datetime) else str(claim.created_at),
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


def _scope_doc_ids(db: Database, request: PruneTrivialClaimsRequest) -> tuple[str, set[str]]:
    if request.document_id is not None:
        document = db.get(Document, request.document_id)
        if document is None:
            raise HTTPException(status_code=404, detail=f"Document not found: {request.document_id}")
        return "document", {request.document_id}

    if request.folder_id is not None:
        folder = db.get(Document, request.folder_id)
        if folder is None:
            raise HTTPException(status_code=404, detail=f"Folder not found: {request.folder_id}")
        if folder.doc_type != DocType.folder:
            raise HTTPException(status_code=400, detail=f"Document {request.folder_id} is not a folder")
        from fichero.api.routes.claims import _descendant_doc_ids
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
    db: Database = Depends(get_library_database),
) -> ClaimTransitionResponse:
    """Transition a claim's curation state."""
    claim = db.get(KnowledgeClaim, claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail=f"Claim not found: {claim_id}")

    # Validate target state
    target_state = _validate_curation_state(request.to_state)

    # Record transition
    from_state = claim.curation_state
    transitioned_at = datetime.now()

    # Update claim
    claim.curation_state = target_state
    claim.updated_at = transitioned_at

    # Record in review history
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
    logger.info(f"Transitioned claim {claim_id}: {from_state.value} → {target_state.value}")

    return ClaimTransitionResponse(
        claim_id=claim_id,
        success=True,
        from_state=from_state.value,
        to_state=target_state.value,
        transitioned_at=transitioned_at.isoformat(),
    )


@router.post(
    "/batch/transition",
    response_model=BatchClaimTransitionResponse,
    summary="Batch transition claims",
    description="Transition multiple claims to a new curation state in one operation.",
)
async def batch_transition_claims(
    request: BatchClaimTransitionRequest,
    db: Database = Depends(get_library_database),
) -> BatchClaimTransitionResponse:
    """Batch transition multiple claims."""
    target_state = _validate_curation_state(request.to_state)
    results = []
    succeeded = 0
    failed = 0
    transitioned_at = datetime.now()

    for claim_id in request.claim_ids:
        claim = db.get(KnowledgeClaim, claim_id)
        if not claim:
            results.append(ClaimTransitionResponse(
                claim_id=claim_id,
                success=False,
                from_state="",
                to_state=request.to_state,
                transitioned_at=transitioned_at.isoformat(),
                error="Claim not found",
            ))
            failed += 1
            continue

        from_state = claim.curation_state
        claim.curation_state = target_state
        claim.updated_at = transitioned_at

        # Record in review history
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
        results.append(ClaimTransitionResponse(
            claim_id=claim_id,
            success=True,
            from_state=from_state.value,
            to_state=target_state.value,
            transitioned_at=transitioned_at.isoformat(),
        ))

    logger.info(f"Batch transition: {succeeded} succeeded, {failed} failed")
    return BatchClaimTransitionResponse(
        results=results,
        total=len(request.claim_ids),
        succeeded=succeeded,
        failed=failed,
    )


@kg_claims_router.patch(
    "/batch-curation",
    response_model=BatchClaimCurationResponse,
    summary="Batch set claim curation state",
)
async def batch_set_claim_curation_state(
    request: BatchClaimCurationRequest,
    db: Database = Depends(get_library_database),
) -> BatchClaimCurationResponse:
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

    logger.info("Batch curation update: %s claims set to %s", len(updated_ids), request.curation_state.value)
    return BatchClaimCurationResponse(updated=len(updated_ids), claim_ids=updated_ids)


@kg_claims_router.post(
    "/prune-trivial",
    response_model=PruneTrivialClaimsResponse,
    summary="Prune trivially-true claims",
)
async def prune_trivial_claims(
    request: PruneTrivialClaimsRequest,
    db: Database = Depends(get_library_database),
) -> PruneTrivialClaimsResponse:
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
    unreviewed = [c for c in claims if c.curation_state == ClaimCurationState.unreviewed]

    # Apply filters
    if person:
        unreviewed = [
            c for c in unreviewed
            if any(person.lower() in name.lower() for name in _get_entity_names(c.entity_ids, db))
        ]
    if topic:
        unreviewed = [
            c for c in unreviewed
            if any(topic.lower() in name.lower() for name in _get_entity_names(c.entity_ids, db))
            or (c.text and topic.lower() in c.text.lower())
        ]
    if question:
        unreviewed = [c for c in unreviewed if c.text and question.lower() in c.text.lower()]

    total = len(unreviewed)
    paginated = unreviewed[offset:offset + limit]

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
    shortlisted = [c for c in claims if c.curation_state == ClaimCurationState.shortlisted]

    # Apply filters
    if person:
        shortlisted = [
            c for c in shortlisted
            if any(person.lower() in name.lower() for name in _get_entity_names(c.entity_ids, db))
        ]
    if topic:
        shortlisted = [
            c for c in shortlisted
            if any(topic.lower() in name.lower() for name in _get_entity_names(c.entity_ids, db))
            or (c.text and topic.lower() in c.text.lower())
        ]
    if question:
        shortlisted = [c for c in shortlisted if c.text and question.lower() in c.text.lower()]

    total = len(shortlisted)
    paginated = shortlisted[offset:offset + limit]

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
            c for c in curated
            if any(person.lower() in name.lower() for name in _get_entity_names(c.entity_ids, db))
        ]
    if topic:
        curated = [
            c for c in curated
            if any(topic.lower() in name.lower() for name in _get_entity_names(c.entity_ids, db))
            or (c.text and topic.lower() in c.text.lower())
        ]
    if question:
        curated = [c for c in curated if c.text and question.lower() in c.text.lower()]

    total = len(curated)
    paginated = curated[offset:offset + limit]

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
            c for c in rejected
            if any(person.lower() in name.lower() for name in _get_entity_names(c.entity_ids, db))
        ]
    if topic:
        rejected = [
            c for c in rejected
            if any(topic.lower() in name.lower() for name in _get_entity_names(c.entity_ids, db))
            or (c.text and topic.lower() in c.text.lower())
        ]
    if question:
        rejected = [c for c in rejected if c.text and question.lower() in c.text.lower()]

    total = len(rejected)
    paginated = rejected[offset:offset + limit]

    return QueueListResponse(
        queue="rejected",
        claims=[_build_queue_item(c, db) for c in paginated],
        total=total,
        limit=limit,
        offset=offset,
    )
