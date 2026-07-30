"""Agent working-memory routes — local, transparent, source-anchored notes."""

from __future__ import annotations

from fichero_server.core.timeutil import utc_now

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, ValidationError

from fichero_server.security import authz
from fichero_server.actions.registry import ActionContext, ChangeSpec, action, registry
from fichero_server.api.auth import action_context
from fichero_server.api.main import get_library_database, get_library_database_for_write
from fichero_server.db import Database
from fichero_server.models import (
    AgentNote,
    AgentNoteActor,
    AgentNoteListResponse,
    AgentNoteSourceAnchor,
    Document,
    DocType,
)

router = APIRouter(prefix="/agent-memory")


class AgentNoteCreateRequest(BaseModel):
    body: str
    source_anchor: AgentNoteSourceAnchor
    actor: AgentNoteActor
    kind: str | None = None
    tags: list[str] = Field(default_factory=list)


class AgentNotePatchRequest(BaseModel):
    body: str | None = None
    source_anchor: AgentNoteSourceAnchor | None = None
    actor: AgentNoteActor | None = None
    kind: str | None = None
    tags: list[str] | None = None


class AgentNoteUpdateActionParams(BaseModel):
    note_id: str = Field(description="Agent note id to update")
    update: AgentNotePatchRequest = Field(description="Partial agent note update")


class AgentNoteIdParams(BaseModel):
    note_id: str = Field(description="Agent note id")


class AgentNoteRestoreParams(BaseModel):
    snapshot: dict = Field(description="AgentNote.model_dump snapshot")


def _anchor_document_ids(anchor: AgentNoteSourceAnchor | None) -> list[str]:
    if anchor is None:
        return []
    return [doc_id for doc_id in {anchor.document_id, anchor.page_id} if doc_id]


def _validate_anchor(db: Database, anchor: AgentNoteSourceAnchor) -> None:
    if not any([anchor.document_id, anchor.page_id, anchor.expediente]):
        raise HTTPException(
            status_code=422,
            detail="source_anchor must include document_id, page_id, or expediente",
        )
    if (anchor.char_start is None) != (anchor.char_end is None):
        raise HTTPException(
            status_code=422,
            detail="source_anchor char_start and char_end must be set together",
        )
    if (
        anchor.char_start is not None
        and anchor.char_end is not None
        and anchor.char_start > anchor.char_end
    ):
        raise HTTPException(
            status_code=422,
            detail="source_anchor char_start must be <= char_end",
        )
    if anchor.document_id is not None and db.get(Document, anchor.document_id) is None:
        raise HTTPException(404, f"Document not found: {anchor.document_id}")
    if anchor.page_id is not None:
        page = db.get(Document, anchor.page_id)
        if page is None:
            raise HTTPException(404, f"Page not found: {anchor.page_id}")
        if page.doc_type != DocType.page:
            raise HTTPException(400, f"Document {anchor.page_id} is not a page")


def create_agent_note_impl(db: Database, request: AgentNoteCreateRequest) -> AgentNote:
    _validate_anchor(db, request.source_anchor)
    note = AgentNote(**request.model_dump())
    db.save(note)
    return note


def patch_agent_note_impl(
    db: Database,
    note_id: str,
    request: AgentNotePatchRequest,
) -> tuple[AgentNote, dict]:
    note = db.get(AgentNote, note_id)
    if note is None:
        raise HTTPException(404, f"Agent note not found: {note_id}")
    before = note.model_dump(mode="json")
    updates = request.model_dump(exclude_unset=True)
    next_anchor = (
        AgentNoteSourceAnchor.model_validate(updates["source_anchor"])
        if "source_anchor" in updates
        else note.source_anchor
    )
    _validate_anchor(db, next_anchor)
    if "source_anchor" in updates:
        updates["source_anchor"] = next_anchor
    if "actor" in updates:
        updates["actor"] = AgentNoteActor.model_validate(updates["actor"])
    for field, value in updates.items():
        setattr(note, field, value)
    note.updated_at = utc_now()
    db.save(note)
    return note, before


def delete_agent_note_impl(db: Database, note_id: str) -> tuple[list[str], dict]:
    note = db.get(AgentNote, note_id)
    if note is None:
        raise HTTPException(404, f"Agent note not found: {note_id}")
    before = note.model_dump(mode="json")
    document_ids = _anchor_document_ids(note.source_anchor)
    db.delete(note)
    return document_ids, before


def restore_agent_note_impl(db: Database, snapshot: dict) -> AgentNote:
    note = AgentNote(**snapshot)
    _validate_anchor(db, note.source_anchor)
    db.save(note)
    return note


def _invoke_agent_memory_action(
    db: Database,
    ctx: ActionContext,
    *,
    name: str,
    params: dict,
):
    try:
        return registry.invoke(db, name, params, ctx)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    except authz.AuthorizationError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("", response_model=AgentNote)
