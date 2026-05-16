"""
Search Routes

Semantic search using LanceDB vector embeddings.
"""

import logging
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from fichero.api.main import get_library_database
from fichero.search.query_parser import parse_query
from fichero.db import Database, SearchResult
from fichero.models import Document, SavedSearch

logger = logging.getLogger(__name__)
router = APIRouter()


def _safe_isoformat(value) -> str:
    """Return ISO string when value behaves like datetime, else now."""
    return (
        value.isoformat() if hasattr(value, "isoformat") else datetime.now().isoformat()
    )


def _suggest_for_no_results(
    db: Database, query: str, limit: int = 5
) -> list[str]:
    """Build 'did you mean…?' suggestions when search returns nothing.

    Strategy: scan distinct entity names (people / places / orgs /
    keywords) from the artifacts table, fold each for accent-blind
    comparison, score by Levenshtein-ish closeness against the folded
    query, return the top-K closest.

    Cheap: only runs on the zero-results path so latency hit is bounded
    to the rare 'user typed a typo' case. Caller is responsible for
    surfacing the suggestions in SearchResponse.suggestions.
    """
    from fichero.db import _fold_for_search

    needle = _fold_for_search(query.strip())
    if not needle:
        return []

    try:
        rows = db.conn.execute(
            """
            SELECT data FROM artifacts
            WHERE artifact_type IN ('people', 'places', 'organizations', 'keywords')
            """,
        ).fetchall()
    except Exception as exc:  # noqa: BLE001
        logger.warning("did-you-mean lookup failed: %s", exc)
        return []

    candidates: set[str] = set()
    for (data_blob,) in rows:
        if not data_blob:
            continue
        # data is JSON-serialised; parse defensively.
        import json

        try:
            parsed = json.loads(data_blob) if isinstance(data_blob, str) else data_blob
        except (TypeError, ValueError):
            continue
        if isinstance(parsed, dict):
            items = parsed.get("items")
            if isinstance(items, list):
                for entry in items:
                    if isinstance(entry, dict):
                        for value in entry.values():
                            if isinstance(value, str) and value:
                                candidates.add(value)
            keywords = parsed.get("keywords")
            if isinstance(keywords, list):
                for kw in keywords:
                    if isinstance(kw, str) and kw:
                        candidates.add(kw)

    # Score each candidate by best-of (substring containment, per-word
    # substring containment, character-set overlap). Multi-word entity
    # names like "Joseph Antonio Asprilla" need per-word matching so a
    # 1-token typo like "Aspriya" still surfaces — just checking the
    # whole name against the typo gives diluted scores. No Levenshtein
    # to keep the dependency surface flat.
    scored: list[tuple[float, str]] = []
    for name in candidates:
        folded = _fold_for_search(name)
        if not folded:
            continue
        if needle in folded or folded in needle:
            similarity = 1.0 - abs(len(folded) - len(needle)) / max(len(folded), len(needle))
        else:
            # Per-word containment: best score across each whitespace
            # token in the candidate. Helps "Aspriya" match "Joseph
            # Antonio Asprilla" via the 'asprilla' token.
            best_word = 0.0
            for word in folded.split():
                if needle in word or word in needle:
                    best_word = max(
                        best_word,
                        1.0 - abs(len(word) - len(needle)) / max(len(word), len(needle)),
                    )
                else:
                    common = set(needle) & set(word)
                    overlap = len(common) / max(len(set(needle) | set(word)), 1)
                    # Bonus for sharing a leading char — typos usually
                    # preserve the first letter.
                    if word and needle and word[0] == needle[0]:
                        overlap += 0.1
                    best_word = max(best_word, overlap)
            similarity = best_word
        scored.append((similarity, name))

    scored.sort(reverse=True)
    return [name for score, name in scored[:limit] if score >= 0.5]


