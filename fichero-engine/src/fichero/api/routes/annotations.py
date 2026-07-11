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

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from fichero.api.auth import action_context
from fichero.api.change_stream import emit_change
from fichero.api.main import get_library_database, get_library_database_for_write
from fichero.actions.registry import registry
from fichero.db import Database
from fichero.knowledge_models import (
    Annotation,
    AnnotationKind,
    KnowledgeClaim,
    validate_annotation_bbox,
    validate_annotation_color,
)
from fichero.utf16_offsets import utf16_range_to_codepoint_range
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
    anchor_kind: str | None = None
    paragraph_index: int | None = None
    text: str | None = None
    rating: int | None = Field(default=None, ge=1, le=5)
    color: str | None = None
    tags: list[str] = []
    linked_claim_ids: list[str] = []
    linked_entity_ids: list[str] = []
    linked_note_ids: list[str] = []
    metadata: dict[str, Any] = {}

    @field_validator("bbox")
    @classmethod
    def validate_bbox(cls, v: list[float] | None) -> list[float] | None:
        return validate_annotation_bbox(v)

    @field_validator("color")
    @classmethod
    def validate_color(cls, v: str | None) -> str | None:
        return validate_annotation_color(v)


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
                raise HTTPException(
                    400,
                    "document_id and page_id must match for page-scoped annotations",
                )
            resolved_page_id = document_id
        elif document.doc_type == DocType.folder:
            if resolved_folder_id and resolved_folder_id != document_id:
                raise HTTPException(
                    400,
                    "document_id and folder_id must match for folder-scoped annotations",
                )
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


def _annotation_scope_document_ids(ann: Annotation) -> list[str]:
    """The document/page/folder ids an annotation hangs off — drives
    ``emit_change`` so the observable layer refreshes the right windows."""
    return [i for i in [ann.document_id, ann.page_id, ann.folder_id] if i]


def create_annotation_impl(
    db: Database, request: AnnotationCreateRequest, *, actor: str = "human"
) -> Annotation:
    """Normalize the annotation's scope, build, and persist it.

    Extracted from the ``POST /annotations`` route so BOTH the route and the
    ``annotation.create`` action (EPIC #1848) drive the SAME scope-resolution +
    save logic (iterate-not-replace). Emission stays with the caller. Raises
    ``HTTPException`` on bad scope exactly as before.

    ``actor`` is the ctx.actor from the action layer — the server-side,
    forgery-proof attribution source (#3263). It overrides the model default
    ``"human"`` so every annotation carries the real creating user.
    """
    scope = _normalize_annotation_scope(
        db,
        document_id=request.document_id,
        page_id=request.page_id,
        folder_id=request.folder_id,
    )
    payload = request.model_dump()
    payload.update(scope.model_dump())
    payload["created_by"] = actor
    ann = Annotation(**payload)
    db.save(ann)
    return ann


@router.post("", response_model=Annotation, summary="Create an annotation")
async def create_annotation(
    request: AnnotationCreateRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: "ActionContext" = Depends(action_context),
) -> Annotation:
    result = registry.invoke(
        db,
        "annotation.create",
        request.model_dump(mode="json"),
        ctx,
    )
    return Annotation.model_validate(result.result)


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
            r
            for r in rows
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
    rating: int | None = Field(default=None, ge=1, le=5)
    color: str | None = None
    tags: list[str] | None = None
    linked_claim_ids: list[str] | None = None
    linked_entity_ids: list[str] | None = None
    linked_note_ids: list[str] | None = None
    char_start: int | None = None
    char_end: int | None = None
    bbox: list[float] | None = None
    anchor_kind: str | None = None
    paragraph_index: int | None = None
    metadata: dict[str, Any] | None = None

    @field_validator("bbox")
    @classmethod
    def validate_bbox(cls, v: list[float] | None) -> list[float] | None:
        return validate_annotation_bbox(v)

    @field_validator("color")
    @classmethod
    def validate_color(cls, v: str | None) -> str | None:
        return validate_annotation_color(v)


