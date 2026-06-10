"""User annotations API (#914).

CRUD for highlight / note / rating / bookmark / comment annotations
anchored to documents (with optional sub-page char range or bbox).
Plus the "promote to claim" action that turns a highlight into a
KnowledgeClaim with the annotation's anchor as source.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel

from fichero.api.change_stream import emit_change
from fichero.api.main import get_library_database
from fichero.db import Database
from fichero.knowledge_models import (
    Annotation,
    AnnotationKind,
    KnowledgeClaim,
)
from fichero.models import AnnotationListResponse, DocType, Document
from fichero.storage import resolve_source

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/annotations")


class AnnotationCreateRequest(BaseModel):
    document_id: str | None = None
    page_id: str | None = None
    folder_id: str | None = None
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
    metadata: dict[str, Any] = {}


class AnnotationScopePayload(BaseModel):
    document_id: str | None = None
    page_id: str | None = None
    folder_id: str | None = None


def _normalize_annotation_scope(
    db: Database,
    *,
    document_id: str | None,
    page_id: str | None,
    folder_id: str | None,
) -> AnnotationScopePayload:
    if page_id and folder_id:
        raise HTTPException(
            400,
            "Annotations can be scoped to either a page or a folder, not both",
        )
    resolved_document_id = document_id
    resolved_page_id = page_id
    resolved_folder_id = folder_id

    if document_id is not None:
        document = db.get(Document, document_id)
        if document is None:
            raise HTTPException(404, f"Document not found: {document_id}")
        if document.doc_type == DocType.page:
            if resolved_page_id and resolved_page_id != document_id:
                raise HTTPException(400, "document_id and page_id must match for page-scoped annotations")
            resolved_page_id = document_id
        elif document.doc_type == DocType.folder:
            if resolved_folder_id and resolved_folder_id != document_id:
                raise HTTPException(400, "document_id and folder_id must match for folder-scoped annotations")
            resolved_folder_id = document_id

    if resolved_page_id is not None:
        page = db.get(Document, resolved_page_id)
        if page is None:
            raise HTTPException(404, f"Page not found: {resolved_page_id}")
        if page.doc_type != DocType.page:
            raise HTTPException(400, f"Document {resolved_page_id} is not a page")
        resolved_document_id = resolved_page_id

    if resolved_folder_id is not None:
        folder = db.get(Document, resolved_folder_id)
        if folder is None:
            raise HTTPException(404, f"Folder not found: {resolved_folder_id}")
        if folder.doc_type != DocType.folder:
            raise HTTPException(400, f"Document {resolved_folder_id} is not a folder")

    if resolved_document_id is None and resolved_folder_id is None:
        raise HTTPException(
            400,
            "Annotations require document_id/page_id or folder_id scope",
        )

    return AnnotationScopePayload(
        document_id=resolved_document_id,
        page_id=resolved_page_id,
        folder_id=resolved_folder_id,
    )


@router.post("", response_model=Annotation, summary="Create an annotation")
async def create_annotation(
    request: AnnotationCreateRequest,
    db: Database = Depends(get_library_database),
    x_fichero_library_path: str = Header(..., alias="X-Fichero-Library-Path"),
    x_fichero_origin_window: str | None = Header(
        default=None, alias="X-Fichero-Origin-Window"
    ),
) -> Annotation:
    scope = _normalize_annotation_scope(
        db,
        document_id=request.document_id,
        page_id=request.page_id,
        folder_id=request.folder_id,
    )
    payload = request.model_dump()
    payload.update(scope.model_dump())
    ann = Annotation(**payload)
    db.save(ann)
    emit_change(
        x_fichero_library_path,
        type="annotation.created",
        document_ids=[i for i in [ann.document_id, ann.page_id, ann.folder_id] if i],
        actor="ui",
        origin_window=x_fichero_origin_window,
    )
    return ann


@router.get(
    "",
    response_model=AnnotationListResponse,
    summary="List annotations, filterable by document / kind / tag",
)
async def list_annotations(
    document_id: str | None = Query(default=None),
    page_id: str | None = Query(default=None),
    folder_id: str | None = Query(default=None),
    kind: AnnotationKind | None = Query(default=None),
    tag: str | None = Query(default=None),
    min_rating: int | None = Query(default=None, ge=1, le=5),
    db: Database = Depends(get_library_database),
) -> AnnotationListResponse:
    rows = db.query(Annotation)
    if document_id is not None:
        rows = [
            r for r in rows
            if r.document_id == document_id
            or r.page_id == document_id
            or r.folder_id == document_id
        ]
    if page_id is not None:
        rows = [r for r in rows if r.page_id == page_id or r.document_id == page_id]
    if folder_id is not None:
        rows = [r for r in rows if r.folder_id == folder_id]
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
    document_id: str | None = None
    page_id: str | None = None
    folder_id: str | None = None
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
    metadata: dict[str, Any] | None = None


@router.patch("/{annotation_id}", response_model=Annotation)
async def patch_annotation(
    annotation_id: str,
    request: AnnotationPatchRequest,
    db: Database = Depends(get_library_database),
    x_fichero_library_path: str = Header(..., alias="X-Fichero-Library-Path"),
    x_fichero_origin_window: str | None = Header(
        default=None, alias="X-Fichero-Origin-Window"
    ),
) -> Annotation:
    ann = db.get(Annotation, annotation_id)
    if ann is None:
        raise HTTPException(404, f"Annotation not found: {annotation_id}")
    updates = request.model_dump(exclude_unset=True)
    if (
        "document_id" in updates
        or "page_id" in updates
        or "folder_id" in updates
    ):
        scope = _normalize_annotation_scope(
            db,
            document_id=updates.get("document_id", ann.document_id),
            page_id=updates.get("page_id", ann.page_id),
            folder_id=updates.get("folder_id", ann.folder_id),
        )
        updates.update(scope.model_dump())
    for field, value in updates.items():
        setattr(ann, field, value)
    ann.updated_at = datetime.now()
    db.save(ann)
    emit_change(
        x_fichero_library_path,
        type="annotation.updated",
        document_ids=[i for i in [ann.document_id, ann.page_id, ann.folder_id] if i],
        actor="ui",
        origin_window=x_fichero_origin_window,
    )
    return ann


@router.delete("/{annotation_id}", status_code=204)
async def delete_annotation(
    annotation_id: str,
    db: Database = Depends(get_library_database),
    x_fichero_library_path: str = Header(..., alias="X-Fichero-Library-Path"),
    x_fichero_origin_window: str | None = Header(
        default=None, alias="X-Fichero-Origin-Window"
    ),
) -> None:
    ann = db.get(Annotation, annotation_id)
    if ann is None:
        raise HTTPException(404, f"Annotation not found: {annotation_id}")
    document_ids = [i for i in [ann.document_id, ann.page_id, ann.folder_id] if i]
    db.delete(ann)
    emit_change(
        x_fichero_library_path,
        type="annotation.deleted",
        document_ids=document_ids,
        actor="ui",
        origin_window=x_fichero_origin_window,
    )


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
    from fastapi.responses import PlainTextResponse, Response

    from fichero.workflows.tools._annotation_input import (
        crop_image,
        crop_pdf_page,
        crop_text,
    )

    ann = db.get(Annotation, annotation_id)
    if ann is None:
        raise HTTPException(404, f"Annotation not found: {annotation_id}")
    if ann.document_id is None:
        raise HTTPException(400, "Folder-scoped annotations do not have crop content")
    doc = db.get(Document, ann.document_id)
    if doc is None:
        raise HTTPException(404, f"Document not found: {ann.document_id}")

    source_path = resolve_source(doc, library_root=db.path.parent)
    if source_path and ann.bbox:
        suffix = source_path.suffix.lower()
        if suffix == ".pdf":
            png = crop_pdf_page(str(source_path), ann)
            if png:
                return Response(content=png, media_type="image/png")
        elif suffix in {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp", ".heic"}:
            png = crop_image(str(source_path), ann)
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
    x_fichero_library_path: str = Header(..., alias="X-Fichero-Library-Path"),
    x_fichero_origin_window: str | None = Header(
        default=None, alias="X-Fichero-Origin-Window"
    ),
) -> PromoteResponse:
    ann = db.get(Annotation, annotation_id)
    if ann is None:
        raise HTTPException(404, f"Annotation not found: {annotation_id}")
    if ann.document_id is None:
        raise HTTPException(400, "Folder-scoped annotations cannot be promoted to claims")

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
    emit_change(
        x_fichero_library_path,
        type="annotation.updated",
        document_ids=[i for i in [ann.document_id, ann.page_id, ann.folder_id] if i],
        actor="ui",
        origin_window=x_fichero_origin_window,
    )
    emit_change(
        x_fichero_library_path,
        type="claim.created",
        claim_ids=[claim.id],
        actor="ui",
        origin_window=x_fichero_origin_window,
    )

    return PromoteResponse(
        annotation_id=ann.id,
        claim_id=claim.id,
        claim_text=claim_text,
    )