def _apply_filename_boost(results, query: str):
    """Promote results whose document name matches the query.

    Filename matches signal strong user intent — when the user types a
    filename slug ('tubb2020shift') they want THAT doc first, not
    whichever doc has the most semantically similar body. We re-score
    in priority bands:

      +10.0  exact match (case-insensitive, sans extension)
       +5.0  whole-word match within the name
       +2.0  substring match anywhere in the name

    Highest boost wins per row; original score is preserved as a
    secondary sort key so within a band the retriever's ranking still
    matters. (#886)
    """
    import re as _re

    query_lower = query.strip().lower()
    if not query_lower:
        return results
    # Strip common file extensions for the exact-match comparison so
    # 'tubb2020shift' matches 'tubb2020shift.pdf'.
    def _stem(name: str) -> str:
        out = name.lower()
        for ext in (".pdf", ".docx", ".txt", ".md", ".html", ".epub"):
            if out.endswith(ext):
                return out[: -len(ext)]
        return out

    # Tokenise on whitespace + punctuation so "tubb 2020 shift" matches
    # "tubb2020shift.pdf" via word-boundary checks.
    query_words = [w for w in _re.findall(r"\w+", query_lower) if w]

    def _boost(result_name: str) -> float:
        if not result_name:
            return 0.0
        name_lower = result_name.lower()
        name_stem = _stem(name_lower)
        if name_stem == query_lower or name_lower == query_lower:
            return 10.0
        # Whole-word match: every query word appears as its own word in
        # the name (split on non-alphanumerics).
        name_words = set(_re.findall(r"\w+", name_lower))
        if query_words and all(w in name_words for w in query_words):
            return 5.0
        # Substring fallback.
        if query_lower in name_lower:
            return 2.0
        return 0.0

    def _name_of(result) -> str:
        meta = getattr(result, "metadata", None) or {}
        return str(meta.get("name") or "")

    decorated = [
        (_boost(_name_of(r)), getattr(r, "score", 0.0) or 0.0, r)
        for r in results
    ]
    decorated.sort(key=lambda t: (-t[0], -t[1]))
    return [t[2] for t in decorated]


def _apply_phrase_and_exclude_filters(
    db: Database,
    results: list[SearchResult],
    phrases: list[str],
    excludes: list[str],
) -> list[SearchResult]:
    """Drop docs that don't satisfy required phrases or that contain an
    excluded term. Looks up the doc's full page_content from DuckDB
    (the result.content_preview is truncated to 200 chars and may not
    reach a phrase match in the body).
    """
    if not phrases and not excludes:
        return results

    from fichero.db import _fold_for_search

    folded_phrases = [_fold_for_search(p) for p in phrases]
    folded_excludes = [_fold_for_search(e) for e in excludes]

    out: list[SearchResult] = []
    for r in results:
        try:
            row = db.conn.execute(
                "SELECT page_content FROM documents WHERE id = $id", {"id": r.document_id}
            ).fetchone()
            content = (row[0] or "") if row else ""
        except Exception:
            content = r.content_preview or ""
        folded = _fold_for_search(content)

        if any(p not in folded for p in folded_phrases):
            continue
        if any(e in folded for e in folded_excludes):
            continue
        out.append(r)
    return out


_ALL_ENTITY_TYPES: tuple[str, ...] = (
    "people",
    "places",
    "organizations",
    "dates",
    "events",
    "keywords",
)


