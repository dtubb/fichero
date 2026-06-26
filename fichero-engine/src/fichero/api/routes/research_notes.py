"""Research Agents notes routes — Search Sources, Notes, Checklists."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from fichero.api.library_header import require_library_path
from fichero.api.auth import request_actor
from fichero.api.change_stream import emit_change
from fichero.api.main import get_library_database, get_library_database_for_write
from fichero.db import Database
from fichero.research_models import (
    ChecklistItem,
    ResearchChecklist,
    ResearchNote,
    ResearchNoteType,
    SearchSource,
    SearchSourceType,
)
from fichero.models import ResearchNotesListResponse

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# Search Sources
# ─────────────────────────────────────────────────────────────────────────────


class SearchSourceCreateRequest(BaseModel):
    project_id: str
    source_type: SearchSourceType
    label: str
    url: str | None = None
    path: str | None = None
    description: str = ""
    access_status: str = "public"
    reliability: float = 0.5
    metadata: dict[str, Any] = Field(default_factory=dict)


@router.post("/sources", response_model=SearchSource)
async def create_search_source(
    request: SearchSourceCreateRequest,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str = Depends(require_library_path),
    x_fichero_origin_window: str | None = Header(
        default=None, alias="X-Fichero-Origin-Window"
    ),
    actor: str = Depends(request_actor),
) -> SearchSource:
    source = SearchSource(
        project_id=request.project_id,
        source_type=request.source_type,
        label=request.label,
        url=request.url,
        path=request.path,
        description=request.description,
        access_status=request.access_status,
        reliability=request.reliability,
        metadata=request.metadata,
    )
    db.save(source)
    emit_change(
        x_fichero_library_path,
        type="note.updated",
        actor=actor,
        run_id=None,
        origin_window=x_fichero_origin_window,
        origin_user=actor,
    )
    return source


@router.get("/projects/{project_id}/sources", response_model=ResearchNotesListResponse)
async def list_search_sources(
    project_id: str,
    db: Database = Depends(get_library_database),
) -> ResearchNotesListResponse:
    items = db.query(SearchSource, project_id=project_id)
    return ResearchNotesListResponse(items=items, count=len(items))


# ─────────────────────────────────────────────────────────────────────────────
# Research Notes
# ─────────────────────────────────────────────────────────────────────────────


class NoteCreateRequest(BaseModel):
    project_id: str
    task_id: str | None = None
    step_id: str | None = None
    note_type: ResearchNoteType = ResearchNoteType.observation
    content: str
    tags: list[str] = Field(default_factory=list)
    linked_source_ids: list[str] = Field(default_factory=list)
    linked_claim_ids: list[str] = Field(default_factory=list)
    created_by: str = "human"
    metadata: dict[str, Any] = Field(default_factory=dict)


class NoteUpdateRequest(BaseModel):
    content: str | None = None
    note_type: ResearchNoteType | None = None
    tags: list[str] | None = None
    linked_source_ids: list[str] | None = None
    linked_claim_ids: list[str] | None = None
    metadata: dict[str, Any] | None = None


@router.post("/notes", response_model=ResearchNote)
async def create_note(
    request: NoteCreateRequest,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str = Depends(require_library_path),
    x_fichero_origin_window: str | None = Header(
        default=None, alias="X-Fichero-Origin-Window"
    ),
    actor: str = Depends(request_actor),
) -> ResearchNote:
    note = ResearchNote(
        project_id=request.project_id,
        task_id=request.task_id,
        step_id=request.step_id,
        note_type=request.note_type,
        content=request.content,
        tags=request.tags,
        linked_source_ids=request.linked_source_ids,
        linked_claim_ids=request.linked_claim_ids,
        created_by=request.created_by,
        metadata=request.metadata,
    )
    db.save(note)
    emit_change(
        x_fichero_library_path,
        type="note.created",
        actor=actor,
        origin_window=x_fichero_origin_window,
        origin_user=actor,
    )
    return note


@router.get("/projects/{project_id}/notes", response_model=ResearchNotesListResponse)
async def list_notes(
    project_id: str,
    task_id: str | None = None,
    db: Database = Depends(get_library_database),
) -> list[ResearchNote]:
    notes = db.query(ResearchNote, project_id=project_id)
    if task_id is not None:
        notes = [n for n in notes if n.task_id == task_id]
    items = sorted(notes, key=lambda n: n.created_at, reverse=True)
    return ResearchNotesListResponse(items=items, count=len(items))


@router.get("/notes/{note_id}", response_model=ResearchNote)
async def get_note(
    note_id: str,
    db: Database = Depends(get_library_database),
) -> ResearchNote:
    note = db.get(ResearchNote, note_id)
    if not note:
        raise HTTPException(status_code=404, detail=f"Note not found: {note_id}")
    return note


@router.patch("/notes/{note_id}", response_model=ResearchNote)
async def update_note(
    note_id: str,
    request: NoteUpdateRequest,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str = Depends(require_library_path),
    x_fichero_origin_window: str | None = Header(
        default=None, alias="X-Fichero-Origin-Window"
    ),
    actor: str = Depends(request_actor),
) -> ResearchNote:
    note = db.get(ResearchNote, note_id)
    if not note:
        raise HTTPException(status_code=404, detail=f"Note not found: {note_id}")
    if request.content is not None:
        note.content = request.content
    if request.note_type is not None:
        note.note_type = request.note_type
    if request.tags is not None:
        note.tags = request.tags
    if request.linked_source_ids is not None:
        note.linked_source_ids = request.linked_source_ids
    if request.linked_claim_ids is not None:
        note.linked_claim_ids = request.linked_claim_ids
    if request.metadata is not None:
        note.metadata = request.metadata
    note.updated_at = datetime.now()
    db.save(note)
    emit_change(
        x_fichero_library_path,
        type="note.updated",
        actor=actor,
        origin_window=x_fichero_origin_window,
        origin_user=actor,
    )
    return note


# ─────────────────────────────────────────────────────────────────────────────
# Research Checklists
# ─────────────────────────────────────────────────────────────────────────────


class ChecklistCreateRequest(BaseModel):
    project_id: str
    task_id: str | None = None
    step_id: str | None = None
    title: str
    items: list[ChecklistItem] = Field(default_factory=list)
    created_by: str = "human"
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChecklistItemToggleRequest(BaseModel):
    checked: bool
    notes: str = ""


@router.post("/checklists", response_model=ResearchChecklist)
async def create_checklist(
    request: ChecklistCreateRequest,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str = Depends(require_library_path),
    x_fichero_origin_window: str | None = Header(
        default=None, alias="X-Fichero-Origin-Window"
    ),
    actor: str = Depends(request_actor),
) -> ResearchChecklist:
    checklist = ResearchChecklist(
        project_id=request.project_id,
        task_id=request.task_id,
        step_id=request.step_id,
        title=request.title,
        items=request.items,
        created_by=request.created_by,
        metadata=request.metadata,
    )
    db.save(checklist)
    emit_change(
        x_fichero_library_path,
        type="note.updated",
        actor=actor,
        run_id=None,
        origin_window=x_fichero_origin_window,
        origin_user=actor,
    )
    return checklist


@router.get(
    "/projects/{project_id}/checklists", response_model=ResearchNotesListResponse
)
async def list_checklists(
    project_id: str,
    db: Database = Depends(get_library_database),
) -> ResearchNotesListResponse:
    items = db.query(ResearchChecklist, project_id=project_id)
    return ResearchNotesListResponse(items=items, count=len(items))


@router.patch(
    "/checklists/{checklist_id}/items/{item_id}", response_model=ResearchChecklist
)
async def toggle_checklist_item(
    checklist_id: str,
    item_id: str,
    request: ChecklistItemToggleRequest,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str = Depends(require_library_path),
    x_fichero_origin_window: str | None = Header(
        default=None, alias="X-Fichero-Origin-Window"
    ),
    actor: str = Depends(request_actor),
) -> ResearchChecklist:
    checklist = db.get(ResearchChecklist, checklist_id)
    if not checklist:
        raise HTTPException(
            status_code=404, detail=f"Checklist not found: {checklist_id}"
        )
    for item in checklist.items:
        if item.id == item_id:
            item.checked = request.checked
            item.notes = request.notes
            if request.checked:
                item.checked_at = datetime.now()
                item.checked_by = "human"
            break
    checklist.updated_at = datetime.now()
    db.save(checklist)
    emit_change(
        x_fichero_library_path,
        type="note.updated",
        actor=actor,
        run_id=None,
        origin_window=x_fichero_origin_window,
        origin_user=actor,
    )
    return checklist
