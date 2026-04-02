"""Knowledge graph API routes (dev tier, backend-first 0.0.2 slice)."""

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
    EntityType,
    EpistemicStatus,
    InclusionScopeType,
    KnowledgeClaim,
    KnowledgeClaimLink,
    KnowledgeEntity,
    KnowledgeGraphInclusion,
    PredictionMetadata,
    SourceType,
)
from fichero.models import DocType, Document

router = APIRouter()


class EntityUpsertRequest(BaseModel):
    id: str | None = None
    canonical_name: str
    entity_type: EntityType = EntityType.other
    aliases: list[str] = Field(default_factory=list)
    description: str | None = None
    language: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EntityAliasRequest(BaseModel):
    aliases: list[str]


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
    # --- multi-source ---
    source_type: SourceType = SourceType.document
    source_ids: list[str] = Field(default_factory=list)
    source_page_labels: list[str] = Field(default_factory=list)
    source_languages: list[str] = Field(default_factory=list)
    # --- claim classification ---
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


def _normalize_text(value: str | None) -> str:
    return (value or "").strip().lower()


def _descendant_ids_for_folder(db: Database, folder_id: str) -> set[str]:
    documents = db.all(Document)
    children_by_parent: dict[str | None, list[Document]] = {}
    for doc in documents:
        children_by_parent.setdefault(doc.parent_id, []).append(doc)

    result: set[str] = set()
    stack: list[str] = [folder_id]
    while stack:
        current = stack.pop()
        result.add(current)
        for child in children_by_parent.get(current, []):
            stack.append(child.id)
    return result


def _resolve_scope_document_ids(
    db: Database,
    scope_type: InclusionScopeType | None,
    target_id: str | None,
) -> set[str] | None:
    if scope_type is None:
        return None
    if scope_type == InclusionScopeType.library:
        return None
    if not target_id:
        raise HTTPException(status_code=400, detail="target_id is required for non-library scopes")

    if scope_type == InclusionScopeType.document:
        return {target_id}

    folder = db.get(Document, target_id)
    if not folder or folder.doc_type != DocType.folder:
        raise HTTPException(status_code=404, detail=f"Folder not found: {target_id}")
    return _descendant_ids_for_folder(db, target_id)


def _load_entity_map(db: Database) -> dict[str, KnowledgeEntity]:
    return {entity.id: entity for entity in db.all(KnowledgeEntity)}


def _passes_query_filter(claim: KnowledgeClaim, q: str | None, entity_map: dict[str, KnowledgeEntity]) -> bool:
    if not q:
        return True
    needle = _normalize_text(q)
    if needle in _normalize_text(claim.text):
        return True
    for entity_id in claim.entity_ids:
        entity = entity_map.get(entity_id)
        if not entity:
            continue
        if needle in _normalize_text(entity.canonical_name):
            return True
        if any(needle in _normalize_text(alias) for alias in entity.aliases):
            return True
    return False


def _is_source_included(db: Database, source_document_id: str) -> bool:
    rows = db.query(
        KnowledgeGraphInclusion,
        scope_type=InclusionScopeType.document,
        target_id=source_document_id,
    )
    if not rows:
        return True
    latest = max(rows, key=lambda row: row.updated_at)
    return latest.included


@router.post("/entities", response_model=KnowledgeEntity)
async def upsert_entity(
    request: EntityUpsertRequest,
    db: Database = Depends(get_library_database),
) -> KnowledgeEntity:
    entity = db.get(KnowledgeEntity, request.id) if request.id else None
    now = datetime.now()
    if entity is None:
        entity = KnowledgeEntity(
            canonical_name=request.canonical_name.strip(),
            entity_type=request.entity_type,
            aliases=sorted(set(a.strip() for a in request.aliases if a.strip())),
            description=request.description,
            language=request.language,
            metadata=request.metadata,
            created_at=now,
            updated_at=now,
        )
    else:
        entity.canonical_name = request.canonical_name.strip()
        entity.entity_type = request.entity_type
        entity.aliases = sorted(set(a.strip() for a in request.aliases if a.strip()))
        entity.description = request.description
        entity.language = request.language
        entity.metadata = request.metadata
        entity.updated_at = now
    db.save(entity)
    return entity


