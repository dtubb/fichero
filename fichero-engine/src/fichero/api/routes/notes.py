"""Zettelkasten Notes API (#917).

Atomic user notes networked by bidirectional links. Notes can
cross-reference other notes, entities, claims, and documents,
forming a personal knowledge graph independent of the source
corpus.
"""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from fichero.api.library_header import require_library_path
from fichero.api.auth import action_context, request_actor
from fichero.api.change_stream import emit_change
from fichero.api.main import get_library_database, get_library_database_for_write
from fichero.actions.registry import registry
from fichero.db import Database
from fichero.knowledge_models import Note, NoteKind, NoteLink
from fichero.models import DocType, Document, NoteListResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/notes")


# =============================================================================
# Notes — CRUD
# =============================================================================


class NoteCreateRequest(BaseModel):
    title: str | None = None
    body: str = ""
    kind: NoteKind = NoteKind.zettel
    tags: list[str] = []
    linked_note_ids: list[str] = []
    linked_entity_ids: list[str] = []
    linked_claim_ids: list[str] = []
    linked_document_ids: list[str] = []
    page_id: str | None = None
    folder_id: str | None = None
    linked_structure_node_id: str | None = None
    address: str | None = None
    parent_address: str | None = None


def _validate_note_scope(
    db: Database,
    *,
    page_id: str | None,
    folder_id: str | None,
) -> None:
    if page_id and folder_id:
        raise HTTPException(
            400, "Notes can be scoped to either a page or a folder, not both"
        )
    if page_id is not None:
        page = db.get(Document, page_id)
        if page is None:
            raise HTTPException(404, f"Page not found: {page_id}")
        if page.doc_type != DocType.page:
            raise HTTPException(400, f"Document {page_id} is not a page")
    if folder_id is not None:
        folder = db.get(Document, folder_id)
        if folder is None:
            raise HTTPException(404, f"Folder not found: {folder_id}")
        if folder.doc_type != DocType.folder:
            raise HTTPException(400, f"Document {folder_id} is not a folder")


def _note_links_document(note: Note, document_id: str) -> bool:
    return (
        document_id in (note.linked_document_ids or [])
        or note.page_id == document_id
        or note.folder_id == document_id
    )


def _scoped_document_links(
    linked_document_ids: list[str],
    *,
    page_id: str | None,
    folder_id: str | None,
) -> list[str]:
    merged: list[str] = []
    for candidate in [*linked_document_ids, page_id, folder_id]:
        if candidate and candidate not in merged:
            merged.append(candidate)
    return merged


def _note_scope_document_ids(note: Note | None) -> list[str]:
    if note is None:
        return []
    return [
        i
        for i in {note.page_id, note.folder_id, *(note.linked_document_ids or [])}
        if i
    ]


def _emit_note_change_ctx(
    ctx: "ActionContext",
    *,
    event_type: str,
    document_ids: list[str],
) -> None:
    if not ctx.library_path:
        return
    emit_change(
        ctx.library_path,
        type=event_type,
        document_ids=document_ids,
        actor=ctx.actor,
        origin_window=ctx.origin_window,
        origin_user=ctx.actor,
    )


def create_note_impl(db: Database, request: NoteCreateRequest) -> Note:
    """Validate scope, fold the page/folder into linked_document_ids, persist.

    The single create path: the ``create_note`` route AND the ``note.create``
    audited action (EPIC #1848) drive this exact code (iterate-not-replace).
    """
    _validate_note_scope(db, page_id=request.page_id, folder_id=request.folder_id)
    payload = request.model_dump()
    payload["linked_document_ids"] = _scoped_document_links(
        payload["linked_document_ids"],
        page_id=request.page_id,
        folder_id=request.folder_id,
    )
    note = Note(**payload)
    db.save(note)
    return note


@router.post("", response_model=Note)
async def create_note(
    request: NoteCreateRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: "ActionContext" = Depends(action_context),
) -> Note:
    result = registry.invoke(
        db,
        "note.create",
        request.model_dump(mode="json"),
        ctx,
    )
    return Note.model_validate(result.result)


