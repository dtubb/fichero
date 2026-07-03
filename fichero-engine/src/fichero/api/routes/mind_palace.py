"""Mind Palace API routes (dev tier) — Layer 6 spatial workspace."""

import math
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from fichero.api.auth import action_context, request_actor
from fichero.api.change_stream import emit_change
from fichero.api.library_header import require_library_path
from fichero.api.main import get_library_database, get_library_database_for_write
from fichero.db import Database
from fichero.spatial_models import (
    ArrangementType,
    CanvasItem,
    CanvasItemKind,
    CanvasLayout,
    CaptureRegion,
    ConnectionType,
    NativeNote,
    NodeType,
    NoteStatus,
    NoteType,
    RoomSceneSummary,
    RoomType,
    SpatialConnection,
    SpatialNode,
    SpatialStack,
    SpatialViewport,
    SpatialRoom,
)
from fichero.models import Document, MindPalaceListResponse
from fichero.actions.registry import action, ActionContext, ChangeSpec, registry
from fichero.spatial_arrange import (
    DEFAULT_SPACING,
    ArrangeStrategy,
    compute_arrangement,
)


router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# Request/Response models
# ─────────────────────────────────────────────────────────────────────────────


class RoomCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    description: str = ""
    room_type: RoomType = RoomType.research
    owner_id: str = "user"
    metadata: dict[str, Any] = Field(default_factory=dict)


class RoomUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    description: str | None = None
    room_type: RoomType | None = None
    metadata: dict[str, Any] | None = None


class RoomUpdateActionParams(BaseModel):
    room_id: str
    update: RoomUpdateRequest


class RoomDeleteParams(BaseModel):
    room_id: str


class NodeCreateRequest(BaseModel):
    room_id: str
    node_type: NodeType
    source_id: str | None = None
    label: str = ""
    position_x: float = 0.0
    position_y: float = 0.0
    position_z: float = 0.0
    rotation_x: float = 0.0
    rotation_y: float = 0.0
    rotation_z: float = 0.0
    scale: float = 1.0
    created_by: str = "user"
    metadata: dict[str, Any] = Field(default_factory=dict)


class NodeMoveRequest(BaseModel):
    position_x: float
    position_y: float
    position_z: float
    rotation_x: float | None = None
    rotation_y: float | None = None
    rotation_z: float | None = None
    scale: float | None = None


class ConnectionCreateRequest(BaseModel):
    room_id: str
    source_node_id: str
    target_node_id: str
    connection_type: ConnectionType
    link_subtype: str | None = None
    created_by: str = "user"
    metadata: dict[str, Any] = Field(default_factory=dict)


class StackCreateRequest(BaseModel):
    room_id: str
    name: str = ""
    node_ids: list[str] = Field(default_factory=list)
    position_x: float = 0.0
    position_y: float = 0.0
    position_z: float = 0.0


class NoteCreateRequest(BaseModel):
    room_id: str | None = None
    content: str = ""
    note_type: NoteType = NoteType.user
    author_id: str = "user"
    linked_claim_ids: list[str] = Field(default_factory=list)
    linked_source_ids: list[str] = Field(default_factory=list)
    linked_entity_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class NoteUpdateRequest(BaseModel):
    content: str | None = None
    note_type: NoteType | None = None
    status: NoteStatus | None = None
    linked_claim_ids: list[str] | None = None
    linked_source_ids: list[str] | None = None
    linked_entity_ids: list[str] | None = None
    metadata: dict[str, Any] | None = None


class FocusNodeRequest(BaseModel):
    node_id: str


class CaptureRequest(BaseModel):
    region: CaptureRegion = CaptureRegion.full
    selection_ids: list[str] | None = None


class ArrangeRequest(BaseModel):
    node_ids: list[str]
    arrangement_type: ArrangementType = ArrangementType.semantic


class MindPalaceDeletedResponse(BaseModel):
    status: str


class CaptureViewportResponse(BaseModel):
    status: str
    message: str
    room_id: str
    region: str


class TinderboxExportResponse(BaseModel):
    status: str
    message: str
    room_id: str


class ViewportSaveRequest(BaseModel):
    """Viewport save — camera fields optional, room/user from path."""

    camera_x: float = 0.0
    camera_y: float = 0.0
    camera_z: float = 10.0
    focus_node_id: str | None = None
    zoom_level: float = 1.0
    bookmark_name: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


def _resolve_action_ctx(
    ctx: ActionContext | object,
    *,
    actor: str | object = "system",
    library_path: str | object | None = None,
    origin_window: str | object | None = None,
) -> ActionContext:
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


def _legacy_room_exists(db: Database, room_id: str) -> bool:
    """True when the legacy spatial-room table still has ``room_id``."""
    return any(room.id == room_id for room in db._legacy_all_spatial_room_rows())


def _room_from_node_or_404(db: Database, room_id: str) -> SpatialRoom:
    """Read a room from its node-backed representation, never the legacy row."""
    doc = db.get(Document, room_id)
    if doc is None:
        if _legacy_room_exists(db, room_id):
            raise HTTPException(status_code=404, detail=f"Room node not found: {room_id}")
        raise HTTPException(status_code=404, detail=f"Room not found: {room_id}")
    try:
        return db._spatial_room_from_document(db, doc)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _list_rooms_from_nodes(
    db: Database,
    *,
    room_type: RoomType | None = None,
    owner_id: str | None = None,
) -> list[SpatialRoom]:
    """List room nodes, but fail loudly if a legacy room lost its node."""
    docs = db.query(Document, node_kind="room")
    by_id: dict[str, SpatialRoom] = {}
    for doc in docs:
        room = db._spatial_room_from_document(db, doc)
        by_id[room.id] = room

    for legacy_room in db._legacy_all_spatial_room_rows():
        if legacy_room.id not in by_id:
            raise HTTPException(
                status_code=404,
                detail=f"Room node not found: {legacy_room.id}",
            )

    rows = list(by_id.values())
    if room_type is not None:
        rows = [r for r in rows if r.room_type == room_type]
    if owner_id is not None:
        rows = [r for r in rows if r.owner_id == owner_id]
    return rows


