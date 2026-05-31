"""Claims API - Canonical FastAPI routes for knowledge claims.

This module implements dedicated routes for knowledge claim operations,
providing a clean separation from the broader knowledge graph functionality.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from fichero.api.main import get_library_database
from fichero.db import Database
from fichero.knowledge_models import (
    ClaimCurationState,
    ClaimType,
    EpistemicStatus,
    GeoPoint,
    KnowledgeClaim,
    KnowledgeClaimLink,
    KnowledgeEntity,
    MutationLog,
    MutationOperationType,
    PredictionMetadata,
    ProvenanceLayer,
    QuotationKind,
    SourceGenre,
    SourceType,
)
from fichero.models import Document
from fichero.models import ClaimListResponse

router = APIRouter(prefix="/claims", tags=["claims"])


# =============================================================================
# Request/Response Models
# =============================================================================


class ClaimCreateRequest(BaseModel):
    """Request to create a knowledge claim."""

    text: str
    source_document_id: str | None = None  # None for manually-asserted claims
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
    # Multi-source support
    source_type: SourceType = SourceType.document
    source_ids: list[str] = Field(default_factory=list)
    source_page_labels: list[str] = Field(default_factory=list)
    source_languages: list[str] = Field(default_factory=list)
    # Claim classification
    claim_type: ClaimType | None = None
    epistemic_status: EpistemicStatus | None = None
    # SVO triple (#984) — request-side optional; auto-canonicalised below
    subject_canonical: str | None = None
    subject_entity_id: str | None = None
    predicate_verb: str | None = None
    object_phrase: str | None = None
    # Attribution taxonomy (#1123) — request-side optional. If the
    # caller doesn't pass these, the create route's heuristic detection
    # mirrors `_entity_writer.save_claim` so manually-created and
    # extractor-created claims have the same attribution shape.
    speaker_name: str | None = None
    speaker_entity_id: str | None = None
    subject_of_inquiry_entity_id: str | None = None
    scribe_name: str | None = None
    scribe_entity_id: str | None = None
    editor_name: str | None = None
    editor_entity_id: str | None = None
    quotation_kind: QuotationKind | None = None
    provenance_layer: ProvenanceLayer = ProvenanceLayer.main_text
    source_language: str | None = None
    translation_chain: list[str] = Field(default_factory=list)
    audience: str | None = None
    source_genre: SourceGenre | None = None
    claim_recorded_at: str | None = None
    claim_geo: GeoPoint | None = None
    confidence_source: str | None = None


class ClaimPatchRequest(BaseModel):
    """Request to patch/update a knowledge claim."""

    text: str | None = None
    source_document_id: str | None = None
    source_segment_id: str | None = None
    source_page_label: str | None = None
    source_excerpt: str | None = None
    source_ref: str | None = None
    source_char_start: int | None = None
    source_char_end: int | None = None
    source_bbox: list[float] | None = None
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
    subject_canonical: str | None = None
    subject_entity_id: str | None = None
    predicate_verb: str | None = None
    predicate_canonical: str | None = None
    object_phrase: str | None = None
    svo_subject: str | None = None
    svo_verb: str | None = None
    svo_object: str | None = None
    time_start: str | None = None
    time_end: str | None = None
    time_precision: str | None = None
    speaker_name: str | None = None
    speaker_entity_id: str | None = None
    subject_of_inquiry_entity_id: str | None = None
    scribe_name: str | None = None
    scribe_entity_id: str | None = None
    editor_name: str | None = None
    editor_entity_id: str | None = None
    quotation_kind: QuotationKind | None = None
    provenance_layer: ProvenanceLayer | None = None
    source_language: str | None = None
    translation_chain: list[str] | None = None
    audience: str | None = None
    source_genre: SourceGenre | None = None
    claim_recorded_at: str | None = None
    claim_geo: GeoPoint | None = None
    confidence_source: str | None = None


class ClaimSourceResolveRequest(BaseModel):
    """Resolve a claim or SVO triple to source page + char span."""

    claim_id: str | None = None
    subject_canonical: str | None = None
    predicate_verb: str | None = None
    object_phrase: str | None = None
    source_document_id: str | None = None


class ClaimSourceResolveResponse(BaseModel):
    claim_id: str
    source_document_id: str
    source_page_label: str | None = None
    source_char_start: int | None = None
    source_char_end: int | None = None
    source_excerpt: str | None = None
    subject_canonical: str | None = None
    predicate_verb: str | None = None
    object_phrase: str | None = None


def _validate_claim_references(db: Database, data: dict[str, Any]) -> None:
    """Validate editable foreign-key-ish claim references."""
    if data.get("source_document_id") is not None:
        source_doc = db.get(Document, data["source_document_id"])
        if source_doc is None:
            raise HTTPException(
                status_code=404,
                detail=f"Source document not found: {data['source_document_id']}",
            )

    entity_ids = data.get("entity_ids")
    if entity_ids is not None:
        missing_entities = [
            entity_id
            for entity_id in entity_ids
            if db.get(KnowledgeEntity, entity_id) is None
        ]
        if missing_entities:
            raise HTTPException(
                status_code=404, detail=f"Unknown entities: {missing_entities}"
            )

    for field in (
        "subject_entity_id",
        "speaker_entity_id",
        "subject_of_inquiry_entity_id",
        "scribe_entity_id",
        "editor_entity_id",
    ):
        entity_id = data.get(field)
        if entity_id is not None and db.get(KnowledgeEntity, entity_id) is None:
            raise HTTPException(
                status_code=404, detail=f"Unknown entity for {field}: {entity_id}"
            )


def _apply_claim_patch(claim: KnowledgeClaim, data: dict[str, Any]) -> None:
    """Apply patch fields and keep canonical SVO fields consistent."""
    from fichero.kg._common import canonical_verb

    if "text" in data and isinstance(data["text"], str):
        data["text"] = data["text"].strip()

    if "predicate_verb" in data and "predicate_canonical" not in data:
        data["predicate_canonical"] = canonical_verb(data["predicate_verb"])
    if "predicate_verb" in data and "svo_verb" not in data:
        data["svo_verb"] = data.get("predicate_canonical")
    if "subject_canonical" in data and "svo_subject" not in data:
        data["svo_subject"] = data.get("subject_canonical")
    if "object_phrase" in data and "svo_object" not in data:
        data["svo_object"] = data.get("object_phrase")

    for key, value in data.items():
        setattr(claim, key, value)
    claim.updated_at = datetime.now()


def _delete_claim_links_for_claim(db: Database, claim_id: str) -> list[dict[str, Any]]:
    """Delete KnowledgeClaimLink rows that would orphan after claim deletion."""
    links = [
        link
        for link in db.query(KnowledgeClaimLink)
        if link.claim_id == claim_id or link.related_claim_id == claim_id
    ]
    snapshots: list[dict[str, Any]] = []
    for link in links:
        snapshots.append(link.model_dump(mode="json"))
        db.delete(link)
    return snapshots


# =============================================================================
# Claim CRUD Endpoints
# =============================================================================


@router.post("", response_model=KnowledgeClaim)
async def create_claim(
    request: ClaimCreateRequest,
    db: Database = Depends(get_library_database),
) -> KnowledgeClaim:
    """Create a new knowledge claim."""
    # Validate source document exists (manual claims have no source doc)
    if request.source_document_id is not None:
        source_doc = db.get(Document, request.source_document_id)
        if source_doc is None:
            raise HTTPException(
                status_code=404,
                detail=f"Source document not found: {request.source_document_id}",
            )

    # Validate entity IDs exist
    missing_entities = [
        entity_id
        for entity_id in request.entity_ids
        if db.get(KnowledgeEntity, entity_id) is None
    ]
    if missing_entities:
        raise HTTPException(
            status_code=404, detail=f"Unknown entities: {missing_entities}"
        )

    # Auto-derive predicate_canonical + heuristic attribution to mirror
    # the extractor pipeline (#1123). Without this, manually-created
    # claims would be missing the canonicalisation that extractor-
    # created claims get for free, and the inspector / SPARQL views
    # would treat the two writers' output differently. We import the
    # helpers from `_entity_writer` so there's one source of truth.
    from fichero.kg._common import canonical_verb as _canonical_verb
    from fichero.workflows.tools._entity_writer import (
        _detect_audience,
        _detect_quotation_kind,
        _detect_speaker,
    )

    predicate_canonical = _canonical_verb(request.predicate_verb)
    quotation_kind = request.quotation_kind or _detect_quotation_kind(
        request.predicate_verb, request.source_excerpt
    )
    speaker_name = request.speaker_name or _detect_speaker(
        request.text, request.source_excerpt
    )
    audience = request.audience or _detect_audience(
        request.text, request.source_excerpt
    )
    source_language = request.source_language or request.language

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
        # SVO + canonical predicate
        subject_canonical=request.subject_canonical,
        subject_entity_id=request.subject_entity_id,
        predicate_verb=request.predicate_verb,
        predicate_canonical=predicate_canonical,
        object_phrase=request.object_phrase,
        # #1123 attribution — explicit request fields win over heuristics.
        speaker_name=speaker_name,
        speaker_entity_id=request.speaker_entity_id,
        subject_of_inquiry_entity_id=request.subject_of_inquiry_entity_id,
        scribe_name=request.scribe_name,
        scribe_entity_id=request.scribe_entity_id,
        editor_name=request.editor_name,
        editor_entity_id=request.editor_entity_id,
        quotation_kind=quotation_kind,
        provenance_layer=request.provenance_layer,
        source_language=source_language,
        translation_chain=request.translation_chain,
        audience=audience,
        source_genre=request.source_genre,
        claim_recorded_at=request.claim_recorded_at,
        claim_geo=request.claim_geo,
        confidence_source=request.confidence_source,
    )
    db.save(claim)
    return claim


@router.patch("/{claim_id}", response_model=KnowledgeClaim)
async def patch_claim(
    claim_id: str,
    request: ClaimPatchRequest,
    db: Database = Depends(get_library_database),
) -> KnowledgeClaim:
    """Update an existing knowledge claim."""
    claim = db.get(KnowledgeClaim, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail=f"Claim not found: {claim_id}")

    data = request.model_dump(exclude_unset=True)
    _validate_claim_references(db, data)
    _apply_claim_patch(claim, data)
    db.save(claim)
    return claim


@router.post("/resolve-source", response_model=ClaimSourceResolveResponse)
async def resolve_claim_source(
    request: ClaimSourceResolveRequest,
    db: Database = Depends(get_library_database),
) -> ClaimSourceResolveResponse:
    """Resolve claim/SVO selectors to exact source provenance anchor."""
    selected: KnowledgeClaim | None = None

    if request.claim_id:
        selected = db.get(KnowledgeClaim, request.claim_id)
        if selected is None:
            raise HTTPException(status_code=404, detail=f"Claim not found: {request.claim_id}")
    else:
        if not (request.subject_canonical and request.predicate_verb and request.object_phrase):
            raise HTTPException(
                status_code=400,
                detail="Provide claim_id, or full SVO fields (subject_canonical, predicate_verb, object_phrase).",
            )
        candidates = [
            claim
            for claim in db.all(KnowledgeClaim)
            if (claim.subject_canonical or "").strip().lower() == request.subject_canonical.strip().lower()
            and (claim.predicate_verb or "").strip().lower() == request.predicate_verb.strip().lower()
            and (claim.object_phrase or "").strip().lower() == request.object_phrase.strip().lower()
            and (
                request.source_document_id is None
                or claim.source_document_id == request.source_document_id
            )
        ]
        if not candidates:
            raise HTTPException(status_code=404, detail="No matching claim for supplied SVO.")
        # Prefer exact-span anchors for click-through, then newest update.
        candidates.sort(
            key=lambda claim: (
                claim.source_char_start is None or claim.source_char_end is None,
                -(claim.updated_at.timestamp() if claim.updated_at else 0.0),
            )
        )
        selected = candidates[0]

    return ClaimSourceResolveResponse(
        claim_id=selected.id,
        source_document_id=selected.source_document_id,
        source_page_label=selected.source_page_label,
        source_char_start=selected.source_char_start,
        source_char_end=selected.source_char_end,
        source_excerpt=selected.source_excerpt,
        subject_canonical=selected.subject_canonical,
        predicate_verb=selected.predicate_verb,
        object_phrase=selected.object_phrase,
    )


@router.get("/{claim_id}", response_model=KnowledgeClaim)
async def get_claim(
    claim_id: str,
    db: Database = Depends(get_library_database),
) -> KnowledgeClaim:
    """Get a knowledge claim by ID."""
    claim = db.get(KnowledgeClaim, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail=f"Claim not found: {claim_id}")
    return claim


@router.delete("/{claim_id}", status_code=204)
async def delete_claim(
    claim_id: str,
    db: Database = Depends(get_library_database),
) -> None:
    """Hard-delete a single knowledge claim.

    Entities referenced by the claim's ``entity_ids`` are not
    touched — the entity is the bigger concept, the claim is one
    piece of evidence about it. Use ``DELETE /api/entities/{id}``
    to remove the entity itself. (#901)
    """
    claim = db.get(KnowledgeClaim, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail=f"Claim not found: {claim_id}")
    before_state = claim.model_dump(mode="json")
    deleted_links = _delete_claim_links_for_claim(db, claim_id)
    db.delete(claim)

    # Mutation log row for undo. (#901)
    try:
        db.save(MutationLog(
            entity_type="KnowledgeClaim",
            entity_id=claim_id,
            operation=MutationOperationType.delete,
            before_state={**before_state, "deleted_claim_links": deleted_links},
            after_state=None,
        ))
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning(
            "delete_claim: mutation log write failed: %s", exc
        )


# =============================================================================
# Claim Listing and Filtering
# =============================================================================


def _normalize_text(value: str | None) -> str:
    """Normalize text for comparison."""
    return (value or "").strip().lower()


def _descendant_doc_ids(db: Database, root_id: str) -> set[str]:
    """Collect the doc id and every descendant doc id (BFS), so callers
    can scope KG queries to "everything under this folder" — claims are
    written to PAGE doc ids by extract_all, not the folder, so a folder
    KG view that only filters by source_document_id=<folder> returns
    empty even when descendants have rich entities (#826)."""
    from fichero.models import Document
    seen: set[str] = {root_id}
    frontier: list[str] = [root_id]
    while frontier:
        next_frontier: list[str] = []
        for parent_id in frontier:
            children = db.query(Document, parent_id=parent_id) or []
            for child in children:
                if child.id and child.id not in seen:
                    seen.add(child.id)
                    next_frontier.append(child.id)
        frontier = next_frontier
    return seen


@router.get("", response_model=ClaimListResponse)
async def list_claims(
    q: Annotated[str | None, Query()] = None,
    entity_id: Annotated[str | None, Query()] = None,
    curated_only: Annotated[bool, Query()] = False,
    curation_state: Annotated[ClaimCurationState | None, Query()] = None,
    claim_type: Annotated[ClaimType | None, Query()] = None,
    epistemic_status: Annotated[EpistemicStatus | None, Query()] = None,
    source_document_id: Annotated[str | None, Query()] = None,
    include_descendants: Annotated[bool, Query()] = False,
    source_language: Annotated[str | None, Query()] = None,
    source_type: Annotated[SourceType | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Database = Depends(get_library_database),
) -> ClaimListResponse:
    """List knowledge claims with optional filtering.

    When ``include_descendants=true`` is combined with
    ``source_document_id=<folder_id>``, claims for the folder AND every
    descendant doc are returned — required by the folder KG view
    because extract_all writes claims to PAGE docs, not the container
    (#826).
    """
    claims = db.all(KnowledgeClaim)

    # Apply filters
    if q:
        needle = _normalize_text(q)
        claims = [c for c in claims if needle in _normalize_text(c.text)]
    if entity_id:
        claims = [c for c in claims if entity_id in c.entity_ids]
    if curated_only:
        claims = [c for c in claims if c.curation_state == ClaimCurationState.curated]
    if curation_state:
        claims = [c for c in claims if c.curation_state == curation_state]
    if claim_type:
        claims = [c for c in claims if c.claim_type == claim_type]
    if epistemic_status:
        claims = [c for c in claims if c.epistemic_status == epistemic_status]
    if source_document_id:
        if include_descendants:
            doc_ids = _descendant_doc_ids(db, source_document_id)
            claims = [c for c in claims if c.source_document_id in doc_ids]
        else:
            claims = [c for c in claims if c.source_document_id == source_document_id]
    if source_language:
        claims = [c for c in claims if source_language in c.source_languages]
    if source_type:
        claims = [c for c in claims if c.source_type == source_type]

    items = claims[offset : offset + limit]
    return ClaimListResponse(items=items, count=len(items))
