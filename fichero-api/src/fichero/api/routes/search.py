"""
Search Routes

Semantic search using LanceDB vector embeddings.
"""

import logging
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from pydantic import BaseModel

from fichero.db import Database, SearchResult

logger = logging.getLogger(__name__)
router = APIRouter()


def _safe_isoformat(value) -> str:
    """Return ISO string when value behaves like datetime, else now."""
    return (
        value.isoformat() if hasattr(value, "isoformat") else datetime.now().isoformat()
    )


# Import the get_library_database dependency
from fichero.api.main import get_library_database  # noqa: E402


# Request/Response models
class SearchRequest(BaseModel):
    """Request model for enhanced search."""

    query: str
    limit: int = 10
    min_score: float = 0.0

    # Advanced search options
    search_type: str = "hybrid"  # "semantic", "fulltext", or "hybrid"
    filters: dict | None = (
        None  # Advanced filters (doc_type, file_type, date ranges, etc.)
    )
    sort_by: str = "relevance"  # "relevance", "date", "name", "size"
    sort_direction: str = "desc"  # "asc" or "desc"

    # Pagination
    offset: int = 0

    # Full-text search options
    use_fuzzy_match: bool = False
    highlight_results: bool = True


class SearchResponse(BaseModel):
    """Response model for enhanced search results."""

    query: str
    results: list[SearchResult]
    count: int
    total_results: int  # Total results before pagination
    search_type: str  # Type of search performed
    execution_time_ms: float  # Search execution time

    # Search statistics
    has_more: bool = False  # Whether more results are available
    filters_applied: dict | None = None  # Filters that were applied
    suggestions: list[str] | None = None  # Search suggestions


class ReindexResponse(BaseModel):
    """Response for reindex operation."""

    status: str
    indexed: int


# Routes


@router.post("")
async def enhanced_search(
    request: SearchRequest, db: Database = Depends(get_library_database)
) -> SearchResponse:
    """
    Perform enhanced search over documents.

    Supports hybrid search (semantic + full-text), advanced filtering, sorting, and pagination.
    """
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    # Validate search type
    if request.search_type not in ["semantic", "fulltext", "hybrid"]:
        raise HTTPException(
            status_code=400,
            detail="Invalid search_type. Must be 'semantic', 'fulltext', or 'hybrid'",
        )

    # Validate sort options
    if request.sort_by not in ["relevance", "date", "name", "size"]:
        raise HTTPException(
            status_code=400,
            detail="Invalid sort_by. Must be 'relevance', 'date', 'name', or 'size'",
        )

    if request.sort_direction not in ["asc", "desc"]:
        raise HTTPException(
            status_code=400, detail="Invalid sort_direction. Must be 'asc' or 'desc'"
        )

    # Perform enhanced search
    results, total_count, search_stats = db.search(
        query=request.query,
        limit=request.limit,
        min_score=request.min_score,
        search_type=request.search_type,
        filters=request.filters,
        sort_by=request.sort_by,
        sort_order=request.sort_direction,  # db.search uses sort_order param for direction
        offset=request.offset,
        use_fuzzy_match=request.use_fuzzy_match,
        highlight_results=request.highlight_results,
    )

    return SearchResponse(
        query=request.query,
        results=results,
        count=len(results),
        total_results=total_count,
        search_type=search_stats.get("search_type", request.search_type),
        execution_time_ms=search_stats.get("execution_time_ms", 0),
        has_more=search_stats.get("has_more", False),
        filters_applied=request.filters,
        suggestions=None,  # Could be populated with search suggestions
    )


@router.get("/stats")
async def search_stats(db: Database = Depends(get_library_database)):
    """Get embedding/search statistics."""
    return db.embedding_stats()


@router.post("/reindex")
async def reindex_all(
    background_tasks: BackgroundTasks, db: Database = Depends(get_library_database)
):
    """
    Rebuild search index for all documents.

    This runs in the background - poll /stats to check progress.
    """

    def do_reindex():
        try:
            count = db.reindex_all()
            logger.info(f"Reindexed {count} documents")
        except Exception as e:
            logger.error(f"Reindex failed: {e}")

    background_tasks.add_task(do_reindex)

    return {
        "status": "started",
        "message": "Reindex started in background. Poll /api/search/stats for progress.",
    }


@router.post("/embed/{doc_id}")
async def embed_document(doc_id: str, db: Database = Depends(get_library_database)):
    """Create embedding for a specific document."""
    from fichero.models import Document

    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")

    success = db.embed(doc)

    return {
        "document_id": doc_id,
        "embedded": success,
    }


# =============================================================================
# Saved Searches
# =============================================================================

from typing import List  # noqa: E402

from fichero.models import SavedSearch  # noqa: E402


class SavedSearchCreate(BaseModel):
    """Request to save a search."""

    query: str
    is_smart_search: bool = True
    filters: Optional[dict] = None
    search_type: str = "hybrid"
    sort_by: str = "relevance"
    sort_direction: str = "desc"  # "asc" or "desc"
    folder_path: str = "/"  # Organization folder
    sort_order: int = 0  # Position within folder


class SavedSearchResponse(BaseModel):
    """Saved search response."""

    id: str
    query: str
    is_smart_search: bool
    filters: Optional[dict]
    search_type: str
    sort_by: str
    sort_direction: str  # "asc" or "desc"
    folder_path: str
    sort_order: int  # Position within folder
    created_at: str