def patch_annotation_impl(
    db: Database, annotation_id: str, request: AnnotationPatchRequest
) -> tuple[Annotation, dict]:
    """Apply a partial update to an annotation. Returns ``(ann, before_snapshot)``.

    ``before_snapshot`` is the full pre-mutation row — the undo payload the
    ``annotation.update`` action inverts to ``annotation.restore``. Shared by the
    route and the action so both drive the same exclude-unset / scope-
    reconciliation logic (iterate-not-replace). Raises ``HTTPException`` on a
    missing id or bad scope exactly as before.
    """
    ann = db.get(Annotation, annotation_id)
    if ann is None:
        raise HTTPException(404, f"Annotation not found: {annotation_id}")
    before = ann.model_dump(mode="json")
    updates = request.model_dump(exclude_unset=True)
    if "document_id" in updates or "page_id" in updates or "folder_id" in updates:
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
    return ann, before


@router.patch("/{annotation_id}", response_model=Annotation)
async def patch_annotation(
    annotation_id: str,
    request: AnnotationPatchRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: "ActionContext" = Depends(action_context),
) -> Annotation:
    result = registry.invoke(
        db,
        "annotation.update",
        {"annotation_id": annotation_id, "update": request.model_dump(mode="json", exclude_unset=True)},
        ctx,
    )
    return Annotation.model_validate(result.result)


def delete_annotation_impl(db: Database, annotation_id: str) -> tuple[list[str], dict]:
    """Delete an annotation. Returns ``(scope_document_ids, before_snapshot)``.

    The before-snapshot is captured BEFORE deletion so the ``annotation.delete``
    action can invert to ``annotation.restore`` (a full-snapshot upsert preserving
    the id). The scope ids drive ``emit_change``. Raises ``HTTPException`` on a
    missing id exactly as before.
    """
    ann = db.get(Annotation, annotation_id)
    if ann is None:
        raise HTTPException(404, f"Annotation not found: {annotation_id}")
    before = ann.model_dump(mode="json")
    document_ids = _annotation_scope_document_ids(ann)
    db.delete(ann)
    return document_ids, before


def restore_annotation_impl(db: Database, snapshot: dict) -> Annotation:
    """Re-create / overwrite an annotation from a JSON snapshot (preserving id).

    The single inverse used by every undoable annotation action: ``db.save`` is an
    upsert by id, so this reuses the proven ``Annotation(**snapshot)`` round-trip to
    restore the exact pre-mutation row rather than re-deriving a field diff.
    """
    ann = Annotation(**snapshot)
    db.save(ann)
    return ann


@router.delete("/{annotation_id}", status_code=204)
async def delete_annotation(
    annotation_id: str,
    db: Database = Depends(get_library_database_for_write),
    ctx: "ActionContext" = Depends(action_context),
) -> None:
    registry.invoke(db, "annotation.delete", {"annotation_id": annotation_id}, ctx)


# The crop routes return PNG bytes (image / PDF region) or a text substring —
# never JSON. Declare the real media types so the generated OpenAPI client
# exposes a binary body variant instead of defaulting to application/json (the
# old default silently hid image crops from typed clients — #2105, #3442).
_CROP_RESPONSES = {
    200: {
        "content": {
            "image/png": {"schema": {"type": "string", "format": "binary"}},
            "text/plain": {"schema": {"type": "string"}},
        },
        "description": (
            "Cropped source region: PNG bytes for an image / PDF bbox, or the "
            "verbatim substring for a text char-range."
        ),
    },
}


def _crop_response(db: Database, ann: Annotation):
    """Resolve an annotation's cropped content to an HTTP response.

    Shared by ``GET /{id}/crop`` (a persisted annotation) and the ephemeral
    ``POST /crop`` (an unsaved region) so both drive identical crop logic
    (iterate-not-replace, #2256). Works on any in-memory ``Annotation`` — it
    never touches the annotation table, only the source ``Document``.
    """
    from fastapi.responses import PlainTextResponse, Response

    from fichero.workflows.tools._annotation_input import (
        crop_image,
        crop_pdf_page,
        crop_text,
    )

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


@router.get(
    "/{annotation_id}/crop",
    summary="Cropped content for this annotation (text body or image bytes)",
    description=(
        "Returns the annotation's underlying content cropped to its "
        "anchor: substring for text, PNG bytes for image / PDF region. "
        "Workflow tools call this to feed only the highlighted region "
        "to vision / LLM providers instead of the whole document. (#914)"
    ),
    responses=_CROP_RESPONSES,
)
async def get_crop(
    annotation_id: str,
    db: Database = Depends(get_library_database),
):
    ann = db.get(Annotation, annotation_id)
    if ann is None:
        raise HTTPException(404, f"Annotation not found: {annotation_id}")
    return _crop_response(db, ann)