def _entity_match_results(
    db: Database,
    query: str,
    limit: int,
    exclude_doc_ids: set[str],
    entity_types: tuple[str, ...] = _ALL_ENTITY_TYPES,
) -> list[SearchResult]:
    """Find documents whose extracted entity artifacts contain `query`.

    Catches the case where a name (e.g. 'Asprilla') was extracted by the
    catalogue/extract_all workflow into an artifact's typed JSON but
    never appeared in the document's page_content (image-only PDFs,
    handwritten notes). (#481 / B4)

    Pass `entity_types` to scope the search (e.g. `("people",)` for a
    `people:Asprilla` query). Defaults to all six types when the caller
    doesn't care.

    DuckDB's `LIKE` over the JSON-serialised `data` column is enough for
    sub-string match across the typed shapes ({"items": [{"name": ...}]}
    for people/places/orgs, {"keywords": [...]} for keywords, dates,
    events). Case-insensitive.
    """
    if not query.strip() or not entity_types:
        return []
    needle = f"%{query.strip().lower()}%"
    placeholders = ",".join(f"$t{i}" for i in range(len(entity_types)))
    params: dict[str, object] = {"needle": needle, "limit": limit}
    for i, t in enumerate(entity_types):
        params[f"t{i}"] = t
    try:
        rows = db.conn.execute(
            f"""
            SELECT DISTINCT a.document_id, d.name, d.doc_type, d.file_type
            FROM artifacts a
            JOIN documents d ON d.id = a.document_id
            WHERE a.artifact_type IN ({placeholders})
              AND lower(CAST(a.data AS VARCHAR)) LIKE $needle
            LIMIT $limit
            """,
            params,
        ).fetchall()
    except Exception as exc:  # noqa: BLE001
        logger.warning("entity-match search failed: %s", exc)
        return []

    out: list[SearchResult] = []
    for doc_id, name, doc_type, file_type in rows:
        if doc_id in exclude_doc_ids:
            continue
        out.append(
            SearchResult(
                document_id=doc_id,
                score=0.5,  # Below semantic top-1 (1.0), above no-content (0.0025)
                content_preview=f"Entity match for '{query}'",
                metadata={
                    "name": name,
                    "doc_type": doc_type,
                    "file_type": file_type,
                    "match_source": "entity",
                },
                highlights=[],
            )
        )
    return out


# Request/Response models
class SearchRequest(BaseModel):
    """Request model for enhanced search."""

    query: str
    limit: int = 10
    # 0.3 cosine ≈ "loosely related" floor; below that are usually
    # incidental matches across an embedding space. Callers wanting
    # everything can pass 0.0; callers wanting tight matches can pass
    # 0.5+. Applies to semantic results only.
    min_score: float = 0.3

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


class ReindexStartedResponse(BaseModel):
    status: str
    message: str


class EmbedDocumentResponse(BaseModel):
    document_id: str
    embedded: bool


class DeletedResponse(BaseModel):
    status: str


class ReorderResponse(BaseModel):
    status: str
    count: int


# Routes