async def create_agent_note(
    request: AgentNoteCreateRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> AgentNote:
    result = _invoke_agent_memory_action(
        db,
        ctx,
        name="agent_memory.create",
        params=request.model_dump(mode="json"),
    )
    return AgentNote.model_validate(result.result)


@router.get("", response_model=AgentNoteListResponse)
async def list_agent_notes(
    actor_id: str | None = Query(default=None),
    kind: str | None = Query(default=None),
    source_document_id: str | None = Query(default=None),
    page_id: str | None = Query(default=None),
    expediente: str | None = Query(default=None),
    db: Database = Depends(get_library_database),
) -> AgentNoteListResponse:
    rows = db.query(AgentNote)
    if actor_id is not None:
        rows = [row for row in rows if row.actor.actor_id == actor_id]
    if kind is not None:
        rows = [row for row in rows if row.kind == kind]
    if source_document_id is not None:
        rows = [row for row in rows if row.source_anchor.document_id == source_document_id]
    if page_id is not None:
        rows = [row for row in rows if row.source_anchor.page_id == page_id]
    if expediente is not None:
        rows = [row for row in rows if row.source_anchor.expediente == expediente]
    rows.sort(key=lambda row: row.updated_at, reverse=True)
    return AgentNoteListResponse(items=rows, count=len(rows))


@router.get("/{note_id}", response_model=AgentNote)
async def get_agent_note(
    note_id: str,
    db: Database = Depends(get_library_database),
) -> AgentNote:
    note = db.get(AgentNote, note_id)
    if note is None:
        raise HTTPException(404, f"Agent note not found: {note_id}")
    return note


@router.patch("/{note_id}", response_model=AgentNote)
async def patch_agent_note(
    note_id: str,
    request: AgentNotePatchRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> AgentNote:
    result = _invoke_agent_memory_action(
        db,
        ctx,
        name="agent_memory.update",
        params={
            "note_id": note_id,
            "update": request.model_dump(mode="json", exclude_unset=True),
        },
    )
    return AgentNote.model_validate(result.result)


@router.delete("/{note_id}", status_code=204)
async def delete_agent_note(
    note_id: str,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> None:
    _invoke_agent_memory_action(
        db,
        ctx,
        name="agent_memory.delete",
        params={"note_id": note_id},
    )


def _invert_create(
    before: dict | None,
    after: dict | None,
    ctx: ActionContext,
) -> tuple[str, dict] | None:
    if not after or not after.get("id"):
        return None
    return ("agent_memory.delete", {"note_id": after["id"]})


def _invert_to_restore_before(
    before: dict | None,
    after: dict | None,
    ctx: ActionContext,
) -> tuple[str, dict] | None:
    if not before:
        return None
    return ("agent_memory.restore", {"snapshot": before})


def _invert_restore(
    before: dict | None,
    after: dict | None,
    ctx: ActionContext,
) -> tuple[str, dict] | None:
    if not after:
        return None
    note_id = after.get("id")
    if before is None:
        if not note_id:
            return None
        return ("agent_memory.delete", {"note_id": note_id})
    return ("agent_memory.restore", {"snapshot": before})


@action(
    "agent_memory.create",
    AgentNoteCreateRequest,
    domains=["agent-memory"],
    undoable=True,
    invert=_invert_create,
)
def _action_create_agent_note(
    db: Database,
    params: AgentNoteCreateRequest,
    ctx: ActionContext,
) -> tuple[dict, ChangeSpec]:
    note = create_agent_note_impl(db, params)
    after = note.model_dump(mode="json")
    spec = ChangeSpec(
        domains=["agent-memory"],
        target_ids=[note.id],
        before=None,
        after=after,
        emit_type="agent_memory.created",
        document_ids=_anchor_document_ids(note.source_anchor),
    )
    return after, spec


@action(
    "agent_memory.update",
    AgentNoteUpdateActionParams,
    domains=["agent-memory"],
    undoable=True,
    invert=_invert_to_restore_before,
)
def _action_update_agent_note(
    db: Database,
    params: AgentNoteUpdateActionParams,
    ctx: ActionContext,
) -> tuple[dict, ChangeSpec]:
    note, before = patch_agent_note_impl(db, params.note_id, params.update)
    after = note.model_dump(mode="json")
    spec = ChangeSpec(
        domains=["agent-memory"],
        target_ids=[note.id],
        before=before,
        after=after,
        emit_type="agent_memory.updated",
        document_ids=_anchor_document_ids(note.source_anchor),
    )
    return after, spec


@action(
    "agent_memory.delete",
    AgentNoteIdParams,
    domains=["agent-memory"],
    undoable=True,
    invert=_invert_to_restore_before,
)
def _action_delete_agent_note(
    db: Database,
    params: AgentNoteIdParams,
    ctx: ActionContext,
) -> tuple[dict, ChangeSpec]:
    document_ids, before = delete_agent_note_impl(db, params.note_id)
    spec = ChangeSpec(
        domains=["agent-memory"],
        target_ids=[params.note_id],
        before=before,
        after=None,
        emit_type="agent_memory.deleted",
        document_ids=document_ids,
    )
    return before, spec


@action(
    "agent_memory.restore",
    AgentNoteRestoreParams,
    domains=["agent-memory"],
    undoable=True,
    invert=_invert_restore,
)
def _action_restore_agent_note(
    db: Database,
    params: AgentNoteRestoreParams,
    ctx: ActionContext,
) -> tuple[dict, ChangeSpec]:
    note_id = params.snapshot.get("id")
    existing = db.get(AgentNote, note_id) if note_id else None
    before = existing.model_dump(mode="json") if existing else None
    note = restore_agent_note_impl(db, params.snapshot)
    after = note.model_dump(mode="json")
    spec = ChangeSpec(
        domains=["agent-memory"],
        target_ids=[note.id],
        before=before,
        after=after,
        emit_type="agent_memory.updated" if before else "agent_memory.created",
        document_ids=_anchor_document_ids(note.source_anchor),
    )
    return after, spec
