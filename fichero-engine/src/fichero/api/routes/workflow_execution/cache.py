"""Workflow node result cache management routes."""

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from fichero.db import Database
from fichero.api.main import get_library_database, get_library_database_for_write
from fichero.workflows.cache import get_node_cache
from .schemas import workflow_internal_error

logger = logging.getLogger(__name__)
router = APIRouter()


# =============================================================================
# Models
# =============================================================================


class CacheStatsResponse(BaseModel):
    """Response with cache statistics."""

    total_entries: int
    workflows_cached: int | None = None
    nodes_cached: int | None = None
    tools_cached: int
    oldest_entry: str | None = None
    newest_entry: str | None = None


class CacheClearResponse(BaseModel):
    """Response after clearing cache."""

    entries_deleted: int
    message: str


# =============================================================================
# Endpoints
# =============================================================================


@router.get("/workflows/{workflow_id}/cache/stats")
async def get_workflow_cache_stats(
    workflow_id: str,
    db: Database = Depends(get_library_database),
) -> CacheStatsResponse:
    """
    Get cache statistics for a workflow.

    Shows how many node results are cached, which tools are cached, etc.

    Args:
        workflow_id: Workflow ID

    Returns:
        Cache statistics
    """
    try:
        cache = get_node_cache(db.path)
        stats = cache.get_stats(workflow_id=workflow_id)

        return CacheStatsResponse(**stats)

    except Exception:
        logger.exception(f"Failed to get cache stats for workflow {workflow_id}")
        raise workflow_internal_error("Failed to get workflow cache stats")


@router.delete("/workflows/{workflow_id}/cache")
async def clear_workflow_cache(
    workflow_id: str,
    db: Database = Depends(get_library_database_for_write),
) -> CacheClearResponse:
    """
    Clear all cached results for a workflow.

    This will cause all nodes to be re-executed on the next run.

    Args:
        workflow_id: Workflow ID

    Returns:
        Number of entries deleted
    """
    try:
        cache = get_node_cache(db.path)
        count = cache.clear_workflow(workflow_id)

        return CacheClearResponse(
            entries_deleted=count,
            message=f"Cleared {count} cached entries for workflow {workflow_id}",
        )

    except Exception:
        logger.exception(f"Failed to clear cache for workflow {workflow_id}")
        raise workflow_internal_error("Failed to clear workflow cache")


@router.delete("/cache")
async def clear_all_cache(
    db: Database = Depends(get_library_database_for_write),
) -> CacheClearResponse:
    """
    Clear all cached node results.

    This will cause all nodes in all workflows to be re-executed on next run.

    Returns:
        Number of entries deleted
    """
    try:
        cache = get_node_cache(db.path)
        count = cache.clear_all()

        return CacheClearResponse(
            entries_deleted=count, message=f"Cleared entire cache: {count} entries"
        )

    except Exception:
        logger.exception("Failed to clear cache")
        raise workflow_internal_error("Failed to clear workflow cache")


@router.get("/cache/stats")
async def get_all_cache_stats(
    db: Database = Depends(get_library_database),
) -> CacheStatsResponse:
    """
    Get overall cache statistics.

    Shows total cached entries across all workflows.

    Returns:
        Cache statistics
    """
    try:
        cache = get_node_cache(db.path)
        stats = cache.get_stats()

        return CacheStatsResponse(**stats)

    except Exception:
        logger.exception("Failed to get cache stats")
        raise workflow_internal_error("Failed to get workflow cache stats")