@router.post("")
async def enhanced_search(
    request: SearchRequest, db: Database = Depends(get_library_database)
) -> SearchResponse:
    """
    Perform enhanced search over documents.

    Supports hybrid search (semantic + full-text), advanced filtering, sorting, and pagination.
    Empty query is allowed: returns the most-recently-updated docs as a
    "browse the index" affordance — better UX than 400-on-empty.
    """
    if not request.query.strip():
        # Empty-query → recent documents. Lets the search pane double
        # as a "show me what's indexed" view instead of dead-empty.
        try:
            rows = db.conn.execute(
                """
                SELECT d.id, d.name, d.doc_type, d.file_type, d.updated_at, d.page_content
                FROM documents d
                WHERE d.page_content IS NOT NULL AND length(d.page_content) > 0
                ORDER BY d.updated_at DESC
                LIMIT $limit
                """,
                {"limit": request.limit},
            ).fetchall()
        except Exception:
            rows = []
        recents = [
            SearchResult(
                document_id=row[0],
                score=0.0,
                content_preview=(row[5] or "")[:200],
                metadata={
                    "name": row[1],
                    "doc_type": row[2],
                    "file_type": row[3],
                    "updated_at": _safe_isoformat(row[4]),
                    "match_source": "recent",
                },
                highlights=[],
            )
            for row in rows
        ]
        return SearchResponse(
            query="",
            results=recents,
            count=len(recents),
            total_results=len(recents),
            search_type="recent",
            execution_time_ms=0.0,
            has_more=False,
            filters_applied=None,
            suggestions=None,
        )

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

    # Parse query into a plan (quoted phrases / field scopes /
    # NOT exclusions / plain free-text). The retriever still consumes
    # a plain query string — we feed it the free-text portion, then
    # post-filter for phrases + excludes and union-in entity scopes.
    plan = parse_query(request.query)
    retrieval_query = plan.free_text or " ".join(plan.phrases) or request.query

    # Pure scope queries (e.g. `people:Asprilla` alone) skip the
    # text retriever entirely — answers are 100% from the entity bridge.
    skip_retriever = plan.has_entity_scope and not plan.has_freetext_intent

    # Perform enhanced search
    if skip_retriever:
        results, total_count, search_stats = (
            [],
            0,
            {"search_type": request.search_type, "execution_time_ms": 0.0, "filters_applied": {}},
        )
    else:
        results, total_count, search_stats = db.search(
            query=retrieval_query,
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

    # Apply NOT exclusions and required phrases. Both operate on the
    # post-retrieval result set — cheaper than rebuilding the index for
    # exotic queries and keeps the retrievers simple. The phrase filter
    # MUST run when there's a phrase even if there's only one — semantic
    # retrieval finds neighbours that don't contain the phrase verbatim
    # (e.g. another doc about Leidy without 'sluice wedged' literally).
    if plan.excludes or plan.phrases:
        results = _apply_phrase_and_exclude_filters(
            db, results, phrases=plan.phrases, excludes=plan.excludes
        )
        total_count = len(results)

    # Entity-name bridge: also match the query against extracted entity
    # artifacts. When the user typed an explicit scope (e.g. `people:Asprilla`)
    # we restrict to that entity_type. Otherwise we fall back to scanning
    # all entity types, which is what makes clicking a blue lozenge
    # always return the doc the lozenge came from. (#481 / B4)
    bridge_run = (
        request.search_type in ("hybrid", "fulltext") or skip_retriever
    )
    if bridge_run:
        seen_ids = {r.document_id for r in results}
        slots_remaining = max(0, request.limit - len(results))
        if slots_remaining > 0:
            entity_hits: list[SearchResult] = []
            if plan.has_entity_scope:
                # Scoped: emit one batch per (type, value) and dedupe.
                for entity_type, values in plan.scopes.items():
                    for value in values:
                        hits = _entity_match_results(
                            db,
                            query=value,
                            limit=slots_remaining,
                            exclude_doc_ids=seen_ids,
                            entity_types=(entity_type,),
                        )
                        for hit in hits:
                            seen_ids.add(hit.document_id)
                        entity_hits.extend(hits)
            else:
                entity_hits = _entity_match_results(
                    db,
                    query=request.query,
                    limit=slots_remaining,
                    exclude_doc_ids=seen_ids,
                )
            if entity_hits:
                results = list(results) + entity_hits
                total_count = total_count + len(entity_hits)

    # The noise-floor hack is no longer needed now that embeddings are
    # L2-normalised and scores are real cosine similarities (see
    # db_embeddings._l2_normalize). The user-controllable min_score on
    # SearchRequest replaces it for callers who want to floor explicitly.

    # Filename-match boost (#886). Docs whose name contains the query
    # are promoted to the top of the result list regardless of their
    # semantic / FTS score. Filename matches are the strongest signal
    # of intent — when a user types "tubb2020shift" they want THAT doc
    # first, not the doc with the most semantically similar body.
    # Boost rules:
    #  - exact filename match (case-insensitive, sans extension): +10.0
    #  - whole-word match in filename: +5.0
    #  - any substring match in filename: +2.0
    # Applied to a fresh score column; original score preserved as
    # tiebreaker. Skipped on pure-scope queries (skip_retriever=True)
    # where filename relevance is meaningless.
    if results and not skip_retriever and request.query.strip():
        results = _apply_filename_boost(results, request.query)

    # Did-you-mean: only when the user got *zero* results, AND their
    # query looks substantive (>2 chars). Avoids spamming suggestions on
    # short or accidental queries.
    suggestions: list[str] | None = None
    if not results and len(request.query.strip()) > 2:
        try:
            hits = _suggest_for_no_results(db, request.query, limit=5)
            suggestions = hits or None
        except Exception as exc:  # noqa: BLE001
            logger.warning("did-you-mean failed: %s", exc)

    return SearchResponse(
        query=request.query,
        results=results,
        count=len(results),
        total_results=total_count,
        search_type=search_stats.get("search_type", request.search_type),
        execution_time_ms=search_stats.get("execution_time_ms", 0),
        has_more=search_stats.get("has_more", False),
        filters_applied=request.filters,
        suggestions=suggestions,
    )


@router.get("/stats")
async def search_stats(db: Database = Depends(get_library_database)):
    """Get embedding/search statistics."""
    return db.embedding_stats()


class KeywordCloudEntry(BaseModel):
    """Single entry in the keyword cloud — name + how many docs use it."""

    name: str
    count: int


@router.get("/keywords")
async def keyword_cloud(
    db: Database = Depends(get_library_database),
    limit: int = Query(50, ge=1, le=500),
) -> list[KeywordCloudEntry]:
    """Top-N keywords across the library, sorted by document frequency.

    Reads the 'keywords' artifacts emitted by extract_all and counts the
    distinct documents each keyword appears in. Empty list when no
    keywords have been extracted yet (workflow hasn't run).

    Used by the search empty-state to surface clickable terms — a
    "browse by tag" affordance for users who don't know what to type.
    """
    try:
        rows = db.conn.execute(
            "SELECT data, document_id FROM artifacts WHERE artifact_type = 'keywords'"
        ).fetchall()
    except Exception as exc:  # noqa: BLE001
        logger.warning("keyword cloud query failed: %s", exc)
        return []

    import json
    from collections import Counter

    counter: Counter[str] = Counter()
    for data_blob, doc_id in rows:
        if not data_blob:
            continue
        try:
            parsed = json.loads(data_blob) if isinstance(data_blob, str) else data_blob
        except (TypeError, ValueError):
            continue
        if not isinstance(parsed, dict):
            continue
        keywords = parsed.get("keywords")
        if not isinstance(keywords, list):
            continue
        seen_in_doc: set[str] = set()
        for kw in keywords:
            if not isinstance(kw, str):
                continue
            term = kw.strip()
            if not term:
                continue
            # Document-frequency count: a keyword appearing twice in the
            # same doc still counts once.
            key = (term, doc_id)
            if key in seen_in_doc:
                continue
            seen_in_doc.add(key)
            counter[term] += 1

    return [
        KeywordCloudEntry(name=name, count=count)
        for name, count in counter.most_common(limit)
    ]


@router.post("/reindex")
async def reindex_all(
    background_tasks: BackgroundTasks, db: Database = Depends(get_library_database)
) -> ReindexStartedResponse:
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

    return ReindexStartedResponse(
        status="started",
        message="Reindex started in background. Poll /api/search/stats for progress.",
    )


@router.post("/embed/{doc_id}")
async def embed_document(doc_id: str, db: Database = Depends(get_library_database)) -> EmbedDocumentResponse:
    """Create embedding for a specific document."""
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")

    success = db.embed(doc)

    return EmbedDocumentResponse(document_id=doc_id, embedded=success)


# =============================================================================
# Saved Searches
# =============================================================================


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
) -> list[SavedSearchResponse]:
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

    model_config = ConfigDict(extra="allow")


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
) -> DeletedResponse:
    """Delete a saved search."""
    saved = db.get(SavedSearch, search_id)
    if not saved:
        raise HTTPException(status_code=404, detail="Saved search not found")

    db.delete(saved)
    return DeletedResponse(status="deleted")


