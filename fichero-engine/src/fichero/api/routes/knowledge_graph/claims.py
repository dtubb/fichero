"""Knowledge graph claims CRUD, semantic search, links, inclusion, and overview routes."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from fichero.api.main import get_library_database
from fichero.db import Database
from fichero.knowledge_models import (
    ClaimCurationState,
    ClaimRelationType,
    ClaimType,
    EpistemicStatus,
    InclusionScopeType,
    KnowledgeClaim,
    KnowledgeClaimLink,
    KnowledgeEntity,
    KnowledgeGraphInclusion,
    MutationOperationType,
    PredictionMetadata,
    SourceType,
)
from fichero.models import Document
from fichero.api.routes.knowledge_graph._shared import (
    KG_CLAIM_EMBEDDINGS_TABLE,
    _filter_claims,
    _is_source_included,
    _log_mutation,
)

router = APIRouter()


class ClaimCreateRequest(BaseModel):
    text: str
    source_document_id: str
    source_segment_id: str | None = None
    source_page_label: str | None = None
    source_excerpt: str | None = None
    source_ref: str | None = None
    entity_ids: list[str] = Field(default_factory=list)
    curation_state: ClaimCurationState = ClaimCurationState.unreviewed
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    predicted_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    predicted_by: list[str] = Field(default_factory=list)
    prediction: PredictionMetadata | None = None
    language: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_by: str = "human"
    source_type: SourceType = SourceType.document
    source_ids: list[str] = Field(default_factory=list)
    source_page_labels: list[str] = Field(default_factory=list)
    source_languages: list[str] = Field(default_factory=list)
    claim_type: ClaimType | None = None
    epistemic_status: EpistemicStatus | None = None


class ClaimPatchRequest(BaseModel):
    text: str | None = None
    source_segment_id: str | None = None
    source_page_label: str | None = None
    source_excerpt: str | None = None
    source_ref: str | None = None
    entity_ids: list[str] | None = None
    curation_state: ClaimCurationState | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    predicted_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    predicted_by: list[str] | None = None
    prediction: PredictionMetadata | None = None
    language: str | None = None
    metadata: dict[str, Any] | None = None
    source_type: SourceType | None = None
    source_ids: list[str] | None = None
    source_page_labels: list[str] | None = None
    source_languages: list[str] | None = None
    claim_type: ClaimType | None = None
    epistemic_status: EpistemicStatus | None = None


class ClaimLinkCreateRequest(BaseModel):
    related_claim_id: str
    relation_type: ClaimRelationType
    link_quality: float = Field(default=0.5, ge=0.0, le=1.0)
    evidence: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class InclusionUpsertRequest(BaseModel):
    scope_type: InclusionScopeType
    target_id: str
    included: bool
    reason: str | None = None
    updated_by: str = "human"


# Static /claims sub-paths MUST be defined BEFORE /{claim_id} to avoid
# FastAPI's greedy path-parameter matching swallowing them.

class EmbedClaimsResponse(BaseModel):
    embedded: int
    table: str


class OverviewCounts(BaseModel):
    claims: int
    entities: int
    claim_links: int
    curated_claims: int
    shortlisted_claims: int
    rejected_claims: int
    unreviewed_claims: int
    predicted_claims: int
    included_claims: int


class OverviewMetrics(BaseModel):
    average_confidence: float


class OverviewScope(BaseModel):
    scope_type: str | None
    target_id: str | None


class ClaimsOverviewResponse(BaseModel):
    counts: OverviewCounts
    metrics: OverviewMetrics
    scope: OverviewScope


class _EmbedClaimRequest(BaseModel):
    claim_ids: list[str] | None = None


@router.post("/claims/semantic/embed")
async def embed_claims(
    request: _EmbedClaimRequest | None = None,
    db: Database = Depends(get_library_database),
) -> EmbedClaimsResponse:
    """Embed claims into LanceDB for semantic search."""
    if request and request.claim_ids:
        claims = [db.get(KnowledgeClaim, cid) for cid in request.claim_ids]
        claims = [c for c in claims if c is not None]
    else:
        claims = db.all(KnowledgeClaim)

    if not claims:
        return EmbedClaimsResponse(embedded=0, table=KG_CLAIM_EMBEDDINGS_TABLE)

    texts = [c.text for c in claims]
    vectors = db._embed_texts(texts)  # type: ignore[attr-defined]

    records = [
        {
            "id": c.id,
            "text": c.text,
            "vector": v,
            "claim_type": c.claim_type.value if c.claim_type else None,
        }
        for c, v in zip(claims, vectors)
    ]
    db.save_vectors(KG_CLAIM_EMBEDDINGS_TABLE, records)
    return EmbedClaimsResponse(embedded=len(records), table=KG_CLAIM_EMBEDDINGS_TABLE)


@router.get("/claims/semantic")
async def search_claims_semantic(
    q: str = Query(..., description="Natural language query"),
    claim_type: ClaimType | None = Query(default=None),
    curation_state: ClaimCurationState | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    db: Database = Depends(get_library_database),
) -> list[dict[str, Any]]:
    """Semantic claim search using LanceDB vectors."""
    if KG_CLAIM_EMBEDDINGS_TABLE not in db._lance_tables():
        raise HTTPException(
            status_code=503,
            detail="Claim embeddings not yet indexed. POST /claims/semantic/embed first.",
        )

    try:
        query_vector = db._embed_text(q)  # type: ignore[attr-defined]
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Embedding generation failed: {e}")

    results = db.search_vectors(KG_CLAIM_EMBEDDINGS_TABLE, query_vector, limit=limit)
    claim_ids = [r["id"] for r in results]

    if not claim_ids:
        return []

    claims = {c.id: c for c in db.all(KnowledgeClaim) if c.id in claim_ids}
    filtered = [
        claims[cid]
        for cid in claim_ids
        if cid in claims
        and (claim_type is None or claims[cid].claim_type == claim_type)
        and (curation_state is None or claims[cid].curation_state == curation_state)
    ]

    score_map = {r["id"]: r.get("_score", 0.0) for r in results}
    return [
        {**c.model_dump(), "similarity_score": score_map.get(c.id, 0.0)}
        for c in filtered
    ]


@router.get("/claims/filtered", response_model=list[KnowledgeClaim])
async def list_claims_filtered(
    q: str | None = Query(default=None),
    claim_type: ClaimType | None = Query(default=None),
    curation_state: ClaimCurationState | None = Query(default=None),
    epistemic_status: EpistemicStatus | None = Query(default=None),
    entity_id: str | None = Query(default=None),
    source_language: str | None = Query(default=None),
    source_type: SourceType | None = Query(default=None),
    scope_type: InclusionScopeType | None = Query(default=None),
    target_id: str | None = Query(default=None),
    included_only: bool = Query(default=False),
    curated_only: bool = Query(default=False),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Database = Depends(get_library_database),
) -> list[KnowledgeClaim]:
    """Advanced claim search with all filter types."""
    claims = db.all(KnowledgeClaim)
    claims = _filter_claims(
        claims,
        db,
        q=q,
        entity_id=entity_id,
        curation_state=curation_state,
        claim_type=claim_type,
        epistemic_status=epistemic_status,
        source_language=source_language,
        source_type=source_type,
        scope_type=scope_type,
        target_id=target_id,
        included_only=included_only,
        curated_only=curated_only,
    )
    return claims[offset : offset + limit]


# Wildcard /{claim_id} must come AFTER all static /claims sub-paths.
@router.get("/claims/{claim_id}", response_model=KnowledgeClaim)
async def get_claim(
    claim_id: str, db: Database = Depends(get_library_database)
) -> KnowledgeClaim:
    claim = db.get(KnowledgeClaim, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail=f"Claim not found: {claim_id}")
    return claim


@router.get("/claims/{claim_id}/similar")
async def find_similar_claims(
    claim_id: str,
    limit: int = Query(default=10, ge=1, le=50),
    db: Database = Depends(get_library_database),
) -> list[dict[str, Any]]:
    """Find claims similar to a given claim."""
    claim = db.get(KnowledgeClaim, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail=f"Claim not found: {claim_id}")

    if KG_CLAIM_EMBEDDINGS_TABLE not in db._lance_tables():
        raise HTTPException(status_code=503, detail="Claims not embedded yet.")

    try:
        query_vector = db._embed_text(claim.text)  # type: ignore[attr-defined]
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Embedding failed: {e}")

    results = db.search_vectors(
        KG_CLAIM_EMBEDDINGS_TABLE, query_vector, limit=limit + 1
    )
    results = [r for r in results if r["id"] != claim_id]

    claim_map = {
        c.id: c for c in db.all(KnowledgeClaim) if c.id in [r["id"] for r in results]
    }
    score_map = {r["id"]: r.get("_score", 0.0) for r in results}

    return [
        {**claim_map[rid].model_dump(), "similarity_score": score_map.get(rid, 0.0)}
        for rid in [r["id"] for r in results]
        if rid in claim_map
    ][:limit]


@router.post("/claims/{claim_id}/links", response_model=KnowledgeClaimLink)
async def create_claim_link(
    claim_id: str,
    request: ClaimLinkCreateRequest,
    db: Database = Depends(get_library_database),
) -> KnowledgeClaimLink:
    claim = db.get(KnowledgeClaim, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail=f"Claim not found: {claim_id}")
    related_claim = db.get(KnowledgeClaim, request.related_claim_id)
    if related_claim is None:
        raise HTTPException(
            status_code=404,
            detail=f"Related claim not found: {request.related_claim_id}",
        )

    link = KnowledgeClaimLink(
        claim_id=claim_id,
        related_claim_id=request.related_claim_id,
        relation_type=request.relation_type,
        link_quality=request.link_quality,
        evidence=request.evidence,
        metadata=request.metadata,
        created_at=datetime.now(),
    )
    db.save(link)
    return link


@router.get("/claims/{claim_id}/links", response_model=list[KnowledgeClaimLink])
async def list_claim_links(
    claim_id: str, db: Database = Depends(get_library_database)
) -> list[KnowledgeClaimLink]:
    links = db.query(KnowledgeClaimLink, claim_id=claim_id)
    reverse_links = db.query(KnowledgeClaimLink, related_claim_id=claim_id)
    merged = {link.id: link for link in [*links, *reverse_links]}
    return sorted(merged.values(), key=lambda link: link.created_at, reverse=True)


@router.post("/claims", response_model=KnowledgeClaim)
async def create_claim(
    request: ClaimCreateRequest,
    run_id: str | None = Query(default=None),
    agent_id: str | None = Query(default=None),
    db: Database = Depends(get_library_database),
) -> KnowledgeClaim:
    source_doc = db.get(Document, request.source_document_id)
    if source_doc is None:
        raise HTTPException(
            status_code=404,
            detail=f"Source document not found: {request.source_document_id}",
        )

    missing_entities = [
        entity_id
        for entity_id in request.entity_ids
        if db.get(KnowledgeEntity, entity_id) is None
    ]
    if missing_entities:
        raise HTTPException(
            status_code=404, detail=f"Unknown entities: {missing_entities}"
        )

    now = datetime.now()
    claim_metadata = dict(request.metadata)
    claim_metadata.setdefault("sensitivity", "public")

    claim = KnowledgeClaim(
        text=request.text.strip(),
        source_document_id=request.source_document_id,
        source_segment_id=request.source_segment_id,
        source_page_label=request.source_page_label,
        source_excerpt=request.source_excerpt,
        source_ref=request.source_ref,
        entity_ids=request.entity_ids,
        curation_state=request.curation_state,
        confidence=request.confidence,
        predicted_confidence=request.predicted_confidence,
        predicted_by=request.predicted_by,
        prediction=request.prediction,
        language=request.language,
        metadata=claim_metadata,
        created_by=request.created_by,
        created_at=now,
        updated_at=now,
        source_type=request.source_type,
        source_ids=request.source_ids,
        source_page_labels=request.source_page_labels,
        source_languages=request.source_languages,
        claim_type=request.claim_type,
        epistemic_status=request.epistemic_status,
    )
    db.save(claim)

    _log_mutation(
        db=db,
        entity_type="KnowledgeClaim",
        entity_id=claim.id,
        operation=MutationOperationType.create,
        before_state=None,
        after_state={
            k: v for k, v in claim.model_dump().items() if k not in ("id", "created_at")
        },
        changed_fields=None,
        run_id=run_id,
        agent_id=agent_id,
        created_by=agent_id if agent_id else "human",
    )

    return claim


@router.patch("/claims/{claim_id}", response_model=KnowledgeClaim)
async def patch_claim(
    claim_id: str,
    request: ClaimPatchRequest,
    run_id: str | None = Query(default=None),
    agent_id: str | None = Query(default=None),
    db: Database = Depends(get_library_database),
) -> KnowledgeClaim:
    claim = db.get(KnowledgeClaim, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail=f"Claim not found: {claim_id}")

    before_state = {
        k: v for k, v in claim.model_dump().items() if k not in ("id", "created_at")
    }

    data = request.model_dump(exclude_unset=True, exclude_none=True)
    if "entity_ids" in data and data["entity_ids"] is not None:
        missing_entities = [
            entity_id
            for entity_id in data["entity_ids"]
            if db.get(KnowledgeEntity, entity_id) is None
        ]
        if missing_entities:
            raise HTTPException(
                status_code=404, detail=f"Unknown entities: {missing_entities}"
            )

    changed_fields = list(data.keys())
    for key, value in data.items():
        setattr(claim, key, value)
    claim.updated_at = datetime.now()
    db.save(claim)

    after_state = {
        k: v for k, v in claim.model_dump().items() if k not in ("id", "created_at")
    }
    _log_mutation(
        db=db,
        entity_type="KnowledgeClaim",
        entity_id=claim_id,
        operation=MutationOperationType.update,
        before_state=before_state,
        after_state=after_state,
        changed_fields=changed_fields,
        run_id=run_id,
        agent_id=agent_id,
        created_by=agent_id if agent_id else "human",
    )

    return claim


@router.get("/claims", response_model=list[KnowledgeClaim])
async def list_claims(
    q: str | None = Query(default=None),
    entity_id: str | None = Query(default=None),
    entity: str | None = Query(default=None),
    entity_type=Query(default=None),
    curation_state: ClaimCurationState | None = Query(default=None),
    curated_only: bool = Query(default=False),
    claim_type: ClaimType | None = Query(default=None),
    epistemic_status: EpistemicStatus | None = Query(default=None),
    source_document_id: str | None = Query(default=None),
    source_language: str | None = Query(default=None),
    source_type: SourceType | None = Query(default=None),
    scope_type: InclusionScopeType | None = Query(default=None),
    target_id: str | None = Query(default=None),
    included_only: bool = Query(default=False),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Database = Depends(get_library_database),
) -> list[KnowledgeClaim]:
    claims = db.all(KnowledgeClaim)
    claims = _filter_claims(
        claims,
        db,
        q=q,
        entity_id=entity_id,
        entity=entity,
        entity_type=entity_type,
        curation_state=curation_state,
        curated_only=curated_only,
        claim_type=claim_type,
        epistemic_status=epistemic_status,
        source_document_id=source_document_id,
        source_language=source_language,
        source_type=source_type,
        scope_type=scope_type,
        target_id=target_id,
        included_only=included_only,
    )
    return claims[offset : offset + limit]


@router.post("/inclusion", response_model=KnowledgeGraphInclusion)
async def upsert_inclusion(
    request: InclusionUpsertRequest,
    db: Database = Depends(get_library_database),
) -> KnowledgeGraphInclusion:
    existing = db.query(
        KnowledgeGraphInclusion,
        scope_type=request.scope_type,
        target_id=request.target_id,
    )
    now = datetime.now()
    if existing:
        record = max(existing, key=lambda row: row.updated_at)
        record.included = request.included
        record.reason = request.reason
        record.updated_by = request.updated_by
        record.updated_at = now
    else:
        record = KnowledgeGraphInclusion(
            scope_type=request.scope_type,
            target_id=request.target_id,
            included=request.included,
            reason=request.reason,
            updated_by=request.updated_by,
            updated_at=now,
        )
    db.save(record)
    return record


@router.get("/inclusion", response_model=list[KnowledgeGraphInclusion])
async def list_inclusion(
    scope_type: InclusionScopeType | None = Query(default=None),
    target_id: str | None = Query(default=None),
    db: Database = Depends(get_library_database),
) -> list[KnowledgeGraphInclusion]:
    if scope_type and target_id:
        rows = db.query(
            KnowledgeGraphInclusion, scope_type=scope_type, target_id=target_id
        )
    elif scope_type:
        rows = db.query(KnowledgeGraphInclusion, scope_type=scope_type)
    elif target_id:
        rows = db.query(KnowledgeGraphInclusion, target_id=target_id)
    else:
        rows = db.all(KnowledgeGraphInclusion)
    rows.sort(key=lambda row: row.updated_at, reverse=True)
    return rows


@router.get("/overview")
async def overview(
    scope_type: InclusionScopeType | None = Query(default=None),
    target_id: str | None = Query(default=None),
    db: Database = Depends(get_library_database),
) -> ClaimsOverviewResponse:
    claims = db.all(KnowledgeClaim)
    claims = _filter_claims(
        claims,
        db,
        q=None,
        entity_id=None,
        entity_type=None,
        curation_state=None,
        scope_type=scope_type,
        target_id=target_id,
        included_only=False,
    )
    entities = db.all(KnowledgeEntity)
    claim_links = db.all(KnowledgeClaimLink)
    curated = sum(
        1 for claim in claims if claim.curation_state == ClaimCurationState.curated
    )
    shortlisted = sum(
        1 for claim in claims if claim.curation_state == ClaimCurationState.shortlisted
    )
    rejected = sum(
        1 for claim in claims if claim.curation_state == ClaimCurationState.rejected
    )
    unreviewed = sum(
        1 for claim in claims if claim.curation_state == ClaimCurationState.unreviewed
    )
    predicted = sum(1 for claim in claims if claim.predicted_by)
    included_claims = sum(
        1 for claim in claims if _is_source_included(db, claim.source_document_id)
    )
    average_confidence = (
        sum(claim.confidence for claim in claims) / len(claims) if claims else 0.0
    )

    return ClaimsOverviewResponse(
        counts=OverviewCounts(
            claims=len(claims),
            entities=len(entities),
            claim_links=len(claim_links),
            curated_claims=curated,
            shortlisted_claims=shortlisted,
            rejected_claims=rejected,
            unreviewed_claims=unreviewed,
            predicted_claims=predicted,
            included_claims=included_claims,
        ),
        metrics=OverviewMetrics(average_confidence=average_confidence),
        scope=OverviewScope(
            scope_type=scope_type.value if scope_type else None,
            target_id=target_id,
        ),
    )
