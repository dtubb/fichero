"""
Folder Management Routes

Generic folder operations for hierarchical organization.
Works with Workflows, SavedSearches, and Conversations.
"""

import logging
from datetime import datetime
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from fichero_server.api.main import get_library_database, get_library_database_for_write
from fichero_server.db import Database
from fichero_server.models import Conversation, DocType, Document, SavedSearch, Workflow

logger = logging.getLogger(__name__)
router = APIRouter()


# =============================================================================
# Entity Type Enum
# =============================================================================


class EntityType(str, Enum):
    """Type of entity for folder operations."""

    workflow = "workflow"
    search = "search"
    conversation = "conversation"


def _get_model_for_entity(entity_type: EntityType):
    """Get the database model class for an entity type."""
    mapping = {
        EntityType.workflow: Workflow,
        EntityType.search: SavedSearch,
        EntityType.conversation: Conversation,
    }
    return mapping[entity_type]


# =============================================================================
# Request/Response Models
# =============================================================================


class FolderInfo(BaseModel):
    """Folder information."""

    path: str
    item_count: int
    parent_path: str


class FolderListResponse(BaseModel):
    """Standardized {items, count} envelope for GET /api/folders/{entity_type}/folders."""

    items: list[FolderInfo]
    count: int


class MoveItemsRequest(BaseModel):
    """Request to move items to a folder."""

    item_ids: list[str]
    folder_path: str


class FolderRenameResponse(BaseModel):
    moved_count: int
    old_path: str
    new_path: str


class FolderMoveResponse(BaseModel):
    moved_count: int
    folder_path: str


class FolderDeleteResponse(BaseModel):
    deleted_count: int
    moved_to_root: int
    parent_path: str | None = None


class FolderViewInfo(BaseModel):
    """A lens available for a folder/workspace and whether it has content."""

    id: str
    label: str
    populated: bool
    item_count: int = 0


class FolderViewsResponse(BaseModel):
    """Available folder/workspace lenses for the selected document folder."""

    folder_id: str
    is_workspace: bool
    curated_item_count: int
    child_count: int
    views: list[FolderViewInfo]


class RenameFolderRequest(BaseModel):
    """Request to rename a folder."""

    old_path: str
    new_path: str


# =============================================================================
# Folder Routes
# =============================================================================


def _metadata_has_geo(metadata: dict | None) -> bool:
    """Return true when document or curated-item metadata carries map data."""
    if not isinstance(metadata, dict):
        return False
    if metadata.get("latitude") is not None and metadata.get("longitude") is not None:
        return True
    if metadata.get("lat") is not None and metadata.get("lon") is not None:
        return True
    if metadata.get("geo") or metadata.get("geojson") or metadata.get("coordinates"):
        return True
    return False


def _document_has_geo(doc: Document) -> bool:
    return _metadata_has_geo(doc.metadata) or _metadata_has_geo(doc.source_metadata)


def _curated_item_url(item: dict) -> str | None:
    value = item.get("url") or item.get("source_url") or item.get("href")
    return value if isinstance(value, str) and value else None


def _curated_item_has_geo(item: dict) -> bool:
    return _metadata_has_geo(item) or _metadata_has_geo(item.get("metadata"))


def _folder_descendant_documents(db: Database, folder_id: str) -> list[Document]:
    """Collect all descendant documents for a folder, breadth-first."""
    descendants: list[Document] = []
    frontier = [folder_id]
    seen = {folder_id}
    while frontier:
        parent_id = frontier.pop(0)
        for child in db.query(Document, parent_id=parent_id):
            if child.id in seen:
                continue
            seen.add(child.id)
            descendants.append(child)
            frontier.append(child.id)
    return descendants


@router.get("/{folder_id}/views", response_model=FolderViewsResponse)
async def get_folder_views(
    folder_id: str,
    db: Database = Depends(get_library_database),
) -> FolderViewsResponse:
    """Return the list/map/WebKit/RealityKit lenses available for a folder.

    Workspaces are ordinary folder documents with ``is_workspace=true`` and
    optional curated items. The views are still available for any folder; the
    ``populated`` flag tells SwiftUI which lenses currently have content.
    """
    folder = db.get(Document, folder_id)
    if folder is None:
        raise HTTPException(status_code=404, detail="Folder not found")
    if folder.doc_type != DocType.folder:
        raise HTTPException(status_code=400, detail="Document is not a folder")

    descendants = _folder_descendant_documents(db, folder_id)
    curated_items = folder.curated_items or []
    content_count = len(descendants) + len(curated_items)

    map_count = sum(1 for doc in descendants if _document_has_geo(doc))
    map_count += sum(
        1 for item in curated_items if isinstance(item, dict) and _curated_item_has_geo(item)
    )

    web_count = sum(1 for doc in descendants if doc.path or doc.source_url)
    web_count += sum(
        1 for item in curated_items if isinstance(item, dict) and _curated_item_url(item)
    )

    return FolderViewsResponse(
        folder_id=folder.id,
        is_workspace=folder.is_workspace,
        curated_item_count=len(curated_items),
        child_count=len(descendants),
        views=[
            FolderViewInfo(
                id="list",
                label="List",
                populated=content_count > 0,
                item_count=content_count,
            ),
            FolderViewInfo(
                id="map",
                label="Map",
                populated=map_count > 0,
                item_count=map_count,
            ),
            FolderViewInfo(
                id="webkit",
                label="WebKit",
                populated=web_count > 0,
                item_count=web_count,
            ),
            FolderViewInfo(
                id="realitykit",
                label="RealityKit",
                populated=content_count > 0,
                item_count=content_count,
            ),
        ],
    )