def create_room_impl(db: Database, request: RoomCreateRequest) -> SpatialRoom:
    now = datetime.now()
    room = SpatialRoom(
        name=request.name.strip(),
        description=request.description.strip(),
        room_type=request.room_type,
        owner_id=request.owner_id,
        metadata=dict(request.metadata),
        created_at=now,
        updated_at=now,
    )
    db.save(room)
    return _room_from_node_or_404(db, room.id)


def update_room_impl(
    db: Database, room_id: str, request: RoomUpdateRequest
) -> tuple[dict[str, Any], SpatialRoom]:
    room = _room_from_node_or_404(db, room_id)
    before = room.model_dump(mode="json")
    updates = request.model_dump(exclude_unset=True, exclude_none=True)
    for key, value in updates.items():
        setattr(room, key, value)
    room.updated_at = datetime.now()
    db.save(room)
    return before, _room_from_node_or_404(db, room_id)


def delete_room_impl(db: Database, room_id: str) -> dict[str, Any]:
    room = _room_from_node_or_404(db, room_id)
    before = room.model_dump(mode="json")
    db.delete(room)
    return before


# ─────────────────────────────────────────────────────────────────────────────
# Room Management
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/rooms", response_model=SpatialRoom)
async def create_room(
    request: RoomCreateRequest,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str | object = Depends(require_library_path),
    x_fichero_origin_window: str | object | None = Header(
        default=None, alias="X-Fichero-Origin-Window"
    ),
    actor: str | object = Depends(request_actor),
    ctx: ActionContext | object = Depends(action_context),
) -> SpatialRoom:
    ctx = _resolve_action_ctx(
        ctx,
        actor=actor,
        library_path=x_fichero_library_path,
        origin_window=x_fichero_origin_window,
    )
    result = registry.invoke(
        db,
        "room.create",
        request.model_dump(mode="json"),
        ctx,
    )
    return SpatialRoom.model_validate(result.result)


@router.get("/rooms", response_model=MindPalaceListResponse)
async def list_rooms(
    room_type: RoomType | None = None,
    owner_id: str | None = None,
    db: Database = Depends(get_library_database),
) -> list[SpatialRoom]:
    rows = _list_rooms_from_nodes(db, room_type=room_type, owner_id=owner_id)
    return MindPalaceListResponse(items=rows, count=len(rows))


@router.get("/rooms/{room_id}", response_model=SpatialRoom)
async def get_room(
    room_id: str,
    db: Database = Depends(get_library_database),
) -> SpatialRoom:
    return _room_from_node_or_404(db, room_id)


@router.patch("/rooms/{room_id}", response_model=SpatialRoom)
async def update_room(
    room_id: str,
    request: RoomUpdateRequest,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str | object = Depends(require_library_path),
    x_fichero_origin_window: str | object | None = Header(
        default=None, alias="X-Fichero-Origin-Window"
    ),
    actor: str | object = Depends(request_actor),
    ctx: ActionContext | object = Depends(action_context),
) -> SpatialRoom:
    ctx = _resolve_action_ctx(
        ctx,
        actor=actor,
        library_path=x_fichero_library_path,
        origin_window=x_fichero_origin_window,
    )
    result = registry.invoke(
        db,
        "room.update",
        {
            "room_id": room_id,
            "update": request.model_dump(mode="json", exclude_unset=True),
        },
        ctx,
    )
    return SpatialRoom.model_validate(result.result)


@router.delete("/rooms/{room_id}")
async def delete_room(
    room_id: str,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str | object = Depends(require_library_path),
    x_fichero_origin_window: str | object | None = Header(
        default=None, alias="X-Fichero-Origin-Window"
    ),
    actor: str | object = Depends(request_actor),
    ctx: ActionContext | object = Depends(action_context),
) -> MindPalaceDeletedResponse:
    ctx = _resolve_action_ctx(
        ctx,
        actor=actor,
        library_path=x_fichero_library_path,
        origin_window=x_fichero_origin_window,
    )
    result = registry.invoke(db, "room.delete", {"room_id": room_id}, ctx)
    return MindPalaceDeletedResponse.model_validate(result.result)


