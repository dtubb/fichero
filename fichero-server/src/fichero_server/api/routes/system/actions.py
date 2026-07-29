"""
API routes for Action Library.

Provides endpoints for:
- Listing and searching actions
- Creating custom actions
- Importing/exporting actions
- Recording action usage
"""

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from fichero_server.api.library_header import require_library_path
from fichero_server.api.auth import request_actor
from fichero_server.api.change_stream import emit_change
from fichero_server.api.main import get_library_database
from fichero_server.db import Database
from fichero_server.models import (
    ActionCategoriesResponse,
    ActionJsonResponse,
    ActionListResponse,
    ActionSuccessResponse,
)
from fichero_server.workflows.action_store import ActionStore, Action

router = APIRouter(prefix="/actions", tags=["actions"])


# =========================================================================
# Request/Response Models
# =========================================================================


class ActionResponse(BaseModel):
    """Action response model."""

    id: str
    name: str
    description: str
    category: str
    tags: list[str]
    icon: str
    node_template: dict[str, Any]
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    is_builtin: bool
    is_composite: bool
    author: str
    use_count: int
    last_used_at: str | None
    created_at: str
    updated_at: str


class CreateActionRequest(BaseModel):
    """Request to create a new action."""

    name: str
    description: str = ""
    category: str = "custom"
    tags: list[str] = []
    icon: str = "square.stack.3d.up"
    node_template: dict[str, Any] = {}
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    author: str = ""


class UpdateActionRequest(BaseModel):
    """Request to update an action."""

    name: str | None = None
    description: str | None = None
    category: str | None = None
    tags: list[str] | None = None
    icon: str | None = None
    node_template: dict[str, Any] | None = None
    nodes: list[dict[str, Any]] | None = None
    edges: list[dict[str, Any]] | None = None


class ImportActionRequest(BaseModel):
    """Request to import an action."""

    json_data: str
    new_id: bool = True


class CreateFromNodeRequest(BaseModel):
    """Request to create action from workflow node."""

    name: str
    node: dict[str, Any]
    description: str = ""
    category: str = "custom"
    tags: list[str] = []


class CreateCompositeRequest(BaseModel):
    """Request to create composite action."""

    name: str
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    description: str = ""
    category: str = "custom"
    tags: list[str] = []


# =========================================================================
# Helper Functions
# =========================================================================


def action_to_response(action: Action) -> ActionResponse:
    """Convert Action model to response."""
    return ActionResponse(
        id=action.id,
        name=action.name,
        description=action.description,
        category=action.category,
        tags=action.tags,
        icon=action.icon,
        node_template=action.node_template,
        nodes=action.nodes,
        edges=action.edges,
        is_builtin=action.is_builtin,
        is_composite=action.is_composite,
        author=action.author,
        use_count=action.use_count,
        last_used_at=action.last_used_at.isoformat() if action.last_used_at else None,
        created_at=action.created_at.isoformat(),
        updated_at=action.updated_at.isoformat(),
    )


def get_action_store(db: Database = Depends(get_library_database)) -> ActionStore:
    """Get ActionStore for current library."""
    return ActionStore(db)


def create_action_impl(store: ActionStore, request: CreateActionRequest) -> Action:
    """Build + persist a custom Action — the proven create logic.

    Extracted from the ``POST /actions`` route so BOTH the route and the
    ``actionlib.create`` audited action (EPIC #1848) drive the *same* code
    (iterate-not-replace: the algorithm is wrapped, never re-derived). Emission
    to the observable layer stays with the caller.
    """
    action = Action(
        name=request.name,
        description=request.description,
        category=request.category,
        tags=request.tags,
        icon=request.icon,
        node_template=request.node_template,
        nodes=request.nodes,
        edges=request.edges,
        author=request.author,
    )
    store.save(action)
    return action


def delete_action_impl(store: ActionStore, action_id: str) -> bool:
    """Validate + delete a custom Action — the proven delete logic.

    Raises ``HTTPException(404)`` if the action is missing and
    ``HTTPException(403)`` for a built-in (cannot be deleted). Shared verbatim by
    the ``DELETE /actions/{id}`` route and the ``actionlib.delete`` action so the
    same guard rails apply on every path. Emission stays with the caller.
    """
    action = store.get(action_id)
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")
    if action.is_builtin:
        raise HTTPException(status_code=403, detail="Cannot delete built-in action")
    return store.delete(action_id)


# =========================================================================
# List Endpoints
# =========================================================================


