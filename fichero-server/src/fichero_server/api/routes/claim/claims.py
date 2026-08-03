"""Claims API - Canonical FastAPI routes for knowledge claims.

This module implements dedicated routes for knowledge claim operations,
providing a clean separation from the broader knowledge graph functionality.
"""

from __future__ import annotations

from fichero_server.core.timeutil import utc_now
import re
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from fichero_server.api.library_header import require_library_path
from fichero_server.api.auth import action_context, request_actor
from fichero_server.api.change_stream import emit_change
from fichero_server.api.main import get_library_database, get_library_database_for_write
from fichero_server.actions.registry import registry
from fichero_server.db import Database
from fichero_server.models.knowledge import (
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
from fichero_server.models import Document
from fichero_server.models import ClaimListResponse

router = APIRouter(prefix="/claims", tags=["claims"])


def _resolve_action_ctx(
    ctx: "ActionContext" | object,
    *,
    actor: str | object = "system",
    library_path: str | object | None = None,
    origin_window: str | object | None = None,
) -> "ActionContext":
    if isinstance(ctx, ActionContext):
        return ctx
    resolved_actor = actor if isinstance(actor, str) else "system"
    resolved_library_path = library_path if isinstance(library_path, str) else None
    resolved_origin_window = (
        origin_window if isinstance(origin_window, str) else None
    )
    return ActionContext(
        actor=resolved_actor,
        library_path=resolved_library_path,
        origin_window=resolved_origin_window,
    )


def _emit_claim_change_ctx(
    ctx: "ActionContext",
    *,
    event_type: str,
    claim_ids: list[str],
    entity_ids: list[str] | None = None,
) -> None:
    if not ctx.library_path or not claim_ids:
        return
    emit_change(
        ctx.library_path,
        type=event_type,
        claim_ids=claim_ids,
        entity_ids=list(entity_ids or []),
        actor=ctx.actor,
        origin_window=ctx.origin_window,
        origin_user=ctx.actor,
    )


def _emit_claim_change_spec(ctx: "ActionContext", spec: "ChangeSpec") -> None:
    if spec.emit_type is None:
        return
    _emit_claim_change_ctx(
        ctx,
        event_type=spec.emit_type,
        claim_ids=list(spec.claim_ids),
        entity_ids=list(spec.entity_ids),
    )


# =============================================================================
# Request/Response Models
# =============================================================================


class ClaimCreateRequest(BaseModel):
    """Request to create a knowledge claim."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)
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

    model_config = ConfigDict(extra="forbid")

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


class ClaimAssignTimePeriodRequest(BaseModel):
    """Bulk-assign a temporal scope to claims for timeline population."""

    source_document_id: str
    include_descendants: bool = False
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    time_start: str
    time_end: str | None = None
    time_precision: str | None = None
    overwrite_existing: bool = True


class ClaimAssignTimePeriodResponse(BaseModel):
    matched_count: int
    updated_count: int
    skipped_existing_count: int
    skipped_unparseable_page_label_count: int = 0


class ClaimAssignTimePeriodFromMetadataRequest(BaseModel):
    """Bulk-assign time period using metadata date on a source document."""

    source_document_id: str
    include_descendants: bool = False
    overwrite_existing: bool = True


class ClaimAssignTimePeriodFromMetadataResponse(ClaimAssignTimePeriodResponse):
    time_start: str
    time_end: str
    source_field: str


_DATE_FIELDS = (
    "publication_date",
    "date",
    "issued",
    "year",
    "publication_year",
    "time_start",
)


def _normalize_date_value(raw: Any) -> str | None:
    value = str(raw or "").strip()
    if not value:
        return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return value
    if re.fullmatch(r"\d{4}-\d{2}", value):
        return f"{value}-01"
    if re.fullmatch(r"\d{4}", value):
        return f"{value}-01-01"
    return None


def _resolve_metadata_date(doc: Document) -> tuple[str, str] | None:
    """Return (field_name, normalized_iso_date) when metadata has a date."""
    for field in _DATE_FIELDS:
        normalized = _normalize_date_value((doc.metadata or {}).get(field))
        if normalized:
            return field, normalized
    for field in _DATE_FIELDS:
        normalized = _normalize_date_value((doc.source_metadata or {}).get(field))
        if normalized:
            return f"source_metadata.{field}", normalized
    return None


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
    from fichero_server.kg._common import canonical_verb

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
    claim.updated_at = utc_now()


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
# Claim mutation impls — the proven business logic, extracted so BOTH the route
# handler and the audited action (EPIC #1848 / #2014) drive the SAME code
# (iterate-not-replace: wrapped, never re-derived). Emission to the observable
# layer stays with the caller (route OR registry.invoke). Each raises
# HTTPException on bad input exactly as the route did.
# =============================================================================


def create_claim_impl(db: Database, request: ClaimCreateRequest) -> KnowledgeClaim:
    """Create + persist a knowledge claim (validation + heuristic attribution)."""
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
    from fichero_server.kg._common import canonical_verb as _canonical_verb
    from fichero_server.workflows.tools._entity_writer import (
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

    now = utc_now()
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


def patch_claim_impl(
    db: Database,
    claim_id: str,
    request: ClaimPatchRequest,
    actor: str | None = None,
) -> tuple[KnowledgeClaim, dict[str, Any]]:
    """Apply a patch to an existing claim. Returns (claim, before_snapshot).

    An edit that changes what the claim *says* also records who said so and
    what reading was corrected away from (#4499). Without the second half, a
    later extraction reproducing the pre-edit reading matches nothing and is
    filed as a second claim, leaving the archive asserting both the correction
    and the thing it corrected. Provenance is stamped through #4415's guard —
    the same mechanism dates (#3322 5b) and catalogue re-runs already use.
    """
    from fichero_server.workflows.curation_guard import record_superseded, stamp
    from fichero_server.workflows.tools._entity_writer import claim_identity_snapshot

    claim = db.get(KnowledgeClaim, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail=f"Claim not found: {claim_id}")

    before = claim.model_dump(mode="json")
    prior_identity = claim_identity_snapshot(claim)
    data = request.model_dump(exclude_unset=True)
    _validate_claim_references(db, data)
    _apply_claim_patch(claim, data)

    # A patch that only touches, say, curation_state has not corrected any
    # reading, so it leaves no superseded entry — the guard must fire on
    # corrections, not on every save.
    if claim_identity_snapshot(claim) != prior_identity:
        source = _curation_source_for_actor(actor)
        stamp(claim, source=source, actor=actor, basis="claim.patch")
        if source.is_curated:
            # Only a correction supersedes a reading. A rewrite by the
            # pipeline's own actors is tool output being refreshed, and
            # recording it here would let a tool freeze its own results.
            record_superseded(claim, identity=prior_identity)

    db.save(claim)
    return claim, before


def _curation_source_for_actor(actor: str | None):
    """Which provenance an edit by ``actor`` carries.

    Agents curate through audited routes as user accounts, so their
    corrections are corrections; only the pipeline driving this route on its
    own behalf is tool output.

    ``"system"`` is *not* read as a machine here, unlike in the audit-table
    derivation: on a single-user library nobody is signed in, so an edit
    arriving through this route carries that actor and is nonetheless a person
    at the loopback owner's keyboard. It stamps ``unknown`` — protected, and
    honest that we cannot name who it was rather than guessing either way.
    Reading it as ``tool`` would leave the single-user case, which is most of
    them, with no correction survival at all.
    """
    from fichero_server.workflows.curation_guard import CurationSource

    if actor == "workflow":
        return CurationSource.tool
    if not actor or actor == "system":
        return CurationSource.unknown
    return CurationSource.user


def delete_claim_impl(
    db: Database, claim_id: str, actor: str
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    """Hard-delete a claim + its orphaning links.

    Returns ``(claim_before, deleted_link_snapshots, affected_entity_ids)`` so
    the caller can emit + so the audited action can invert to ``claim.restore``.
    """
    claim = db.get(KnowledgeClaim, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail=f"Claim not found: {claim_id}")
    before_state = claim.model_dump(mode="json")
    affected_entity_ids = list(claim.entity_ids or [])
    deleted_links = _delete_claim_links_for_claim(db, claim_id)
    db.delete(claim)

    # Mutation log row for undo. (#901)
    try:
        db.save(
            MutationLog(
                entity_type="KnowledgeClaim",
                entity_id=claim_id,
                operation=MutationOperationType.delete,
                before_state={**before_state, "deleted_claim_links": deleted_links},
                after_state=None,
                # #4415: name the actor; never let it default.
                created_by=actor,
            )
        )
    except Exception as exc:
        import logging

        logging.getLogger(__name__).warning(
            "delete_claim: mutation log write failed: %s", exc
        )
    return before_state, deleted_links, affected_entity_ids


def restore_claim_impl(
    db: Database,
    *,
    snapshot: dict[str, Any],
    link_snapshots: list[dict[str, Any]] | None = None,
) -> KnowledgeClaim:
    """Re-create a claim (and any deleted links) from JSON snapshots.

    The inverse of ``patch_claim_impl`` / ``delete_claim_impl``: it reuses the
    proven ``model_validate`` round-trip so undo restores the exact pre-mutation
    row rather than re-deriving a field diff.
    """
    claim = KnowledgeClaim.model_validate(snapshot)
    db.save(claim)
    for link_snapshot in link_snapshots or []:
        db.save(KnowledgeClaimLink.model_validate(link_snapshot))
    return claim


def assign_time_period_impl(
    db: Database, request: "ClaimAssignTimePeriodRequest"
) -> tuple["ClaimAssignTimePeriodResponse", list[str]]:
    """Bulk-assign a temporal scope to claims. Returns (response, updated_ids)."""
    source_doc = db.get(Document, request.source_document_id)
    if source_doc is None:
        raise HTTPException(
            status_code=404,
            detail=f"Source document not found: {request.source_document_id}",
        )
    if (
        request.page_start is not None
        and request.page_end is not None
        and request.page_start > request.page_end
    ):
        raise HTTPException(
            status_code=422,
            detail="page_start must be <= page_end",
        )

    if request.include_descendants:
        scope_ids = _descendant_doc_ids(db, request.source_document_id)
    else:
        scope_ids = {request.source_document_id}

    matched = 0
    updated = 0
    skipped_existing = 0
    skipped_unparseable_page_label = 0
    updated_ids: list[str] = []

    for claim in db.all(KnowledgeClaim):
        if claim.source_document_id not in scope_ids:
            continue
        if request.page_start is not None or request.page_end is not None:
            page_no = _page_number(claim.source_page_label)
            if page_no is None:
                skipped_unparseable_page_label += 1
                continue
            if request.page_start is not None and page_no < request.page_start:
                continue
            if request.page_end is not None and page_no > request.page_end:
                continue

        matched += 1
        if not request.overwrite_existing and claim.time_start:
            skipped_existing += 1
            continue

        claim.time_start = request.time_start
        claim.time_end = request.time_end or request.time_start
        claim.time_precision = request.time_precision
        claim.updated_at = utc_now()
        db.save(claim)
        updated += 1
        updated_ids.append(claim.id)

    return (
        ClaimAssignTimePeriodResponse(
            matched_count=matched,
            updated_count=updated,
            skipped_existing_count=skipped_existing,
            skipped_unparseable_page_label_count=skipped_unparseable_page_label,
        ),
        updated_ids,
    )


def assign_time_period_from_metadata_impl(
    db: Database, request: "ClaimAssignTimePeriodFromMetadataRequest"
) -> tuple["ClaimAssignTimePeriodFromMetadataResponse", list[str]]:
    """Assign claim dates from the source document's metadata date field.

    Returns (response, updated_ids). Sibling of ``assign_time_period_impl``
    (fix-then-sweep): same shape, but the date comes from the source document's
    metadata rather than a caller-supplied value.
    """
    source_doc = db.get(Document, request.source_document_id)
    if source_doc is None:
        raise HTTPException(
            status_code=404,
            detail=f"Source document not found: {request.source_document_id}",
        )
    resolved = _resolve_metadata_date(source_doc)
    if resolved is None:
        raise HTTPException(
            status_code=422,
            detail="No supported date field found on source document metadata",
        )
    source_field, date_value = resolved

    scoped_ids = (
        _descendant_doc_ids(db, request.source_document_id)
        if request.include_descendants
        else {request.source_document_id}
    )
    matched = 0
    updated = 0
    skipped_existing = 0
    updated_ids: list[str] = []
    for claim in db.all(KnowledgeClaim):
        if claim.source_document_id not in scoped_ids:
            continue
        matched += 1
        if not request.overwrite_existing and claim.time_start:
            skipped_existing += 1
            continue
        claim.time_start = date_value
        claim.time_end = date_value
        claim.time_precision = "metadata"
        claim.updated_at = utc_now()
        db.save(claim)
        updated += 1
        updated_ids.append(claim.id)

    return (
        ClaimAssignTimePeriodFromMetadataResponse(
            matched_count=matched,
            updated_count=updated,
            skipped_existing_count=skipped_existing,
            time_start=date_value,
            time_end=date_value,
            source_field=source_field,
        ),
        updated_ids,
    )


# =============================================================================
# Claim CRUD Endpoints
# =============================================================================


@router.post("", response_model=KnowledgeClaim)
async def create_claim(
    request: ClaimCreateRequest,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str | object = Depends(require_library_path),
    x_fichero_origin_window: str | object | None = Header(
        default=None, alias="X-Fichero-Origin-Window"
    ),
    actor: str | object = Depends(request_actor),
    ctx: "ActionContext" = Depends(action_context),
) -> KnowledgeClaim:
    """Create a new knowledge claim."""
    ctx = _resolve_action_ctx(
        ctx,
        actor=actor,
        library_path=x_fichero_library_path,
        origin_window=x_fichero_origin_window,
    )
    result = registry.invoke(
        db,
        "claim.create",
        request.model_dump(mode="json"),
        ctx,
    )
    return KnowledgeClaim.model_validate(result.result)


@router.patch("/{claim_id}", response_model=KnowledgeClaim)
async def patch_claim(
    claim_id: str,
    request: ClaimPatchRequest,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str | object = Depends(require_library_path),
    x_fichero_origin_window: str | object | None = Header(
        default=None, alias="X-Fichero-Origin-Window"
    ),
    actor: str | object = Depends(request_actor),
    ctx: "ActionContext" = Depends(action_context),
) -> KnowledgeClaim:
    """Update an existing knowledge claim."""
    ctx = _resolve_action_ctx(
        ctx,
        actor=actor,
        library_path=x_fichero_library_path,
        origin_window=x_fichero_origin_window,
    )
    result = registry.invoke(
        db,
        "claim.patch",
        {
            "claim_id": claim_id,
            "patch": request.model_dump(mode="json", exclude_unset=True),
        },
        ctx,
    )
    return KnowledgeClaim.model_validate(result.result)


@router.post("/resolve-source", response_model=ClaimSourceResolveResponse)
async def resolve_claim_source(
    request: ClaimSourceResolveRequest,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str = Depends(require_library_path),
    x_fichero_origin_window: str | None = Header(
        default=None, alias="X-Fichero-Origin-Window"
    ),
    actor: str = Depends(request_actor),
) -> ClaimSourceResolveResponse:
    """Resolve claim/SVO selectors to exact source provenance anchor."""
    selected: KnowledgeClaim | None = None

    if request.claim_id:
        selected = db.get(KnowledgeClaim, request.claim_id)
        if selected is None:
            raise HTTPException(
                status_code=404, detail=f"Claim not found: {request.claim_id}"
            )
    else:
        if not (
            request.subject_canonical
            and request.predicate_verb
            and request.object_phrase
        ):
            raise HTTPException(
                status_code=400,
                detail="Provide claim_id, or full SVO fields (subject_canonical, predicate_verb, object_phrase).",
            )
        candidates = [
            claim
            for claim in db.all(KnowledgeClaim)
            if (claim.subject_canonical or "").strip().lower()
            == request.subject_canonical.strip().lower()
            and (claim.predicate_verb or "").strip().lower()
            == request.predicate_verb.strip().lower()
            and (claim.object_phrase or "").strip().lower()
            == request.object_phrase.strip().lower()
            and (
                request.source_document_id is None
                or claim.source_document_id == request.source_document_id
            )
        ]
        if not candidates:
            raise HTTPException(
                status_code=404, detail="No matching claim for supplied SVO."
            )
        # Prefer exact-span anchors for click-through, then newest update.
        candidates.sort(
            key=lambda claim: (
                claim.source_char_start is None or claim.source_char_end is None,
                -(claim.updated_at.timestamp() if claim.updated_at else 0.0),
            )
        )
        selected = candidates[0]

    emit_change(
        x_fichero_library_path,
        type="claim.updated",
        claim_ids=[selected.id],
        actor=actor,
        origin_window=x_fichero_origin_window,
        origin_user=actor,
    )

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
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str | object = Depends(require_library_path),
    x_fichero_origin_window: str | object | None = Header(
        default=None, alias="X-Fichero-Origin-Window"
    ),
    actor: str | object = Depends(request_actor),
    ctx: "ActionContext" = Depends(action_context),
) -> None:
    """Hard-delete a single knowledge claim.

    Entities referenced by the claim's ``entity_ids`` are not
    touched — the entity is the bigger concept, the claim is one
    piece of evidence about it. Use ``DELETE /api/entities/{id}``
    to remove the entity itself. (#901)
    """
    ctx = _resolve_action_ctx(
        ctx,
        actor=actor,
        library_path=x_fichero_library_path,
        origin_window=x_fichero_origin_window,
    )
    registry.invoke(db, "claim.delete", {"claim_id": claim_id}, ctx)


# =============================================================================
# Claim Listing and Filtering
# =============================================================================


def _normalize_text(value: str | None) -> str:
    """Normalize text for comparison."""
    return (value or "").strip().lower()


def _page_number(value: str | None) -> int | None:
    if not value:
        return None
    digits = "".join(ch for ch in value if ch.isdigit())
    return int(digits) if digits else None


def _descendant_doc_ids(db: Database, root_id: str) -> set[str]:
    """Collect the doc id and every descendant doc id (BFS), so callers
    can scope KG queries to "everything under this folder" — claims are
    written to PAGE doc ids by extract_all, not the folder, so a folder
    KG view that only filters by source_document_id=<folder> returns
    empty even when descendants have rich entities (#826)."""
    from fichero_server.models import Document

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


@router.post("/assign-time-period", response_model=ClaimAssignTimePeriodResponse)
async def assign_time_period(
    request: ClaimAssignTimePeriodRequest,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str = Depends(require_library_path),
    x_fichero_origin_window: str | None = Header(
        default=None, alias="X-Fichero-Origin-Window"
    ),
    actor: str = Depends(request_actor),
) -> ClaimAssignTimePeriodResponse:
    """Assign a user-curated period to many claims at once.

    This powers timeline seeding from user decisions (page range / folder scope)
    by writing directly into `KnowledgeClaim.time_start/time_end`.
    """
    response, updated_ids = assign_time_period_impl(db, request)

    if updated_ids:
        emit_change(
            x_fichero_library_path,
            type="claim.updated",
            claim_ids=updated_ids,
            actor=actor,
            origin_window=x_fichero_origin_window,
            origin_user=actor,
        )

    return response


@router.post(
    "/assign-time-period-from-metadata",
    response_model=ClaimAssignTimePeriodFromMetadataResponse,
)
async def assign_time_period_from_metadata(
    request: ClaimAssignTimePeriodFromMetadataRequest,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str = Depends(require_library_path),
    x_fichero_origin_window: str | None = Header(
        default=None, alias="X-Fichero-Origin-Window"
    ),
    actor: str = Depends(request_actor),
) -> ClaimAssignTimePeriodFromMetadataResponse:
    """Assign claim dates from the source document's metadata date field."""
    response, updated_ids = assign_time_period_from_metadata_impl(db, request)

    if updated_ids:
        emit_change(
            x_fichero_library_path,
            type="claim.updated",
            claim_ids=updated_ids,
            actor=actor,
            origin_window=x_fichero_origin_window,
            origin_user=actor,
        )

    return response


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


# =============================================================================
# Action layer registration (EPIC #1848 / #2014) — claim CRUD + time-period.
# =============================================================================
#
# Each action WRAPS the proven ``*_impl`` above (iterate-not-replace) and routes
# through ``registry.invoke`` so chat tools / App Intents / tests / the audit
# log share ONE path with the typed routes. The routes themselves are untouched
# (they call the same ``*_impl`` directly and emit), matching the entity.merge
# pilot in ``kg_entity_curation.py``.
#
# Undo is data, not code: ``ChangeSpec.before/after`` becomes the ActionAudit
# payload, and ``invert(before, after)`` derives the inverse action. The
# reversible pairs here:
#   * claim.create -> claim.delete
#   * claim.patch  -> claim.restore   (restore the before-snapshot)
#   * claim.delete -> claim.restore   (restore claim + its deleted links)

from fichero_server.actions.registry import action, ActionContext, ChangeSpec  # noqa: E402


class ClaimDeleteParams(BaseModel):
    """Params for claim.delete — also the inverse of claim.create."""

    claim_id: str = Field(description="Claim id to hard-delete")


class ClaimPatchActionParams(BaseModel):
    """Params for claim.patch — the path claim_id + the partial patch body.

    ``patch`` is a nested :class:`ClaimPatchRequest` so the registry's
    ``model_validate`` preserves exclude-unset semantics: only fields actually
    present in the request are applied (a ``None`` the caller sent is honoured;
    a field omitted entirely is left untouched).
    """

    claim_id: str = Field(description="Claim id to patch")
    patch: ClaimPatchRequest = Field(description="Partial claim update")


class ClaimRestoreParams(BaseModel):
    """Params for claim.restore — re-create a claim (+ its links) from snapshots."""

    snapshot: dict[str, Any] = Field(description="KnowledgeClaim.model_dump snapshot")
    link_snapshots: list[dict[str, Any]] = Field(
        default_factory=list,
        description="KnowledgeClaimLink snapshots deleted alongside the claim.",
    )


def _invert_create_claim(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    if not after:
        return None
    claim_id = after.get("claim_id")
    if not claim_id:
        return None
    return ("claim.delete", {"claim_id": claim_id})


def _invert_patch_claim(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    if not before:
        return None
    return ("claim.restore", {"snapshot": before})


def _invert_delete_claim(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    if not before:
        return None
    return (
        "claim.restore",
        {
            "snapshot": before.get("claim", {}),
            "link_snapshots": before.get("deleted_links", []),
        },
    )


@action(
    "claim.create",
    ClaimCreateRequest,
    domains=["claim"],
    undoable=True,
    invert=_invert_create_claim,
)
def _action_create_claim(
    db: Database, params: ClaimCreateRequest, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    claim = create_claim_impl(db, params)
    entity_ids = list(claim.entity_ids or [])
    spec = ChangeSpec(
        domains=["claim"],
        target_ids=[claim.id],
        after={"claim_id": claim.id},
        emit_type="claim.updated",
        claim_ids=[claim.id],
        entity_ids=entity_ids,
        emit_fn=_emit_claim_change_spec,
    )
    return claim.model_dump(mode="json"), spec


@action(
    "claim.patch",
    ClaimPatchActionParams,
    domains=["claim"],
    undoable=True,
    invert=_invert_patch_claim,
)
def _action_patch_claim(
    db: Database, params: ClaimPatchActionParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    claim, before = patch_claim_impl(db, params.claim_id, params.patch, actor=ctx.actor)
    spec = ChangeSpec(
        domains=["claim"],
        target_ids=[claim.id],
        before=before,
        after=claim.model_dump(mode="json"),
        emit_type="claim.updated",
        claim_ids=[claim.id],
        entity_ids=list(claim.entity_ids or []),
        emit_fn=_emit_claim_change_spec,
    )
    return claim.model_dump(mode="json"), spec


@action(
    "claim.delete",
    ClaimDeleteParams,
    domains=["claim"],
    undoable=True,
    invert=_invert_delete_claim,
)
def _action_delete_claim(
    db: Database, params: ClaimDeleteParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    before_state, deleted_links, affected_entity_ids = delete_claim_impl(
        db, params.claim_id, ctx.actor
    )
    spec = ChangeSpec(
        domains=["claim"],
        target_ids=[params.claim_id],
        before={"claim": before_state, "deleted_links": deleted_links},
        after=None,
        emit_type="claim.deleted",
        claim_ids=[params.claim_id],
        entity_ids=affected_entity_ids,
        emit_fn=_emit_claim_change_spec,
    )
    return {"deleted_claim_id": params.claim_id}, spec


@action(
    "claim.restore",
    ClaimRestoreParams,
    domains=["claim"],
    undoable=False,
)
def _action_restore_claim(
    db: Database, params: ClaimRestoreParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    claim = restore_claim_impl(
        db, snapshot=params.snapshot, link_snapshots=params.link_snapshots
    )
    spec = ChangeSpec(
        domains=["claim"],
        target_ids=[claim.id],
        after=claim.model_dump(mode="json"),
        emit_type="claim.updated",
        claim_ids=[claim.id],
        entity_ids=list(claim.entity_ids or []),
    )
    return claim.model_dump(mode="json"), spec


@action(
    "claim.assign_time_period",
    ClaimAssignTimePeriodRequest,
    domains=["claim"],
    undoable=False,
)
def _action_assign_time_period(
    db: Database, params: ClaimAssignTimePeriodRequest, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    response, updated_ids = assign_time_period_impl(db, params)
    spec = ChangeSpec(
        domains=["claim"],
        target_ids=updated_ids,
        after=response.model_dump(mode="json"),
        emit_type="claim.updated" if updated_ids else None,
        claim_ids=updated_ids,
    )
    return response.model_dump(mode="json"), spec


@action(
    "claim.assign_time_period_from_metadata",
    ClaimAssignTimePeriodFromMetadataRequest,
    domains=["claim"],
    undoable=False,
)
def _action_assign_time_period_from_metadata(
    db: Database, params: ClaimAssignTimePeriodFromMetadataRequest, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    response, updated_ids = assign_time_period_from_metadata_impl(db, params)
    spec = ChangeSpec(
        domains=["claim"],
        target_ids=updated_ids,
        after=response.model_dump(mode="json"),
        emit_type="claim.updated" if updated_ids else None,
        claim_ids=updated_ids,
    )
    return response.model_dump(mode="json"), spec
