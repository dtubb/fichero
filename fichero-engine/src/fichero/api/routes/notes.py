"""Zettelkasten Notes API (#917).

Atomic user notes networked by bidirectional links. Notes can
cross-reference other notes, entities, claims, and documents,
forming a personal knowledge graph independent of the source
corpus.
"""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from fichero.api.main import get_library_database
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
        raise HTTPException(400, "Notes can be scoped to either a page or a folder, not both")
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


@router.post("", response_model=Note)
async def create_note(
    request: NoteCreateRequest,
    db: Database = Depends(get_library_database),
) -> Note:
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
        rows = [r for r in rows if r.page_id == page_id or _note_links_document(r, page_id)]
    if folder_id is not None:
        rows = [r for r in rows if r.folder_id == folder_id or _note_links_document(r, folder_id)]
    if linked_structure_node_id is not None:
        rows = [r for r in rows if r.linked_structure_node_id == linked_structure_node_id]
    if q:
        needle = q.lower()
        rows = [
            r for r in rows
            if needle in (r.body or "").lower()
            or needle in (r.title or "").lower()
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


@router.patch("/{note_id}", response_model=Note)
async def patch_note(
    note_id: str,
    request: NotePatchRequest,
    db: Database = Depends(get_library_database),
) -> Note:
    note = db.get(Note, note_id)
    if note is None:
        raise HTTPException(404, f"Note not found: {note_id}")
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
    return note


@router.delete("/{note_id}", status_code=204)
async def delete_note(
    note_id: str,
    db: Database = Depends(get_library_database),
) -> None:
    note = db.get(Note, note_id)
    if note is None:
        raise HTTPException(404, f"Note not found: {note_id}")
    db.delete(note)


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
    db: Database = Depends(get_library_database),
) -> NoteLink:
    if db.get(Note, note_id) is None:
        raise HTTPException(404, f"Source note not found: {note_id}")
    if db.get(Note, request.target_note_id) is None:
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
    return link


@router.delete("/{note_id}/links/{link_id}", status_code=204)
async def delete_note_link(
    note_id: str,
    link_id: str,
    db: Database = Depends(get_library_database),
) -> None:
    link = db.get(NoteLink, link_id)
    if link is None:
        raise HTTPException(404, f"Link not found: {link_id}")
    if link.source_note_id != note_id and link.target_note_id != note_id:
        raise HTTPException(400, f"Link {link_id} does not involve note {note_id}")
    db.delete(link)


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
    incoming = [
        link for link in db.query(NoteLink)
        if link.target_note_id == note_id
    ]
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
    outgoing = [
        link for link in db.query(NoteLink)
        if link.source_note_id == note_id
    ]
    target_ids = {link.target_note_id for link in outgoing}
    notes = [db.get(Note, tid) for tid in target_ids]
    items = [n for n in notes if n is not None]
    return NoteListResponse(items=items, count=len(items))