@router.get("", response_model=ActionListResponse)
async def list_actions(store: ActionStore = Depends(get_action_store)):
    """List all actions."""
    actions = store.list_all()
    return ActionListResponse(
        items=[action_to_response(a) for a in actions], count=len(actions)
    )


@router.get("/builtin", response_model=ActionListResponse)
async def list_builtin_actions(store: ActionStore = Depends(get_action_store)):
    """List built-in actions only."""
    actions = store.list_builtin()
    return ActionListResponse(
        items=[action_to_response(a) for a in actions], count=len(actions)
    )


@router.get("/custom", response_model=ActionListResponse)
async def list_custom_actions(store: ActionStore = Depends(get_action_store)):
    """List user-created actions only."""
    actions = store.list_custom()
    return ActionListResponse(
        items=[action_to_response(a) for a in actions], count=len(actions)
    )


@router.get("/recent", response_model=ActionListResponse)
async def list_recent_actions(
    limit: int = Query(default=10, ge=1, le=50),
    store: ActionStore = Depends(get_action_store),
):
    """List recently used actions."""
    actions = store.list_recent(limit=limit)
    return ActionListResponse(
        items=[action_to_response(a) for a in actions], count=len(actions)
    )


@router.get("/popular", response_model=ActionListResponse)
async def list_popular_actions(
    limit: int = Query(default=10, ge=1, le=50),
    store: ActionStore = Depends(get_action_store),
):
    """List most frequently used actions."""
    actions = store.list_popular(limit=limit)
    return ActionListResponse(
        items=[action_to_response(a) for a in actions], count=len(actions)
    )


@router.get("/categories", response_model=ActionCategoriesResponse)
async def list_categories(
    store: ActionStore = Depends(get_action_store),
) -> ActionCategoriesResponse:
    """List all action categories."""
    categories = store.get_categories()
    return ActionCategoriesResponse(categories=categories)


@router.get("/category/{category}", response_model=ActionListResponse)
async def list_actions_by_category(
    category: str, store: ActionStore = Depends(get_action_store)
):
    """List actions in a specific category."""
    actions = store.list_by_category(category)
    return ActionListResponse(
        items=[action_to_response(a) for a in actions], count=len(actions)
    )


# =========================================================================
# Search
# =========================================================================


@router.get("/search", response_model=ActionListResponse)
async def search_actions(
    query: str | None = None,
    category: str | None = None,
    tags: str | None = Query(default=None, description="Comma-separated tags"),
    store: ActionStore = Depends(get_action_store),
):
    """
    Search actions by criteria.

    Args:
        query: Search in name and description
        category: Filter by category
        tags: Comma-separated list of tags (must have all)
    """
    tag_list = [t.strip() for t in tags.split(",")] if tags else None

    actions = store.search(query=query, category=category, tags=tag_list)
    return ActionListResponse(
        items=[action_to_response(a) for a in actions], count=len(actions)
    )


# =========================================================================
# CRUD
# =========================================================================


@router.get("/{action_id}", response_model=ActionResponse)
async def get_action(action_id: str, store: ActionStore = Depends(get_action_store)):
    """Get an action by ID."""
    action = store.get(action_id)
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")
    return action_to_response(action)


@router.post("", response_model=ActionResponse)
async def create_action(
    request: CreateActionRequest,
    store: ActionStore = Depends(get_action_store),
    x_fichero_library_path: str = Depends(require_library_path),
    x_fichero_origin_window: str | None = Header(
        default=None, alias="X-Fichero-Origin-Window"
    ),
    actor: str = Depends(request_actor),
):
    """Create a new action."""
    action = create_action_impl(store, request)
    emit_change(
        x_fichero_library_path,
        type="action.created",
        entity_ids=[action.id],
        actor=actor,
        origin_window=x_fichero_origin_window,
        origin_user=actor,
    )
    return action_to_response(action)


