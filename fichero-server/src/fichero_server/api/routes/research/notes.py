"""Research Agents notes routes — Search Sources, Notes, Checklists."""

from fichero_server.core.timeutil import utc_now
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from fichero_server.api.auth import action_context
from fichero_server.api.change_stream import emit_change
from fichero_server.api.main import get_library_database, get_library_database_for_write
from fichero_server.actions.registry import ActionContext, ChangeSpec, action, registry
from fichero_server.db import Database
from fichero_server.models import ResearchNotesListResponse
from fichero_server.models.research import (
    ChecklistItem,
    ResearchChecklist,
    ResearchNote,
    ResearchNoteType,
    SearchSource,
    SearchSourceType,
)

router = APIRouter()


def _research_note_spec(
    row_id: str,
    *,
    emit_type: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> ChangeSpec:
    def _emit(ctx: ActionContext, spec: ChangeSpec) -> None:
        if not ctx.library_path:
            return
        emit_change(
            ctx.library_path,
            type=spec.emit_type,
            entity_ids=spec.entity_ids,
            actor=ctx.actor,
            run_id=ctx.run_id,
            origin_window=ctx.origin_window,
            origin_user=ctx.actor,
        )

    return ChangeSpec(
        domains=["research"],
        target_ids=[row_id],
        before=before,
        after=after,
        emit_type=emit_type,
        entity_ids=[row_id],
        emit_fn=_emit,
    )


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


def create_search_source_impl(
    db: Database, request: SearchSourceCreateRequest
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
    return source


def delete_search_source_impl(db: Database, source_id: str) -> dict[str, Any]:
    source = db.get(SearchSource, source_id)
    if not source:
        raise HTTPException(status_code=404, detail=f"Search source not found: {source_id}")
    before = source.model_dump(mode="json")
    db.delete(source)
    return before


def restore_search_source_impl(
    db: Database, snapshot: dict[str, Any]
) -> SearchSource:
    source = SearchSource(**snapshot)
    db.save(source)
    return source


@router.post("/sources", response_model=SearchSource)
async def create_search_source(
    request: SearchSourceCreateRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> SearchSource:
    result = registry.invoke(
        db,
        "research.source.create",
        request.model_dump(mode="json"),
        ctx,
    )
    return result.result


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


def create_note_impl(db: Database, request: NoteCreateRequest) -> ResearchNote:
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
    return note


def update_note_impl(
    db: Database, note_id: str, request: NoteUpdateRequest
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
    note.updated_at = utc_now()
    db.save(note)
    return note


def delete_note_impl(db: Database, note_id: str) -> dict[str, Any]:
    note = db.get(ResearchNote, note_id)
    if not note:
        raise HTTPException(status_code=404, detail=f"Note not found: {note_id}")
    before = note.model_dump(mode="json")
    db.delete(note)
    return before


def restore_note_impl(db: Database, snapshot: dict[str, Any]) -> ResearchNote:
    note = ResearchNote(**snapshot)
    db.save(note)
    return note


@router.post("/notes", response_model=ResearchNote)
async def create_note(
    request: NoteCreateRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> ResearchNote:
    result = registry.invoke(
        db,
        "research.note.create",
        request.model_dump(mode="json"),
        ctx,
    )
    return result.result


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
    ctx: ActionContext = Depends(action_context),
) -> ResearchNote:
    result = registry.invoke(
        db,
        "research.note.update",
        {"note_id": note_id, **request.model_dump(mode="json")},
        ctx,
    )
    return result.result


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


def create_checklist_impl(
    db: Database, request: ChecklistCreateRequest
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
    return checklist


def toggle_checklist_item_impl(
    db: Database,
    checklist_id: str,
    item_id: str,
    request: ChecklistItemToggleRequest,
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
                item.checked_at = utc_now()
                item.checked_by = "human"
            break
    checklist.updated_at = utc_now()
    db.save(checklist)
    return checklist


def delete_checklist_impl(db: Database, checklist_id: str) -> dict[str, Any]:
    checklist = db.get(ResearchChecklist, checklist_id)
    if not checklist:
        raise HTTPException(
            status_code=404, detail=f"Checklist not found: {checklist_id}"
        )
    before = checklist.model_dump(mode="json")
    db.delete(checklist)
    return before


def restore_checklist_impl(
    db: Database, snapshot: dict[str, Any]
) -> ResearchChecklist:
    checklist = ResearchChecklist(**snapshot)
    db.save(checklist)
    return checklist


@router.post("/checklists", response_model=ResearchChecklist)
async def create_checklist(
    request: ChecklistCreateRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> ResearchChecklist:
    result = registry.invoke(
        db,
        "research.checklist.create",
        request.model_dump(mode="json"),
        ctx,
    )
    return result.result


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
    ctx: ActionContext = Depends(action_context),
) -> ResearchChecklist:
    result = registry.invoke(
        db,
        "research.checklist.update",
        {
            "checklist_id": checklist_id,
            "item_id": item_id,
            **request.model_dump(mode="json"),
        },
        ctx,
    )
    return result.result


class SearchSourceIdParams(BaseModel):
    source_id: str


class SearchSourceRestoreParams(BaseModel):
    snapshot: dict[str, Any]


class NoteUpdateActionParams(BaseModel):
    note_id: str
    content: str | None = None
    note_type: ResearchNoteType | None = None
    tags: list[str] | None = None
    linked_source_ids: list[str] | None = None
    linked_claim_ids: list[str] | None = None
    metadata: dict[str, Any] | None = None


class NoteIdParams(BaseModel):
    note_id: str


class NoteRestoreParams(BaseModel):
    snapshot: dict[str, Any]


class ChecklistIdParams(BaseModel):
    checklist_id: str


class ChecklistRestoreParams(BaseModel):
    snapshot: dict[str, Any]


class ChecklistUpdateActionParams(BaseModel):
    checklist_id: str
    item_id: str
    checked: bool
    notes: str = ""


def _invert_create_source(before, after, ctx):
    if not after or not after.get("id"):
        return None
    return ("research.source.delete", {"source_id": after["id"]})


def _invert_restore_snapshot(action_name: str):
    def _invert(before, after, ctx):
        if not before:
            return None
        return (action_name, {"snapshot": before})

    return _invert


@action(
    "research.source.create",
    SearchSourceCreateRequest,
    domains=["research"],
    undoable=True,
    invert=_invert_create_source,
)
def _action_create_source(
    db: Database, params: SearchSourceCreateRequest, ctx: ActionContext
) -> tuple[SearchSource, ChangeSpec]:
    source = create_search_source_impl(db, params)
    return source, _research_note_spec(
        source.id,
        emit_type="note.updated",
        after=source.model_dump(mode="json"),
    )


@action(
    "research.source.delete",
    SearchSourceIdParams,
    domains=["research"],
    undoable=True,
    invert=_invert_restore_snapshot("research.source.restore"),
)
def _action_delete_source(
    db: Database, params: SearchSourceIdParams, ctx: ActionContext
) -> tuple[dict[str, Any], ChangeSpec]:
    before = delete_search_source_impl(db, params.source_id)
    return {"status": "deleted", "id": params.source_id}, _research_note_spec(
        params.source_id,
        emit_type="note.updated",
        before=before,
        after={"id": params.source_id},
    )


@action("research.source.restore", SearchSourceRestoreParams, domains=["research"])
def _action_restore_source(
    db: Database, params: SearchSourceRestoreParams, ctx: ActionContext
) -> tuple[SearchSource, ChangeSpec]:
    source = restore_search_source_impl(db, params.snapshot)
    return source, _research_note_spec(
        source.id,
        emit_type="note.updated",
        after=source.model_dump(mode="json"),
    )


def _invert_create_note(before, after, ctx):
    if not after or not after.get("id"):
        return None
    return ("research.note.delete", {"note_id": after["id"]})


@action(
    "research.note.create",
    NoteCreateRequest,
    domains=["research"],
    undoable=True,
    invert=_invert_create_note,
)
def _action_create_note(
    db: Database, params: NoteCreateRequest, ctx: ActionContext
) -> tuple[ResearchNote, ChangeSpec]:
    note = create_note_impl(db, params)
    return note, _research_note_spec(
        note.id,
        emit_type="note.created",
        after=note.model_dump(mode="json"),
    )


@action(
    "research.note.update",
    NoteUpdateActionParams,
    domains=["research"],
    undoable=True,
    invert=_invert_restore_snapshot("research.note.restore"),
)
def _action_update_note(
    db: Database, params: NoteUpdateActionParams, ctx: ActionContext
) -> tuple[ResearchNote, ChangeSpec]:
    before_note = db.get(ResearchNote, params.note_id)
    if before_note is None:
        raise HTTPException(status_code=404, detail=f"Note not found: {params.note_id}")
    note = update_note_impl(
        db,
        params.note_id,
        NoteUpdateRequest.model_validate(params.model_dump(exclude={"note_id"})),
    )
    return note, _research_note_spec(
        note.id,
        emit_type="note.updated",
        before=before_note.model_dump(mode="json"),
        after=note.model_dump(mode="json"),
    )


@action(
    "research.note.delete",
    NoteIdParams,
    domains=["research"],
    undoable=True,
    invert=_invert_restore_snapshot("research.note.restore"),
)
def _action_delete_note(
    db: Database, params: NoteIdParams, ctx: ActionContext
) -> tuple[dict[str, Any], ChangeSpec]:
    before = delete_note_impl(db, params.note_id)
    return {"status": "deleted", "id": params.note_id}, _research_note_spec(
        params.note_id,
        emit_type="note.updated",
        before=before,
        after={"id": params.note_id},
    )


@action("research.note.restore", NoteRestoreParams, domains=["research"])
def _action_restore_note(
    db: Database, params: NoteRestoreParams, ctx: ActionContext
) -> tuple[ResearchNote, ChangeSpec]:
    note = restore_note_impl(db, params.snapshot)
    return note, _research_note_spec(
        note.id,
        emit_type="note.updated",
        after=note.model_dump(mode="json"),
    )


def _invert_create_checklist(before, after, ctx):
    if not after or not after.get("id"):
        return None
    return ("research.checklist.delete", {"checklist_id": after["id"]})


@action(
    "research.checklist.create",
    ChecklistCreateRequest,
    domains=["research"],
    undoable=True,
    invert=_invert_create_checklist,
)
def _action_create_checklist(
    db: Database, params: ChecklistCreateRequest, ctx: ActionContext
) -> tuple[ResearchChecklist, ChangeSpec]:
    checklist = create_checklist_impl(db, params)
    return checklist, _research_note_spec(
        checklist.id,
        emit_type="note.updated",
        after=checklist.model_dump(mode="json"),
    )


@action(
    "research.checklist.update",
    ChecklistUpdateActionParams,
    domains=["research"],
    undoable=True,
    invert=_invert_restore_snapshot("research.checklist.restore"),
)
def _action_update_checklist(
    db: Database, params: ChecklistUpdateActionParams, ctx: ActionContext
) -> tuple[ResearchChecklist, ChangeSpec]:
    before_checklist = db.get(ResearchChecklist, params.checklist_id)
    if before_checklist is None:
        raise HTTPException(
            status_code=404, detail=f"Checklist not found: {params.checklist_id}"
        )
    checklist = toggle_checklist_item_impl(
        db,
        params.checklist_id,
        params.item_id,
        ChecklistItemToggleRequest.model_validate(
            params.model_dump(exclude={"checklist_id", "item_id"})
        ),
    )
    return checklist, _research_note_spec(
        checklist.id,
        emit_type="note.updated",
        before=before_checklist.model_dump(mode="json"),
        after=checklist.model_dump(mode="json"),
    )


@action(
    "research.checklist.delete",
    ChecklistIdParams,
    domains=["research"],
    undoable=True,
    invert=_invert_restore_snapshot("research.checklist.restore"),
)
def _action_delete_checklist(
    db: Database, params: ChecklistIdParams, ctx: ActionContext
) -> tuple[dict[str, Any], ChangeSpec]:
    before = delete_checklist_impl(db, params.checklist_id)
    return {"status": "deleted", "id": params.checklist_id}, _research_note_spec(
        params.checklist_id,
        emit_type="note.updated",
        before=before,
        after={"id": params.checklist_id},
    )


@action("research.checklist.restore", ChecklistRestoreParams, domains=["research"])
def _action_restore_checklist(
    db: Database, params: ChecklistRestoreParams, ctx: ActionContext
) -> tuple[ResearchChecklist, ChangeSpec]:
    checklist = restore_checklist_impl(db, params.snapshot)
    return checklist, _research_note_spec(
        checklist.id,
        emit_type="note.updated",
        after=checklist.model_dump(mode="json"),
    )