@router.post("/entities/{entity_id}/aliases", response_model=KnowledgeEntity)
async def add_entity_aliases(
    entity_id: str,
    request: EntityAliasRequest,
    db: Database = Depends(get_library_database),
) -> KnowledgeEntity:
    entity = db.get(KnowledgeEntity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail=f"Entity not found: {entity_id}")
    merged = set(entity.aliases)
    merged.update(a.strip() for a in request.aliases if a.strip())
    entity.aliases = sorted(merged)
    entity.updated_at = datetime.now()
    db.save(entity)
    return entity


@router.get("/entities", response_model=list[KnowledgeEntity])
async def list_entities(
    q: str | None = Query(default=None),
    entity_type: EntityType | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    db: Database = Depends(get_library_database),
) -> list[KnowledgeEntity]:
    entities = db.query(KnowledgeEntity, entity_type=entity_type) if entity_type else db.all(KnowledgeEntity)
    needle = _normalize_text(q)
    if needle:
        entities = [
            entity
            for entity in entities
            if needle in _normalize_text(entity.canonical_name)
            or any(needle in _normalize_text(alias) for alias in entity.aliases)
        ]
    entities.sort(key=lambda entity: entity.canonical_name.lower())
    return entities[:limit]


@router.post("/claims", response_model=KnowledgeClaim)
async def create_claim(
    request: ClaimCreateRequest,
    db: Database = Depends(get_library_database),
) -> KnowledgeClaim:
    source_doc = db.get(Document, request.source_document_id)
    if source_doc is None:
        raise HTTPException(status_code=404, detail=f"Source document not found: {request.source_document_id}")

    missing_entities = [entity_id for entity_id in request.entity_ids if db.get(KnowledgeEntity, entity_id) is None]
    if missing_entities:
        raise HTTPException(status_code=404, detail=f"Unknown entities: {missing_entities}")

    now = datetime.now()
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
        metadata=request.metadata,
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
    return claim


@router.patch("/claims/{claim_id}", response_model=KnowledgeClaim)
async def patch_claim(
    claim_id: str,
    request: ClaimPatchRequest,
    db: Database = Depends(get_library_database),
) -> KnowledgeClaim:
    claim = db.get(KnowledgeClaim, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail=f"Claim not found: {claim_id}")

    data = request.model_dump(exclude_unset=True)
    if "entity_ids" in data and data["entity_ids"] is not None:
        missing_entities = [entity_id for entity_id in data["entity_ids"] if db.get(KnowledgeEntity, entity_id) is None]
        if missing_entities:
            raise HTTPException(status_code=404, detail=f"Unknown entities: {missing_entities}")

    for key, value in data.items():
        setattr(claim, key, value)
    claim.updated_at = datetime.now()
    db.save(claim)
    return claim


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
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Database = Depends(get_library_database),
) -> list[KnowledgeClaim]:
    """Advanced claim search with all Phase 1 filter types.

    Separate from /claims to keep the simple list endpoint clean for SwiftUI.
    """
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
    )
    return claims[offset:offset + limit]


@router.get("/claims/{claim_id}", response_model=KnowledgeClaim)
async def get_claim(claim_id: str, db: Database = Depends(get_library_database)) -> KnowledgeClaim:
    claim = db.get(KnowledgeClaim, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail=f"Claim not found: {claim_id}")
    return claim


