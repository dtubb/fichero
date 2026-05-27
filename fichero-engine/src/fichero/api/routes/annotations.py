"""User annotations API (#914).

CRUD for highlight / note / rating / bookmark / comment annotations
anchored to documents (with optional sub-page char range or bbox).
Plus the "promote to claim" action that turns a highlight into a
KnowledgeClaim with the annotation's anchor as source.
"""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from fichero.api.main import get_library_database
from fichero.db import Database
from fichero.knowledge_models import (
    Annotation,
    AnnotationKind,
    KnowledgeClaim,
)
from fichero.models import AnnotationListResponse, Document

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/annotations")


class AnnotationCreateRequest(BaseModel):
    document_id: str
    kind: AnnotationKind
    page_index: int | None = None
    page_label: str | None = None
    char_start: int | None = None
    char_end: int | None = None
    bbox: list[float] | None = None
    text: str | None = None
    rating: int | None = None
    color: str | None = None
    tags: list[str] = []
    linked_claim_ids: list[str] = []
    linked_entity_ids: list[str] = []
    linked_note_ids: list[str] = []


@router.post("", response_model=Annotation, summary="Create an annotation")
async def create_annotation(
    request: AnnotationCreateRequest,
    db: Database = Depends(get_library_database),
) -> Annotation:
    if db.get(Document, request.document_id) is None:
        raise HTTPException(404, f"Document not found: {request.document_id}")
    ann = Annotation(**request.model_dump())
    db.save(ann)
    return ann


@router.get(
    "",
    response_model=AnnotationListResponse,
    summary="List annotations, filterable by document / kind / tag",
)
async def list_annotations(
    document_id: str | None = Query(default=None),
    kind: AnnotationKind | None = Query(default=None),
    tag: str | None = Query(default=None),
    min_rating: int | None = Query(default=None, ge=1, le=5),
    db: Database = Depends(get_library_database),
) -> AnnotationListResponse:
    rows = db.query(Annotation)
    if document_id is not None:
        rows = [r for r in rows if r.document_id == document_id]
    if kind is not None:
        rows = [r for r in rows if r.kind == kind]
    if tag is not None:
        rows = [r for r in rows if tag in (r.tags or [])]
    if min_rating is not None:
        rows = [r for r in rows if r.rating is not None and r.rating >= min_rating]
    rows.sort(key=lambda r: r.created_at, reverse=True)
    return AnnotationListResponse(items=rows, count=len(rows))


@router.get("/{annotation_id}", response_model=Annotation)
async def get_annotation(
    annotation_id: str,
    db: Database = Depends(get_library_database),
) -> Annotation:
    ann = db.get(Annotation, annotation_id)
    if ann is None:
        raise HTTPException(404, f"Annotation not found: {annotation_id}")
    return ann


class AnnotationPatchRequest(BaseModel):
    text: str | None = None
    rating: int | None = None
    color: str | None = None
    tags: list[str] | None = None
    linked_claim_ids: list[str] | None = None
    linked_entity_ids: list[str] | None = None
    linked_note_ids: list[str] | None = None
    char_start: int | None = None
    char_end: int | None = None
    bbox: list[float] | None = None


@router.patch("/{annotation_id}", response_model=Annotation)
async def patch_annotation(
    annotation_id: str,
    request: AnnotationPatchRequest,
    db: Database = Depends(get_library_database),
) -> Annotation:
    ann = db.get(Annotation, annotation_id)
    if ann is None:
        raise HTTPException(404, f"Annotation not found: {annotation_id}")
    for field, value in request.model_dump(exclude_unset=True).items():
        setattr(ann, field, value)
    ann.updated_at = datetime.now()
    db.save(ann)
    return ann


@router.delete("/{annotation_id}", status_code=204)
async def delete_annotation(
    annotation_id: str,
    db: Database = Depends(get_library_database),
) -> None:
    ann = db.get(Annotation, annotation_id)
    if ann is None:
        raise HTTPException(404, f"Annotation not found: {annotation_id}")
    db.delete(ann)


@router.get(
    "/{annotation_id}/crop",
    summary="Cropped content for this annotation (text body or image bytes)",
    description=(
        "Returns the annotation's underlying content cropped to its "
        "anchor: substring for text, PNG bytes for image / PDF region. "
        "Workflow tools call this to feed only the highlighted region "
        "to vision / LLM providers instead of the whole document. (#914)"
    ),
)
async def get_crop(
    annotation_id: str,
    db: Database = Depends(get_library_database),
):
    from pathlib import Path

    from fastapi.responses import PlainTextResponse, Response

    from fichero.workflows.tools._annotation_input import (
        crop_image,
        crop_pdf_page,
        crop_text,
    )

    ann = db.get(Annotation, annotation_id)
    if ann is None:
        raise HTTPException(404, f"Annotation not found: {annotation_id}")
    doc = db.get(Document, ann.document_id)
    if doc is None:
        raise HTTPException(404, f"Document not found: {ann.document_id}")

    if doc.path and ann.bbox:
        suffix = Path(doc.path).suffix.lower()
        if suffix == ".pdf":
            png = crop_pdf_page(doc.path, ann)
            if png:
                return Response(content=png, media_type="image/png")
        elif suffix in {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp", ".heic"}:
            png = crop_image(doc.path, ann)
            if png:
                return Response(content=png, media_type="image/png")

    text = crop_text(doc, ann)
    if text is None:
        raise HTTPException(404, "No crop available for this annotation")
    return PlainTextResponse(text)


class PromoteResponse(BaseModel):
    annotation_id: str
    claim_id: str
    claim_text: str


@router.post(
    "/{annotation_id}/promote-to-claim",
    response_model=PromoteResponse,
    summary="Turn a highlight or note into a KnowledgeClaim",
    description=(
        "Creates a KnowledgeClaim using the annotation's anchor as "
        "source provenance. The claim.text defaults to the "
        "annotation.text; the source_excerpt uses the annotation's "
        "highlighted text via char_start/end + the document's "
        "page_content. The annotation is updated to point at the "
        "new claim_id."
    ),
)
async def promote_to_claim(
    annotation_id: str,
    db: Database = Depends(get_library_database),
) -> PromoteResponse:
    ann = db.get(Annotation, annotation_id)
    if ann is None:
        raise HTTPException(404, f"Annotation not found: {annotation_id}")

    # Resolve the source excerpt — prefer the highlighted span, fall
    # back to the annotation's note text.
    doc = db.get(Document, ann.document_id)
    excerpt: str | None = None
    if doc is not None and doc.page_content and ann.char_start is not None and ann.char_end is not None:
        excerpt = doc.page_content[ann.char_start : ann.char_end]
    if not excerpt:
        excerpt = ann.text

    claim_text = ann.text or excerpt or f"Annotation {ann.id}"
    claim = KnowledgeClaim(
        text=claim_text,
        source_document_id=ann.document_id,
        source_page_label=ann.page_label,
        source_char_start=ann.char_start,
        source_char_end=ann.char_end,
        source_bbox=ann.bbox,
        source_excerpt=excerpt,
        created_by=ann.created_by,
    )
    db.save(claim)

    # Link the annotation back to its claim.
    linked = set(ann.linked_claim_ids or [])
    linked.add(claim.id)
    ann.linked_claim_ids = sorted(linked)
    ann.updated_at = datetime.now()
    db.save(ann)

    return PromoteResponse(
        annotation_id=ann.id,
        claim_id=claim.id,
        claim_text=claim_text,
    )
