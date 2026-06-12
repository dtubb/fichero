"""Search Explanation API Routes

Provides search explanation, metrics, and RAG mode controls for
transparent search operations and RAG pipeline visibility.
"""

from __future__ import annotations

import logging
import time
from collections import Counter
from datetime import datetime
from enum import Enum
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from fichero.api.main import get_library_database
from fichero.db import Database, _fold_for_search
from fichero.knowledge_models import KnowledgeClaim
from fichero.models import Document

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/search", tags=["search-explain"])


# =============================================================================
# Enums and Types
# =============================================================================


class RAGMode(str, Enum):
    """RAG search modes with different precision/recall tradeoffs."""

    CONSERVATIVE = "conservative"  # High precision, low hallucination risk
    BALANCED = "balanced"  # Default: good balance
    SPECULATIVE = "speculative"  # High recall, more context included


class SearchType(str, Enum):
    """Types of search performed."""

    SEMANTIC = "semantic"
    FULLTEXT = "fulltext"
    HYBRID = "hybrid"


# =============================================================================
# Request/Response Models
# =============================================================================


class SearchExplainRequest(BaseModel):
    """Request to explain a search query."""

    query: str = Field(..., description="Search query to explain", min_length=1)
    search_type: SearchType = Field(default=SearchType.HYBRID, description="Type of search")
    rag_mode: RAGMode = Field(default=RAGMode.BALANCED, description="RAG mode setting")
    limit: int = Field(default=10, ge=1, le=100)
    show_scores: bool = Field(default=True, description="Include relevance scores")


class SourceAttribution(BaseModel):
    """Attribution for a single source in search results."""

    source_id: str
    source_type: str  # "document", "claim"
    title: str
    excerpt: str | None
    relevance_score: float
    match_type: str  # "semantic", "keyword", "hybrid"
    position: int  # Rank in results


class SearchMetrics(BaseModel):
    """Metrics for a search operation."""

    total_candidates: int
    filtered_results: int
    precision_estimate: float  # Estimated precision based on top-k scores
    recall_estimate: float | None
    avg_relevance_score: float
    min_relevance_score: float
    max_relevance_score: float
    token_estimate: int  # Estimated tokens for RAG context
    execution_time_ms: float


class SearchExplanation(BaseModel):
    """Complete search explanation with attribution and metrics."""

    query: str
    search_type: str
    rag_mode: str
    explanation: str  # Human-readable explanation
    sources: list[SourceAttribution]
    metrics: SearchMetrics
    suggested_refinements: list[str]
    filters_applied: dict[str, Any] | None = None


class RAGModeConfig(BaseModel):
    """Configuration for a RAG mode."""

    mode: RAGMode
    name: str
    description: str
    min_score_threshold: float
    max_results: int
    context_window_ratio: float  # How much context to include
    enable_hybrid: bool


class RAGModesResponse(BaseModel):
    """Response listing available RAG modes."""

    modes: list[RAGModeConfig]
    current_default: RAGMode


class SearchMetricsSummary(BaseModel):
    """Summary of search system metrics."""

    total_searches: int
    avg_execution_time_ms: float
    avg_results_returned: float
    top_sources: list[dict[str, Any]]  # Most frequently returned sources
    popular_queries: list[str]
    rag_usage_by_mode: dict[str, int]  # Count by RAG mode
    timestamp: str


# =============================================================================
# Search Explanation Logic
# =============================================================================


def _generate_explanation(
    query: str, search_type: SearchType, rag_mode: RAGMode, result_count: int
) -> str:
    """Generate a human-readable explanation of the search."""
    explanations = []

    # Base explanation
    explanations.append(f"Searched for: '{query}'")

    # Search type
    type_desc = {
        SearchType.SEMANTIC: "using semantic similarity (meaning-based matching)",
        SearchType.FULLTEXT: "using keyword matching",
        SearchType.HYBRID: "using hybrid search (semantic + keyword)",
    }
    explanations.append(f"Search method: {type_desc[search_type]}")

    # RAG mode explanation
    mode_desc = {
        RAGMode.CONSERVATIVE: (
            "Conservative mode: High precision with strict relevance thresholds. "
            "Results must strongly match the query meaning."
        ),
        RAGMode.BALANCED: (
            "Balanced mode: Good trade-off between finding relevant content "
            "and avoiding irrelevant matches."
        ),
        RAGMode.SPECULATIVE: (
            "Speculative mode: Higher recall with broader context inclusion. "
            "May include tangentially related content."
        ),
    }
    explanations.append(mode_desc[rag_mode])

    # Results summary
    if result_count == 0:
        explanations.append("No results found. Consider broadening your query.")
    elif result_count < 3:
        explanations.append(
            f"Found {result_count} relevant result(s). "
            "Results are highly relevant to your query."
        )
    else:
        explanations.append(
            f"Found {result_count} relevant results, "
            "ranked by relevance to your query."
        )

    return " ".join(explanations)