@router.post("/saved/reorder")
async def reorder_saved_searches(
    search_ids: list[str],
    folder_path: str = "/",
    db: Database = Depends(get_library_database),
) -> ReorderResponse:
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

    return ReorderResponse(status="reordered", count=len(search_ids))


# =============================================================================
# Search Views API (Issue #434)
# =============================================================================


class SearchViewConfig(BaseModel):
    """Configuration for a search view."""

    id: str
    name: str
    description: str
    view_type: str  # "table", "grid", "map", "timeline"
    default: bool = False
    columns: list[dict[str, Any]] | None = None
    filters: list[dict[str, Any]] | None = None
    sort_options: list[dict[str, Any]] | None = None


class SearchViewsResponse(BaseModel):
    """Response with available search views."""

    views: list[SearchViewConfig]
    default_view: str
    total: int


class TableViewData(BaseModel):
    """Data for table view."""

    columns: list[dict[str, Any]]
    rows: list[dict[str, Any]]
    total: int
    page: int
    page_size: int


class MapMarker(BaseModel):
    """Marker data for map view."""

    id: str
    lat: float
    lng: float
    title: str
    snippet: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MapViewData(BaseModel):
    """Data for map view."""

    markers: list[MapMarker]
    bounds: dict[str, float] | None = None  # sw_lat, sw_lng, ne_lat, ne_lng
    clusters: list[dict[str, Any]] | None = None
    total: int


