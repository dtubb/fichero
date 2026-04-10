"""Mind Palace spatial models for 0.0.2 Layer 6 — visual and text assembly workspace."""

from datetime import datetime
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field, ConfigDict


def _new_id() -> str:
    return uuid4().hex


class RoomType(str, Enum):
    research = "research"
    synthesis = "synthesis"
    presentation = "presentation"


class NodeType(str, Enum):
    source = "source"
    claim = "claim"
    note = "note"
    entity = "entity"
    transcription = "transcription"


class ConnectionType(str, Enum):
    evidentiary = "evidentiary"
    semantic = "semantic"
    ontological = "ontological"
    hermeneutic = "hermeneutic"
    user_drawn = "user_drawn"


class NoteType(str, Enum):
    user = "user"
    ai_workspace = "ai_workspace"
    ai_hypothesis = "ai_hypothesis"
    ai_summary = "ai_summary"
    ai_relation = "ai_relation"
    shared = "shared"


class AuthorType(str, Enum):
    user = "user"
    ai = "ai"
    agent_team = "agent_team"


class NoteStatus(str, Enum):
    draft = "draft"
    active = "active"
    surfaced = "surfaced"
    accepted = "accepted"
    archived = "archived"
    discarded = "discarded"


class ArrangementType(str, Enum):
    semantic = "semantic"
    chronological = "chronological"
    thematic = "thematic"


class CaptureRegion(str, Enum):
    full = "full"
    focused = "focused"
    selection = "selection"


class SpatialRoom(BaseModel):
    """3D workspace room for organizing materials."""

    model_config = ConfigDict(from_attributes=True, extra="allow")

    id: str = Field(default_factory=_new_id)
    name: str
    description: str = ""
    room_type: RoomType = RoomType.research
    owner_id: str = "user"
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class SpatialNode(BaseModel):
    """Item placed in 3D space (source, claim, note, entity, transcription)."""

    model_config = ConfigDict(from_attributes=True, extra="allow")

    id: str = Field(default_factory=_new_id)
    room_id: str
    node_type: NodeType
    source_id: str | None = None  # ID of the underlying item
    label: str = ""
    position_x: float = 0.0
    position_y: float = 0.0
    position_z: float = 0.0
    rotation_x: float = 0.0
    rotation_y: float = 0.0
    rotation_z: float = 0.0
    scale: float = 1.0
    created_by: str = "user"
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class SpatialConnection(BaseModel):
    """Visual link between nodes in a room."""

    model_config = ConfigDict(from_attributes=True, extra="allow")

    id: str = Field(default_factory=_new_id)
    room_id: str
    source_node_id: str
    target_node_id: str
    connection_type: ConnectionType
    link_subtype: str | None = None  # e.g., "supports", "derived_from", "interprets"
    created_by: str = "user"
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)


class SpatialStack(BaseModel):
    """Grouped nodes within a room."""

    model_config = ConfigDict(from_attributes=True, extra="allow")

    id: str = Field(default_factory=_new_id)
    room_id: str
    name: str = ""
    node_ids: list[str] = Field(default_factory=list)
    position_x: float = 0.0
    position_y: float = 0.0
    position_z: float = 0.0
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class NativeNote(BaseModel):
    """First-class text note in Mind Palace workspace."""

    model_config = ConfigDict(from_attributes=True, extra="allow")

    id: str = Field(default_factory=_new_id)
    room_id: str | None = None
    content: str = ""
    note_type: NoteType = NoteType.user
    author_type: AuthorType = AuthorType.user
    author_id: str = "user"
    status: NoteStatus = NoteStatus.draft
    linked_claim_ids: list[str] = Field(default_factory=list)
    linked_source_ids: list[str] = Field(default_factory=list)
    linked_entity_ids: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class SpatialViewport(BaseModel):
    """Camera and focus state for a room."""

    model_config = ConfigDict(from_attributes=True, extra="allow")

    id: str = Field(default_factory=_new_id)
    room_id: str
    user_id: str = "user"
    camera_x: float = 0.0
    camera_y: float = 0.0
    camera_z: float = 10.0
    focus_node_id: str | None = None
    zoom_level: float = 1.0
    bookmark_name: str | None = None
    metadata: dict = Field(default_factory=dict)
    updated_at: datetime = Field(default_factory=datetime.now)


class RoomSceneSummary(BaseModel):
    """Compact scene state for a room."""

    room_id: str
    room_name: str
    node_count: int = 0
    connection_count: int = 0
    stack_count: int = 0
    note_count: int = 0
    node_types: dict[str, int] = Field(default_factory=dict)  # node_type → count