def _calculate_metrics(results: list[dict], query_time_ms: float) -> SearchMetrics:
    """Calculate search metrics from results."""
    if not results:
        return SearchMetrics(
            total_candidates=0,
            filtered_results=0,
            precision_estimate=0.0,
            recall_estimate=None,
            avg_relevance_score=0.0,
            min_relevance_score=0.0,
            max_relevance_score=0.0,
            token_estimate=0,
            execution_time_ms=query_time_ms,
        )

    scores = [r.get("relevance_score", 0.0) for r in results]

    # Estimate tokens (rough approximation)
    token_estimate = sum(len(r.get("text", "")) for r in results) // 4

    # Precision estimate based on score distribution
    high_confidence = sum(1 for s in scores if s > 0.7)
    precision_estimate = high_confidence / len(scores) if scores else 0.0

    return SearchMetrics(
        total_candidates=len(results) * 3,  # Rough estimate
        filtered_results=len(results),
        precision_estimate=precision_estimate,
        recall_estimate=None,  # Requires ground truth
        avg_relevance_score=sum(scores) / len(scores),
        min_relevance_score=min(scores),
        max_relevance_score=max(scores),
        token_estimate=token_estimate,
        execution_time_ms=query_time_ms,
    )


def _suggest_refinements(query: str, result_count: int) -> list[str]:
    """Suggest query refinements if needed."""
    suggestions = []

    if result_count == 0:
        suggestions.append(f"Try broadening: remove specific terms from '{query}'")
        suggestions.append("Try synonyms: use alternative words for key concepts")
    elif result_count > 50:
        suggestions.append("Add more specific terms to narrow results")
        suggestions.append("Use exact phrases with quotes for precise matching")

    if len(query.split()) < 3:
        suggestions.append("Add more context: include additional relevant terms")

    return suggestions


# =============================================================================
# RAG Mode Configurations
# =============================================================================


RAG_MODE_CONFIGS: dict[RAGMode, RAGModeConfig] = {
    RAGMode.CONSERVATIVE: RAGModeConfig(
        mode=RAGMode.CONSERVATIVE,
        name="Conservative",
        description="High precision, low hallucination risk. Only highly relevant content included.",
        min_score_threshold=0.8,
        max_results=5,
        context_window_ratio=0.3,
        enable_hybrid=False,
    ),
    RAGMode.BALANCED: RAGModeConfig(
        mode=RAGMode.BALANCED,
        name="Balanced",
        description="Good balance between precision and recall. Recommended for most queries.",
        min_score_threshold=0.5,
        max_results=10,
        context_window_ratio=0.5,
        enable_hybrid=True,
    ),
    RAGMode.SPECULATIVE: RAGModeConfig(
        mode=RAGMode.SPECULATIVE,
        name="Speculative",
        description="Higher recall with broader context. May include tangentially related content.",
        min_score_threshold=0.3,
        max_results=20,
        context_window_ratio=0.8,
        enable_hybrid=True,
    ),
}


# =============================================================================
# API Endpoints
# =============================================================================