@router.get("", response_model=NoteListResponse)
async def list_notes(
    kind: NoteKind | None = Query(default=None),
    tag: str | None = Query(default=None),
    linked_entity_id: str | None = Query(default=None),
    linked_claim_id: str | None = Query(default=None),
    linked_document_id: str | None = Query(default=None),
    page_id: str | None = Query(default=None),
    folder_id: str | None = Query(default=None),
    linked_structure_node_id: str | None = Query(default=None),
    q: str | None = Query(default=None, description="full-text body search"),
    db: Database = Depends(get_library_database),
) -> NoteListResponse:
    rows = db.query(Note)
    if kind is not None:
        rows = [r for r in rows if r.kind == kind]
    if tag is not None:
        rows = [r for r in rows if tag in (r.tags or [])]
    if linked_entity_id is not None:
        rows = [r for r in rows if linked_entity_id in (r.linked_entity_ids or [])]
    if linked_claim_id is not None:
        rows = [r for r in rows if linked_claim_id in (r.linked_claim_ids or [])]
    if linked_document_id is not None:
        rows = [r for r in rows if _note_links_document(r, linked_document_id)]
    if page_id is not None:
        rows = [
            r for r in rows if r.page_id == page_id or _note_links_document(r, page_id)
        ]
    if folder_id is not None:
        rows = [
            r
            for r in rows
            if r.folder_id == folder_id or _note_links_document(r, folder_id)
        ]
    if linked_structure_node_id is not None:
        rows = [
            r for r in rows if r.linked_structure_node_id == linked_structure_node_id
        ]
    if q:
        needle = q.lower()
        rows = [
            r
            for r in rows
            if needle in (r.body or "").lower() or needle in (r.title or "").lower()
        ]
    rows.sort(key=lambda r: r.updated_at, reverse=True)
    return NoteListResponse(items=rows, count=len(rows))


@router.get("/{note_id}", response_model=Note)
async def get_note(
    note_id: str,
    db: Database = Depends(get_library_database),
) -> Note:
    note = db.get(Note, note_id)
    if note is None:
        raise HTTPException(404, f"Note not found: {note_id}")
    return note


class NotePatchRequest(BaseModel):
    title: str | None = None
    body: str | None = None
    kind: NoteKind | None = None
    tags: list[str] | None = None
    linked_note_ids: list[str] | None = None
    linked_entity_ids: list[str] | None = None
    linked_claim_ids: list[str] | None = None
    linked_document_ids: list[str] | None = None
    page_id: str | None = None
    folder_id: str | None = None
    linked_structure_node_id: str | None = None
    address: str | None = None
    parent_address: str | None = None


def patch_note_impl(
    db: Database, note_id: str, request: NotePatchRequest
) -> tuple[Note, dict]:
    """Apply a partial update to a note. Returns ``(note, before_snapshot)``.

    ``before_snapshot`` is the full pre-mutation row — the undo payload the
    ``note.update`` action inverts to ``note.restore``. Shared by the route and
    the action so both drive the same exclude-unset / scope-reconciliation logic.
    """
    note = db.get(Note, note_id)
    if note is None:
        raise HTTPException(404, f"Note not found: {note_id}")
    before = note.model_dump(mode="json")
    updates = request.model_dump(exclude_unset=True)
    next_page_id = updates.get("page_id", note.page_id)
    next_folder_id = updates.get("folder_id", note.folder_id)
    _validate_note_scope(db, page_id=next_page_id, folder_id=next_folder_id)
    if (
        "linked_document_ids" in updates
        or "page_id" in updates
        or "folder_id" in updates
    ):
        updates["linked_document_ids"] = _scoped_document_links(
            updates.get("linked_document_ids", note.linked_document_ids or []),
            page_id=next_page_id,
            folder_id=next_folder_id,
        )
    for field, value in updates.items():
        setattr(note, field, value)
    note.updated_at = datetime.now()
    db.save(note)
    return note, before