@router.put("/{action_id}", response_model=ActionResponse)
async def update_action(
    action_id: str,
    request: UpdateActionRequest,
    store: ActionStore = Depends(get_action_store),
    x_fichero_library_path: str = Depends(require_library_path),
    x_fichero_origin_window: str | None = Header(
        default=None, alias="X-Fichero-Origin-Window"
    ),
    actor: str = Depends(request_actor),
):
    """Update an action."""
    action = store.get(action_id)
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")

    if action.is_builtin:
        raise HTTPException(status_code=403, detail="Cannot modify built-in action")

    # Update fields if provided
    if request.name is not None:
        action.name = request.name
    if request.description is not None:
        action.description = request.description
    if request.category is not None:
        action.category = request.category
    if request.tags is not None:
        action.tags = request.tags
    if request.icon is not None:
        action.icon = request.icon
    if request.node_template is not None:
        action.node_template = request.node_template
    if request.nodes is not None:
        action.nodes = request.nodes
    if request.edges is not None:
        action.edges = request.edges

    store.save(action)
    emit_change(
        x_fichero_library_path,
        type="action.updated",
        entity_ids=[action.id],
        actor=actor,
        origin_window=x_fichero_origin_window,
        origin_user=actor,
    )
    return action_to_response(action)


@router.delete("/{action_id}", response_model=ActionSuccessResponse)
async def delete_action(
    action_id: str,
    store: ActionStore = Depends(get_action_store),
    x_fichero_library_path: str = Depends(require_library_path),
    x_fichero_origin_window: str | None = Header(
        default=None, alias="X-Fichero-Origin-Window"
    ),
    actor: str = Depends(request_actor),
) -> ActionSuccessResponse:
    """Delete an action."""
    success = delete_action_impl(store, action_id)
    emit_change(
        x_fichero_library_path,
        type="action.deleted",
        entity_ids=[action_id],
        actor=actor,
        origin_window=x_fichero_origin_window,
        origin_user=actor,
    )
    return ActionSuccessResponse(success=success)


# =========================================================================
# Usage Tracking
# =========================================================================


@router.post("/{action_id}/use", response_model=ActionSuccessResponse)
async def record_action_use(
    action_id: str,
    store: ActionStore = Depends(get_action_store),
    x_fichero_library_path: str = Depends(require_library_path),
    x_fichero_origin_window: str | None = Header(
        default=None, alias="X-Fichero-Origin-Window"
    ),
    actor: str = Depends(request_actor),
) -> ActionSuccessResponse:
    """Record that an action was used."""
    action = store.get(action_id)
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")

    store.record_use(action_id)
    emit_change(
        x_fichero_library_path,
        type="action.updated",
        entity_ids=[action_id],
        actor=actor,
        origin_window=x_fichero_origin_window,
        origin_user=actor,
    )
    return ActionSuccessResponse(success=True)


# =========================================================================
# Import/Export
# =========================================================================


@router.get("/{action_id}/export", response_model=ActionJsonResponse)
async def export_action(
    action_id: str, store: ActionStore = Depends(get_action_store)
) -> ActionJsonResponse:
    """Export an action as JSON."""
    try:
        json_str = store.export_action(action_id)
        return ActionJsonResponse(json_data=json_str)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/import", response_model=ActionResponse)
async def import_action(
    request: ImportActionRequest,
    store: ActionStore = Depends(get_action_store),
    x_fichero_library_path: str = Depends(require_library_path),
    x_fichero_origin_window: str | None = Header(
        default=None, alias="X-Fichero-Origin-Window"
    ),
    actor: str = Depends(request_actor),
):
    """Import an action from JSON."""
    try:
        action = store.import_action(request.json_data, new_id=request.new_id)
        emit_change(
            x_fichero_library_path,
            type="action.created",
            entity_ids=[action.id],
            actor=actor,
            origin_window=x_fichero_origin_window,
            origin_user=actor,
        )
        return action_to_response(action)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# =========================================================================
# Creation Helpers
# =========================================================================


@router.post("/from-node", response_model=ActionResponse)
async def create_action_from_node(
    request: CreateFromNodeRequest,
    store: ActionStore = Depends(get_action_store),
    x_fichero_library_path: str = Depends(require_library_path),
    x_fichero_origin_window: str | None = Header(
        default=None, alias="X-Fichero-Origin-Window"
    ),
    actor: str = Depends(request_actor),
):
    """Create an action from a workflow node."""
    action = store.create_from_node(
        name=request.name,
        node=request.node,
        description=request.description,
        category=request.category,
        tags=request.tags,
    )
    emit_change(
        x_fichero_library_path,
        type="action.created",
        entity_ids=[action.id],
        actor=actor,
        origin_window=x_fichero_origin_window,
        origin_user=actor,
    )
    return action_to_response(action)