@router.post(
    "/explain",
    response_model=SearchExplanation,
    summary="Explain a search query",
    description="Returns detailed explanation of why results were matched, with source attribution.",
)
async def explain_search(
    request: SearchExplainRequest,
    db: Database = Depends(get_library_database),
) -> SearchExplanation:
    """Generate explanation for a search query with full attribution."""
    start_time = time.time()

    # Get RAG mode config
    rag_config = RAG_MODE_CONFIGS.get(request.rag_mode, RAG_MODE_CONFIGS[RAGMode.BALANCED])

    try:
        # Perform search based on type
        if request.search_type == SearchType.SEMANTIC:
            results = await _semantic_search(db, request.query, rag_config)
        elif request.search_type == SearchType.FULLTEXT:
            results = await _fulltext_search(db, request.query, rag_config)
        else:  # HYBRID
            semantic_results = await _semantic_search(db, request.query, rag_config)
            fulltext_results = await _fulltext_search(db, request.query, rag_config)
            results = _merge_results(semantic_results, fulltext_results)

    except Exception as e:
        logger.exception(f"Search explanation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

    execution_time_ms = (time.time() - start_time) * 1000

    # Build source attributions
    sources = [
        SourceAttribution(
            source_id=r["id"],
            source_type=r.get("source_type", "document"),
            title=r.get("title", "Untitled"),
            excerpt=r.get("text", "")[:200] + "..." if len(r.get("text", "")) > 200 else r.get("text"),
            relevance_score=r.get("relevance_score", 0.0),
            match_type=r.get("match_type", "semantic"),
            position=i + 1,
        )
        for i, r in enumerate(results[: request.limit])
    ]

    # Calculate metrics
    metrics = _calculate_metrics(results, execution_time_ms)

    # Generate explanation
    explanation = _generate_explanation(
        request.query, request.search_type, request.rag_mode, len(sources)
    )

    # Suggest refinements
    refinements = _suggest_refinements(request.query, len(sources))

    return SearchExplanation(
        query=request.query,
        search_type=request.search_type.value,
        rag_mode=request.rag_mode.value,
        explanation=explanation,
        sources=sources,
        metrics=metrics,
        suggested_refinements=refinements,
    )


@router.get(
    "/explain/{query}",
    response_model=SearchExplanation,
    summary="Explain search by path",
    description="Get search explanation using URL path (GET alternative to POST /explain).",
)
async def explain_search_path(
    query: str,
    search_type: SearchType = Query(default=SearchType.HYBRID),
    rag_mode: RAGMode = Query(default=RAGMode.BALANCED),
    limit: int = Query(default=10, ge=1, le=100),
    db: Database = Depends(get_library_database),
) -> SearchExplanation:
    """Explain search via GET request."""
    request = SearchExplainRequest(
        query=query,
        search_type=search_type,
        rag_mode=rag_mode,
        limit=limit,
    )
    return await explain_search(request, db)


@router.get(
    "/modes",
    response_model=RAGModesResponse,
    summary="List RAG modes",
    description="Get available RAG modes with their configurations.",
)
async def list_rag_modes() -> RAGModesResponse:
    """List all available RAG modes."""
    return RAGModesResponse(
        modes=list(RAG_MODE_CONFIGS.values()),
        current_default=RAGMode.BALANCED,
    )


@router.get(
    "/metrics",
    response_model=SearchMetricsSummary,
    summary="Get search metrics",
    description="Returns aggregated search metrics and usage statistics.",
)
async def get_search_metrics(
    db: Database = Depends(get_library_database),
) -> SearchMetricsSummary:
    """Get search system metrics."""
    # In a real implementation, this would query a metrics store
    # For now, return placeholder metrics based on available data

    documents = db.all(Document)
    claims = db.all(KnowledgeClaim)

    # Estimate top sources (most frequently referenced)
    top_sources = []
    if claims:
        doc_refs = Counter(
            c.source_document_id for c in claims if c.source_document_id
        )
        top_doc_ids = [doc_id for doc_id, _ in doc_refs.most_common(5)]

        for doc_id in top_doc_ids:
            doc = db.get(Document, doc_id)
            if doc:
                top_sources.append(
                    {
                        "id": doc_id,
                        "title": doc.title if hasattr(doc, "title") else "Untitled",
                        "reference_count": doc_refs[doc_id],
                    }
                )

    return SearchMetricsSummary(
        total_searches=0,  # Would come from metrics store
        avg_execution_time_ms=0.0,
        avg_results_returned=float(len(documents)) if documents else 0.0,
        top_sources=top_sources,
        popular_queries=[],
        rag_usage_by_mode={"conservative": 0, "balanced": 0, "speculative": 0},
        timestamp=datetime.now().isoformat(),
    )


# =============================================================================
# Helper Functions
# =============================================================================


async def _semantic_search(
    db: Database, query: str, config: RAGModeConfig
) -> list[dict[str, Any]]:
    """Perform semantic search."""
    try:
        results, _, _ = db.search(
            query=query,
            limit=config.max_results,
            min_score=config.min_score_threshold,
            search_type="semantic",
            highlight_results=False,
        )
        return [
            {
                "id": r.document_id,
                "title": (r.metadata or {}).get("name", "Untitled"),
                "text": r.content_preview or "",
                "relevance_score": r.score,
                "source_type": "document",
                "match_type": "semantic",
            }
            for r in results
            if r.score >= config.min_score_threshold
        ]
    except Exception as e:
        logger.warning(f"Semantic search failed: {e}")
        return []


async def _fulltext_search(
    db: Database, query: str, config: RAGModeConfig
) -> list[dict[str, Any]]:
    """Perform full-text search."""
    try:
        # Simple keyword search across documents using folded text.
        documents = db.all(Document)
        query_folded = _fold_for_search(query)

        results = []
        for doc in documents:
            score = 0.0
            text = getattr(doc, "page_content", "") or ""
            title = getattr(doc, "name", "") or ""
            title_folded = _fold_for_search(title)
            text_folded = _fold_for_search(text)

            if query_folded in title_folded:
                score += 0.5
            if query_folded in text_folded:
                score += 0.3

            if score >= config.min_score_threshold * 0.5:  # Lower threshold for keyword
                results.append(
                    {
                        "id": doc.id,
                        "title": title or "Untitled",
                        "text": text[:500] if text else "",
                        "relevance_score": score,
                        "source_type": "document",
                        "match_type": "keyword",
                    }
                )

        return sorted(results, key=lambda x: x["relevance_score"], reverse=True)[
            : config.max_results
        ]
    except Exception as e:
        logger.warning(f"Full-text search failed: {e}")
        return []


def _merge_results(
    semantic: list[dict[str, Any]], fulltext: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Merge semantic and full-text results, deduplicating by ID."""
    seen_ids = set()
    merged = []

    # Interleave results, prioritizing semantic
    max_len = max(len(semantic), len(fulltext))
    for i in range(max_len):
        if i < len(semantic):
            r = semantic[i]
            if r["id"] not in seen_ids:
                seen_ids.add(r["id"])
                merged.append(r)

        if i < len(fulltext):
            r = fulltext[i]
            if r["id"] not in seen_ids:
                seen_ids.add(r["id"])
                r["match_type"] = "hybrid"  # Mark as hybrid match
                merged.append(r)

    return merged