class GridViewItem(BaseModel):
    """Item for grid view."""

    id: str
    title: str
    thumbnail: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class GridViewData(BaseModel):
    """Data for grid view."""

    items: list[GridViewItem]
    total: int
    page: int
    page_size: int


DEFAULT_VIEWS: list[SearchViewConfig] = [
    SearchViewConfig(
        id="table",
        name="Table",
        description="Tabular view of search results",
        view_type="table",
        default=True,
        columns=[
            {"key": "id", "label": "ID", "sortable": True},
            {"key": "name", "label": "Name", "sortable": True},
            {"key": "doc_type", "label": "Type", "sortable": True},
            {"key": "created_at", "label": "Created", "sortable": True},
            {"key": "relevance_score", "label": "Relevance", "sortable": True},
        ],
    ),
    SearchViewConfig(
        id="grid",
        name="Grid",
        description="Grid card view of search results",
        view_type="grid",
        columns=[
            {"key": "thumbnail", "label": "Preview"},
            {"key": "name", "label": "Name"},
        ],
    ),
    SearchViewConfig(
        id="map",
        name="Map",
        description="Geographic view of search results with location data",
        view_type="map",
    ),
]


@router.get("/views", response_model=SearchViewsResponse)
async def list_search_views(
    db: Database = Depends(get_library_database),
) -> SearchViewsResponse:
    """List available search views and their configurations.

    Returns table, grid, and map view configurations.
    """
    return SearchViewsResponse(
        views=DEFAULT_VIEWS,
        default_view="table",
        total=len(DEFAULT_VIEWS),
    )


