"""Canvas routes."""

from datetime import datetime
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from fichero.actions.registry import ActionContext, ChangeSpec, action, registry
from fichero.api.auth import action_context
from fichero.api.main import get_library_database, get_library_database_for_write
from fichero.db import Database
from fichero.models import CanvasDeletedResponse, CanvasListResponse, Document
from fichero.knowledge.knowledge_models import KnowledgeClaim, KnowledgeEntity
from fichero.spatial_arrange import DEFAULT_SPACING, ArrangeStrategy, compute_arrangement
from fichero.canvas_models import CanvasItem, CanvasItemKind, CanvasLayout

router = APIRouter()
logger = logging.getLogger(__name__)


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


class CanvasLayoutSkippedItem(BaseModel):
    item_id: str
    detail: str


class CanvasLayoutBatchResponse(BaseModel):
    items: list[CanvasLayout]
    count: int
    skipped: list[CanvasLayoutSkippedItem] = Field(default_factory=list)


def _canvas_layout_row_from_document(scope_id: str, doc: Document) -> CanvasLayout:
    metadata = doc.metadata if isinstance(doc.metadata, dict) else {}
    return CanvasLayout(
        id=CanvasLayout.make_id(scope_id, doc.id),
        folder_id=scope_id,
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


def _legacy_canvas_documents(db: Database, scope_id: str) -> list[Document]:
    rows = db.query(Document, parent_id=scope_id)
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


def _load_canvas_layout(db: Database, scope_id: str) -> list[CanvasLayout]:
    rows = {row.item_id: row for row in db.query(CanvasLayout, folder_id=scope_id)}
    for doc in _legacy_canvas_documents(db, scope_id):
        rows.setdefault(doc.id, _canvas_layout_row_from_document(scope_id, doc))
    return list(rows.values())


def _canvas_placeable_exists(db: Database, item_id: str) -> bool:
    return (
        db.get(Document, item_id) is not None
        or db.get(CanvasItem, item_id) is not None
        or db.get(KnowledgeEntity, item_id) is not None
        or db.get(KnowledgeClaim, item_id) is not None
    )


def _save_canvas_layout_row(
    db: Database, scope_id: str, item: CanvasLayoutItem
) -> CanvasLayout:
    existing = db.get(CanvasLayout, CanvasLayout.make_id(scope_id, item.item_id))
    field_set = item.model_fields_set
    row = CanvasLayout(
        id=CanvasLayout.make_id(scope_id, item.item_id),
        folder_id=scope_id,
        item_id=item.item_id,
        x=item.x,
        y=item.y,
        z=item.z,
        w=item.w if "w" in field_set else (existing.w if existing else None),
        h=item.h if "h" in field_set else (existing.h if existing else None),
        d=item.d if "d" in field_set else (existing.d if existing else None),
        angle=item.angle,
        z_index=item.z_index,
        style=item.style if "style" in field_set else (existing.style if existing else None),
        updated_at=datetime.now(),
    )
    db.save(row)
    return row


def _canvas_skip(item_id: str, detail: str) -> CanvasLayoutSkippedItem:
    logger.warning("canvas layout skipped %s: %s", item_id, detail)
    return CanvasLayoutSkippedItem(item_id=item_id, detail=detail)


def _canvas_layout_change_spec(
    *,
    emit_type: str,
    scope_id: str,
    rows: list[CanvasLayout],
    before: list[dict[str, Any]],
    skipped: list[CanvasLayoutSkippedItem],
) -> ChangeSpec:
    item_ids = [row.item_id for row in rows]

    def _emit(ctx: ActionContext, spec: ChangeSpec) -> None:
        if not ctx.library_path or not spec.emit_type:
            return
        from fichero.api.change_stream import emit_change

        emit_change(
            ctx.library_path,
            type=spec.emit_type,
            entity_ids=item_ids,
            document_ids=[scope_id],
            run_id=ctx.run_id,
            actor=ctx.actor,
            origin_window=ctx.origin_window,
            origin_user=ctx.actor,
        )

    return ChangeSpec(
        domains=["canvas"],
        target_ids=[row.id for row in rows],
        before={"scope_id": scope_id, "rows": before},
        after={
            "scope_id": scope_id,
            "rows": [row.model_dump(mode="json") for row in rows],
            "skipped": [item.model_dump(mode="json") for item in skipped],
        },
        emit_type=emit_type,
        entity_ids=item_ids,
        document_ids=[scope_id],
        emit_fn=_emit,
    )


@router.get("/folders/{scope_id}/layout", response_model=CanvasListResponse)
async def get_canvas_layout(
    scope_id: str,
    db: Database = Depends(get_library_database),
) -> CanvasListResponse:
    rows = _load_canvas_layout(db, scope_id)
    return CanvasListResponse(items=rows, count=len(rows))


def save_canvas_layout_impl(
    scope_id: str,
    request: CanvasLayoutSaveRequest,
    db: Database,
) -> tuple[list[CanvasLayout], list[CanvasLayoutSkippedItem]]:
    saved: list[CanvasLayout] = []
    skipped: list[CanvasLayoutSkippedItem] = []
    for item in request.items:
        if not _canvas_placeable_exists(db, item.item_id):
            skipped.append(_canvas_skip(item.item_id, "unknown canvas item id"))
            continue
        saved.append(_save_canvas_layout_row(db, scope_id, item))
    return saved, skipped


@router.put("/folders/{scope_id}/layout", response_model=CanvasLayoutBatchResponse)
async def save_canvas_layout(
    scope_id: str,
    request: CanvasLayoutSaveRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> CanvasLayoutBatchResponse:
    result = registry.invoke(
        db,
        "canvas.layout.save",
        {
            "folder_id": scope_id,
            "items": [item.model_dump(mode="json") for item in request.items],
        },
        ctx,
    )
    rows = [CanvasLayout.model_validate(row) for row in result.result["items"]]
    skipped = [
        CanvasLayoutSkippedItem.model_validate(item)
        for item in result.result.get("skipped", [])
    ]
    return CanvasLayoutBatchResponse(items=rows, count=len(rows), skipped=skipped)


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
    scope_id: str,
    node_ids: list[str],
    strategy: ArrangeStrategy | str,
    *,
    spacing: float = DEFAULT_SPACING,
    columns: int | None = None,
    radius: float | None = None,
) -> tuple[list[CanvasLayout], list[CanvasLayoutSkippedItem]]:
    if not node_ids:
        raise ValueError("node_ids must not be empty")

    positions = compute_arrangement(
        node_ids, strategy, spacing=spacing, columns=columns, radius=radius
    )
    saved: list[CanvasLayout] = []
    skipped: list[CanvasLayoutSkippedItem] = []
    for pos in positions:
        if not _canvas_placeable_exists(db, pos["item_id"]):
            skipped.append(_canvas_skip(pos["item_id"], "unknown canvas item id"))
            continue
        saved.append(
            _save_canvas_layout_row(
                db,
                scope_id,
                CanvasLayoutItem(
                    item_id=pos["item_id"],
                    x=pos["x"],
                    y=pos["y"],
                    z=pos["z"],
                    z_index=pos["z_index"],
                ),
            )
        )
    return saved, skipped


@router.post("/folders/{scope_id}/arrange", response_model=CanvasLayoutBatchResponse)
async def arrange_folder_canvas(
    scope_id: str,
    request: ArrangeNodesRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> CanvasLayoutBatchResponse:
    try:
        result = registry.invoke(
            db,
            "canvas.arrange",
            {
                "folder_id": scope_id,
                "node_ids": request.node_ids,
                "strategy": request.strategy,
                "spacing": request.spacing,
                "columns": request.columns,
                "radius": request.radius,
            },
            ctx,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    rows = [CanvasLayout.model_validate(row) for row in result.result["items"]]
    skipped = [
        CanvasLayoutSkippedItem.model_validate(item)
        for item in result.result.get("skipped", [])
    ]
    return CanvasLayoutBatchResponse(items=rows, count=len(rows), skipped=skipped)


class CanvasArrangeParams(ArrangeNodesRequest):
    folder_id: str


class CanvasLayoutSaveParams(CanvasLayoutSaveRequest):
    folder_id: str


class CanvasLayoutRestoreParams(BaseModel):
    folder_id: str
    rows: list[dict[str, Any]] = Field(default_factory=list)
    current_item_ids: list[str] = Field(default_factory=list)


def _invert_canvas_layout_to_restore(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    if not after:
        return None
    scope_id = after.get("scope_id") if isinstance(after, dict) else None
    rows_after = after.get("rows") if isinstance(after, dict) else None
    if not scope_id or not isinstance(rows_after, list):
        return None
    rows_before = before.get("rows") if isinstance(before, dict) else []
    if not isinstance(rows_before, list):
        rows_before = []
    current_item_ids = [
        row.get("item_id") for row in rows_after if isinstance(row, dict) and row.get("item_id")
    ]
    return (
        "canvas.layout.restore",
        {
            "folder_id": scope_id,
            "rows": rows_before,
            "current_item_ids": current_item_ids,
        },
    )


@action(
    "canvas.layout.save",
    CanvasLayoutSaveParams,
    domains=["canvas"],
    undoable=True,
    invert=_invert_canvas_layout_to_restore,
)
def _action_save_canvas_layout(
    db: Database, params: CanvasLayoutSaveParams, ctx: ActionContext
) -> tuple[dict[str, Any], ChangeSpec]:
    item_id_set = {item.item_id for item in params.items}
    before = [
        row.model_dump(mode="json")
        for row in _load_canvas_layout(db, params.folder_id)
        if row.item_id in item_id_set
    ]
    rows, skipped = save_canvas_layout_impl(
        params.folder_id,
        CanvasLayoutSaveRequest(items=params.items),
        db,
    )
    spec = _canvas_layout_change_spec(
        emit_type="canvas.layout.saved",
        scope_id=params.folder_id,
        rows=rows,
        before=before,
        skipped=skipped,
    )
    return {
        "items": [row.model_dump(mode="json") for row in rows],
        "skipped": [item.model_dump(mode="json") for item in skipped],
    }, spec


@action(
    "canvas.layout.restore",
    CanvasLayoutRestoreParams,
    domains=["canvas"],
    undoable=False,
)
def _action_restore_canvas_layout(
    db: Database, params: CanvasLayoutRestoreParams, ctx: ActionContext
) -> tuple[dict[str, Any], ChangeSpec]:
    before = [
        row.model_dump(mode="json")
        for row in _load_canvas_layout(db, params.folder_id)
        if row.item_id in set(params.current_item_ids)
    ]

    restored_item_ids = {
        row.get("item_id") for row in params.rows if isinstance(row, dict) and row.get("item_id")
    }
    for item_id in params.current_item_ids:
        if item_id in restored_item_ids:
            continue
        existing = db.get(CanvasLayout, CanvasLayout.make_id(params.folder_id, item_id))
        if existing is not None:
            db.delete(existing)

    restored_rows: list[CanvasLayout] = []
    for snapshot in params.rows:
        row = CanvasLayout.model_validate(snapshot)
        db.save(row)
        restored_rows.append(row)

    spec = _canvas_layout_change_spec(
        emit_type="canvas.layout.saved",
        scope_id=params.folder_id,
        rows=restored_rows,
        before=before,
        skipped=[],
    )
    return {
        "items": [row.model_dump(mode="json") for row in restored_rows],
        "skipped": [],
    }, spec


@action(
    "canvas.arrange",
    CanvasArrangeParams,
    domains=["canvas"],
    undoable=True,
    invert=_invert_canvas_layout_to_restore,
)
def _action_arrange_canvas(
    db: Database, params: CanvasArrangeParams, ctx: ActionContext
) -> tuple[dict[str, Any], ChangeSpec]:
    node_id_set = set(params.node_ids)
    before = [
        row.model_dump(mode="json")
        for row in _load_canvas_layout(db, params.folder_id)
        if row.item_id in node_id_set
    ]
    rows, skipped = arrange_impl(
        db,
        params.folder_id,
        params.node_ids,
        params.strategy,
        spacing=params.spacing,
        columns=params.columns,
        radius=params.radius,
    )
    spec = _canvas_layout_change_spec(
        emit_type="canvas.arranged",
        scope_id=params.folder_id,
        rows=rows,
        before=before,
        skipped=skipped,
    )
    return {
        "items": [row.model_dump(mode="json") for row in rows],
        "skipped": [item.model_dump(mode="json") for item in skipped],
    }, spec


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


@router.get("/folders/{scope_id}/items", response_model=CanvasListResponse)
async def list_canvas_items(
    scope_id: str,
    kind: CanvasItemKind | None = None,
    db: Database = Depends(get_library_database),
) -> CanvasListResponse:
    filters: dict[str, Any] = {"folder_id": scope_id}
    if kind is not None:
        filters["kind"] = kind
    rows = db.query(CanvasItem, **filters)
    return CanvasListResponse(items=rows, count=len(rows))


@router.post("/folders/{scope_id}/items", response_model=CanvasItem)
async def create_canvas_item(
    scope_id: str,
    request: CanvasItemCreateRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> CanvasItem:
    result = registry.invoke(
        db,
        "canvas.item.create",
        {
            "folder_id": scope_id,
            **request.model_dump(mode="json"),
        },
        ctx,
    )
    return CanvasItem.model_validate(result.result)


@router.patch("/folders/{scope_id}/items/{item_id}", response_model=CanvasItem)
async def update_canvas_item(
    scope_id: str,
    item_id: str,
    request: CanvasItemUpdateRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> CanvasItem:
    try:
        result = registry.invoke(
            db,
            "canvas.item.update",
            {
                "folder_id": scope_id,
                "item_id": item_id,
                **request.model_dump(mode="json", exclude_unset=True),
            },
            ctx,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="canvas item not found") from exc
    return CanvasItem.model_validate(result.result)


@router.delete(
    "/folders/{scope_id}/items/{item_id}",
    response_model=CanvasDeletedResponse,
)
async def delete_canvas_item(
    scope_id: str,
    item_id: str,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> CanvasDeletedResponse:
    try:
        registry.invoke(
            db,
            "canvas.item.delete",
            {"folder_id": scope_id, "item_id": item_id},
            ctx,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="canvas item not found") from exc
    return CanvasDeletedResponse(status="deleted")


class CanvasItemCreateParams(CanvasItemCreateRequest):
    folder_id: str


class CanvasItemUpdateParams(CanvasItemUpdateRequest):
    folder_id: str
    item_id: str


class CanvasItemDeleteParams(BaseModel):
    folder_id: str
    item_id: str


class CanvasItemRestoreParams(BaseModel):
    snapshot: dict


def _invert_create_canvas_item(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    if not after:
        return None
    item = after.get("item") if isinstance(after.get("item"), dict) else after
    item_id = item.get("id") if isinstance(item, dict) else None
    folder_id = item.get("folder_id") if isinstance(item, dict) else None
    if not item_id or not folder_id:
        return None
    return ("canvas.item.delete", {"folder_id": folder_id, "item_id": item_id})


def _invert_restore_canvas_item(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    if not after:
        return None
    item = after.get("item") if isinstance(after.get("item"), dict) else after
    item_id = item.get("id") if isinstance(item, dict) else None
    folder_id = item.get("folder_id") if isinstance(item, dict) else None
    if before is None:
        if not item_id or not folder_id:
            return None
        return ("canvas.item.delete", {"folder_id": folder_id, "item_id": item_id})
    if not isinstance(before, dict):
        return None
    return ("canvas.item.restore", {"snapshot": before})


def _invert_to_restore_canvas_item(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    if not before:
        return None
    item = before.get("item") if isinstance(before.get("item"), dict) else before
    if not isinstance(item, dict):
        return None
    return ("canvas.item.restore", {"snapshot": item})


@action(
    "canvas.item.create",
    CanvasItemCreateParams,
    domains=["canvas"],
    undoable=True,
    invert=_invert_create_canvas_item,
)
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


@action(
    "canvas.item.update",
    CanvasItemUpdateParams,
    domains=["canvas"],
    undoable=True,
    invert=_invert_to_restore_canvas_item,
)
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


@action(
    "canvas.item.delete",
    CanvasItemDeleteParams,
    domains=["canvas"],
    undoable=True,
    invert=_invert_to_restore_canvas_item,
)
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


@action(
    "canvas.item.restore",
    CanvasItemRestoreParams,
    domains=["canvas"],
    undoable=False,
)
def _action_restore_canvas_item(
    db: Database, params: CanvasItemRestoreParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    item_id = params.snapshot.get("id")
    existing = db.get(CanvasItem, item_id) if item_id else None
    before = existing.model_dump(mode="json") if existing else None
    item = CanvasItem.model_validate(params.snapshot)
    item.updated_at = datetime.now()
    db.save(item)
    after = item.model_dump(mode="json")
    spec = ChangeSpec(
        domains=["canvas"],
        target_ids=[item.id],
        before={"item": before} if before else None,
        after={"item": after},
        emit_type="canvas.item.updated" if before else "canvas.item.created",
    )
    return after, spec