@router.patch("/{note_id}", response_model=Note)
async def patch_note(
    note_id: str,
    request: NotePatchRequest,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str = Depends(require_library_path),
    x_fichero_origin_window: str | None = Header(
        default=None, alias="X-Fichero-Origin-Window"
    ),
    actor: str = Depends(request_actor),
) -> Note:
    note, _before = patch_note_impl(db, note_id, request)
    emit_change(
        x_fichero_library_path,
        type="note.updated",
        document_ids=_note_scope_document_ids(note),
        actor=actor,
        origin_window=x_fichero_origin_window,
        origin_user=actor,
    )
    return note


def delete_note_impl(db: Database, note_id: str) -> tuple[list[str], dict]:
    """Delete a note. Returns ``(scope_document_ids, before_snapshot)``.

    The before-snapshot is captured BEFORE deletion so the ``note.delete`` action
    can invert to ``note.restore`` (a full-snapshot upsert preserving the id). The
    scope ids drive ``emit_change`` for the windows the note was attached to.
    """
    note = db.get(Note, note_id)
    if note is None:
        raise HTTPException(404, f"Note not found: {note_id}")
    before = note.model_dump(mode="json")
    document_ids = _note_scope_document_ids(note)
    db.delete(note)
    return document_ids, before


def restore_note_impl(db: Database, snapshot: dict) -> Note:
    """Re-create / overwrite a note from a JSON snapshot (preserving its id).

    The single inverse used by every undoable note action: ``db.save`` is an
    upsert by id, so this reuses the proven ``Note(**snapshot)`` round-trip to
    restore the exact pre-mutation row rather than re-deriving a field diff.
    """
    note = Note(**snapshot)
    db.save(note)
    return note


@router.delete("/{note_id}", status_code=204)
async def delete_note(
    note_id: str,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str = Depends(require_library_path),
    x_fichero_origin_window: str | None = Header(
        default=None, alias="X-Fichero-Origin-Window"
    ),
    actor: str = Depends(request_actor),
) -> None:
    document_ids, _before = delete_note_impl(db, note_id)
    emit_change(
        x_fichero_library_path,
        type="note.deleted",
        document_ids=document_ids,
        actor=actor,
        origin_window=x_fichero_origin_window,
        origin_user=actor,
    )


# =============================================================================
# Bidirectional links between notes
# =============================================================================


class NoteLinkCreateRequest(BaseModel):
    target_note_id: str
    link_type: str = "free"
    annotation: str | None = None


@router.post(
    "/{note_id}/links",
    response_model=NoteLink,
    summary="Create a bidirectional link between two notes",
)
async def create_note_link(
    note_id: str,
    request: NoteLinkCreateRequest,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str = Depends(require_library_path),
    x_fichero_origin_window: str | None = Header(
        default=None, alias="X-Fichero-Origin-Window"
    ),
    actor: str = Depends(request_actor),
) -> NoteLink:
    source_note = db.get(Note, note_id)
    if source_note is None:
        raise HTTPException(404, f"Source note not found: {note_id}")
    target_note = db.get(Note, request.target_note_id)
    if target_note is None:
        raise HTTPException(404, f"Target note not found: {request.target_note_id}")
    if note_id == request.target_note_id:
        raise HTTPException(400, "Cannot link a note to itself")
    link = NoteLink(
        source_note_id=note_id,
        target_note_id=request.target_note_id,
        link_type=request.link_type,
        annotation=request.annotation,
    )
    db.save(link)
    emit_change(
        x_fichero_library_path,
        type="note.updated",
        document_ids=[
            i
            for i in {
                *_note_scope_document_ids(source_note),
                *_note_scope_document_ids(target_note),
            }
            if i
        ],
        actor=actor,
        origin_window=x_fichero_origin_window,
        origin_user=actor,
        run_id=None,
    )
    return link