def _filter_claims(
    claims: list[KnowledgeClaim],
    db: Database,
    q: str | None = None,
    entity_id: str | None = None,
    entity_type: EntityType | None = None,
    curation_state: ClaimCurationState | None = None,
    claim_type: ClaimType | None = None,
    epistemic_status: EpistemicStatus | None = None,
    source_document_id: str | None = None,
    source_language: str | None = None,
    source_type: SourceType | None = None,
    scope_type: InclusionScopeType | None = None,
    target_id: str | None = None,
    included_only: bool = False,
) -> list[KnowledgeClaim]:
    """Apply all claim filters to an already-loaded list of claims."""
    entity_map = _load_entity_map(db)
    scoped_document_ids = _resolve_scope_document_ids(db, scope_type, target_id)

    if source_document_id:
        claims = [c for c in claims if c.source_document_id == source_document_id]
    if scoped_document_ids is not None:
        claims = [c for c in claims if c.source_document_id in scoped_document_ids]
    if entity_id:
        claims = [c for c in claims if entity_id in c.entity_ids]
    if entity_type:
        claims = [
            c
            for c in claims
            if any(
                entity_map.get(eid) and entity_map[eid].entity_type == entity_type
                for eid in c.entity_ids
            )
        ]
    if curation_state:
        claims = [c for c in claims if c.curation_state == curation_state]
    if claim_type:
        claims = [c for c in claims if c.claim_type == claim_type]
    if epistemic_status:
        claims = [c for c in claims if c.epistemic_status == epistemic_status]
    if source_language:
        claims = [c for c in claims if source_language in c.source_languages]
    if source_type:
        claims = [c for c in claims if c.source_type == source_type]

    claims = [c for c in claims if _passes_query_filter(c, q, entity_map)]
    if included_only:
        claims = [c for c in claims if _is_source_included(db, c.source_document_id)]

    claims.sort(key=lambda c: c.updated_at, reverse=True)
    return claims


@router.get("/claims", response_model=list[KnowledgeClaim])
async def list_claims(
    q: str | None = Query(default=None),
    entity_id: str | None = Query(default=None),
    entity_type: EntityType | None = Query(default=None),
    curation_state: ClaimCurationState | None = Query(default=None),
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
        entity_type=entity_type,
        curation_state=curation_state,
        claim_type=claim_type,
        epistemic_status=epistemic_status,
        source_document_id=source_document_id,
        source_language=source_language,
        source_type=source_type,
        scope_type=scope_type,
        target_id=target_id,
        included_only=included_only,
    )
    return claims[offset:offset + limit]


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
        raise HTTPException(status_code=404, detail=f"Related claim not found: {request.related_claim_id}")

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
async def list_claim_links(claim_id: str, db: Database = Depends(get_library_database)) -> list[KnowledgeClaimLink]:
    links = db.query(KnowledgeClaimLink, claim_id=claim_id)
    reverse_links = db.query(KnowledgeClaimLink, related_claim_id=claim_id)
    merged = {link.id: link for link in [*links, *reverse_links]}
    return sorted(merged.values(), key=lambda link: link.created_at, reverse=True)


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
        rows = db.query(KnowledgeGraphInclusion, scope_type=scope_type, target_id=target_id)
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
) -> dict[str, Any]:
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
    curated = sum(1 for claim in claims if claim.curation_state == ClaimCurationState.curated)
    shortlisted = sum(1 for claim in claims if claim.curation_state == ClaimCurationState.shortlisted)
    rejected = sum(1 for claim in claims if claim.curation_state == ClaimCurationState.rejected)
    unreviewed = sum(1 for claim in claims if claim.curation_state == ClaimCurationState.unreviewed)
    predicted = sum(1 for claim in claims if claim.predicted_by)
    included_claims = sum(1 for claim in claims if _is_source_included(db, claim.source_document_id))
    average_confidence = sum(claim.confidence for claim in claims) / len(claims) if claims else 0.0

    return {
        "counts": {
            "claims": len(claims),
            "entities": len(entities),
            "claim_links": len(claim_links),
            "curated_claims": curated,
            "shortlisted_claims": shortlisted,
            "rejected_claims": rejected,
            "unreviewed_claims": unreviewed,
            "predicted_claims": predicted,
            "included_claims": included_claims,
        },
        "metrics": {
            "average_confidence": average_confidence,
        },
        "scope": {
            "scope_type": scope_type.value if scope_type else None,
            "target_id": target_id,
        },
    }
