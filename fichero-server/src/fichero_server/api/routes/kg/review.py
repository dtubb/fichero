"""Entity-match review queue routes (#899 Phase D / #377).

When ``upsert_entity`` lands in the 0.75-0.92 cosine band, it queues
an ``EntityMatchCandidate`` for human review. The reviewer accepts
(merge survivor + candidate) or rejects (labelled negative — fed to
splink/PyKEEN as training data).

Endpoints:
- GET    /api/kg/review/pairs           — list pending pairs
- POST   /api/kg/review/pairs/{id}/accept  — merge candidate into survivor
- POST   /api/kg/review/pairs/{id}/reject  — keep distinct (labelled neg)
- GET    /api/kg/review/labels          — accumulated decisions (for training)
"""

from __future__ import annotations

import logging
from datetime import datetime
from fichero_server.core.timeutil import utc_now

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel

from fichero_server.api.main import get_library_database, get_library_database_for_write
from fichero_server.db import Database
from fichero_server.models.knowledge import (
    EntityMatchCandidate,
    EntityMergeAudit,
    EntityMergeOperationType,
    KnowledgeClaim,
    KnowledgeEntity,
    PendingMatchMethod,
    PendingMatchState,
)
from fichero_server.models import ReviewListResponse, KGGraphListResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/kg/review")


# Auto-retrain trigger — every N new labelled decisions kicks off a
# background PyKEEN retrain so predictions stay current as users
# curates. Set to 10 by default; tunable per library if needed.
RETRAIN_EVERY_N_LABELS = 10


def _maybe_trigger_retrain(db: Database, background_tasks: BackgroundTasks) -> None:
    """If we've crossed the next RETRAIN_EVERY_N_LABELS multiple of
    labelled pairs, enqueue a PyKEEN training run.

    Runs as a FastAPI background task so the accept/reject HTTP
    response doesn't block on a 30-second train. Failures are logged
    inside the background task itself — the API endpoint always
    returns the immediate decision result.
    """
    try:
        decided = [
            c for c in db.query(EntityMatchCandidate)
            if c.state in (PendingMatchState.accepted, PendingMatchState.rejected)
        ]
        if decided and len(decided) % RETRAIN_EVERY_N_LABELS == 0:
            logger.info(
                "review queue: %d labels accumulated — triggering PyKEEN retrain",
                len(decided),
            )
            background_tasks.add_task(_run_retrain, db)
    except Exception as exc:
        logger.warning("auto-retrain trigger failed: %s", exc)


def _run_retrain(db: Database) -> None:
    """Background-thread PyKEEN retrain. Logs only."""
    try:
        from fichero_server.knowledge.pykeen_predictor import train_model
        stats = train_model(db)
        logger.info(
            "auto-retrain: %s — triples=%s, entities=%s, relations=%s",
            "trained" if stats.get("trained") else "skipped",
            stats.get("triples"),
            stats.get("entities"),
            stats.get("relations"),
        )
    except Exception as exc:
        logger.error("auto-retrain failed: %s", exc)


class ReviewPairResponse(BaseModel):
    """One pending pair waiting for a reviewer decision."""
    id: str
    survivor_entity_id: str
    candidate_entity_id: str
    survivor_name: str
    candidate_name: str
    survivor_type: str
    candidate_type: str
    score: float
    method: str
    reason: str | None
    created_at: datetime


class ReviewSummaryResponse(BaseModel):
    """Compact queue status for badge/UI polling."""
    pending_count: int
    has_pending: bool


@router.get(
    "/summary",
    response_model=ReviewSummaryResponse,
    summary="Review queue summary for badge counts",
)
async def review_summary(
    db: Database = Depends(get_library_database),
) -> ReviewSummaryResponse:
    pending_count = len(
        db.query(EntityMatchCandidate, state=PendingMatchState.pending)
    )
    return ReviewSummaryResponse(
        pending_count=pending_count,
        has_pending=pending_count > 0,
    )