class EphemeralCropRequest(BaseModel):
    """A region to crop WITHOUT persisting an annotation (#2256).

    Lets the reader send the LLM/vision provider just the marked region of a
    document on the fly — the user is still deciding, so nothing is saved.
    """

    document_id: str
    kind: AnnotationKind = AnnotationKind.highlight
    bbox: list[float] | None = None
    char_start: int | None = None
    char_end: int | None = None
    page_index: int | None = None
    page_label: str | None = None
    text: str | None = None


@router.post(
    "/crop",
    summary="Ephemeral crop for an unsaved region (no annotation persisted)",
    description=(
        "Crops a document to a transient region (bbox / char range) and returns "
        "the content — substring for text, PNG bytes for image / PDF — WITHOUT "
        "creating an annotation. The inspector's source popover (#2105/#3449) "
        "renders the returned PNG to show the cropped evidence for any "
        "bbox-anchored claim/entity/annotation. (#2256)"
    ),
    responses=_CROP_RESPONSES,
)
async def crop_ephemeral(
    request: EphemeralCropRequest,
    db: Database = Depends(get_library_database),
):
    ann = Annotation(
        document_id=request.document_id,
        kind=request.kind,
        bbox=request.bbox,
        char_start=request.char_start,
        char_end=request.char_end,
        page_index=request.page_index,
        page_label=request.page_label,
        text=request.text,
    )
    return _crop_response(db, ann)


class PromoteResponse(BaseModel):
    annotation_id: str
    claim_id: str
    claim_text: str


def promote_to_claim_impl(
    db: Database, annotation_id: str, *, actor: str | None = None
) -> tuple[Annotation, KnowledgeClaim, dict]:
    """Promote an annotation to a KnowledgeClaim. Returns ``(ann, claim, before)``.

    Extracted from the ``/promote-to-claim`` route so BOTH the route and the
    ``annotation.promote_to_claim`` action drive the SAME excerpt-resolution +
    claim-creation + back-link logic (iterate-not-replace). ``before`` is the
    annotation's pre-mutation snapshot (the link it gains is the only change).
    Emission stays with the caller. Raises ``HTTPException`` exactly as before.

    ``actor`` is the ctx.actor from the action layer (#3263). If provided it
    overrides the annotation's created_by; otherwise the annotation's own
    created_by is inherited (backwards-compatible default).
    """
    ann = db.get(Annotation, annotation_id)
    if ann is None:
        raise HTTPException(404, f"Annotation not found: {annotation_id}")
    if ann.document_id is None:
        raise HTTPException(
            400, "Folder-scoped annotations cannot be promoted to claims"
        )
    before = ann.model_dump(mode="json")

    # Resolve the source excerpt — prefer the highlighted span, fall
    # back to the annotation's note text.
    doc = db.get(Document, ann.document_id)
    excerpt: str | None = None
    if (
        doc is not None
        and doc.page_content
        and ann.char_start is not None
        and ann.char_end is not None
    ):
        # Convert UTF-16 offsets (from Swift frontend) to Python code-point
        # offsets before slicing page_content (#3262).
        cp_start, cp_end = utf16_range_to_codepoint_range(
            doc.page_content, ann.char_start, ann.char_end
        )
        excerpt = doc.page_content[cp_start:cp_end]
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
        created_by=actor or ann.created_by,
    )
    db.save(claim)

    # Link the annotation back to its claim.
    linked = set(ann.linked_claim_ids or [])
    linked.add(claim.id)
    ann.linked_claim_ids = sorted(linked)
    ann.updated_at = datetime.now()
    db.save(ann)
    return ann, claim, before


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
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> PromoteResponse:
    """Route through the audited action layer (#3261).

    The REST endpoint now delegates to registry.invoke so every
    promote gets an ActionAudit row, actor attribution, and the
    ChangeSpec's claim.created event (plus annotation.updated via
    a second emit in the action). The previous hand-rolled emit_change
    calls are replaced by the registry's built-in audit+emit pipeline.
    """
    result = registry.invoke(
        db,
        "annotation.promote_to_claim",
        {"annotation_id": annotation_id},
        ctx,
    )
    after = result.result
    # The action emits claim.created; also emit annotation.updated
    # for the scope documents the annotation hangs off.
    ann = db.get(Annotation, annotation_id)
    if ann is not None:
        emit_change(
            ctx.library_path or "",
            type="annotation.updated",
            document_ids=_annotation_scope_document_ids(ann),
            actor=ctx.actor,
            origin_window=ctx.origin_window,
            origin_user=ctx.actor,
        )
    return PromoteResponse(
        annotation_id=after["annotation"]["id"],
        claim_id=after["claim_id"],
        claim_text=after["claim_text"],
    )