@router.post("/saved")
async def save_search(
    request: SavedSearchCreate, db: Database = Depends(get_library_database)
) -> SavedSearchResponse:
    """Save a search for later."""
    saved = SavedSearch(
        query=request.query,
        is_smart_search=request.is_smart_search,
        filters=request.filters,
        search_type=request.search_type,
        sort_by=request.sort_by,
        sort_direction=request.sort_direction,
        folder_path=request.folder_path,
        sort_order=request.sort_order,
    )
    db.save(saved)

    return SavedSearchResponse(
        id=saved.id,
        query=saved.query,
        is_smart_search=saved.is_smart_search,
        filters=saved.filters,
        search_type=saved.search_type,
        sort_by=saved.sort_by,
        sort_direction=saved.sort_direction,
        folder_path=saved.folder_path,
        sort_order=saved.sort_order,
        created_at=_safe_isoformat(getattr(saved, "created_at", None)),
    )


@router.get("/saved")
async def list_saved_searches(
    db: Database = Depends(get_library_database),
) -> List[SavedSearchResponse]:
    """List all saved searches."""
    searches = db.all(SavedSearch)
    return [
        SavedSearchResponse(
            id=s.id,
            query=s.query,
            is_smart_search=s.is_smart_search,
            filters=s.filters,
            search_type=s.search_type,
            sort_by=s.sort_by,
            sort_direction=s.sort_direction,
            folder_path=s.folder_path,
            sort_order=s.sort_order,
            created_at=_safe_isoformat(getattr(s, "created_at", None)),
        )
        for s in searches
    ]


class SavedSearchUpdate(BaseModel):
    """Request to update saved search properties."""

    query: Optional[str] = None
    is_smart_search: Optional[bool] = None
    filters: Optional[dict] = None
    search_type: Optional[str] = None
    sort_by: Optional[str] = None
    sort_direction: Optional[str] = None  # "asc" or "desc"
    folder_path: Optional[str] = None

    model_config = {"extra": "allow"}


@router.put("/saved/{search_id}")
async def update_saved_search(
    search_id: str,
    request: SavedSearchUpdate,
    db: Database = Depends(get_library_database),
) -> SavedSearchResponse:
    """Update a saved search."""
    saved = db.get(SavedSearch, search_id)
    if not saved:
        raise HTTPException(status_code=404, detail="Saved search not found")

    # Update fields
    if request.query is not None:
        saved.query = request.query
    if request.is_smart_search is not None:
        saved.is_smart_search = request.is_smart_search
    if request.filters is not None:
        saved.filters = request.filters
    if request.search_type is not None:
        saved.search_type = request.search_type
    if request.sort_by is not None:
        saved.sort_by = request.sort_by
    if request.sort_direction is not None:
        saved.sort_direction = request.sort_direction
    if request.folder_path is not None:
        saved.folder_path = request.folder_path

    saved.updated_at = datetime.now()
    db.save(saved)

    return SavedSearchResponse(
        id=saved.id,
        query=saved.query,
        is_smart_search=saved.is_smart_search,
        filters=saved.filters,
        search_type=saved.search_type,
        sort_by=saved.sort_by,
        sort_direction=saved.sort_direction,
        folder_path=saved.folder_path,
        sort_order=saved.sort_order,
        created_at=_safe_isoformat(getattr(saved, "created_at", None)),
    )


@router.post("/saved/{search_id}/duplicate")
async def duplicate_saved_search(
    search_id: str, db: Database = Depends(get_library_database)
) -> SavedSearchResponse:
    """Duplicate a saved search with a new name."""
    original = db.get(SavedSearch, search_id)
    if not original:
        raise HTTPException(status_code=404, detail="Saved search not found")

    # Create a new saved search with same properties but different ID and modified name
    new_saved = SavedSearch(
        query=original.query,
        is_smart_search=original.is_smart_search,
        filters=original.filters,
        search_type=original.search_type,
        sort_by=original.sort_by,
        sort_direction=original.sort_direction,
        folder_path=original.folder_path,
        sort_order=original.sort_order,
    )

    # The database layer will generate a new ID
    db.save(new_saved)

    return SavedSearchResponse(
        id=new_saved.id,
        query=new_saved.query,
        is_smart_search=new_saved.is_smart_search,
        filters=new_saved.filters,
        search_type=new_saved.search_type,
        sort_by=new_saved.sort_by,
        sort_direction=new_saved.sort_direction,
        folder_path=new_saved.folder_path,
        sort_order=new_saved.sort_order,
        created_at=_safe_isoformat(getattr(new_saved, "created_at", None)),
    )


@router.delete("/saved/{search_id}")
async def delete_saved_search(
    search_id: str, db: Database = Depends(get_library_database)
):
    """Delete a saved search."""
    saved = db.get(SavedSearch, search_id)
    if not saved:
        raise HTTPException(status_code=404, detail="Saved search not found")

    db.delete(saved)
    return {"status": "deleted"}


@router.post("/saved/reorder")
async def reorder_saved_searches(
    search_ids: list[str],
    folder_path: str = "/",
    db: Database = Depends(get_library_database),
) -> dict:
    """Reorder saved searches within a folder."""
    # Update sort_order for each saved search
    for i, search_id in enumerate(search_ids):
        saved = db.get(SavedSearch, search_id)
        if not saved:
            raise HTTPException(
                status_code=404, detail=f"Saved search not found: {search_id}"
            )

        # Update sort order
        saved.sort_order = i
        db.save(saved)

    return {"status": "reordered", "count": len(search_ids)}
