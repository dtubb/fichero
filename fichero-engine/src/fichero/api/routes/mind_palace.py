"""Mind Palace canvas routes."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from fichero.actions.registry import ActionContext, ChangeSpec, action
from fichero.api.main import get_library_database, get_library_database_for_write
from fichero.db import Database
from fichero.models import Document, MindPalaceListResponse
from fichero.spatial_arrange import DEFAULT_SPACING, ArrangeStrategy, compute_arrangement
from fichero.spatial_models import CanvasItem, CanvasItemKind, CanvasLayout

router = APIRouter()


class MindPalaceDeletedResponse(BaseModel):
    status: str


# ─────────────────────────────────────────────────────────────────────────────
# Canvas layout (FOLDER-scoped spatial positions — NOT room-scoped)
# ─────────────────────────────────────────────────────────────────────────────


class CanvasLayoutItem(BaseModel):
    """One item's position within a folder's spatial canvas."""

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
    """Batch of item positions to persist for a folder."""

    items: list[CanvasLayoutItem]


def _canvas_layout_row_from_document(folder_id: str, doc: Document) -> CanvasLayout:
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
    rows = db.query(Document, parent_id=folder_id)
    return [
        doc
        for doc in rows
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
# Arrange — compute + persist canvas transforms
# ─────────────────────────────────────────────────────────────────────────────


class ArrangeNodesRequest(BaseModel):
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


class CanvasArrangeParams(ArrangeNodesRequest):
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
    after = [row.model_dump(mode="json") for row in rows]
    spec = ChangeSpec(
        domains=["canvas"],
        target_ids=[row.id for row in rows],
        before={"rows": before},
        after={"rows": after},
        emit_type="canvas.arranged",
    )
    return after, spec


# ─────────────────────────────────────────────────────────────────────────────
# Canvas items — standalone placeable content
# ─────────────────────────────────────────────────────────────────────────────


class CanvasItemCreateRequest(BaseModel):
    kind: CanvasItemKind = CanvasItemKind.note
    text: str = ""
    source_item_id: str | None = None
    target_item_id: str | None = None
    payload: dict = Field(default_factory=dict)


class CanvasItemUpdateRequest(BaseModel):
    kind: CanvasItemKind | None = None
    text: str | None = None
    source_item_id: str | None = None
    target_item_id: str | None = None
    payload: dict | None = None


def create_canvas_item_impl(
    db: Database, folder_id: str, req: CanvasItemCreateRequest
) -> CanvasItem:
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
    item = db.get(CanvasItem, item_id)
    if item is None or item.folder_id != folder_id:
        raise KeyError(item_id)
    before = item.model_dump(mode="json")
    for name, value in req.model_dump(exclude_unset=True).items():
        setattr(item, name, value)
    item.updated_at = datetime.now()
    db.save(item)
    return before, item


def delete_canvas_item_impl(db: Database, folder_id: str, item_id: str) -> CanvasItem:
    item = db.get(CanvasItem, item_id)
    if item is None or item.folder_id != folder_id:
        raise KeyError(item_id)
    db.delete(item)
    return item


@router.get("/folders/{folder_id}/canvas-items", response_model=MindPalaceListResponse)
async def list_canvas_items(
    folder_id: str,
    kind: CanvasItemKind | None = None,
    db: Database = Depends(get_library_database),
) -> MindPalaceListResponse:
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
    return create_canvas_item_impl(db, folder_id, request)


@router.patch("/folders/{folder_id}/canvas-items/{item_id}", response_model=CanvasItem)
async def update_canvas_item(
    folder_id: str,
    item_id: str,
    request: CanvasItemUpdateRequest,
    db: Database = Depends(get_library_database_for_write),
) -> CanvasItem:
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
    try:
        delete_canvas_item_impl(db, folder_id, item_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="canvas item not found") from exc
    return MindPalaceDeletedResponse(status="deleted")


class CanvasItemCreateParams(CanvasItemCreateRequest):
    folder_id: str


class CanvasItemUpdateParams(CanvasItemUpdateRequest):
    folder_id: str
    item_id: str


class CanvasItemDeleteParams(BaseModel):
    folder_id: str
    item_id: str


@action("canvas.item.create", CanvasItemCreateParams, domains=["canvas"])
def _action_create_canvas_item(
    db: Database, params: CanvasItemCreateParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
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