@router.get("/{entity_type}/folders", response_model=FolderListResponse)
async def list_folders(
    entity_type: EntityType,
    parent_path: str = "/",
    db: Database = Depends(get_library_database),
) -> FolderListResponse:
    """List unique folder paths under parent.

    Args:
        entity_type: Type of entity (workflow, search, conversation)
        parent_path: Parent folder path (default: "/")

    Returns:
        List of folders with item counts
    """
    model = _get_model_for_entity(entity_type)
    all_items = db.all(model)

    # Extract unique folders under parent
    folders = set()
    for item in all_items:
        path = item.folder_path
        if path.startswith(parent_path) and path != parent_path:
            # Get immediate child folder
            relative = path[len(parent_path) :].lstrip("/")
            if "/" in relative:
                # This is a subfolder - get the immediate child
                child_folder = parent_path.rstrip("/") + "/" + relative.split("/")[0]
            else:
                # This is a direct child
                child_folder = path
            folders.add(child_folder)

    # Count items in each folder
    result = []
    for folder in sorted(folders):
        count = len([i for i in all_items if i.folder_path == folder])
        # Calculate parent path
        parent = "/".join(folder.rstrip("/").split("/")[:-1]) or "/"

        result.append(FolderInfo(path=folder, item_count=count, parent_path=parent))

    return FolderListResponse(items=result, count=len(result))


@router.post("/{entity_type}/folders")
async def create_folder(
    entity_type: EntityType,
    folder_path: str,
    db: Database = Depends(get_library_database_for_write),
) -> FolderInfo:
    """Create a folder (validates path format).

    Folders are virtual - they exist when items reference them.
    This endpoint validates the path and returns folder info.

    Args:
        entity_type: Type of entity (workflow, search, conversation)
        folder_path: New folder path (must start with '/')

    Returns:
        Folder information
    """
    if not folder_path.startswith("/"):
        raise HTTPException(status_code=400, detail="folder_path must start with '/'")

    # Validate path doesn't have trailing slash (except root)
    if folder_path != "/" and folder_path.endswith("/"):
        raise HTTPException(
            status_code=400, detail="folder_path must not end with '/' (except root)"
        )

    # Count existing items in folder
    model = _get_model_for_entity(entity_type)
    items = db.query(model, folder_path=folder_path)

    # Calculate parent path
    parent = "/".join(folder_path.rstrip("/").split("/")[:-1]) or "/"

    return FolderInfo(path=folder_path, item_count=len(items), parent_path=parent)


@router.put("/{entity_type}/folders")
async def rename_folder(
    entity_type: EntityType,
    request: RenameFolderRequest,
    db: Database = Depends(get_library_database_for_write),
) -> FolderRenameResponse:
    """Rename a folder and all items within it.

    Also renames all subfolders recursively.

    Args:
        entity_type: Type of entity (workflow, search, conversation)
        request: Rename request with old_path and new_path

    Returns:
        Number of items moved
    """
    model = _get_model_for_entity(entity_type)
    all_items = db.all(model)

    # Validate new path
    if not request.new_path.startswith("/"):
        raise HTTPException(status_code=400, detail="new_path must start with '/'")

    # Find all items in old path or its subfolders
    moved_count = 0
    for item in all_items:
        if item.folder_path == request.old_path or item.folder_path.startswith(
            request.old_path + "/"
        ):
            # Update path - replace old prefix with new prefix
            item.folder_path = (
                request.new_path + item.folder_path[len(request.old_path) :]
            )
            item.updated_at = datetime.now()
            db.save(item)
            moved_count += 1

    return FolderRenameResponse(
        moved_count=moved_count,
        old_path=request.old_path,
        new_path=request.new_path,
    )


@router.put("/{entity_type}/move")
async def move_items(
    entity_type: EntityType,
    request: MoveItemsRequest,
    db: Database = Depends(get_library_database_for_write),
) -> FolderMoveResponse:
    """Move items to a different folder.

    Args:
        entity_type: Type of entity (workflow, search, conversation)
        request: Move request with item_ids and folder_path

    Returns:
        Number of items moved
    """
    model = _get_model_for_entity(entity_type)

    # Validate folder path
    if not request.folder_path.startswith("/"):
        raise HTTPException(status_code=400, detail="folder_path must start with '/'")

    moved_count = 0
    for item_id in request.item_ids:
        item = db.get(model, item_id)
        if item:
            item.folder_path = request.folder_path
            item.updated_at = datetime.now()
            db.save(item)
            moved_count += 1

    return FolderMoveResponse(moved_count=moved_count, folder_path=request.folder_path)


@router.delete("/{entity_type}/folders")
async def delete_folder(
    entity_type: EntityType,
    folder_path: str,
    delete_contents: bool = False,
    db: Database = Depends(get_library_database_for_write),
) -> FolderDeleteResponse:
    """Delete a folder (optionally with contents).

    Args:
        entity_type: Type of entity (workflow, search, conversation)
        folder_path: Folder path to delete
        delete_contents: If True, delete all items. If False, move to parent folder.

    Returns:
        Number of items deleted/moved
    """
    model = _get_model_for_entity(entity_type)
    items = db.query(model, folder_path=folder_path)

    if delete_contents:
        # Delete all items in folder
        for item in items:
            db.delete(item)
        return FolderDeleteResponse(deleted_count=len(items), moved_to_root=0)
    else:
        # Move items to parent folder
        parent_path = "/".join(folder_path.rstrip("/").split("/")[:-1]) or "/"
        for item in items:
            item.folder_path = parent_path
            item.updated_at = datetime.now()
            db.save(item)
        return FolderDeleteResponse(
            deleted_count=0,
            moved_to_root=len(items),
            parent_path=parent_path,
        )