@router.get(
    "/pairs",
    response_model=ReviewListResponse,
    summary="List pending entity-match pairs",
)
async def list_pairs(
    limit: int = Query(default=50, ge=1, le=500),
    db: Database = Depends(get_library_database),
) -> ReviewListResponse:
    """Return up-to ``limit`` pending pairs, newest first."""
    pending = db.query(EntityMatchCandidate, state=PendingMatchState.pending)
    pending.sort(key=lambda c: c.created_at, reverse=True)
    pending = pending[:limit]

    out: list[ReviewPairResponse] = []
    for cand in pending:
        survivor = db.get(KnowledgeEntity, cand.survivor_entity_id)
        candidate = db.get(KnowledgeEntity, cand.candidate_entity_id)
        if survivor is None or candidate is None:
            # Stale row — entity was deleted out from under it. Skip
            # rather than 500. A cleanup task could prune these later.
            continue
        out.append(ReviewPairResponse(
            id=cand.id,
            survivor_entity_id=cand.survivor_entity_id,
            candidate_entity_id=cand.candidate_entity_id,
            survivor_name=survivor.canonical_name,
            candidate_name=candidate.canonical_name,
            survivor_type=survivor.entity_type.value if hasattr(survivor.entity_type, "value") else str(survivor.entity_type),
            candidate_type=candidate.entity_type.value if hasattr(candidate.entity_type, "value") else str(candidate.entity_type),
            score=cand.score,
            method=cand.method.value if hasattr(cand.method, "value") else str(cand.method),
            reason=cand.reason,
            created_at=cand.created_at,
        ))
    return ReviewListResponse(items=out, count=len(out))


class GraphCandidateResponse(BaseModel):
    """One graph-context merge proposal — surfaced, not yet queued.

    Comes from co-occurrence neighbourhood overlap (#988): the two
    entities are never directly co-mentioned but share neighbours, so
    they may be the same entity under different surface forms. A human
    promotes a proposal into the review queue via POST /pairs.
    """
    entity_a_id: str
    entity_b_id: str
    name_a: str
    name_b: str
    shared_neighbours: int
    jaccard: float
    already_queued: bool


@router.get(
    "/graph-candidates",
    response_model=KGGraphListResponse,
    summary="Propose entity-merge candidates from co-occurrence overlap",
    description=(
        "Runs the graph-context heuristic (#988) over the full "
        "co-occurrence graph: entities that are never directly "
        "co-mentioned but share a high-Jaccard neighbourhood are "
        "likely the same entity under different surface forms. "
        "Read-only — proposals are not persisted; promote one into "
        "the review queue via POST /api/kg/review/pairs."
    ),
)
async def graph_candidates(
    threshold: float = Query(default=0.5, ge=0.0, le=1.0),
    min_shared: int = Query(default=2, ge=1),
    limit: int = Query(default=50, ge=1, le=500),
    db: Database = Depends(get_library_database),
) -> KGGraphListResponse:
    from fichero_server.knowledge.graph import (
        build_full_cooccurrence,
        graph_context_merge_candidates,
    )

    g = build_full_cooccurrence(db)
    candidates = graph_context_merge_candidates(
        g, threshold=threshold, min_shared=min_shared, top_k=limit,
    )
    if not candidates:
        return KGGraphListResponse(items=[], count=0)

    # Soft-deleted entities still appear as graph nodes — drop any
    # candidate touching one (it was already merged away).
    soft_deleted = {
        e.id for e in db.query(KnowledgeEntity) if e.merged_into_id
    }
    # An unordered-pair lookup so already-decided/pending pairs get
    # flagged regardless of which side is survivor vs candidate.
    queued = {
        frozenset((c.survivor_entity_id, c.candidate_entity_id))
        for c in db.query(EntityMatchCandidate)
    }

    out: list[GraphCandidateResponse] = []
    for cand in candidates:
        if cand.entity_a_id in soft_deleted or cand.entity_b_id in soft_deleted:
            continue
        out.append(GraphCandidateResponse(
            entity_a_id=cand.entity_a_id,
            entity_b_id=cand.entity_b_id,
            name_a=cand.name_a,
            name_b=cand.name_b,
            shared_neighbours=cand.shared_neighbours,
            jaccard=cand.jaccard,
            already_queued=frozenset(
                (cand.entity_a_id, cand.entity_b_id)
            ) in queued,
        ))
    return KGGraphListResponse(items=out, count=len(out))


class AcceptResponse(BaseModel):
    survivor_entity_id: str
    absorbed_entity_id: str
    claims_reassigned: int
    audit_id: str


