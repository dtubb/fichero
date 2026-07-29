"""Canvas and retained spatial models."""

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
    room_id: str  # doubles as folder_id when rooms are retired (#2293)
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
    # 2D canvas layout (#2293)
    pos_w: float = 0.0
    pos_h: float = 0.0
    z_index: int = 0
    # 3D extra (#2293)
    depth: float = 0.0
    angle: float = 0.0
    # style blob: {"fontSize": int, "color": str, "style": str} (#2293)
    style_data: dict = Field(default_factory=dict)
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


class CanvasLayout(BaseModel):
    """Persisted per-item position on the spatial 2D/3D library canvas.

    FOLDER-scoped (not room-scoped): keyed by (folder_id, item_id) so that
    switching Library view modes preserves where each item was placed. The
    stored ``id`` is the deterministic ``"{folder_id}::{item_id}"`` composite,
    which makes ``Database.save`` an idempotent upsert on that pair — saving a
    drag of the same item overwrites its previous row rather than duplicating.
    """

    model_config = ConfigDict(from_attributes=True, extra="allow")

    id: str = Field(default_factory=_new_id)
    folder_id: str
    item_id: str
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    w: float | None = None
    h: float | None = None
    d: float | None = None
    angle: float = 0.0
    z_index: int = 0
    style: str | None = None  # opaque JSON text (color, shape, …)
    updated_at: datetime = Field(default_factory=datetime.now)

    @staticmethod
    def make_id(folder_id: str, item_id: str) -> str:
        """Deterministic primary key for the (folder_id, item_id) pair."""
        return f"{folder_id}::{item_id}"


class CanvasItemKind(str, Enum):
    """What a standalone (non-document) canvas item IS."""

    note = "note"
    quote = "quote"
    work_note = "work_note"
    link = "link"  # a connector between two other item_ids
    text = "text"


class CanvasItem(BaseModel):
    """Standalone, placeable CONTENT on a folder's spatial canvas (#2294).

    The non-document placeables — notes, quotes, work-notes, links/connectors,
    free text. Documents/pages/entities/claims already exist elsewhere and get
    their POSITION via :class:`CanvasLayout` (#2293); this model adds the payload
    for items that have no other home.

    Placement is NOT duplicated here: a CanvasItem's x/y/z still live in a
    ``canvas_layout`` row keyed by this item's ``id`` (CanvasItem = *what*,
    CanvasLayout = *where*). FOLDER-scoped, like the layout.

    A ``link`` connects two other items via ``source_item_id`` /
    ``target_item_id`` (which may reference documents, entities, claims, or other
    CanvasItems — any id the layout can place). ``payload`` carries small
    kind-specific bits so we keep ONE model with a ``kind`` field, not a model
    per kind.
    """

    model_config = ConfigDict(from_attributes=True, extra="allow")

    id: str = Field(default_factory=_new_id)
    folder_id: str
    kind: CanvasItemKind = CanvasItemKind.note
    text: str = ""
    source_item_id: str | None = None  # kind=link: the connection's start
    target_item_id: str | None = None  # kind=link: the connection's end
    payload: dict = Field(default_factory=dict)  # opaque kind-specific bits
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