@router.delete("/{note_id}/links/{link_id}", status_code=204)
async def delete_note_link(
    note_id: str,
    link_id: str,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str = Depends(require_library_path),
    x_fichero_origin_window: str | None = Header(
        default=None, alias="X-Fichero-Origin-Window"
    ),
    actor: str = Depends(request_actor),
) -> None:
    link = db.get(NoteLink, link_id)
    if link is None:
        raise HTTPException(404, f"Link not found: {link_id}")
    if link.source_note_id != note_id and link.target_note_id != note_id:
        raise HTTPException(400, f"Link {link_id} does not involve note {note_id}")
    source_note = db.get(Note, note_id)
    target_note_id = (
        link.target_note_id if link.source_note_id == note_id else link.source_note_id
    )
    target_note = db.get(Note, target_note_id)
    db.delete(link)
    emit_change(
        x_fichero_library_path,
        type="note.updated",
        document_ids=[
            i
            for i in {
                *_note_scope_document_ids(source_note),
                *_note_scope_document_ids(target_note),
            }
            if i
        ],
        actor=actor,
        origin_window=x_fichero_origin_window,
        origin_user=actor,
        run_id=None,
    )


@router.get(
    "/{note_id}/backlinks",
    response_model=NoteListResponse,
    summary="Every note that links to this one",
    description=(
        "Returns the notes that point at ``note_id`` via NoteLink "
        "(target side). This is the Zettelkasten 'what points here' "
        "query — the graph IS the analysis."
    ),
)
async def backlinks(
    note_id: str,
    db: Database = Depends(get_library_database),
) -> list[Note]:
    if db.get(Note, note_id) is None:
        raise HTTPException(404, f"Note not found: {note_id}")
    incoming = [link for link in db.query(NoteLink) if link.target_note_id == note_id]
    source_ids = {link.source_note_id for link in incoming}
    notes = [db.get(Note, sid) for sid in source_ids]
    items = [n for n in notes if n is not None]
    return NoteListResponse(items=items, count=len(items))


@router.get(
    "/{note_id}/forward-links",
    response_model=NoteListResponse,
    summary="Every note this one links to",
)
async def forward_links(
    note_id: str,
    db: Database = Depends(get_library_database),
) -> list[Note]:
    if db.get(Note, note_id) is None:
        raise HTTPException(404, f"Note not found: {note_id}")
    outgoing = [link for link in db.query(NoteLink) if link.source_note_id == note_id]
    target_ids = {link.target_note_id for link in outgoing}
    notes = [db.get(Note, tid) for tid in target_ids]
    items = [n for n in notes if n is not None]
    return NoteListResponse(items=items, count=len(items))


# =============================================================================
# Action layer registration (EPIC #1848 / #2014) — NOTE domain sweep
# =============================================================================
#
# Each action WRAPS the proven ``*_impl`` above (iterate-not-replace) and routes
# through ``registry.invoke`` so chat tools / App Intents / tests / the audit log
# all drive the SAME code the UI routes do (the routes call the same ``*_impl``
# directly and emit), matching the entity.merge / conversation.* pattern.
#
# Undo is data, not code: ``db.save`` is an upsert by id, so a single
# ``note.restore`` (full-snapshot upsert preserving the id) inverts BOTH a delete
# (re-inserts the row) and an edit (overwrites with the prior snapshot).
# ``note.restore`` records whether the row pre-existed, so its OWN inverse is
# ``note.delete`` (after a recreate) or ``note.restore`` (after an overwrite) —
# keeping every delete<->restore and edit<->restore redo chain sane. The inverse
# chain:
#   * note.create  -> note.delete  (the new id)
#   * note.update  -> note.restore (before snapshot)
#   * note.delete  -> note.restore (before snapshot)
#   * note.restore -> note.delete / note.restore (self-correcting, see above)
#
# ``ChangeSpec.document_ids`` carries the note's *scope* (page / folder / linked
# documents) so the observable layer refreshes the windows the note hangs off;
# the note id itself rides in ``target_ids``.

from fichero.actions.registry import action, ActionContext, ChangeSpec  # noqa: E402


