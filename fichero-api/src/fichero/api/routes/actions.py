"""
API routes for Action Library.

Provides endpoints for:
- Listing and searching actions
- Creating custom actions
- Importing/exporting actions
- Recording action usage
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from fichero.api.main import get_library_database
from fichero.db import Database
from fichero.workflows.action_store import ActionStore, Action

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


# =========================================================================
# List Endpoints
# =========================================================================


@router.get("", response_model=list[ActionResponse])
async def list_actions(store: ActionStore = Depends(get_action_store)):
    """List all actions."""
    actions = store.list_all()
    return [action_to_response(a) for a in actions]


@router.get("/builtin", response_model=list[ActionResponse])
async def list_builtin_actions(store: ActionStore = Depends(get_action_store)):
    """List built-in actions only."""
    actions = store.list_builtin()
    return [action_to_response(a) for a in actions]


@router.get("/custom", response_model=list[ActionResponse])
async def list_custom_actions(store: ActionStore = Depends(get_action_store)):
    """List user-created actions only."""
    actions = store.list_custom()
    return [action_to_response(a) for a in actions]


@router.get("/recent", response_model=list[ActionResponse])
async def list_recent_actions(
    limit: int = Query(default=10, ge=1, le=50),
    store: ActionStore = Depends(get_action_store),
):
    """List recently used actions."""
    actions = store.list_recent(limit=limit)
    return [action_to_response(a) for a in actions]


@router.get("/popular", response_model=list[ActionResponse])
async def list_popular_actions(
    limit: int = Query(default=10, ge=1, le=50),
    store: ActionStore = Depends(get_action_store),
):
    """List most frequently used actions."""
    actions = store.list_popular(limit=limit)
    return [action_to_response(a) for a in actions]


@router.get("/categories")
async def list_categories(store: ActionStore = Depends(get_action_store)):
    """List all action categories."""
    categories = store.get_categories()
    return {"categories": categories}


@router.get("/category/{category}", response_model=list[ActionResponse])
async def list_actions_by_category(
    category: str, store: ActionStore = Depends(get_action_store)
):
    """List actions in a specific category."""
    actions = store.list_by_category(category)
    return [action_to_response(a) for a in actions]


# =========================================================================
# Search
# =========================================================================


@router.get("/search", response_model=list[ActionResponse])
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
    return [action_to_response(a) for a in actions]


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
    request: CreateActionRequest, store: ActionStore = Depends(get_action_store)
):
    """Create a new action."""
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
    return action_to_response(action)


@router.put("/{action_id}", response_model=ActionResponse)
async def update_action(
    action_id: str,
    request: UpdateActionRequest,
    store: ActionStore = Depends(get_action_store),
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
    return action_to_response(action)


@router.delete("/{action_id}")
async def delete_action(action_id: str, store: ActionStore = Depends(get_action_store)):
    """Delete an action."""
    action = store.get(action_id)
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")

    if action.is_builtin:
        raise HTTPException(status_code=403, detail="Cannot delete built-in action")

    success = store.delete(action_id)
    return {"success": success}


# =========================================================================
# Usage Tracking
# =========================================================================


@router.post("/{action_id}/use")
async def record_action_use(
    action_id: str, store: ActionStore = Depends(get_action_store)
):
    """Record that an action was used."""
    action = store.get(action_id)
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")

    store.record_use(action_id)
    return {"success": True}


# =========================================================================
# Import/Export
# =========================================================================


@router.get("/{action_id}/export")
async def export_action(action_id: str, store: ActionStore = Depends(get_action_store)):
    """Export an action as JSON."""
    try:
        json_str = store.export_action(action_id)
        return {"json": json_str}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/import", response_model=ActionResponse)
async def import_action(
    request: ImportActionRequest, store: ActionStore = Depends(get_action_store)
):
    """Import an action from JSON."""
    try:
        action = store.import_action(request.json_data, new_id=request.new_id)
        return action_to_response(action)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# =========================================================================
# Creation Helpers
# =========================================================================


@router.post("/from-node", response_model=ActionResponse)
async def create_action_from_node(
    request: CreateFromNodeRequest, store: ActionStore = Depends(get_action_store)
):
    """Create an action from a workflow node."""
    action = store.create_from_node(
        name=request.name,
        node=request.node,
        description=request.description,
        category=request.category,
        tags=request.tags,
    )
    return action_to_response(action)


@router.post("/composite", response_model=ActionResponse)
async def create_composite_action(
    request: CreateCompositeRequest, store: ActionStore = Depends(get_action_store)
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
    return action_to_response(action)