@router.post(
    "/pairs/{pair_id}/accept",
    response_model=AcceptResponse,
    summary="Merge candidate into survivor — accept the suggested match",
    description=(
        "Reassigns every claim that referenced the candidate to the "
        "survivor instead, folds candidate.canonical_name + aliases "
        "into survivor.aliases, soft-deletes the candidate via "
        "merged_into_id, drops the candidate's LanceDB vector, and "
        "refreshes the survivor's vector. Writes an EntityMergeAudit "
        "for reversibility. (#899 Phase D / #377)"
    ),
)
async def accept_pair(
    pair_id: str,
    background_tasks: BackgroundTasks,
    db: Database = Depends(get_library_database_for_write),
) -> AcceptResponse:
    pair = db.get(EntityMatchCandidate, pair_id)
    if pair is None:
        raise HTTPException(status_code=404, detail=f"Pair not found: {pair_id}")
    if pair.state != PendingMatchState.pending:
        raise HTTPException(
            status_code=409,
            detail=f"Pair already {pair.state.value} — cannot re-decide",
        )

    survivor = db.get(KnowledgeEntity, pair.survivor_entity_id)
    candidate = db.get(KnowledgeEntity, pair.candidate_entity_id)
    if survivor is None or candidate is None:
        raise HTTPException(
            status_code=410,
            detail="One of the entities in this pair has been deleted",
        )

    # 1. Reassign claims: replace candidate id with survivor id everywhere.
    all_claims = db.query(KnowledgeClaim)
    claims_touched = 0
    for claim in all_claims:
        if candidate.id in (claim.entity_ids or []):
            claim.entity_ids = [
                survivor.id if eid == candidate.id else eid
                for eid in claim.entity_ids
            ]
            # Avoid duplicate survivor id when claim referenced both.
            seen: list[str] = []
            for eid in claim.entity_ids:
                if eid not in seen:
                    seen.append(eid)
            claim.entity_ids = seen
            claim.updated_at = utc_now()
            db.save(claim)
            claims_touched += 1

    # 2. Fold canonical_name + aliases into survivor.aliases.
    merged_aliases = set(survivor.aliases or [])
    merged_aliases.add(candidate.canonical_name)
    for alias in (candidate.aliases or []):
        merged_aliases.add(alias)
    survivor.aliases = sorted(merged_aliases - {survivor.canonical_name})
    survivor.updated_at = utc_now()
    db.save(survivor)

    # 3. Soft-delete the candidate by pointing merged_into_id at survivor.
    #    Keeps the row around for undo + audit.
    candidate.merged_into_id = survivor.id
    candidate.updated_at = utc_now()
    db.save(candidate)

    # 4. Drop the candidate's vector + refresh the survivor's.
    try:
        from fichero_server.knowledge import entity_vectors
        entity_vectors.remove(db=db, entity_id=candidate.id)
        entity_vectors.index_entity(
            db=db,
            entity_id=survivor.id,
            entity_type=survivor.entity_type,
            canonical_name=survivor.canonical_name,
            description=survivor.description,
        )
    except Exception as exc:
        logger.warning("accept_pair: vector cleanup failed: %s", exc)

    # 5. Audit trail.
    audit = EntityMergeAudit(
        operation_type=EntityMergeOperationType.merge,
        source_entity_ids=[candidate.id],
        target_entity_id=survivor.id,
        alias_changes={
            "added": sorted(merged_aliases - set(survivor.aliases or [])),
        },
        created_by="human",
    )
    db.save(audit)

    # 6. Close the review row.
    pair.state = PendingMatchState.accepted
    pair.decided_at = utc_now()
    pair.decided_by = "human"
    db.save(pair)

    _maybe_trigger_retrain(db, background_tasks)

    return AcceptResponse(
        survivor_entity_id=survivor.id,
        absorbed_entity_id=candidate.id,
        claims_reassigned=claims_touched,
        audit_id=audit.id,
    )


class RejectResponse(BaseModel):
    pair_id: str
    state: str
    labelled_negative_pair: tuple[str, str]