@router.get("/views/table", response_model=TableViewData)
async def get_table_view_data(
    query: str = "",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort_by: str = "relevance",
    sort_direction: str = "desc",
    db: Database = Depends(get_library_database),
) -> TableViewData:
    """Get table view data for search results.

    Returns paginated table data with sortable columns.
    """
    # Get all documents
    all_docs = db.all(Document)

    # Filter by query if provided (simplified: name contains)
    if query:
        all_docs = [d for d in all_docs if query.lower() in d.name.lower()]

    # Sort
    if sort_by == "name":
        all_docs.sort(key=lambda d: d.name, reverse=(sort_direction == "desc"))
    elif sort_by == "created_at":
        all_docs.sort(
            key=lambda d: d.created_at.isoformat() if d.created_at else "",
            reverse=(sort_direction == "desc"),
        )
    else:  # relevance or default
        all_docs.sort(key=lambda d: d.name, reverse=(sort_direction == "desc"))

    total = len(all_docs)

    # Paginate
    start = (page - 1) * page_size
    end = start + page_size
    page_docs = all_docs[start:end]

    # Build rows
    rows = []
    for doc in page_docs:
        rows.append({
            "id": doc.id,
            "name": doc.name,
            "doc_type": doc.doc_type.value if doc.doc_type else None,
            "created_at": doc.created_at.isoformat() if doc.created_at else None,
            "relevance_score": 1.0,  # Simplified
            "path": str(doc.path) if doc.path else None,
            "metadata": doc.metadata,
        })

    columns = [
        {"key": "id", "label": "ID", "sortable": True, "type": "string"},
        {"key": "name", "label": "Name", "sortable": True, "type": "string"},
        {"key": "doc_type", "label": "Type", "sortable": True, "type": "string"},
        {"key": "created_at", "label": "Created", "sortable": True, "type": "datetime"},
        {"key": "relevance_score", "label": "Relevance", "sortable": True, "type": "number"},
    ]

    return TableViewData(
        columns=columns,
        rows=rows,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/views/map", response_model=MapViewData)
async def get_map_view_data(
    bounds: str | None = Query(default=None, description="sw_lat,sw_lng,ne_lat,ne_lng"),
    query: str = "",
    limit: int = Query(default=500, ge=1, le=1000),
    db: Database = Depends(get_library_database),
) -> MapViewData:
    """Get map view data with markers.

    Returns geographic markers for documents with location metadata.
    Supports bounds filtering for viewport queries.
    """
    # Parse bounds
    bounds_dict: dict[str, float] | None = None
    if bounds:
        try:
            parts = [float(p) for p in bounds.split(",")]
            if len(parts) == 4:
                bounds_dict = {
                    "sw_lat": parts[0],
                    "sw_lng": parts[1],
                    "ne_lat": parts[2],
                    "ne_lng": parts[3],
                }
        except ValueError:
            pass

    # Get documents with location metadata
    all_docs = db.all(Document)
    markers: list[MapMarker] = []

    for doc in all_docs[:limit]:
        # Check for location in metadata
        location = doc.metadata.get("location") if doc.metadata else None
        lat = None
        lng = None

        if location:
            lat = location.get("lat") if isinstance(location, dict) else None
            lng = location.get("lng") if isinstance(location, dict) else None

        # Fallback: check for lat/lng directly in metadata
        if lat is None and doc.metadata:
            lat = doc.metadata.get("lat")
        if lng is None and doc.metadata:
            lng = doc.metadata.get("lng")

        if lat is not None and lng is not None:
            # Check bounds if provided
            if bounds_dict:
                if not (bounds_dict["sw_lat"] <= lat <= bounds_dict["ne_lat"] and
                        bounds_dict["sw_lng"] <= lng <= bounds_dict["ne_lng"]):
                    continue

            markers.append(
                MapMarker(
                    id=doc.id,
                    lat=float(lat),
                    lng=float(lng),
                    title=doc.name,
                    snippet=doc.description[:100] if doc.description else None,
                    metadata={
                        "doc_type": doc.doc_type.value if doc.doc_type else None,
                        "created_at": doc.created_at.isoformat() if doc.created_at else None,
                    },
                )
            )

    return MapViewData(
        markers=markers,
        bounds=bounds_dict,
        total=len(markers),
    )


@router.get("/views/grid", response_model=GridViewData)
async def get_grid_view_data(
    query: str = "",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Database = Depends(get_library_database),
) -> GridViewData:
    """Get grid view data for search results.

    Returns paginated grid items with thumbnails.
    """
    # Get all documents
    all_docs = db.all(Document)

    # Filter by query
    if query:
        all_docs = [d for d in all_docs if query.lower() in d.name.lower()]

    total = len(all_docs)

    # Paginate
    start = (page - 1) * page_size
    end = start + page_size
    page_docs = all_docs[start:end]

    # Build items
    items = []
    for doc in page_docs:
        thumbnail_path = None
        if hasattr(doc, "thumbnail_path") and doc.thumbnail_path:
            thumbnail_path = str(doc.thumbnail_path)

        items.append(
            GridViewItem(
                id=doc.id,
                title=doc.name,
                thumbnail=thumbnail_path,
                metadata={
                    "doc_type": doc.doc_type.value if doc.doc_type else None,
                    "created_at": doc.created_at.isoformat() if doc.created_at else None,
                },
            )
        )

    return GridViewData(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )
