"""Mind Palace API routes (dev tier) — Layer 6 spatial workspace."""

import math
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from fichero.api.main import get_library_database, get_library_database_for_write
from fichero.db import Database
from fichero.spatial_models import (
    ArrangementType,
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
from fichero.models import MindPalaceListResponse


router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# Request/Response models
# ─────────────────────────────────────────────────────────────────────────────


class RoomCreateRequest(BaseModel):
    name: str
    description: str = ""
    room_type: RoomType = RoomType.research
    owner_id: str = "user"
    metadata: dict[str, Any] = Field(default_factory=dict)


class RoomUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    room_type: RoomType | None = None
    metadata: dict[str, Any] | None = None


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


# ─────────────────────────────────────────────────────────────────────────────
# Room Management
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/rooms", response_model=SpatialRoom)
async def create_room(
    request: RoomCreateRequest,
    db: Database = Depends(get_library_database_for_write),
) -> SpatialRoom:
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
    return room


@router.get("/rooms", response_model=MindPalaceListResponse)
async def list_rooms(
    room_type: RoomType | None = None,
    owner_id: str | None = None,
    db: Database = Depends(get_library_database),
) -> list[SpatialRoom]:
    rows = db.all(SpatialRoom)
    if room_type is not None:
        rows = [r for r in rows if r.room_type == room_type]
    if owner_id is not None:
        rows = [r for r in rows if r.owner_id == owner_id]
    return MindPalaceListResponse(items=rows, count=len(rows))


@router.get("/rooms/{room_id}", response_model=SpatialRoom)
async def get_room(
    room_id: str,
    db: Database = Depends(get_library_database),
) -> SpatialRoom:
    room = db.get(SpatialRoom, room_id)
    if not room:
        raise HTTPException(status_code=404, detail=f"Room not found: {room_id}")
    return room


@router.patch("/rooms/{room_id}", response_model=SpatialRoom)
async def update_room(
    room_id: str,
    request: RoomUpdateRequest,
    db: Database = Depends(get_library_database_for_write),
) -> SpatialRoom:
    room = db.get(SpatialRoom, room_id)
    if not room:
        raise HTTPException(status_code=404, detail=f"Room not found: {room_id}")

    updates = request.model_dump(exclude_unset=True, exclude_none=True)
    for key, value in updates.items():
        setattr(room, key, value)
    room.updated_at = datetime.now()
    db.save(room)
    return room


@router.delete("/rooms/{room_id}")
async def delete_room(
    room_id: str,
    db: Database = Depends(get_library_database_for_write),
) -> MindPalaceDeletedResponse:
    room = db.get(SpatialRoom, room_id)
    if not room:
        raise HTTPException(status_code=404, detail=f"Room not found: {room_id}")
    db.delete(room)
    return MindPalaceDeletedResponse(status="deleted")


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