# =============================================================================
# Action layer registration (EPIC #1848 / #2014) — ANNOTATION domain sweep
# =============================================================================
#
# Each action WRAPS the proven ``*_impl`` above (iterate-not-replace) and routes
# through ``registry.invoke`` so chat tools / App Intents / tests / the audit log
# all drive the SAME code the UI routes do (the routes call the same ``*_impl``
# directly and emit), matching the entity.merge / note.* pattern.
#
# Undo is data, not code: ``db.save`` is an upsert by id, so a single
# ``annotation.restore`` (full-snapshot upsert preserving the id) inverts BOTH a
# delete (re-inserts the row) and an edit (overwrites with the prior snapshot).
# ``annotation.restore`` records whether the row pre-existed, so its OWN inverse
# is ``annotation.delete`` (after a recreate) or ``annotation.restore`` (after an
# overwrite) — keeping every delete<->restore and edit<->restore redo chain sane.
# The inverse chain:
#   * annotation.create  -> annotation.delete  (the new id)
#   * annotation.update  -> annotation.restore (before snapshot)
#   * annotation.delete  -> annotation.restore (before snapshot)
#   * annotation.restore -> annotation.delete / annotation.restore (self-correcting)
#
# ``annotation.promote_to_claim`` is NOT undoable: a true reverse must delete the
# created KnowledgeClaim AND drop the back-link, which crosses into the claim
# domain. A single annotation.restore would silently leave an orphan claim — the
# exact half-undo we refuse to ship — so promote is audited (full before/after)
# but not auto-reversible. A dedicated demote action is future work (the #1848
# "5 missing annotation actions").
#
# ``ChangeSpec.document_ids`` carries the annotation's *scope* (document / page /
# folder) so the observable layer refreshes the windows the annotation hangs off;
# the annotation id itself rides in ``target_ids``.

from fichero.actions.registry import action, ActionContext, ChangeSpec  # noqa: E402
from pydantic import Field  # noqa: E402


class AnnotationUpdateActionParams(BaseModel):
    """``annotation.update`` params — the path annotation_id plus the patch body.

    ``update`` is a nested :class:`AnnotationPatchRequest` so the registry's
    ``model_validate`` preserves exclude-unset semantics: only fields actually
    present in the patch are applied (absent means 'leave unchanged')."""

    annotation_id: str = Field(description="Annotation id to update")
    update: AnnotationPatchRequest = Field(description="Partial annotation update")


class AnnotationIdParams(BaseModel):
    """``annotation.delete`` / ``annotation.promote_to_claim`` params — also reached
    as the inverse of ``annotation.create``."""

    annotation_id: str = Field(description="Annotation id")


class AnnotationRestoreParams(BaseModel):
    """``annotation.restore`` — re-materialize / overwrite an annotation by snapshot
    (preserving its id). The single generic inverse for every undoable verb."""

    snapshot: dict = Field(description="Annotation.model_dump snapshot")