@router.post(
    "/pairs/{pair_id}/reject",
    response_model=RejectResponse,
    summary="Keep distinct — labels this pair as definitely-different",
    description=(
        "Records the reviewer's decision that survivor and candidate "
        "are NOT the same entity. The labelled negative feeds future "
        "splink / PyKEEN training (#899 Phase D)."
    ),
)
async def reject_pair(
    pair_id: str,
    background_tasks: BackgroundTasks,
    db: Database = Depends(get_library_database_for_write),
) -> RejectResponse:
    pair = db.get(EntityMatchCandidate, pair_id)
    if pair is None:
        raise HTTPException(status_code=404, detail=f"Pair not found: {pair_id}")
    if pair.state != PendingMatchState.pending:
        raise HTTPException(
            status_code=409,
            detail=f"Pair already {pair.state.value} — cannot re-decide",
        )
    pair.state = PendingMatchState.rejected
    pair.decided_at = utc_now()
    pair.decided_by = "human"
    db.save(pair)

    _maybe_trigger_retrain(db, background_tasks)

    return RejectResponse(
        pair_id=pair.id,
        state=pair.state.value,
        labelled_negative_pair=(pair.survivor_entity_id, pair.candidate_entity_id),
    )


class LabelRow(BaseModel):
    """One accumulated decision — accepted (positive) or rejected (negative).

    Feeds splink probabilistic linkage and PyKEEN retraining: the
    union of accepted-merge pairs and rejected pairs is the training
    set for future automation.
    """
    pair_id: str
    survivor_entity_id: str
    candidate_entity_id: str
    label: str  # "match" (accepted) or "no_match" (rejected)
    score: float
    method: str
    decided_at: datetime
    decided_by: str | None


@router.get(
    "/labels",
    response_model=KGGraphListResponse,
    summary="Accumulated human-labelled pairs for splink / PyKEEN training",
)
async def list_labels(
    db: Database = Depends(get_library_database),
) -> KGGraphListResponse:
    rows = db.query(EntityMatchCandidate)
    out: list[LabelRow] = []
    for r in rows:
        if r.state == PendingMatchState.accepted:
            label = "match"
        elif r.state == PendingMatchState.rejected:
            label = "no_match"
        else:
            continue
        out.append(LabelRow(
            pair_id=r.id,
            survivor_entity_id=r.survivor_entity_id,
            candidate_entity_id=r.candidate_entity_id,
            label=label,
            score=r.score,
            method=r.method.value if hasattr(r.method, "value") else str(r.method),
            decided_at=r.decided_at or r.created_at,
            decided_by=r.decided_by,
        ))
    return KGGraphListResponse(items=out, count=len(out))


# Manual queueing — lets the inspector "Suggest merge" button create
# a pair on demand, instead of waiting for the next catalogue run to
# stumble into the same review band.
class ManualPairRequest(BaseModel):
    survivor_entity_id: str
    candidate_entity_id: str
    reason: str | None = None


@router.post(
    "/pairs",
    response_model=ReviewPairResponse,
    summary="Manually queue an entity pair for review",
)
async def queue_pair(
    request: ManualPairRequest,
    db: Database = Depends(get_library_database_for_write),
) -> ReviewPairResponse:
    if request.survivor_entity_id == request.candidate_entity_id:
        raise HTTPException(400, "survivor and candidate must differ")
    survivor = db.get(KnowledgeEntity, request.survivor_entity_id)
    candidate = db.get(KnowledgeEntity, request.candidate_entity_id)
    if survivor is None or candidate is None:
        raise HTTPException(404, "One or both entities not found")

    cand = EntityMatchCandidate(
        survivor_entity_id=survivor.id,
        candidate_entity_id=candidate.id,
        score=0.5,  # neutral — human-driven, no model probability yet
        method=PendingMatchMethod.manual,
        reason=request.reason or "manually queued via /api/kg/review/pairs",
    )
    db.save(cand)
    return ReviewPairResponse(
        id=cand.id,
        survivor_entity_id=survivor.id,
        candidate_entity_id=candidate.id,
        survivor_name=survivor.canonical_name,
        candidate_name=candidate.canonical_name,
        survivor_type=survivor.entity_type.value if hasattr(survivor.entity_type, "value") else str(survivor.entity_type),
        candidate_type=candidate.entity_type.value if hasattr(candidate.entity_type, "value") else str(candidate.entity_type),
        score=cand.score,
        method=cand.method.value,
        reason=cand.reason,
        created_at=cand.created_at,
    )
