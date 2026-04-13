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

from fichero.api.main import get_library_database
from fichero.db import Database
from fichero.models import Conversation, SavedSearch, Workflow

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


class MoveItemsRequest(BaseModel):
    """Request to move items to a folder."""

    item_ids: list[str]
    folder_path: str


class RenameFolderRequest(BaseModel):
    """Request to rename a folder."""

    old_path: str
    new_path: str


# =============================================================================
# Folder Routes
# =============================================================================


@router.get("/{entity_type}/folders")
async def list_folders(
    entity_type: EntityType,
    parent_path: str = "/",
    db: Database = Depends(get_library_database),
) -> list[FolderInfo]:
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

    return result


@router.post("/{entity_type}/folders")
async def create_folder(
    entity_type: EntityType,
    folder_path: str,
    db: Database = Depends(get_library_database),
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
    db: Database = Depends(get_library_database),
) -> dict:
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

    return {
        "moved_count": moved_count,
        "old_path": request.old_path,
        "new_path": request.new_path,
    }


@router.put("/{entity_type}/move")
async def move_items(
    entity_type: EntityType,
    request: MoveItemsRequest,
    db: Database = Depends(get_library_database),
) -> dict:
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

    return {"moved_count": moved_count, "folder_path": request.folder_path}


@router.delete("/{entity_type}/folders")
async def delete_folder(
    entity_type: EntityType,
    folder_path: str,
    delete_contents: bool = False,
    db: Database = Depends(get_library_database),
) -> dict:
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
        return {"deleted_count": len(items), "moved_to_root": 0}
    else:
        # Move items to parent folder
        parent_path = "/".join(folder_path.rstrip("/").split("/")[:-1]) or "/"
        for item in items:
            item.folder_path = parent_path
            item.updated_at = datetime.now()
            db.save(item)
        return {
            "deleted_count": 0,
            "moved_to_root": len(items),
            "parent_path": parent_path,
        }