def _invert_create_annotation(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    """Undo a create by deleting the row it produced."""
    if not after:
        return None
    annotation_id = after.get("id")
    if not annotation_id:
        return None
    return ("annotation.delete", {"annotation_id": annotation_id})


def _invert_to_restore_before(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    """Undo an edit/delete by restoring the captured pre-change snapshot."""
    if not before:
        return None
    return ("annotation.restore", {"snapshot": before})


def _invert_restore_annotation(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    """Inverse of restore — depends on whether the row pre-existed.

    If ``before`` is None the restore RE-CREATED a missing row (it was undoing a
    delete) -> redo by deleting again. If ``before`` is a snapshot the restore
    OVERWROTE an existing row (undoing an edit) -> redo by restoring that prior
    snapshot, re-applying the edit. Keeps delete<->restore and edit<->restore
    redo chains correct."""
    if not after:
        return None
    annotation_id = after.get("id")
    if before is None:
        if not annotation_id:
            return None
        return ("annotation.delete", {"annotation_id": annotation_id})
    return ("annotation.restore", {"snapshot": before})


@action(
    "annotation.create",
    AnnotationCreateRequest,
    domains=["annotation"],
    undoable=True,
    invert=_invert_create_annotation,
)
def _action_create_annotation(
    db: Database, params: AnnotationCreateRequest, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    ann = create_annotation_impl(db, params, actor=ctx.actor)
    after = ann.model_dump(mode="json")
    spec = ChangeSpec(
        domains=["annotation"],
        target_ids=[ann.id],
        before=None,
        after=after,
        emit_type="annotation.created",
        document_ids=_annotation_scope_document_ids(ann),
    )
    return after, spec


@action(
    "annotation.update",
    AnnotationUpdateActionParams,
    domains=["annotation"],
    undoable=True,
    invert=_invert_to_restore_before,
)
def _action_update_annotation(
    db: Database, params: AnnotationUpdateActionParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    ann, before = patch_annotation_impl(db, params.annotation_id, params.update)
    after = ann.model_dump(mode="json")
    spec = ChangeSpec(
        domains=["annotation"],
        target_ids=[ann.id],
        before=before,
        after=after,
        emit_type="annotation.updated",
        document_ids=_annotation_scope_document_ids(ann),
    )
    return after, spec


@action(
    "annotation.delete",
    AnnotationIdParams,
    domains=["annotation"],
    undoable=True,
    invert=_invert_to_restore_before,
)
def _action_delete_annotation(
    db: Database, params: AnnotationIdParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    document_ids, before = delete_annotation_impl(db, params.annotation_id)
    spec = ChangeSpec(
        domains=["annotation"],
        target_ids=[params.annotation_id],
        before=before,
        after=None,
        emit_type="annotation.deleted",
        document_ids=document_ids,
    )
    return before, spec


@action(
    "annotation.restore",
    AnnotationRestoreParams,
    domains=["annotation"],
    undoable=True,
    invert=_invert_restore_annotation,
)
def _action_restore_annotation(
    db: Database, params: AnnotationRestoreParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    """Upsert an annotation from its snapshot (preserving id). Records whether the
    row pre-existed so its inverse picks delete (recreate) vs restore (edit)."""
    annotation_id = params.snapshot.get("id")
    existing = db.get(Annotation, annotation_id) if annotation_id else None
    before = existing.model_dump(mode="json") if existing else None
    ann = restore_annotation_impl(db, params.snapshot)
    after = ann.model_dump(mode="json")
    spec = ChangeSpec(
        domains=["annotation"],
        target_ids=[ann.id],
        before=before,
        after=after,
        emit_type="annotation.updated" if before else "annotation.created",
        document_ids=_annotation_scope_document_ids(ann),
    )
    return after, spec


@action(
    "annotation.promote_to_claim",
    AnnotationIdParams,
    domains=["annotation", "claim"],
    undoable=False,
)
def _action_promote_to_claim(
    db: Database, params: AnnotationIdParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    """Promote an annotation to a KnowledgeClaim. NOT undoable (see module note):
    auto-reversing would orphan the created claim, so we audit but don't invert."""
    ann, claim, before = promote_to_claim_impl(db, params.annotation_id, actor=ctx.actor)
    after = {
        "annotation": ann.model_dump(mode="json"),
        "claim_id": claim.id,
        "claim_text": claim.text,
    }
    spec = ChangeSpec(
        domains=["annotation", "claim"],
        target_ids=[ann.id, claim.id],
        before=before,
        after=after,
        emit_type="claim.created",
        claim_ids=[claim.id],
        document_ids=_annotation_scope_document_ids(ann),
    )
    return after, spec


# =============================================================================
# The 3 MISSING annotation actions (#2018) — duplicate / merge / relink
# =============================================================================
#
# The #2000-era inventory flagged these as capabilities the UI wants but no
# single endpoint covers. Each is defined here as a registered action (reachable
# via the generic POST /api/actions/invoke), wrapping new minimal *_impl logic in
# the same iterate-not-replace shape as the CRUD verbs above:
#
#   * annotation.duplicate -> undo via annotation.delete (the copy's new id), the
#     SAME create-family inverse the create action uses.
#   * annotation.relink    -> a focused patch (links + anchor target only) that
#     REUSES patch_annotation_impl, so it inherits the proven scope-normalization
#     + exclude-unset semantics; undo via annotation.restore (before snapshot).
#   * annotation.merge     -> combine two annotations into the target (union the
#     links/tags, concatenate text) and remove the absorbed one. The annotation
#     domain has no tombstone column, so "soft-delete" here means the absorbed row
#     is db.delete'd but its FULL snapshot rides in the audit `before` — exactly
#     restorable. A merge touches TWO rows (target edited + absorbed removed), so
#     no single existing verb can invert it; it gets a dedicated
#     ``annotation.unmerge`` inverse (mirrors how the batch domain added
#     ``batch.restore`` purely as an inverse). ``unmerge`` upserts BOTH captured
#     snapshots back, so merge<->unmerge is a clean undo/redo pair.


def duplicate_annotation_impl(db: Database, annotation_id: str, *, actor: str = "human") -> Annotation:
    """Copy an annotation: a fresh id + timestamps, every other field/link cloned.

    Strips identity/time fields from the source snapshot so the model mints new
    ones; ``db.save`` then inserts the copy. Raises ``HTTPException`` 404 on a
    missing source exactly as the other annotation verbs do.

    ``actor`` is the ctx.actor from the action layer (#3263). The duplicate
    carries the duplicating user, not the original creator.
    """
    ann = db.get(Annotation, annotation_id)
    if ann is None:
        raise HTTPException(404, f"Annotation not found: {annotation_id}")
    snapshot = ann.model_dump()
    for identity_field in ("id", "created_at", "updated_at"):
        snapshot.pop(identity_field, None)
    snapshot["created_by"] = actor
    copy = Annotation(**snapshot)
    db.save(copy)
    return copy


def _scope_doc_ids_from_snapshot(snapshot: dict) -> list[str]:
    """The document/page/folder ids hanging off a snapshot dict — for emit scope."""
    return [
        i
        for i in (
            snapshot.get("document_id"),
            snapshot.get("page_id"),
            snapshot.get("folder_id"),
        )
        if i
    ]


def merge_annotations_impl(
    db: Database, target_id: str, source_id: str
) -> tuple[Annotation, dict, dict]:
    """Merge ``source`` into ``target``. Returns ``(target, target_before, source_before)``.

    Combines text (newline-joined, in target-then-source order) and unions the
    three link lists + tags onto the target, then removes the absorbed source.
    Both pre-mutation snapshots are returned so the merge action's ``before`` can
    restore BOTH rows on undo. Raises ``HTTPException`` 400 on a self-merge and
    404 on a missing id.
    """
    if target_id == source_id:
        raise HTTPException(400, "Cannot merge an annotation into itself")
    target = db.get(Annotation, target_id)
    if target is None:
        raise HTTPException(404, f"Annotation not found: {target_id}")
    source = db.get(Annotation, source_id)
    if source is None:
        raise HTTPException(404, f"Annotation not found: {source_id}")

    target_before = target.model_dump(mode="json")
    source_before = source.model_dump(mode="json")

    texts = [t for t in (target.text, source.text) if t]
    target.text = "\n\n".join(texts) if texts else None
    target.linked_claim_ids = sorted(
        set(target.linked_claim_ids or []) | set(source.linked_claim_ids or [])
    )
    target.linked_entity_ids = sorted(
        set(target.linked_entity_ids or []) | set(source.linked_entity_ids or [])
    )
    target.linked_note_ids = sorted(
        set(target.linked_note_ids or []) | set(source.linked_note_ids or [])
    )
    target.tags = sorted(set(target.tags or []) | set(source.tags or []))
    target.updated_at = datetime.now()
    db.save(target)
    db.delete(source)
    return target, target_before, source_before


class AnnotationDuplicateParams(BaseModel):
    """``annotation.duplicate`` — id of the annotation to copy."""

    annotation_id: str = Field(description="Annotation id to duplicate")


class AnnotationMergeParams(BaseModel):
    """``annotation.merge`` — fold ``source_id`` into ``target_id``."""

    target_id: str = Field(description="Annotation kept (absorbs the source)")
    source_id: str = Field(description="Annotation absorbed + removed")


class AnnotationUnmergeParams(BaseModel):
    """``annotation.unmerge`` — the merge inverse: a ``{target, absorbed}`` pair of
    pre-merge snapshots to upsert back."""

    snapshot: dict = Field(
        description="{'target': <snap>, 'absorbed': <snap>} captured before a merge"
    )


class AnnotationRelinkParams(BaseModel):
    """``annotation.relink`` — update an annotation's cross-links and/or anchor
    target only. Every field is optional; exclude-unset means an absent field is
    left untouched while an explicit ``[]`` clears that link list."""

    annotation_id: str = Field(description="Annotation id to relink")
    linked_claim_ids: list[str] | None = None
    linked_entity_ids: list[str] | None = None
    linked_note_ids: list[str] | None = None
    document_id: str | None = None
    page_id: str | None = None
    folder_id: str | None = None


def relink_annotation_impl(
    db: Database, params: AnnotationRelinkParams
) -> tuple[Annotation, dict]:
    """Apply a links/target-only update by REUSING ``patch_annotation_impl``.

    Only the relink fields actually supplied are forwarded (exclude-unset), so the
    patch's proven scope-reconciliation runs for an anchor move and the link lists
    are set verbatim. Returns ``(ann, before_snapshot)``. Raises ``HTTPException``
    400 when no relink field is supplied and 404 for a missing id.
    """
    updates = params.model_dump(exclude_unset=True)
    updates.pop("annotation_id", None)
    if not updates:
        raise HTTPException(
            400, "annotation.relink requires at least one link or target field"
        )
    return patch_annotation_impl(
        db, params.annotation_id, AnnotationPatchRequest(**updates)
    )


def _invert_merge_annotation(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    """Undo a merge by restoring BOTH captured snapshots via annotation.unmerge."""
    if not before:
        return None
    return ("annotation.unmerge", {"snapshot": before})


@action(
    "annotation.duplicate",
    AnnotationDuplicateParams,
    domains=["annotation"],
    undoable=True,
    invert=_invert_create_annotation,
)
def _action_duplicate_annotation(
    db: Database, params: AnnotationDuplicateParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    copy = duplicate_annotation_impl(db, params.annotation_id, actor=ctx.actor)
    after = copy.model_dump(mode="json")
    spec = ChangeSpec(
        domains=["annotation"],
        target_ids=[copy.id],
        before=None,
        after=after,
        emit_type="annotation.created",
        document_ids=_annotation_scope_document_ids(copy),
    )
    return after, spec


@action(
    "annotation.merge",
    AnnotationMergeParams,
    domains=["annotation"],
    undoable=True,
    invert=_invert_merge_annotation,
)
def _action_merge_annotation(
    db: Database, params: AnnotationMergeParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    target, target_before, source_before = merge_annotations_impl(
        db, params.target_id, params.source_id
    )
    before = {"target": target_before, "absorbed": source_before}
    after = target.model_dump(mode="json")
    document_ids = sorted(
        set(_scope_doc_ids_from_snapshot(target_before))
        | set(_scope_doc_ids_from_snapshot(source_before))
    )
    spec = ChangeSpec(
        domains=["annotation"],
        target_ids=[params.target_id, params.source_id],
        before=before,
        after=after,
        emit_type="annotation.merged",
        document_ids=document_ids,
    )
    return after, spec


@action(
    "annotation.unmerge",
    AnnotationUnmergeParams,
    domains=["annotation"],
    undoable=False,
)
def _action_unmerge_annotation(
    db: Database, params: AnnotationUnmergeParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    """Inverse of annotation.merge — upsert the target + absorbed snapshots back
    (db.save is upsert-by-id, so the absorbed row is re-created with its original
    id and the target reverts to its pre-merge fields)."""
    target_snap = params.snapshot.get("target")
    absorbed_snap = params.snapshot.get("absorbed")
    restored: list[str] = []
    document_ids: list[str] = []
    for snap in (target_snap, absorbed_snap):
        if not snap:
            continue
        ann = restore_annotation_impl(db, snap)
        restored.append(ann.id)
        document_ids.extend(_annotation_scope_document_ids(ann))
    after = {"restored_ids": restored}
    spec = ChangeSpec(
        domains=["annotation"],
        target_ids=restored,
        before=None,
        after=after,
        emit_type="annotation.updated",
        document_ids=sorted(set(document_ids)),
    )
    return after, spec


@action(
    "annotation.relink",
    AnnotationRelinkParams,
    domains=["annotation"],
    undoable=True,
    invert=_invert_to_restore_before,
)
def _action_relink_annotation(
    db: Database, params: AnnotationRelinkParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    ann, before = relink_annotation_impl(db, params)
    after = ann.model_dump(mode="json")
    spec = ChangeSpec(
        domains=["annotation"],
        target_ids=[ann.id],
        before=before,
        after=after,
        emit_type="annotation.updated",
        document_ids=_annotation_scope_document_ids(ann),
    )
    return after, spec
