"""
Search Routes

Semantic search using LanceDB vector embeddings.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel

from fichero.db import db, SearchResult

logger = logging.getLogger(__name__)
router = APIRouter()


# Request/Response models
class SearchRequest(BaseModel):
    """Request model for semantic search."""
    query: str
    limit: int = 10
    min_score: float = 0.0


class SearchResponse(BaseModel):
    """Response model for search results."""
    query: str
    results: list[SearchResult]
    count: int


class ReindexResponse(BaseModel):
    """Response for reindex operation."""
    status: str
    indexed: int


# Routes

@router.post("")
async def semantic_search(request: SearchRequest) -> SearchResponse:
    """
    Perform semantic search over documents.

    Uses LanceDB vector similarity to find relevant documents.
    """
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    results = db.search(
        query=request.query,
        limit=request.limit,
        min_score=request.min_score,
    )

    return SearchResponse(
        query=request.query,
        results=results,
        count=len(results),
    )


@router.get("/stats")
async def search_stats():
    """Get embedding/search statistics."""
    return db.embedding_stats()


@router.post("/reindex")
async def reindex_all(background_tasks: BackgroundTasks):
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
async def embed_document(doc_id: str):
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

from datetime import datetime
from typing import List

from fichero.models import SavedSearch


class SavedSearchCreate(BaseModel):
    """Request to save a search."""
    query: str
    is_smart_search: bool = True
    filters: Optional[dict] = None


class SavedSearchResponse(BaseModel):
    """Saved search response."""
    id: str
    query: str
    is_smart_search: bool
    filters: Optional[dict]
    created_at: str


@router.post("/saved")
async def save_search(request: SavedSearchCreate) -> SavedSearchResponse:
    """Save a search for later."""
    saved = SavedSearch(
        query=request.query,
        is_smart_search=request.is_smart_search,
        filters=request.filters,
    )
    db.save(saved)

    return SavedSearchResponse(
        id=saved.id,
        query=saved.query,
        is_smart_search=saved.is_smart_search,
        filters=saved.filters,
        created_at=saved.created_at.isoformat(),
    )


@router.get("/saved")
async def list_saved_searches() -> List[SavedSearchResponse]:
    """List all saved searches."""
    searches = db.all(SavedSearch)
    return [
        SavedSearchResponse(
            id=s.id,
            query=s.query,
            is_smart_search=s.is_smart_search,
            filters=s.filters,
            created_at=s.created_at.isoformat(),
        )
        for s in searches
    ]


@router.delete("/saved/{search_id}")
async def delete_saved_search(search_id: str):
    """Delete a saved search."""
    saved = db.get(SavedSearch, search_id)
    if not saved:
        raise HTTPException(status_code=404, detail="Saved search not found")

    db.delete(saved)
    return {"status": "deleted"}