class NoteUpdateActionParams(BaseModel):
    """``note.update`` params — the path note_id plus the partial patch body.

    ``update`` is a nested :class:`NotePatchRequest` so the registry's
    ``model_validate`` preserves exclude-unset semantics: only fields actually
    present in the patch are applied (None means 'leave unchanged')."""

    note_id: str = Field(description="Note id to update")
    update: NotePatchRequest = Field(description="Partial note update")


class NoteIdParams(BaseModel):
    """``note.delete`` params — also reached as the inverse of ``note.create``."""

    note_id: str = Field(description="Note id to delete")


class NoteRestoreParams(BaseModel):
    """``note.restore`` — re-materialize / overwrite a note by snapshot
    (preserving its id). The single generic inverse for every undoable verb."""

    snapshot: dict = Field(description="Note.model_dump snapshot")


def _invert_create_note(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    """Undo a create by deleting the row it produced."""
    if not after:
        return None
    note_id = after.get("id")
    if not note_id:
        return None
    return ("note.delete", {"note_id": note_id})


def _invert_to_restore_before(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    """Undo an edit/delete by restoring the captured pre-change snapshot."""
    if not before:
        return None
    return ("note.restore", {"snapshot": before})


def _invert_restore_note(
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
    note_id = after.get("id")
    if before is None:
        if not note_id:
            return None
        return ("note.delete", {"note_id": note_id})
    return ("note.restore", {"snapshot": before})


@action(
    "note.create",
    NoteCreateRequest,
    domains=["note"],
    undoable=True,
    invert=_invert_create_note,
)
def _action_create_note(
    db: Database, params: NoteCreateRequest, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    note = create_note_impl(db, params)
    after = note.model_dump(mode="json")
    _emit_note_change_ctx(
        ctx,
        event_type="note.created",
        document_ids=_note_scope_document_ids(note),
    )
    spec = ChangeSpec(
        domains=["note"],
        target_ids=[note.id],
        before=None,
        after=after,
        document_ids=_note_scope_document_ids(note),
    )
    return after, spec


@action(
    "note.update",
    NoteUpdateActionParams,
    domains=["note"],
    undoable=True,
    invert=_invert_to_restore_before,
)
def _action_update_note(
    db: Database, params: NoteUpdateActionParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    note, before = patch_note_impl(db, params.note_id, params.update)
    after = note.model_dump(mode="json")
    _emit_note_change_ctx(
        ctx,
        event_type="note.updated",
        document_ids=_note_scope_document_ids(note),
    )
    spec = ChangeSpec(
        domains=["note"],
        target_ids=[note.id],
        before=before,
        after=after,
        document_ids=_note_scope_document_ids(note),
    )
    return after, spec


@action(
    "note.delete",
    NoteIdParams,
    domains=["note"],
    undoable=True,
    invert=_invert_to_restore_before,
)
def _action_delete_note(
    db: Database, params: NoteIdParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    document_ids, before = delete_note_impl(db, params.note_id)
    _emit_note_change_ctx(
        ctx,
        event_type="note.deleted",
        document_ids=document_ids,
    )
    spec = ChangeSpec(
        domains=["note"],
        target_ids=[params.note_id],
        before=before,
        after=None,
        document_ids=document_ids,
    )
    return before, spec


@action(
    "note.restore",
    NoteRestoreParams,
    domains=["note"],
    undoable=True,
    invert=_invert_restore_note,
)
def _action_restore_note(
    db: Database, params: NoteRestoreParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    """Upsert a note from its snapshot (preserving id). Records whether the row
    pre-existed so its inverse picks delete (recreate) vs restore (edit)."""
    note_id = params.snapshot.get("id")
    existing = db.get(Note, note_id) if note_id else None
    before = existing.model_dump(mode="json") if existing else None
    note = restore_note_impl(db, params.snapshot)
    after = note.model_dump(mode="json")
    spec = ChangeSpec(
        domains=["note"],
        target_ids=[note.id],
        before=before,
        after=after,
        emit_type="note.updated" if before else "note.created",
        document_ids=_note_scope_document_ids(note),
    )
    return after, spec