@router.post("/composite", response_model=ActionResponse)
async def create_composite_action(
    request: CreateCompositeRequest,
    store: ActionStore = Depends(get_action_store),
    x_fichero_library_path: str = Depends(require_library_path),
    x_fichero_origin_window: str | None = Header(
        default=None, alias="X-Fichero-Origin-Window"
    ),
    actor: str = Depends(request_actor),
):
    """Create a composite action from multiple nodes."""
    action = store.create_composite(
        name=request.name,
        nodes=request.nodes,
        edges=request.edges,
        description=request.description,
        category=request.category,
        tags=request.tags,
    )
    emit_change(
        x_fichero_library_path,
        type="action.created",
        entity_ids=[action.id],
        actor=actor,
        origin_window=x_fichero_origin_window,
        origin_user=actor,
    )
    return action_to_response(action)


# ===========================================================================
# Action layer registration (EPIC #1848 / sweep #2014)
# ===========================================================================
#
# The workflow Action Library's two mutating ops become registered, AUDITED
# actions so chat tools / App Intents / tests / the audit log all drive ONE
# path via POST /api/actions/invoke. Each action WRAPS the proven *_impl above
# (iterate-not-replace) and routes through `registry.invoke`, which writes the
# generic ActionAudit and emits the same `action.created` / `action.deleted`
# change event the typed routes above already emit. The typed routes are
# untouched and stay green — the action is the *additional* uniform path.
#
# Named `actionlib.*` (NOT `action.*`) to avoid confusion with the registry's
# own "action" concept — these mutate the *workflow Action Library*, a
# DuckDB-backed store (`ActionStore`), not knowledge-graph objects.
#
# actionlib.delete is undoable: its before-snapshot is the full Action row, and
# the inverse `actionlib.restore` re-saves it. actionlib.create is undoable too
# (the inverse deletes the freshly-created row).

from fichero_server.actions.registry import (  # noqa: E402
    ActionContext,
    ChangeSpec,
    action,
)


class DeleteActionParams(BaseModel):
    """Params for actionlib.delete — the action-library id to remove."""

    action_id: str = Field(description="Action Library id to delete")


class RestoreActionParams(BaseModel):
    """Params for actionlib.restore — the JSON snapshot of a deleted Action."""

    action: dict[str, Any] = Field(
        description="Full Action.model_dump(mode='json') snapshot to re-insert"
    )


def _invert_create(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    """Undo a create by deleting the row it inserted."""
    if not after or not after.get("action_id"):
        return None
    return ("actionlib.delete", {"action_id": after["action_id"]})


@action(
    "actionlib.create",
    CreateActionRequest,
    domains=["action"],
    undoable=True,
    invert=_invert_create,
)
def _action_create_action(
    db: Database, params: CreateActionRequest, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    store = ActionStore(db)
    action_obj = create_action_impl(store, params)
    spec = ChangeSpec(
        domains=["action"],
        target_ids=[action_obj.id],
        after={"action_id": action_obj.id, "created": True},
        emit_type="action.created",
        entity_ids=[action_obj.id],
    )
    return action_to_response(action_obj).model_dump(mode="json"), spec


def _invert_delete(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    """Undo a delete by re-inserting the captured Action snapshot."""
    if not before or not before.get("action"):
        return None
    return ("actionlib.restore", {"action": before["action"]})


@action(
    "actionlib.delete",
    DeleteActionParams,
    domains=["action"],
    undoable=True,
    invert=_invert_delete,
)
def _action_delete_action(
    db: Database, params: DeleteActionParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    store = ActionStore(db)
    # Snapshot the full row BEFORE delete validates + removes it — this is the
    # undo payload (delete_action_impl raises 404/403 for missing/built-in).
    existing = store.get(params.action_id)
    before = (
        {"action": existing.model_dump(mode="json")} if existing is not None else None
    )
    success = delete_action_impl(store, params.action_id)
    spec = ChangeSpec(
        domains=["action"],
        target_ids=[params.action_id],
        before=before,
        after={"action_id": params.action_id, "deleted": success},
        emit_type="action.deleted",
        entity_ids=[params.action_id],
    )
    return {"success": success, "action_id": params.action_id}, spec


@action(
    "actionlib.restore",
    RestoreActionParams,
    domains=["action"],
    undoable=False,
)
def _action_restore_action(
    db: Database, params: RestoreActionParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    store = ActionStore(db)
    action_obj = Action.model_validate(params.action)
    store.save(action_obj)
    spec = ChangeSpec(
        domains=["action"],
        target_ids=[action_obj.id],
        after={"action_id": action_obj.id, "restored": True},
        emit_type="action.created",
        entity_ids=[action_obj.id],
    )
    return action_to_response(action_obj).model_dump(mode="json"), spec