@action("room.create", RoomCreateRequest, domains=["mind_palace", "document"])
def _action_create_room(
    db: Database, params: RoomCreateRequest, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    room = create_room_impl(db, params)
    payload = room.model_dump(mode="json")
    spec = ChangeSpec(
        domains=["mind_palace", "document"],
        target_ids=[room.id],
        after={"room": payload},
        emit_type="document.created",
        document_ids=[room.id],
    )
    return payload, spec


@action("room.update", RoomUpdateActionParams, domains=["mind_palace", "document"])
def _action_update_room(
    db: Database, params: RoomUpdateActionParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    before, room = update_room_impl(db, params.room_id, params.update)
    payload = room.model_dump(mode="json")
    spec = ChangeSpec(
        domains=["mind_palace", "document"],
        target_ids=[room.id],
        before={"room": before},
        after={"room": payload},
        emit_type="document.updated",
        document_ids=[room.id],
    )
    return payload, spec


@action("room.delete", RoomDeleteParams, domains=["mind_palace", "document"])
def _action_delete_room(
    db: Database, params: RoomDeleteParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    before = delete_room_impl(db, params.room_id)
    spec = ChangeSpec(
        domains=["mind_palace", "document"],
        target_ids=[params.room_id],
        before={"room": before},
        after=None,
        emit_type="document.deleted",
        document_ids=[params.room_id],
    )
    return MindPalaceDeletedResponse(status="deleted").model_dump(mode="json"), spec


@router.get("/rooms/{room_id}/scene", response_model=RoomSceneSummary)
async def get_scene_summary(
    room_id: str,
    db: Database = Depends(get_library_database),
) -> RoomSceneSummary:
    room = db.get(SpatialRoom, room_id)
    if not room:
        raise HTTPException(status_code=404, detail=f"Room not found: {room_id}")

    nodes = [n for n in db.all(SpatialNode) if n.room_id == room_id]
    connections = [c for c in db.all(SpatialConnection) if c.room_id == room_id]
    stacks = [s for s in db.all(SpatialStack) if s.room_id == room_id]
    notes = [n for n in db.all(NativeNote) if n.room_id == room_id]

    node_types: dict[str, int] = {}
    for node in nodes:
        key = node.node_type.value
        node_types[key] = node_types.get(key, 0) + 1

    return RoomSceneSummary(
        room_id=room_id,
        room_name=room.name,
        node_count=len(nodes),
        connection_count=len(connections),
        stack_count=len(stacks),
        note_count=len(notes),
        node_types=node_types,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Node Management
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/nodes", response_model=SpatialNode)
async def place_node(
    request: NodeCreateRequest,
    db: Database = Depends(get_library_database_for_write),
) -> SpatialNode:
    room = db.get(SpatialRoom, request.room_id)
    if not room:
        raise HTTPException(
            status_code=404, detail=f"Room not found: {request.room_id}"
        )

    now = datetime.now()
    node = SpatialNode(
        room_id=request.room_id,
        node_type=request.node_type,
        source_id=request.source_id,
        label=request.label.strip(),
        position_x=request.position_x,
        position_y=request.position_y,
        position_z=request.position_z,
        rotation_x=request.rotation_x,
        rotation_y=request.rotation_y,
        rotation_z=request.rotation_z,
        scale=request.scale,
        created_by=request.created_by,
        metadata=dict(request.metadata),
        created_at=now,
        updated_at=now,
    )
    db.save(node)
    return node


@router.get("/nodes", response_model=MindPalaceListResponse)
async def list_nodes(
    room_id: str,
    node_type: NodeType | None = None,
    db: Database = Depends(get_library_database),
) -> list[SpatialNode]:
    rows = [n for n in db.all(SpatialNode) if n.room_id == room_id]
    if node_type is not None:
        rows = [n for n in rows if n.node_type == node_type]
    return MindPalaceListResponse(items=rows, count=len(rows))


@router.get("/nodes/{node_id}", response_model=SpatialNode)
async def get_node(
    node_id: str,
    db: Database = Depends(get_library_database),
) -> SpatialNode:
    node = db.get(SpatialNode, node_id)
    if not node:
        raise HTTPException(status_code=404, detail=f"Node not found: {node_id}")
    return node


@router.patch("/nodes/{node_id}", response_model=SpatialNode)
async def move_node(
    node_id: str,
    request: NodeMoveRequest,
    db: Database = Depends(get_library_database_for_write),
) -> SpatialNode:
    node = db.get(SpatialNode, node_id)
    if not node:
        raise HTTPException(status_code=404, detail=f"Node not found: {node_id}")

    node.position_x = request.position_x
    node.position_y = request.position_y
    node.position_z = request.position_z
    if request.rotation_x is not None:
        node.rotation_x = request.rotation_x
    if request.rotation_y is not None:
        node.rotation_y = request.rotation_y
    if request.rotation_z is not None:
        node.rotation_z = request.rotation_z
    if request.scale is not None:
        node.scale = request.scale
    node.updated_at = datetime.now()
    db.save(node)
    return node


@router.delete("/nodes/{node_id}")
async def remove_node(
    node_id: str,
    db: Database = Depends(get_library_database_for_write),
) -> MindPalaceDeletedResponse:
    node = db.get(SpatialNode, node_id)
    if not node:
        raise HTTPException(status_code=404, detail=f"Node not found: {node_id}")
    db.delete(node)
    return MindPalaceDeletedResponse(status="deleted")


# ─────────────────────────────────────────────────────────────────────────────
# Connection Management
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/connections", response_model=SpatialConnection)
async def create_connection(
    request: ConnectionCreateRequest,
    db: Database = Depends(get_library_database_for_write),
) -> SpatialConnection:
    room = db.get(SpatialRoom, request.room_id)
    if not room:
        raise HTTPException(
            status_code=404, detail=f"Room not found: {request.room_id}"
        )

    source_node = db.get(SpatialNode, request.source_node_id)
    if not source_node:
        raise HTTPException(
            status_code=404, detail=f"Source node not found: {request.source_node_id}"
        )

    target_node = db.get(SpatialNode, request.target_node_id)
    if not target_node:
        raise HTTPException(
            status_code=404, detail=f"Target node not found: {request.target_node_id}"
        )

    conn = SpatialConnection(
        room_id=request.room_id,
        source_node_id=request.source_node_id,
        target_node_id=request.target_node_id,
        connection_type=request.connection_type,
        link_subtype=request.link_subtype,
        created_by=request.created_by,
        metadata=dict(request.metadata),
        created_at=datetime.now(),
    )
    db.save(conn)
    return conn


@router.get("/connections", response_model=MindPalaceListResponse)
async def list_connections(
    room_id: str,
    connection_type: ConnectionType | None = None,
    db: Database = Depends(get_library_database),
) -> list[SpatialConnection]:
    rows = [c for c in db.all(SpatialConnection) if c.room_id == room_id]
    if connection_type is not None:
        rows = [c for c in rows if c.connection_type == connection_type]
    return MindPalaceListResponse(items=rows, count=len(rows))


@router.delete("/connections/{connection_id}")
async def remove_connection(
    connection_id: str,
    db: Database = Depends(get_library_database_for_write),
) -> MindPalaceDeletedResponse:
    conn = db.get(SpatialConnection, connection_id)
    if not conn:
        raise HTTPException(
            status_code=404, detail=f"Connection not found: {connection_id}"
        )
    db.delete(conn)
    return MindPalaceDeletedResponse(status="deleted")


# ─────────────────────────────────────────────────────────────────────────────
# Stack Management
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/stacks", response_model=SpatialStack)
async def create_stack(
    request: StackCreateRequest,
    db: Database = Depends(get_library_database_for_write),
) -> SpatialStack:
    room = db.get(SpatialRoom, request.room_id)
    if not room:
        raise HTTPException(
            status_code=404, detail=f"Room not found: {request.room_id}"
        )

    now = datetime.now()
    stack = SpatialStack(
        room_id=request.room_id,
        name=request.name.strip(),
        node_ids=list(request.node_ids),
        position_x=request.position_x,
        position_y=request.position_y,
        position_z=request.position_z,
        created_at=now,
        updated_at=now,
    )
    db.save(stack)
    return stack


@router.get("/stacks", response_model=MindPalaceListResponse)
async def list_stacks(
    room_id: str,
    db: Database = Depends(get_library_database),
) -> MindPalaceListResponse:
    stacks = [s for s in db.all(SpatialStack) if s.room_id == room_id]
    return MindPalaceListResponse(items=stacks, count=len(stacks))


@router.get("/stacks/{stack_id}", response_model=SpatialStack)
async def get_stack(
    stack_id: str,
    db: Database = Depends(get_library_database),
) -> SpatialStack:
    stack = db.get(SpatialStack, stack_id)
    if not stack:
        raise HTTPException(status_code=404, detail=f"Stack not found: {stack_id}")
    return stack


@router.post("/stacks/{stack_id}/nodes/{node_id}", response_model=SpatialStack)
async def add_to_stack(
    stack_id: str,
    node_id: str,
    db: Database = Depends(get_library_database_for_write),
) -> SpatialStack:
    stack = db.get(SpatialStack, stack_id)
    if not stack:
        raise HTTPException(status_code=404, detail=f"Stack not found: {stack_id}")
    if node_id not in stack.node_ids:
        stack.node_ids = stack.node_ids + [node_id]
        stack.updated_at = datetime.now()
        db.save(stack)
    return stack


@router.delete("/stacks/{stack_id}/nodes/{node_id}", response_model=SpatialStack)
async def remove_from_stack(
    stack_id: str,
    node_id: str,
    db: Database = Depends(get_library_database_for_write),
) -> SpatialStack:
    stack = db.get(SpatialStack, stack_id)
    if not stack:
        raise HTTPException(status_code=404, detail=f"Stack not found: {stack_id}")
    if node_id in stack.node_ids:
        stack.node_ids = [n for n in stack.node_ids if n != node_id]
        stack.updated_at = datetime.now()
        db.save(stack)
    return stack


# ─────────────────────────────────────────────────────────────────────────────
# Note Management
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/notes", response_model=NativeNote)
async def create_note(
    request: NoteCreateRequest,
    db: Database = Depends(get_library_database_for_write),
) -> NativeNote:
    now = datetime.now()
    note = NativeNote(
        room_id=request.room_id,
        content=request.content,
        note_type=request.note_type,
        author_id=request.author_id,
        linked_claim_ids=list(request.linked_claim_ids),
        linked_source_ids=list(request.linked_source_ids),
        linked_entity_ids=list(request.linked_entity_ids),
        metadata=dict(request.metadata),
        created_at=now,
        updated_at=now,
    )
    db.save(note)
    return note


@router.get("/notes", response_model=MindPalaceListResponse)
async def list_notes(
    room_id: str | None = None,
    note_type: NoteType | None = None,
    status: NoteStatus | None = None,
    author_id: str | None = None,
    db: Database = Depends(get_library_database),
) -> list[NativeNote]:
    rows = db.all(NativeNote)
    if room_id is not None:
        rows = [n for n in rows if n.room_id == room_id]
    if note_type is not None:
        rows = [n for n in rows if n.note_type == note_type]
    if status is not None:
        rows = [n for n in rows if n.status == status]
    if author_id is not None:
        rows = [n for n in rows if n.author_id == author_id]
    return MindPalaceListResponse(items=rows, count=len(rows))


@router.get("/notes/{note_id}", response_model=NativeNote)
async def get_note(
    note_id: str,
    db: Database = Depends(get_library_database),
) -> NativeNote:
    note = db.get(NativeNote, note_id)
    if not note:
        raise HTTPException(status_code=404, detail=f"Note not found: {note_id}")
    return note


@router.patch("/notes/{note_id}", response_model=NativeNote)
async def update_note(
    note_id: str,
    request: NoteUpdateRequest,
    db: Database = Depends(get_library_database_for_write),
) -> NativeNote:
    note = db.get(NativeNote, note_id)
    if not note:
        raise HTTPException(status_code=404, detail=f"Note not found: {note_id}")

    updates = request.model_dump(exclude_unset=True, exclude_none=True)
    for key, value in updates.items():
        setattr(note, key, value)
    note.updated_at = datetime.now()
    db.save(note)
    return note


@router.delete("/notes/{note_id}")
async def delete_note(
    note_id: str,
    db: Database = Depends(get_library_database_for_write),
) -> MindPalaceDeletedResponse:
    note = db.get(NativeNote, note_id)
    if not note:
        raise HTTPException(status_code=404, detail=f"Note not found: {note_id}")
    db.delete(note)
    return MindPalaceDeletedResponse(status="deleted")


# ─────────────────────────────────────────────────────────────────────────────
# Viewport / Navigation
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/rooms/{room_id}/viewport/{user_id}", response_model=SpatialViewport)
async def get_viewport(
    room_id: str,
    user_id: str,
    db: Database = Depends(get_library_database),
) -> SpatialViewport:
    rows = [
        v
        for v in db.all(SpatialViewport)
        if v.room_id == room_id and v.user_id == user_id
    ]
    if rows:
        return rows[0]

    # Return default viewport
    return SpatialViewport(room_id=room_id, user_id=user_id, updated_at=datetime.now())


@router.post("/rooms/{room_id}/viewport/{user_id}", response_model=SpatialViewport)
async def save_viewport(
    room_id: str,
    user_id: str,
    request: ViewportSaveRequest,
    db: Database = Depends(get_library_database_for_write),
) -> SpatialViewport:
    rows = [
        v
        for v in db.all(SpatialViewport)
        if v.room_id == room_id and v.user_id == user_id
    ]
    if rows:
        existing = rows[0]
        existing.camera_x = request.camera_x
        existing.camera_y = request.camera_y
        existing.camera_z = request.camera_z
        existing.focus_node_id = request.focus_node_id
        existing.zoom_level = request.zoom_level
        existing.bookmark_name = request.bookmark_name
        existing.metadata = dict(request.metadata) if request.metadata else {}
        existing.updated_at = datetime.now()
        db.save(existing)
        return existing

    viewport = SpatialViewport(
        room_id=room_id,
        user_id=user_id,
        camera_x=request.camera_x,
        camera_y=request.camera_y,
        camera_z=request.camera_z,
        focus_node_id=request.focus_node_id,
        zoom_level=request.zoom_level,
        bookmark_name=request.bookmark_name,
        metadata=dict(request.metadata) if request.metadata else {},
        updated_at=datetime.now(),
    )
    db.save(viewport)
    return viewport


@router.post("/rooms/{room_id}/focus", response_model=SpatialViewport)
async def focus_node(
    room_id: str,
    user_id: str = "user",
    node_id: str | None = None,
    db: Database = Depends(get_library_database_for_write),
) -> SpatialViewport:
    """Set focus on a specific node in a room."""
    rows = [
        v
        for v in db.all(SpatialViewport)
        if v.room_id == room_id and v.user_id == user_id
    ]
    if rows:
        existing = rows[0]
        existing.focus_node_id = node_id
        existing.updated_at = datetime.now()
        db.save(existing)
        return existing

    viewport = SpatialViewport(
        room_id=room_id,
        user_id=user_id,
        focus_node_id=node_id,
        updated_at=datetime.now(),
    )
    db.save(viewport)
    return viewport


# ─────────────────────────────────────────────────────────────────────────────
# AI-assisted arrangement
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/rooms/{room_id}/suggest-arrangement", response_model=MindPalaceListResponse)
async def suggest_arrangement(
    room_id: str,
    request: ArrangeRequest,
    db: Database = Depends(get_library_database_for_write),
) -> list[SpatialNode]:
    """Propose positions for nodes based on an arrangement strategy.

    Returns updated node objects with suggested positions.
    Currently implements simple placeholder logic — full implementation
    would use embeddings and clustering algorithms.
    """
    room = db.get(SpatialRoom, room_id)
    if not room:
        raise HTTPException(status_code=404, detail=f"Room not found: {room_id}")

    nodes = [db.get(SpatialNode, nid) for nid in request.node_ids]
    nodes = [n for n in nodes if n is not None]

    if not nodes:
        raise HTTPException(
            status_code=400, detail="No valid nodes found for arrangement"
        )

    # Simple circular arrangement as placeholder
    count = len(nodes)
    for i, node in enumerate(nodes):
        angle = 2 * math.pi * i / count
        radius = 3.0
        node.position_x = radius * math.cos(angle)
        node.position_y = radius * math.sin(angle)
        node.position_z = 0.0
        node.updated_at = datetime.now()
        db.save(node)

    return nodes


# ─────────────────────────────────────────────────────────────────────────────
# Capture (placeholder for screenshot/export)
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/rooms/{room_id}/capture")
async def capture_viewport(
    room_id: str,
    request: CaptureRequest,
    db: Database = Depends(get_library_database),
) -> CaptureViewportResponse:
    """Capture a viewport as an image.

    Full implementation would render the 3D scene and return image bytes.
    Currently returns a placeholder response.
    """
    room = db.get(SpatialRoom, room_id)
    if not room:
        raise HTTPException(status_code=404, detail=f"Room not found: {room_id}")

    return CaptureViewportResponse(
        status="placeholder",
        message="Scene capture requires RealityKit Metal renderer — not yet implemented in backend",
        room_id=room_id,
        region=request.region.value,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Tinderbox Integration (stub — requires external Tinderbox connection)
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/export/tinderbox")
async def export_to_tinderbox(
    room_id: str,
    tinderbox_note_id: str | None = None,
    db: Database = Depends(get_library_database_for_write),
) -> TinderboxExportResponse:
    """Export room notes to Tinderbox.

    Requires Tinderbox integration — returns a placeholder.
    """
    room = db.get(SpatialRoom, room_id)
    if not room:
        raise HTTPException(status_code=404, detail=f"Room not found: {room_id}")

    return TinderboxExportResponse(
        status="placeholder",
        message="Tinderbox export requires external Tinderbox integration",
        room_id=room_id,
    )


@router.post("/import/tinderbox")
async def import_from_tinderbox(
    tinderbox_note_id: str,
    room_id: str | None = None,
    db: Database = Depends(get_library_database_for_write),
) -> list[NativeNote]:
    """Import notes from Tinderbox.

    Requires Tinderbox integration — returns a placeholder.
    """
    return []


# ─────────────────────────────────────────────────────────────────────────────
# Canvas layout (FOLDER-scoped spatial positions — NOT room-scoped)
# ─────────────────────────────────────────────────────────────────────────────


class CanvasLayoutItem(BaseModel):
    """One item's position within a folder's spatial canvas.

    ``folder_id`` is taken from the path, never the body, so a batch can only
    update document-backed positions for the folder it is addressed to.
    """

    item_id: str
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    w: float | None = None
    h: float | None = None
    d: float | None = None
    angle: float = 0.0
    z_index: int = 0
    style: str | None = None


class CanvasLayoutSaveRequest(BaseModel):
    """Batch of item positions to persist for a folder (one drag -> one save)."""

    items: list[CanvasLayoutItem]


def _canvas_layout_row_from_document(folder_id: str, doc: Document) -> CanvasLayout:
    """Compatibility shape for the retired canvas_layout table, backed by Document attrs."""
    metadata = doc.metadata if isinstance(doc.metadata, dict) else {}
    return CanvasLayout(
        id=CanvasLayout.make_id(folder_id, doc.id),
        folder_id=folder_id,
        item_id=doc.id,
        x=doc.position_x or 0.0,
        y=doc.position_y or 0.0,
        z=doc.position_z or 0.0,
        w=metadata.get("canvas_w"),
        h=metadata.get("canvas_h"),
        d=metadata.get("canvas_d"),
        angle=doc.rotation_z or 0.0,
        z_index=doc.z_index,
        style=metadata.get("canvas_style"),
        updated_at=doc.updated_at,
    )


def _folder_canvas_documents(db: Database, folder_id: str) -> list[Document]:
    """Folder child documents that currently carry canvas position data."""
    rows = db.query(Document, parent_id=folder_id)
    return [
        doc for doc in rows
        if doc.position_x is not None
        or doc.position_y is not None
        or doc.position_z is not None
        or doc.rotation_z is not None
        or doc.z_index != 0
        or (
            isinstance(doc.metadata, dict)
            and any(
                key in doc.metadata
                for key in ("canvas_w", "canvas_h", "canvas_d", "canvas_style")
            )
        )
    ]


def _folder_canvas_document_or_404(db: Database, folder_id: str, item_id: str) -> Document:
    doc = db.get(Document, item_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Document not found: {item_id}")
    if doc.parent_id != folder_id:
        raise HTTPException(
            status_code=404,
            detail=f"Document {item_id} is not in folder {folder_id}",
        )
    return doc


@router.get("/folders/{folder_id}/canvas-layout", response_model=MindPalaceListResponse)
async def get_canvas_layout(
    folder_id: str,
    db: Database = Depends(get_library_database),
) -> MindPalaceListResponse:
    """Load all persisted item positions for a folder's spatial canvas."""
    rows = [
        _canvas_layout_row_from_document(folder_id, doc)
        for doc in _folder_canvas_documents(db, folder_id)
    ]
    return MindPalaceListResponse(items=rows, count=len(rows))


@router.put("/folders/{folder_id}/canvas-layout")
async def save_canvas_layout(
    folder_id: str,
    request: CanvasLayoutSaveRequest,
    db: Database = Depends(get_library_database_for_write),
) -> list[CanvasLayout]:
    """Compatibility wrapper: persist folder item positions onto Document attrs."""
    saved: list[CanvasLayout] = []
    for item in request.items:
        doc = _folder_canvas_document_or_404(db, folder_id, item.item_id)
        metadata = dict(doc.metadata) if isinstance(doc.metadata, dict) else {}
        doc.position_x = item.x
        doc.position_y = item.y
        doc.position_z = item.z
        doc.rotation_z = item.angle
        doc.z_index = item.z_index
        metadata["canvas_w"] = item.w
        metadata["canvas_h"] = item.h
        metadata["canvas_d"] = item.d
        metadata["canvas_style"] = item.style
        doc.metadata = metadata
        doc.updated_at = datetime.now()
        db.save(doc)
        saved.append(_canvas_layout_row_from_document(folder_id, doc))
    return saved


# ─────────────────────────────────────────────────────────────────────────────
# Arrange — compute + PERSIST canvas transforms for a set of nodes by strategy
# (#2297). One endpoint, agent-callable via the action registry (#1848).
# ─────────────────────────────────────────────────────────────────────────────


class ArrangeNodesRequest(BaseModel):
    """Arrange a set of folder nodes by a geometric strategy and persist them.

    ``folder_id`` comes from the path, never the body — the computed rows can
    only be written for the folder the request is addressed to. An unknown
    ``strategy`` is rejected by Pydantic with a 422 (it is an enum field).
    """

    node_ids: list[str]
    strategy: ArrangeStrategy = ArrangeStrategy.grid
    spacing: float = DEFAULT_SPACING
    columns: int | None = None
    radius: float | None = None


def arrange_impl(
    db: Database,
    folder_id: str,
    node_ids: list[str],
    strategy: ArrangeStrategy | str,
    *,
    spacing: float = DEFAULT_SPACING,
    columns: int | None = None,
    radius: float | None = None,
) -> list[CanvasLayout]:
    """Compute transforms for ``node_ids`` and persist them onto Document attrs.

    Shared by the HTTP route and the registered action so both drive the same
    code (iterate-not-replace). Raises ``ValueError`` (empty / unknown strategy)
    for the caller to map to a 4xx. Each row is keyed by the deterministic
    ``(folder_id, item_id)`` composite, so re-arranging overwrites prior
    positions rather than duplicating.
    """
    if not node_ids:
        raise ValueError("node_ids must not be empty")

    positions = compute_arrangement(
        node_ids, strategy, spacing=spacing, columns=columns, radius=radius
    )
    saved: list[CanvasLayout] = []
    now = datetime.now()
    for pos in positions:
        doc = _folder_canvas_document_or_404(db, folder_id, pos["item_id"])
        doc.position_x = pos["x"]
        doc.position_y = pos["y"]
        doc.position_z = pos["z"]
        doc.z_index = pos["z_index"]
        doc.updated_at = now
        db.save(doc)
        saved.append(_canvas_layout_row_from_document(folder_id, doc))
    return saved


@router.post("/folders/{folder_id}/arrange", response_model=MindPalaceListResponse)
async def arrange_folder_canvas(
    folder_id: str,
    request: ArrangeNodesRequest,
    db: Database = Depends(get_library_database_for_write),
) -> MindPalaceListResponse:
    """Lay out a folder's nodes by ``strategy`` and persist the transforms.

    Computes positions (grid/row/column/circle/stack), writes them onto the
    underlying child documents, then returns the compatibility payload in the
    standard ``{items, count}`` envelope.
    """
    try:
        rows = arrange_impl(
            db,
            folder_id,
            request.node_ids,
            request.strategy,
            spacing=request.spacing,
            columns=request.columns,
            radius=request.radius,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return MindPalaceListResponse(items=rows, count=len(rows))


# Action-layer registration (EPIC #1848) — agent/chat/App-Intents callable.
# Wraps the same ``arrange_impl`` the HTTP route uses (iterate-not-replace), so
# every invocation routes through ``registry.invoke`` → ActionAudit + emit.
class CanvasArrangeParams(ArrangeNodesRequest):
    """Params for the ``canvas.arrange`` action (folder_id carried in the body)."""

    folder_id: str


@action("canvas.arrange", CanvasArrangeParams, domains=["canvas"])
def _action_arrange_canvas(
    db: Database, params: CanvasArrangeParams, ctx: ActionContext
) -> tuple[list[dict], ChangeSpec]:
    node_id_set = set(params.node_ids)
    before = [
        _canvas_layout_row_from_document(params.folder_id, doc).model_dump(mode="json")
        for doc in _folder_canvas_documents(db, params.folder_id)
        if doc.id in node_id_set
    ]
    rows = arrange_impl(
        db,
        params.folder_id,
        params.node_ids,
        params.strategy,
        spacing=params.spacing,
        columns=params.columns,
        radius=params.radius,
    )
    after = [r.model_dump(mode="json") for r in rows]
    spec = ChangeSpec(
        domains=["canvas"],
        target_ids=[r.id for r in rows],
        before={"rows": before},
        after={"rows": after},
        emit_type="canvas.arranged",
    )
    return after, spec


# ─────────────────────────────────────────────────────────────────────────────
# Canvas items — STANDALONE placeable CONTENT (#2294): notes, quotes,
# work-notes, links/connectors, free text. The non-document placeables.
# Folder-scoped via the path. One model, a ``kind`` field -- not a model per
# kind. Document/page placement now lives on Document attrs; these items remain
# as content payloads only.
# ─────────────────────────────────────────────────────────────────────────────


class CanvasItemCreateRequest(BaseModel):
    """Create one standalone canvas item in a folder (``folder_id`` from path).

    For ``kind="link"`` set ``source_item_id``/``target_item_id`` to the two
    item ids the connector joins. ``payload`` carries small kind-specific bits.
    """

    kind: CanvasItemKind = CanvasItemKind.note
    text: str = ""
    source_item_id: str | None = None
    target_item_id: str | None = None
    payload: dict = Field(default_factory=dict)


class CanvasItemUpdateRequest(BaseModel):
    """Patch a canvas item — every field optional; only provided ones change."""

    kind: CanvasItemKind | None = None
    text: str | None = None
    source_item_id: str | None = None
    target_item_id: str | None = None
    payload: dict | None = None


def create_canvas_item_impl(
    db: Database, folder_id: str, req: CanvasItemCreateRequest
) -> CanvasItem:
    """Persist a new canvas item for ``folder_id``. Shared by route + action."""
    now = datetime.now()
    item = CanvasItem(
        folder_id=folder_id,
        kind=req.kind,
        text=req.text,
        source_item_id=req.source_item_id,
        target_item_id=req.target_item_id,
        payload=req.payload,
        created_at=now,
        updated_at=now,
    )
    db.save(item)
    return item


def update_canvas_item_impl(
    db: Database, folder_id: str, item_id: str, req: CanvasItemUpdateRequest
) -> tuple[dict, CanvasItem]:
    """Apply a partial edit to a canvas item. Shared by route + action.

    Returns ``(before, item)`` — the pre-edit snapshot (for the action's audit)
    and the saved row — so the action need not re-read the row. Raises
    ``KeyError`` if the item is absent or belongs to another folder, for the
    caller to map to a 404.
    """
    item = db.get(CanvasItem, item_id)
    if item is None or item.folder_id != folder_id:
        raise KeyError(item_id)
    before = item.model_dump(mode="json")
    fields = req.model_dump(exclude_unset=True)
    for name, value in fields.items():
        setattr(item, name, value)
    item.updated_at = datetime.now()
    db.save(item)
    return before, item


def delete_canvas_item_impl(db: Database, folder_id: str, item_id: str) -> CanvasItem:
    """Delete a canvas item, returning the removed row. Shared by route + action.

    Raises ``KeyError`` if absent / cross-folder, for the caller to map to 404.
    The item's ``canvas_layout`` placement row (if any) is left for the layout
    surface to reap — content and placement are separate concerns (#2293).
    """
    item = db.get(CanvasItem, item_id)
    if item is None or item.folder_id != folder_id:
        raise KeyError(item_id)
    db.delete(item)
    return item


@router.get(
    "/folders/{folder_id}/canvas-items", response_model=MindPalaceListResponse
)
async def list_canvas_items(
    folder_id: str,
    kind: CanvasItemKind | None = None,
    db: Database = Depends(get_library_database),
) -> MindPalaceListResponse:
    """List a folder's standalone canvas items in the ``{items, count}`` envelope."""
    filters: dict[str, Any] = {"folder_id": folder_id}
    if kind is not None:
        filters["kind"] = kind
    rows = db.query(CanvasItem, **filters)
    return MindPalaceListResponse(items=rows, count=len(rows))


@router.post("/folders/{folder_id}/canvas-items", response_model=CanvasItem)
async def create_canvas_item(
    folder_id: str,
    request: CanvasItemCreateRequest,
    db: Database = Depends(get_library_database_for_write),
) -> CanvasItem:
    """Create one standalone canvas item (note / quote / work_note / link / text)."""
    return create_canvas_item_impl(db, folder_id, request)


@router.patch(
    "/folders/{folder_id}/canvas-items/{item_id}", response_model=CanvasItem
)
async def update_canvas_item(
    folder_id: str,
    item_id: str,
    request: CanvasItemUpdateRequest,
    db: Database = Depends(get_library_database_for_write),
) -> CanvasItem:
    """Patch a canvas item's text / payload / kind / link endpoints."""
    try:
        _, item = update_canvas_item_impl(db, folder_id, item_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="canvas item not found") from exc
    return item


@router.delete(
    "/folders/{folder_id}/canvas-items/{item_id}",
    response_model=MindPalaceDeletedResponse,
)
async def delete_canvas_item(
    folder_id: str,
    item_id: str,
    db: Database = Depends(get_library_database_for_write),
) -> MindPalaceDeletedResponse:
    """Delete a standalone canvas item from a folder."""
    try:
        delete_canvas_item_impl(db, folder_id, item_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="canvas item not found") from exc
    return MindPalaceDeletedResponse(status="deleted")


# Action-layer registration (EPIC #1848) — agent/chat/App-Intents callable.
# Each wraps the same ``*_impl`` the HTTP routes use (iterate-not-replace), so
# every agent invocation routes through ``registry.invoke`` → ActionAudit + emit.
class CanvasItemCreateParams(CanvasItemCreateRequest):
    """Params for ``canvas.item.create`` (folder_id carried in the body)."""

    folder_id: str


class CanvasItemUpdateParams(CanvasItemUpdateRequest):
    """Params for ``canvas.item.update`` (folder_id + item_id in the body)."""

    folder_id: str
    item_id: str


class CanvasItemDeleteParams(BaseModel):
    """Params for ``canvas.item.delete`` (folder_id + item_id in the body)."""

    folder_id: str
    item_id: str


@action("canvas.item.create", CanvasItemCreateParams, domains=["canvas"])
def _action_create_canvas_item(
    db: Database, params: CanvasItemCreateParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    # params IS-A CanvasItemCreateRequest (plus folder_id) — pass it straight in.
    item = create_canvas_item_impl(db, params.folder_id, params)
    after = item.model_dump(mode="json")
    spec = ChangeSpec(
        domains=["canvas"],
        target_ids=[item.id],
        before=None,
        after={"item": after},
        emit_type="canvas.item.created",
    )
    return after, spec


@action("canvas.item.update", CanvasItemUpdateParams, domains=["canvas"])
def _action_update_canvas_item(
    db: Database, params: CanvasItemUpdateParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    before, item = update_canvas_item_impl(
        db,
        params.folder_id,
        params.item_id,
        CanvasItemUpdateRequest(
            **params.model_dump(exclude={"folder_id", "item_id"}, exclude_unset=True)
        ),
    )
    after = item.model_dump(mode="json")
    spec = ChangeSpec(
        domains=["canvas"],
        target_ids=[item.id],
        before={"item": before},
        after={"item": after},
        emit_type="canvas.item.updated",
    )
    return after, spec


@action("canvas.item.delete", CanvasItemDeleteParams, domains=["canvas"])
def _action_delete_canvas_item(
    db: Database, params: CanvasItemDeleteParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    item = delete_canvas_item_impl(db, params.folder_id, params.item_id)
    before = item.model_dump(mode="json")
    spec = ChangeSpec(
        domains=["canvas"],
        target_ids=[item.id],
        before={"item": before},
        after=None,
        emit_type="canvas.item.deleted",
    )
    return before, spec
