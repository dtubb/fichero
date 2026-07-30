"""
Search Routes

Semantic search using LanceDB vector embeddings.
"""

import asyncio
import logging
from dataclasses import asdict
from fichero_server.core.timeutil import utc_now

from fichero_server.retrieval.query_compiler import (
    CompiledQuery,
    compile_query,
    looks_like_natural_language,
)
from enum import Enum
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from fichero_server.security import authz
from fichero_server.actions.registry import registry
from fichero_server.api.auth import action_context
from fichero_server.api.library_header import require_library_path
from fichero_server.api.main import get_library_database, get_library_database_for_write
from fichero_server.api.routes.kg.claim_search import search_claims_semantic_impl
from fichero_server.api.routes.kg.entity_curation import search_entities_semantic_impl
from fichero_server.search.query_parser import parse_query
from fichero_server.db import (
    Database,
    SearchExecutionError,
    SearchResult,
    _build_transcript_excerpts,
    _fold_for_search,
    _search_result_preview,
    _search_match_terms,
)
from fichero_server.models.knowledge import KnowledgeClaim, KnowledgeEntity
from fichero_server.models import DocType, Document, EmbeddingStatsResponse, SavedSearch

logger = logging.getLogger(__name__)
router = APIRouter()


def _request_is_bootstrap(request: Request | None) -> bool:
    return bool(getattr(getattr(request, "state", None), "bootstrap_auth", False))


def _saved_search_owner_id(actor: Any) -> str:
    resolved = authz.resolve_user(actor)
    if resolved is not None:
        return resolved.id
    raw = str(actor).strip() if actor is not None else ""
    return raw or "system"


def _saved_search_visible_to_actor(
    saved: SavedSearch,
    actor: Any,
    *,
    is_bootstrap: bool = False,
) -> bool:
    if not authz.multiuser_enabled() or is_bootstrap:
        return True
    resolved = authz.resolve_user(actor)
    if resolved is None:
        return False
    owner_id = str(getattr(saved, "created_by", "") or "")
    return bool(owner_id) and owner_id == resolved.id


def _require_saved_search_owner(
    db: Database,
    search_id: str,
    actor: Any,
    *,
    is_bootstrap: bool = False,
) -> SavedSearch:
    saved = db.get(SavedSearch, search_id)
    if saved is None or not _saved_search_visible_to_actor(
        saved,
        actor,
        is_bootstrap=is_bootstrap,
    ):
        raise HTTPException(status_code=404, detail="Saved search not found")
    return saved


def _readable_document_ids(
    *,
    actor: Any,
    library_path: str,
    document_ids: set[str],
    is_bootstrap: bool = False,
) -> set[str]:
    if not document_ids:
        return set()
    if not authz.multiuser_enabled() or is_bootstrap:
        return set(document_ids)
    return {
        document_id
        for document_id in document_ids
        if authz.can_read(actor, library_path, document_id)
    }


def _filter_entity_hits_for_actor(
    entity_hits: list[dict[str, Any]],
    *,
    actor: Any,
    library_path: str,
    is_bootstrap: bool = False,
) -> list[dict[str, Any]]:
    if not authz.multiuser_enabled() or is_bootstrap:
        return entity_hits
    visible: list[dict[str, Any]] = []
    for hit in entity_hits:
        doc_ids = {
            str(doc_id)
            for doc_id in (hit.get("source_document_ids") or [])
            if isinstance(doc_id, str) and doc_id
        }
        if doc_ids and not any(authz.can_read(actor, library_path, doc_id) for doc_id in doc_ids):
            continue
        visible.append(hit)
    return visible


def _filter_claim_hits_for_actor(
    claim_hits: list[dict[str, Any]],
    *,
    actor: Any,
    library_path: str,
    is_bootstrap: bool = False,
) -> list[dict[str, Any]]:
    if not authz.multiuser_enabled() or is_bootstrap:
        return claim_hits
    visible: list[dict[str, Any]] = []
    for hit in claim_hits:
        doc_ids = {
            str(doc_id)
            for doc_id in ([hit.get("source_document_id")] + list(hit.get("source_ids") or []))
            if isinstance(doc_id, str) and doc_id
        }
        if doc_ids and not any(authz.can_read(actor, library_path, doc_id) for doc_id in doc_ids):
            continue
        visible.append(hit)
    return visible


class SearchInclude(str, Enum):
    content = "content"
    entities = "entities"
    claims = "claims"
    # Unified-object search (#4118): workflow outputs — transcriptions,
    # summaries, translations, catalogues — as first-class hits.
    artifacts = "artifacts"


def _artifact_snippet(body: str, query: str, radius: int = 80) -> str:
    """A display window around the first query match in an artifact body."""
    if not body:
        return ""
    needle = query.strip().lower()
    index = body.lower().find(needle) if needle else -1
    if index < 0:
        return body[: radius * 2].strip()
    start = max(0, index - radius)
    end = min(len(body), index + len(needle) + radius)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(body) else ""
    return f"{prefix}{body[start:end].strip()}{suffix}"


def _safe_isoformat(value) -> str:
    """Return ISO string when value behaves like datetime, else now."""
    return (
        value.isoformat() if hasattr(value, "isoformat") else utc_now().isoformat()
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
    from fichero_server.db import _fold_for_search

    needle = _fold_for_search(query.strip())
    if not needle:
        return []

    try:
        data_blobs = db.artifact_data_for_types(
            ("people", "places", "organizations", "keywords")
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("did-you-mean lookup failed: %s", exc)
        return []

    candidates: set[str] = set()
    for data_blob in data_blobs:
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

    from fichero_server.db import _fold_for_search

    folded_phrases = [_fold_for_search(p) for p in phrases]
    folded_excludes = [_fold_for_search(e) for e in excludes]

    out: list[SearchResult] = []
    for r in results:
        try:
            content = db.document_page_content(r.document_id) or ""
        except Exception:
            content = r.content_preview or ""
        folded = _fold_for_search(content)

        if any(p not in folded for p in folded_phrases):
            continue
        if any(e in folded for e in folded_excludes):
            continue
        out.append(r)
    return out


def _project_pdf_file_hits_to_pages(
    db: Database,
    results: list[SearchResult],
    query: str,
) -> list[SearchResult]:
    """Replace PDF file-level hits with best-matching child page hits."""
    if not results or not query.strip():
        return results

    terms = _search_match_terms(query)
    if not terms:
        return results

    projected: list[SearchResult] = []
    seen_doc_ids: set[str] = set()
    pdf_parent_ids = [
        result.document_id
        for result in results
        if str((result.metadata or {}).get("doc_type") or "").lower() == "file"
        and str((result.metadata or {}).get("file_type") or "").lower() == "pdf"
    ]
    pages_by_parent_id: dict[str, list[Document]] = {}
    if pdf_parent_ids:
        for page in db.query_in(Document, "parent_id", pdf_parent_ids):
            if page.doc_type != DocType.page or getattr(page, "deleted_at", None) is not None:
                continue
            pages_by_parent_id.setdefault(page.parent_id or "", []).append(page)

    def _page_match_score(text: str) -> int:
        folded = _fold_for_search(text or "")
        return sum(folded.count(term) for term in terms)

    for result in results:
        metadata = result.metadata or {}
        doc_type = str(metadata.get("doc_type") or "").lower()
        file_type = str(metadata.get("file_type") or "").lower()
        if doc_type != "file" or file_type != "pdf":
            if result.document_id not in seen_doc_ids:
                projected.append(result)
                seen_doc_ids.add(result.document_id)
            continue

        pages = sorted(
            pages_by_parent_id.get(result.document_id, []),
            key=lambda page: page.sequence or 0,
        )
        if not pages:
            if result.document_id not in seen_doc_ids:
                projected.append(result)
                seen_doc_ids.add(result.document_id)
            continue

        scored_pages = [
            (page, _page_match_score(page.page_content or ""))
            for page in pages
            if page.page_content
        ]
        scored_pages = [pair for pair in scored_pages if pair[1] > 0]
        if not scored_pages:
            if result.document_id not in seen_doc_ids:
                projected.append(result)
                seen_doc_ids.add(result.document_id)
            continue

        best_page, _ = max(
            scored_pages,
            key=lambda pair: (pair[1], -(pair[0].sequence or 0)),
        )
        page_metadata = dict(metadata)
        page_metadata["doc_type"] = str(best_page.doc_type)
        page_metadata["file_type"] = str(best_page.file_type) if best_page.file_type else None
        page_metadata["pdf_parent_id"] = result.document_id
        page_metadata["page_number"] = best_page.sequence
        if best_page.sequence is not None:
            page_metadata["page_label"] = best_page.page_label or str(best_page.sequence)
        if isinstance(best_page.metadata, dict):
            page_metadata.update(best_page.metadata)

        excerpts = _build_transcript_excerpts(
            document_id=best_page.id,
            content=best_page.page_content or "",
            query=query,
        )
        replacement = SearchResult(
            document_id=best_page.id,
            score=result.score,
            content_preview=_search_result_preview(
                best_page.page_content or "",
                excerpts,
            ),
            metadata=page_metadata,
            highlights=result.highlights,
            transcript_excerpts=excerpts,
            kg_claim_ids=result.kg_claim_ids,
            kg_entity_ids=result.kg_entity_ids,
        )
        if replacement.document_id not in seen_doc_ids:
            projected.append(replacement)
            seen_doc_ids.add(replacement.document_id)

    return projected


def _enrich_page_results_with_parent_info(
    db: Database,
    results: list[SearchResult],
) -> list[SearchResult]:
    """Add pdf_parent_id / page_number / page_label / parent_name to page-type results.

    When the vector index returns a page document directly (because pages are
    indexed individually), the embedding metadata only carries the page's own
    fields — it has no knowledge of the parent PDF's ID or display name.  This
    function batch-fetches the page and parent docs and injects the missing
    fields so that the frontend can show "ParentName — p.N" and navigate to
    the right page.

    Results that already have pdf_parent_id set (from _project_pdf_file_hits_to_pages)
    are left unchanged.
    """
    # Collect page-type results that don't yet carry parent info.
    needs_enrichment = [
        result
        for result in results
        if str((result.metadata or {}).get("doc_type") or "").lower() == "page"
        and not (result.metadata or {}).get("pdf_parent_id")
    ]
    if not needs_enrichment:
        return results

    page_ids = [r.document_id for r in needs_enrichment]

    # Batch-fetch page docs.
    pages_by_id: dict[str, Document] = {}
    try:
        for page in db.query_in(Document, "id", page_ids):
            pages_by_id[page.id] = page
    except Exception as exc:  # noqa: BLE001
        logger.warning("page enrichment: failed to fetch page docs: %s", exc)
        return results

    # Batch-fetch parent docs.
    parent_ids = list({
        page.parent_id
        for page in pages_by_id.values()
        if page.parent_id
    })
    parents_by_id: dict[str, Document] = {}
    if parent_ids:
        try:
            for parent in db.query_in(Document, "id", parent_ids):
                parents_by_id[parent.id] = parent
        except Exception as exc:  # noqa: BLE001
            logger.warning("page enrichment: failed to fetch parent docs: %s", exc)

    # Rebuild result list, enriching page hits in place.
    enriched: list[SearchResult] = []
    for result in results:
        metadata = result.metadata or {}
        if str(metadata.get("doc_type") or "").lower() != "page" or metadata.get("pdf_parent_id"):
            enriched.append(result)
            continue

        page = pages_by_id.get(result.document_id)
        if not page or not page.parent_id:
            enriched.append(result)
            continue

        parent = parents_by_id.get(page.parent_id)
        new_metadata = dict(metadata)
        new_metadata["pdf_parent_id"] = page.parent_id
        if page.sequence is not None:
            new_metadata["page_number"] = page.sequence
            new_metadata["page_label"] = page.page_label or str(page.sequence)
        if parent:
            new_metadata["parent_name"] = parent.name

        enriched.append(SearchResult(
            document_id=result.document_id,
            score=result.score,
            content_preview=result.content_preview,
            metadata=new_metadata,
            highlights=result.highlights,
            transcript_excerpts=result.transcript_excerpts,
            kg_claim_ids=result.kg_claim_ids,
            kg_entity_ids=result.kg_entity_ids,
        ))

    return enriched


def _run_content_search_sync(
    db: Database,
    request: Any,
    retrieval_query: str,
) -> tuple[list[SearchResult], int, dict[str, Any]]:
    """Run synchronous content retrieval work off the FastAPI event loop."""
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
    results = _project_pdf_file_hits_to_pages(db, results, retrieval_query)
    results = _enrich_page_results_with_parent_info(db, results)
    # Return the db's REAL pre-pagination match count (#4113): `len(results)`
    # was just the page size, so total_results lied and has_more had nothing
    # honest to compare against.
    return results, total_count, search_stats


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
    try:
        rows = db.artifact_entity_document_matches(
            query=query,
            limit=limit,
            artifact_types=entity_types,
        )
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


def _search_scope_queries(
    *,
    plan: Any,
    scope_name: str,
    fallback_query: str | None,
) -> list[str]:
    values = [value.strip() for value in plan.scopes.get(scope_name, []) if value.strip()]
    if values:
        return values
    if fallback_query:
        return [fallback_query]
    return []


def _fallback_semantic_query(plan: Any, retrieval_query: str) -> str | None:
    query = retrieval_query.strip()
    if not query:
        return None
    if not plan.scopes:
        return query
    if plan.has_freetext_intent:
        return query
    return None


def _dedupe_semantic_hits(items: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for item in items:
        item_id = str(item.get("id") or "")
        if not item_id or item_id in seen_ids:
            continue
        seen_ids.add(item_id)
        deduped.append(item)
        if len(deduped) >= limit:
            break
    return deduped


def _run_entity_semantic_queries(
    *,
    db: Database,
    queries: list[str],
    limit: int,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for query in queries:
        try:
            response = search_entities_semantic_impl(db=db, q=query, limit=limit)
        except HTTPException as exc:
            logger.warning("entity semantic search skipped for query %r: %s", query, exc.detail)
            continue
        except Exception as exc:  # noqa: BLE001
            logger.warning("entity semantic search failed for query %r: %s", query, exc)
            continue
        items.extend(item for item in response.items if isinstance(item, dict))
    return _dedupe_semantic_hits(items, limit=limit)


def _run_claim_semantic_queries(
    *,
    db: Database,
    queries: list[str],
    limit: int,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for query in queries:
        try:
            response = search_claims_semantic_impl(db=db, q=query, limit=limit)
        except HTTPException as exc:
            logger.warning("claim semantic search skipped for query %r: %s", query, exc.detail)
            continue
        except Exception as exc:  # noqa: BLE001
            logger.warning("claim semantic search failed for query %r: %s", query, exc)
            continue
        items.extend(item for item in response.items if isinstance(item, dict))
    return _dedupe_semantic_hits(items, limit=limit)


# Request/Response models
class SearchRequest(BaseModel):
    """Request model for enhanced search."""

    query: str
    limit: int = 10
    include: list[SearchInclude] = Field(
        default_factory=lambda: [
            SearchInclude.content,
            SearchInclude.entities,
            SearchInclude.claims,
        ]
    )
    # 0.55 filters out the unthresholded-semantic noise floor: a query like
    # "racial inequality" over a 15-doc corpus returns every page at
    # 42-50% cosine similarity (#1054). At 0.55 the post-RRF filter
    # keeps only the top few genuinely ranked results.
    # Callers wanting everything can pass 0.0; tight matches: 0.6+.
    min_score: float = 0.55

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

    # Query compilation (#4116): opt-in — the caller decides when the
    # LLM-latency tax is acceptable (explicit submits, chat), never live
    # typing. Only fires when the query passes the natural-language gate.
    compile: bool = False


class SearchArtifactHit(BaseModel):
    """One artifact whose content matched the query (#4118)."""

    document_id: str
    document_name: str | None = None
    artifact_type: str
    snippet: str = ""


class SearchEntityHit(KnowledgeEntity):
    similarity_score: float = 0.0


class SearchClaimHit(KnowledgeClaim):
    similarity_score: float = 0.0


class SearchResponse(BaseModel):
    """Response model for enhanced search results."""

    query: str
    results: list[SearchResult]
    entity_hits: list[SearchEntityHit] = Field(default_factory=list)
    claim_hits: list[SearchClaimHit] = Field(default_factory=list)
    artifact_hits: list[SearchArtifactHit] = Field(default_factory=list)
    count: int
    total_results: int  # Total results before pagination
    search_type: str  # Type of search performed
    execution_time_ms: float  # Search execution time

    # Search statistics
    has_more: bool = False  # Whether more results are available
    filters_applied: dict | None = None  # Filters that were applied
    suggestions: list[str] | None = None  # Search suggestions

    # Query compilation (#4116). AI = instrument: what the LLM compiled the
    # request into is always returned so the user sees and can edit what was
    # actually searched; a failed compilation is reported, never hidden.
    compiled_query: CompiledQuery | None = None
    compilation_error: str | None = None


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
    request: SearchRequest,
    http_request: Request,
    db: Database = Depends(get_library_database),
    x_fichero_library_path: str = Depends(require_library_path),
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
            rows = db.recent_content_document_rows(request.limit)
        except Exception as exc:
            # Same contract as the query path (#4109): a failed browse is a
            # 500, never a silently empty "recent" list.
            raise HTTPException(
                status_code=500, detail=f"recent-documents browse failed: {exc}"
            ) from exc
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
            entity_hits=[],
            claim_hits=[],
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

    # Query compilation (#4116): sentence-like queries drop down to an LLM
    # that compiles them into a semantic query + the date/type filters
    # db.search already understands. Opt-in (compile=true) so live-typing
    # callers never pay LLM latency; keyword queries skip the gate anyway.
    # Failure surfaces in compilation_error and the RAW query still runs —
    # retrieval never breaks on an LLM outage, and nothing is hidden.
    compiled_query: CompiledQuery | None = None
    compilation_error: str | None = None
    effective_query = request.query
    if request.compile and looks_like_natural_language(request.query):
        try:
            compiled_query = await compile_query(db, request.query)
            effective_query = compiled_query.semantic_query
            merged_filters = dict(request.filters or {})
            if compiled_query.date_from:
                merged_filters.setdefault("date_from", compiled_query.date_from)
            if compiled_query.date_to:
                merged_filters.setdefault("date_to", compiled_query.date_to)
            if compiled_query.doc_type:
                merged_filters.setdefault("doc_type", compiled_query.doc_type)
            if merged_filters:
                request = request.model_copy(update={"filters": merged_filters})
        except Exception as exc:  # noqa: BLE001
            compilation_error = str(exc)
            logger.warning("query compilation failed (raw query used): %s", exc)

    # Parse query into a plan (quoted phrases / field scopes /
    # NOT exclusions / plain free-text). The retriever still consumes
    # a plain query string — we feed it the free-text portion, then
    # post-filter for phrases + excludes and union-in entity scopes.
    plan = parse_query(effective_query)
    retrieval_query = plan.free_text or " ".join(plan.phrases) or effective_query
    fallback_semantic_query = _fallback_semantic_query(plan, retrieval_query)
    include_set = set(request.include)
    search_content = SearchInclude.content in include_set
    search_entities = SearchInclude.entities in include_set
    search_claims = SearchInclude.claims in include_set

    # Pure scope queries (e.g. `people:Asprilla` alone) skip the
    # text retriever entirely — answers are 100% from the entity bridge.
    skip_retriever = plan.has_scope and not plan.has_freetext_intent

    # Perform enhanced search
    if not search_content or skip_retriever:
        results, total_count, search_stats = (
            [],
            0,
            {"search_type": request.search_type, "execution_time_ms": 0.0, "filters_applied": {}},
        )
    else:
        try:
            results, total_count, search_stats = await asyncio.to_thread(
                _run_content_search_sync,
                db,
                request,
                retrieval_query,
            )
        except SearchExecutionError as exc:
            # A failed search is a 500, never a 200-with-zero-results (#4109).
            raise HTTPException(status_code=500, detail=str(exc)) from exc

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
    bridge_run = search_content and (
        request.search_type in ("hybrid", "fulltext") or skip_retriever
    )
    if bridge_run:
        seen_ids = {r.document_id for r in results}
        slots_remaining = max(0, request.limit - len(results))
        if slots_remaining > 0:
            artifact_hits: list[SearchResult] = []
            if plan.artifact_scopes:
                # Scoped: emit one batch per (type, value) and dedupe.
                for entity_type, values in plan.artifact_scopes.items():
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
                        artifact_hits.extend(hits)
            else:
                artifact_hits = _entity_match_results(
                    db,
                    query=request.query,
                    limit=slots_remaining,
                    exclude_doc_ids=seen_ids,
                )
            if artifact_hits:
                results = list(results) + artifact_hits
                total_count = total_count + len(artifact_hits)

    # Graph leg (#4115): expand the top semantic entity hits ONE hop through
    # the knowledge graph — entity → claims → source documents — so a query
    # about a person surfaces the documents about them even when their text
    # never matches. Runs BEFORE the ACL filter and KG enrichment below so
    # graph-found docs get the same visibility treatment as every other hit.
    # Entity hits are computed here (moved up from the response-assembly
    # tail) so one computation feeds both the graph leg and the response.
    entity_hits = (
        _run_entity_semantic_queries(
            db=db,
            queries=_search_scope_queries(
                plan=plan,
                scope_name="entities",
                fallback_query=fallback_semantic_query,
            ),
            limit=request.limit,
        )
        if search_entities
        else []
    )
    if search_content and entity_hits:
        graph_seen = {r.document_id for r in results}
        graph_slots = max(0, request.limit - len(results))
        graph_hits: list[SearchResult] = []
        # ponytail: top-5 seed entities, one hop, fixed 0.8 decay — add
        # hop-depth/decay knobs when the graph leg proves out (#4110 tuning).
        for entity_hit in entity_hits[:5]:
            if len(graph_hits) >= graph_slots:
                break
            try:
                source_doc_ids = db.knowledge_claim_source_document_ids_for_entity(
                    entity_hit.id
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("graph-leg claim lookup failed: %s", exc)
                continue
            base_score = max(0.0, float(getattr(entity_hit, "similarity_score", 0.0) or 0.0))
            for doc_id in source_doc_ids:
                if not doc_id or doc_id in graph_seen:
                    continue
                graph_seen.add(doc_id)
                graph_hits.append(
                    SearchResult(
                        document_id=doc_id,
                        score=base_score * 0.8,
                        content_preview="",
                        # Provenance the UI can badge (#4115): this hit came
                        # via the graph, through WHICH entity.
                        metadata={
                            "via": "graph",
                            "entity_id": entity_hit.id,
                            "entity_name": entity_hit.canonical_name,
                        },
                        kg_entity_ids=[entity_hit.id],
                    )
                )
                if len(graph_hits) >= graph_slots:
                    break
        if graph_hits:
            results = list(results) + graph_hits
            total_count = total_count + len(graph_hits)

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

    # Attach KG ids for clickable chips. For scoped queries, enrich
    # against the scoped value ("people:Asprilla" -> "Asprilla") so KG
    # entity names still match. The database method only reads KG rows
    # and result-indexed snippets; it does not refetch document bodies.
    kg_query = retrieval_query
    if plan.has_entity_scope:
        scoped_values = [
            value
            for values in plan.scopes.values()
            for value in values
            if value.strip()
        ]
        kg_query = " ".join([retrieval_query, *scoped_values]).strip()
    try:
        enricher = getattr(db, "enrich_search_results_with_kg", None)
        if callable(enricher):
            enriched = enricher(results, kg_query)
            if isinstance(enriched, list):
                results = enriched
    except Exception as exc:  # noqa: BLE001
        logger.warning("search KG enrichment failed: %s", exc)

    visible_doc_ids = _readable_document_ids(
        actor=getattr(getattr(http_request, "state", None), "user", None),
        library_path=x_fichero_library_path,
        document_ids={result.document_id for result in results},
        is_bootstrap=_request_is_bootstrap(http_request),
    )
    if visible_doc_ids != {result.document_id for result in results}:
        results = [result for result in results if result.document_id in visible_doc_ids]
        total_count = len(results)
        search_stats["has_more"] = False

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

    # entity_hits were computed above (graph leg) — one computation feeds both.
    claim_hits = (
        _run_claim_semantic_queries(
            db=db,
            queries=_search_scope_queries(
                plan=plan,
                scope_name="claims",
                fallback_query=fallback_semantic_query,
            ),
            limit=request.limit,
        )
        if search_claims
        else []
    )
    entity_hits = _filter_entity_hits_for_actor(
        entity_hits,
        actor=getattr(getattr(http_request, "state", None), "user", None),
        library_path=x_fichero_library_path,
        is_bootstrap=_request_is_bootstrap(http_request),
    )
    claim_hits = _filter_claim_hits_for_actor(
        claim_hits,
        actor=getattr(getattr(http_request, "state", None), "user", None),
        library_path=x_fichero_library_path,
        is_bootstrap=_request_is_bootstrap(http_request),
    )

    # Artifact leg (#4118): workflow outputs as first-class hits. Best-effort
    # auxiliary leg like the graph leg — failure degrades with a loud log,
    # never a 500 (the content leg owns hard failures). ACL-filtered by the
    # owning document's visibility.
    artifact_hits: list[SearchArtifactHit] = []
    if SearchInclude.artifacts in include_set and request.query.strip():
        try:
            artifact_rows = db.artifact_content_matches(
                query=retrieval_query or request.query, limit=request.limit
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("artifact search leg failed: %s", exc)
            artifact_rows = []
        if artifact_rows:
            visible_artifact_docs = _readable_document_ids(
                actor=getattr(getattr(http_request, "state", None), "user", None),
                library_path=x_fichero_library_path,
                document_ids={row[0] for row in artifact_rows if row[0]},
                is_bootstrap=_request_is_bootstrap(http_request),
            )
            for doc_id, doc_name, artifact_type, body in artifact_rows:
                if not doc_id or doc_id not in visible_artifact_docs:
                    continue
                artifact_hits.append(
                    SearchArtifactHit(
                        document_id=doc_id,
                        document_name=doc_name,
                        artifact_type=artifact_type,
                        snippet=_artifact_snippet(
                            body or "", retrieval_query or request.query
                        ),
                    )
                )

    return SearchResponse(
        query=request.query,
        results=results,
        entity_hits=[SearchEntityHit.model_validate(item) for item in entity_hits],
        claim_hits=[SearchClaimHit.model_validate(item) for item in claim_hits],
        artifact_hits=artifact_hits,
        count=len(results),
        total_results=total_count,
        search_type=search_stats.get("search_type", request.search_type),
        execution_time_ms=search_stats.get("execution_time_ms", 0),
        has_more=search_stats.get("has_more", False),
        filters_applied=request.filters,
        suggestions=suggestions,
        compiled_query=compiled_query,
        compilation_error=compilation_error,
    )


@router.get("/stats", response_model=EmbeddingStatsResponse)
async def search_stats(
    db: Database = Depends(get_library_database),
) -> EmbeddingStatsResponse:
    """Get embedding/search statistics."""
    return EmbeddingStatsResponse(**db.embedding_stats())


class KeywordCloudEntry(BaseModel):
    """Single entry in the keyword cloud — name + how many docs use it."""

    name: str
    count: int


class KeywordCloudListResponse(BaseModel):
    """Envelope for the keyword cloud list."""

    items: list[KeywordCloudEntry]
    count: int


@router.get("/keywords", response_model=KeywordCloudListResponse)
async def keyword_cloud(
    request: Request,
    db: Database = Depends(get_library_database),
    x_fichero_library_path: str = Depends(require_library_path),
    limit: int = Query(50, ge=1, le=500),
) -> KeywordCloudListResponse:
    """Top-N keywords across the library, sorted by document frequency.

    Reads the 'keywords' artifacts emitted by extract_all and counts the
    distinct documents each keyword appears in. Empty list when no
    keywords have been extracted yet (workflow hasn't run).

    Used by the search empty-state to surface clickable terms — a
    "browse by tag" affordance for users who don't know what to type.
    """
    try:
        rows = db.keyword_artifact_rows()
    except Exception as exc:  # noqa: BLE001
        logger.warning("keyword cloud query failed: %s", exc)
        return KeywordCloudListResponse(items=[], count=0)

    import json
    from collections import Counter

    counter: Counter[str] = Counter()
    readable_ids = _readable_document_ids(
        actor=getattr(getattr(request, "state", None), "user", None),
        library_path=x_fichero_library_path,
        document_ids={str(doc_id) for _, doc_id in rows if isinstance(doc_id, str)},
        is_bootstrap=_request_is_bootstrap(request),
    )

    for data_blob, doc_id in rows:
        if readable_ids and doc_id not in readable_ids:
            continue
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

    items = [
        KeywordCloudEntry(name=name, count=count)
        for name, count in counter.most_common(limit)
    ]
    return KeywordCloudListResponse(items=items, count=len(items))


@router.post("/reindex")
async def reindex_all(
    background_tasks: BackgroundTasks, db: Database = Depends(get_library_database_for_write)
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
async def embed_document(doc_id: str, db: Database = Depends(get_library_database_for_write)) -> EmbedDocumentResponse:
    """Create embedding for a specific document."""
    doc = db.get(Document, doc_id)
    if not doc or getattr(doc, "deleted_at", None) is not None:
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")

    success = db.embed(doc)

    return EmbedDocumentResponse(document_id=doc_id, embedded=success)


# =============================================================================
# Saved Searches
# =============================================================================


class SavedSearchCreate(BaseModel):
    """Request to save a search."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1)
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


class SavedSearchListResponse(BaseModel):
    """Envelope for a list of saved searches."""

    items: list[SavedSearchResponse]
    count: int


def _saved_search_response(saved: SavedSearch) -> SavedSearchResponse:
    """Render a ``SavedSearch`` row as the API response.

    One place — the save / update / duplicate routes (and their actions) used to
    rebuild this struct inline four times over. Collapsing the genuine
    duplication onto this canonical renderer is the iterate-not-replace move.
    """
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


def save_search_impl(db: Database, request: SavedSearchCreate, *, actor: Any = "system") -> SavedSearch:
    """Create + persist a ``SavedSearch`` from the create request.

    Extracted from ``POST /saved`` so BOTH the route and the ``savedsearch.save``
    action (EPIC #1848) drive the *same* code (iterate-not-replace). Returns the
    persisted row.
    """
    saved = SavedSearch(
        query=request.query,
        is_smart_search=request.is_smart_search,
        filters=request.filters,
        search_type=request.search_type,
        sort_by=request.sort_by,
        sort_direction=request.sort_direction,
        created_by=_saved_search_owner_id(actor),
        folder_path=request.folder_path,
        sort_order=request.sort_order,
    )
    db.save(saved)
    return saved


@router.post("/saved")
async def save_search(
    request: SavedSearchCreate,
    db: Database = Depends(get_library_database_for_write),
    ctx: "ActionContext" = Depends(action_context),
) -> SavedSearchResponse:
    """Save a search for later."""
    result = registry.invoke(
        db,
        "savedsearch.save",
        request.model_dump(mode="json"),
        ctx,
    )
    return SavedSearchResponse.model_validate(result.result)


@router.get("/saved", response_model=SavedSearchListResponse)
async def list_saved_searches(
    request: Request,
    db: Database = Depends(get_library_database),
) -> SavedSearchListResponse:
    """List all saved searches."""
    searches = [
        search
        for search in db.all(SavedSearch)
        if _saved_search_visible_to_actor(
            search,
            getattr(getattr(request, "state", None), "user", None),
            is_bootstrap=_request_is_bootstrap(request),
        )
    ]
    items = [_saved_search_response(s) for s in searches]
    return SavedSearchListResponse(items=items, count=len(items))


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


def update_saved_search_impl(
    db: Database,
    search_id: str,
    request: SavedSearchUpdate,
    *,
    actor: Any = "system",
    is_bootstrap: bool = False,
) -> SavedSearch:
    """Apply the present (non-None) ``SavedSearchUpdate`` fields and persist.

    Extracted from ``PUT /saved/{search_id}`` so BOTH the route and the
    ``savedsearch.update`` action drive the *same* code (iterate-not-replace).
    Raises ``HTTPException(404)`` on an unknown id exactly as the route did.
    """
    saved = _require_saved_search_owner(
        db,
        search_id,
        actor,
        is_bootstrap=is_bootstrap,
    )

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

    saved.updated_at = utc_now()
    db.save(saved)
    return saved


@router.put("/saved/{search_id}")
async def update_saved_search(
    search_id: str,
    request: SavedSearchUpdate,
    http_request: Request,
    db: Database = Depends(get_library_database_for_write),
) -> SavedSearchResponse:
    """Update a saved search."""
    return _saved_search_response(
        update_saved_search_impl(
            db,
            search_id,
            request,
            actor=getattr(getattr(http_request, "state", None), "user", None),
            is_bootstrap=_request_is_bootstrap(http_request),
        )
    )


def duplicate_saved_search_impl(
    db: Database,
    search_id: str,
    *,
    actor: Any = "system",
    is_bootstrap: bool = False,
) -> SavedSearch:
    """Create + persist a copy of a saved search under a new id.

    Extracted from ``POST /saved/{search_id}/duplicate`` so BOTH the route and
    the ``savedsearch.duplicate`` action drive the *same* copy logic
    (iterate-not-replace). Raises ``HTTPException(404)`` on an unknown id.
    """
    original = _require_saved_search_owner(
        db,
        search_id,
        actor,
        is_bootstrap=is_bootstrap,
    )

    # Create a new saved search with same properties but different ID and modified name
    new_saved = SavedSearch(
        query=original.query,
        is_smart_search=original.is_smart_search,
        filters=original.filters,
        search_type=original.search_type,
        sort_by=original.sort_by,
        sort_direction=original.sort_direction,
        created_by=_saved_search_owner_id(actor),
        folder_path=original.folder_path,
        sort_order=original.sort_order,
    )

    # The database layer will generate a new ID
    db.save(new_saved)
    return new_saved


@router.post("/saved/{search_id}/duplicate")
async def duplicate_saved_search(
    search_id: str,
    http_request: Request,
    db: Database = Depends(get_library_database_for_write),
) -> SavedSearchResponse:
    """Duplicate a saved search with a new name."""
    return _saved_search_response(
        duplicate_saved_search_impl(
            db,
            search_id,
            actor=getattr(getattr(http_request, "state", None), "user", None),
            is_bootstrap=_request_is_bootstrap(http_request),
        )
    )


def delete_saved_search_impl(
    db: Database,
    search_id: str,
    *,
    actor: Any = "system",
    is_bootstrap: bool = False,
) -> SavedSearch:
    """Delete a saved search, returning the row that was removed.

    Extracted from ``DELETE /saved/{search_id}`` so BOTH the route and the
    ``savedsearch.delete`` action drive the *same* code (iterate-not-replace).
    Returning the deleted row lets the action snapshot it as the undo payload.
    Raises ``HTTPException(404)`` on an unknown id.
    """
    saved = _require_saved_search_owner(
        db,
        search_id,
        actor,
        is_bootstrap=is_bootstrap,
    )

    db.delete(saved)
    return saved


@router.delete("/saved/{search_id}")
async def delete_saved_search(
    search_id: str,
    http_request: Request,
    db: Database = Depends(get_library_database_for_write),
) -> DeletedResponse:
    """Delete a saved search."""
    delete_saved_search_impl(
        db,
        search_id,
        actor=getattr(getattr(http_request, "state", None), "user", None),
        is_bootstrap=_request_is_bootstrap(http_request),
    )
    return DeletedResponse(status="deleted")


def reorder_saved_searches_impl(
    db: Database,
    search_ids: list[str],
    folder_path: str = "/",
    *,
    actor: Any = "system",
    is_bootstrap: bool = False,
) -> tuple[int, dict[str, int], dict[str, int]]:
    """Renumber the listed saved searches to their list position and persist.

    Extracted from ``POST /saved/reorder`` so BOTH the route and the
    ``savedsearch.reorder`` action drive the *same* code (iterate-not-replace).
    Returns ``(count, before_orders, after_orders)`` — the order maps feed the
    action's audit ``before``/``after`` so the reorder is recorded even though it
    is not wired for one-click undo. Raises ``HTTPException(404)`` on an unknown
    id, preserving the route's original (partial-update-on-failure) semantics.
    """
    before_orders: dict[str, int] = {}
    for i, search_id in enumerate(search_ids):
        saved = db.get(SavedSearch, search_id)
        if saved is None:
            raise HTTPException(
                status_code=404, detail=f"Saved search not found: {search_id}"
            )
        if not _saved_search_visible_to_actor(
            saved,
            actor,
            is_bootstrap=is_bootstrap,
        ):
            raise HTTPException(status_code=404, detail="Saved search not found")

        before_orders[search_id] = saved.sort_order
        # Update sort order
        saved.sort_order = i
        db.save(saved)

    after_orders = {sid: i for i, sid in enumerate(search_ids)}
    return len(search_ids), before_orders, after_orders


@router.post("/saved/reorder")
async def reorder_saved_searches(
    http_request: Request,
    search_ids: list[str],
    folder_path: str = "/",
    db: Database = Depends(get_library_database_for_write),
) -> ReorderResponse:
    """Reorder saved searches within a folder."""
    count, _before, _after = reorder_saved_searches_impl(
        db,
        search_ids,
        folder_path,
        actor=getattr(getattr(http_request, "state", None), "user", None),
        is_bootstrap=_request_is_bootstrap(http_request),
    )
    return ReorderResponse(status="reordered", count=count)


# The Search Views API (/views, /views/table, /views/map, /views/grid,
# issue #434) was REMOVED (#4111): the endpoints never called the search
# engine (db.all + substring filter + hardcoded relevance 1.0) and had
# zero frontend callers. If #878's semantic map proceeds, build it on the
# real engine rather than reviving these stubs.


# =============================================================================
# Action layer registration (EPIC #1848 / sweep #2014) — saved-search domain
# =============================================================================
#
# Every saved-search mutation (save / update / duplicate / delete / reorder)
# becomes a registered, audited action that WRAPS the proven ``*_impl`` above —
# the typed routes stay green and untouched; the action is the additional
# uniform path that chat tools / App Intents / tests drive via
# POST /api/actions/invoke, with the ActionAudit row written at registry.invoke.
# ``before``/``after`` snapshots ARE the undo payload.
#
# Undo design (mirrors the conversation sibling): ``db.save`` is an upsert by id,
# so a single ``savedsearch.restore`` (full-snapshot upsert) inverts BOTH a
# delete (re-inserts the row, same id) and an edit (overwrites with the prior
# snapshot). ``restore`` records whether the row pre-existed, so its OWN inverse
# is ``savedsearch.delete`` (after a recreate) or ``savedsearch.restore`` (after
# an overwrite) — keeping every delete<->restore and edit<->restore redo chain
# sane. ``savedsearch.save`` / ``savedsearch.duplicate`` create brand-new rows
# (no prior state to reverse to) and ``savedsearch.reorder`` touches a whole
# folder; per the sweep scope only update + delete are wired undoable, but every
# action still writes an ActionAudit row (who-changed-what).

from fichero_server.actions.registry import action, ActionContext, ChangeSpec  # noqa: E402


def _snap_saved_search(saved: SavedSearch) -> dict:
    """JSON-able snapshot of a SavedSearch row (the undo payload)."""
    return saved.model_dump(mode="json")


class SavedSearchIdParams(BaseModel):
    """Shared params for id-only saved-search actions (duplicate / delete)."""

    search_id: str


class SavedSearchUpdateParams(BaseModel):
    """``savedsearch.update`` params — the target id plus the editable fields.

    Mirrors :class:`SavedSearchUpdate` (``extra="allow"``) with the path id
    folded in so the action is self-contained.
    """

    search_id: str
    query: Optional[str] = None
    is_smart_search: Optional[bool] = None
    filters: Optional[dict] = None
    search_type: Optional[str] = None
    sort_by: Optional[str] = None
    sort_direction: Optional[str] = None
    folder_path: Optional[str] = None

    model_config = ConfigDict(extra="allow")


class ReorderSavedSearchesParams(BaseModel):
    """``savedsearch.reorder`` params — the ordered ids within a folder."""

    search_ids: list[str]
    folder_path: str = "/"


class RestoreSavedSearchOrderParams(BaseModel):
    sort_orders: dict[str, int]


class SavedSearchRestoreParams(BaseModel):
    """``savedsearch.restore`` — re-materialize / overwrite a saved search by
    snapshot (preserving its id)."""

    snapshot: dict


def _invert_create_saved_search(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    if not after:
        return None
    sid = after.get("id")
    if not sid:
        return None
    return ("savedsearch.delete", {"search_id": sid})


def _invert_to_restore_before(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    """Undo an edit/delete by restoring the captured pre-change snapshot."""
    if not before:
        return None
    return ("savedsearch.restore", {"snapshot": before})


def _invert_restore(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    """Inverse of restore — depends on whether the row pre-existed.

    If ``before`` is None the restore RE-CREATED a missing row (it was undoing a
    delete) -> redo by deleting again. If ``before`` is a snapshot the restore
    OVERWROTE an existing row (undoing an edit) -> redo by restoring that prior
    snapshot, which re-applies the edit. Keeps delete<->restore and
    edit<->restore redo chains correct."""
    if not after:
        return None
    sid = after.get("id")
    if before is None:
        if not sid:
            return None
        return ("savedsearch.delete", {"search_id": sid})
    return ("savedsearch.restore", {"snapshot": before})


def _invert_reorder_saved_searches(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    if not before:
        return None
    return ("savedsearch.restore_order", {"sort_orders": before.get("sort_orders", {})})


@action(
    "savedsearch.save",
    SavedSearchCreate,
    domains=["savedsearch"],
    undoable=True,
    invert=_invert_create_saved_search,
)
def _action_save_search(
    db: Database, params: SavedSearchCreate, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    saved = save_search_impl(db, params, actor=ctx.actor)
    after = _snap_saved_search(saved)
    spec = ChangeSpec(
        domains=["savedsearch"],
        target_ids=[saved.id],
        before=None,
        after=after,
        emit_type="savedsearch.created",
    )
    return after, spec


@action(
    "savedsearch.update",
    SavedSearchUpdateParams,
    domains=["savedsearch"],
    undoable=True,
    invert=_invert_to_restore_before,
)
def _action_update_saved_search(
    db: Database, params: SavedSearchUpdateParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    existing = db.get(SavedSearch, params.search_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Saved search not found")
    before = _snap_saved_search(existing)
    request = SavedSearchUpdate(
        query=params.query,
        is_smart_search=params.is_smart_search,
        filters=params.filters,
        search_type=params.search_type,
        sort_by=params.sort_by,
        sort_direction=params.sort_direction,
        folder_path=params.folder_path,
    )
    saved = update_saved_search_impl(
        db,
        params.search_id,
        request,
        actor=ctx.actor,
        is_bootstrap=ctx.is_bootstrap,
    )
    after = _snap_saved_search(saved)
    spec = ChangeSpec(
        domains=["savedsearch"],
        target_ids=[saved.id],
        before=before,
        after=after,
        emit_type="savedsearch.updated",
    )
    return after, spec


@action(
    "savedsearch.duplicate",
    SavedSearchIdParams,
    domains=["savedsearch"],
    undoable=True,
    invert=_invert_create_saved_search,
)
def _action_duplicate_saved_search(
    db: Database, params: SavedSearchIdParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    new_saved = duplicate_saved_search_impl(
        db,
        params.search_id,
        actor=ctx.actor,
        is_bootstrap=ctx.is_bootstrap,
    )
    after = _snap_saved_search(new_saved)
    spec = ChangeSpec(
        domains=["savedsearch"],
        target_ids=[new_saved.id],
        before=None,
        after=after,
        emit_type="savedsearch.created",
    )
    return after, spec


@action(
    "savedsearch.delete",
    SavedSearchIdParams,
    domains=["savedsearch"],
    undoable=True,
    invert=_invert_to_restore_before,
)
def _action_delete_saved_search(
    db: Database, params: SavedSearchIdParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    deleted = delete_saved_search_impl(
        db,
        params.search_id,
        actor=ctx.actor,
        is_bootstrap=ctx.is_bootstrap,
    )
    before = _snap_saved_search(deleted)
    spec = ChangeSpec(
        domains=["savedsearch"],
        target_ids=[params.search_id],
        before=before,
        after=None,
        emit_type="savedsearch.deleted",
    )
    return before, spec


@action(
    "savedsearch.reorder",
    ReorderSavedSearchesParams,
    domains=["savedsearch"],
    undoable=True,
    invert=_invert_reorder_saved_searches,
    atomic=False,
)
def _action_reorder_saved_searches(
    db: Database, params: ReorderSavedSearchesParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    count, before_orders, after_orders = reorder_saved_searches_impl(
        db,
        params.search_ids,
        params.folder_path,
        actor=ctx.actor,
        is_bootstrap=ctx.is_bootstrap,
    )
    spec = ChangeSpec(
        domains=["savedsearch"],
        target_ids=list(params.search_ids),
        before={"sort_orders": before_orders},
        after={"sort_orders": after_orders},
        emit_type="savedsearch.reordered",
    )
    return {"count": count}, spec


@action(
    "savedsearch.restore_order",
    RestoreSavedSearchOrderParams,
    domains=["savedsearch"],
    undoable=True,
    invert=_invert_reorder_saved_searches,
    atomic=False,
)
def _action_restore_saved_search_order(
    db: Database, params: RestoreSavedSearchOrderParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    before_orders: dict[str, int] = {}
    for search_id, sort_order in params.sort_orders.items():
        saved = db.get(SavedSearch, search_id)
        if saved is None:
            raise HTTPException(status_code=404, detail=f"Saved search not found: {search_id}")
        before_orders[search_id] = saved.sort_order
        saved.sort_order = sort_order
        db.save(saved)
    spec = ChangeSpec(
        domains=["savedsearch"],
        target_ids=list(params.sort_orders),
        before={"sort_orders": before_orders},
        after={"sort_orders": dict(params.sort_orders)},
        emit_type="savedsearch.reordered" if params.sort_orders else None,
    )
    return {"count": len(params.sort_orders)}, spec


@action(
    "savedsearch.restore",
    SavedSearchRestoreParams,
    domains=["savedsearch"],
    undoable=True,
    invert=_invert_restore,
)
def _action_restore_saved_search(
    db: Database, params: SavedSearchRestoreParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    """Upsert a saved search from its snapshot (preserving id). Records whether
    the row pre-existed so its inverse picks delete (recreate) vs restore
    (edit)."""
    sid = params.snapshot.get("id")
    existing = db.get(SavedSearch, sid) if sid else None
    before = _snap_saved_search(existing) if existing else None
    saved = SavedSearch(**params.snapshot)
    db.save(saved)
    after = _snap_saved_search(saved)
    spec = ChangeSpec(
        domains=["savedsearch"],
        target_ids=[saved.id],
        before=before,
        after=after,
        emit_type="savedsearch.updated" if before else "savedsearch.created",
    )
    return after, spec


# =============================================================================
# The MISSING search action (#2018) — search.reindex
# =============================================================================
#
# The #2000-era inventory flagged "UI search-index refresh" as a capability with
# no single endpoint: re-embedding claims + entities for semantic search was only
# reachable as TWO separate admin routes (POST /kg/claim-search/embed and POST
# /kg/{...}/semantic/embed). search.reindex WRAPS the proven
# ``Database.embed_claims`` / ``Database.embed_entities`` (iterate-not-replace:
# the embedding algorithm is wrapped, never re-derived) into ONE audited action a
# UI button can drive. Pass ``entity_ids`` / ``claim_ids`` to scope the refresh;
# omit both to re-embed the whole knowledge graph. NOT undoable — re-embedding is
# an idempotent index rebuild with no meaningful inverse.


class SearchReindexParams(BaseModel):
    """``search.reindex`` — optional id subsets; empty/omitted means 'all'."""

    entity_ids: list[str] | None = Field(
        default=None, description="Entities to re-embed; None/empty = all entities"
    )
    claim_ids: list[str] | None = Field(
        default=None, description="Claims to re-embed; None/empty = all claims"
    )
    migrate_embedding_space: bool = Field(
        default=False,
        description=(
            "Drop and rebuild selected embedding tables for the active embedding "
            "space. Requires confirm_embedding_migration=true."
        ),
    )
    confirm_embedding_migration: bool = Field(
        default=False,
        description="Required confirmation for destructive embedding-space migration.",
    )
    include_documents: bool = Field(
        default=True,
        description="When migrating embedding space, rebuild document embeddings.",
    )
    include_entities: bool = Field(
        default=True,
        description="When migrating embedding space, rebuild entity embeddings.",
    )
    include_claims: bool = Field(
        default=True,
        description="When migrating embedding space, rebuild claim embeddings.",
    )


@action(
    "search.reindex",
    SearchReindexParams,
    domains=["search"],
    undoable=False,
)
def _action_search_reindex(
    db: Database, params: SearchReindexParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    """Re-embed claims + entities for semantic search in one audited pass."""
    if params.migrate_embedding_space:
        if params.entity_ids or params.claim_ids:
            raise ValueError("embedding-space migration cannot be scoped by ids")
        result = db.migrate_embedding_space(
            confirm=params.confirm_embedding_migration,
            include_documents=params.include_documents,
            include_entities=params.include_entities,
            include_claims=params.include_claims,
        )
        spec = ChangeSpec(
            domains=["search"],
            target_ids=[],
            before=result.get("before"),
            after=result,
            emit_type="search.reindexed",
        )
        return result, spec

    if params.entity_ids:
        entities = [e for e in (db.get(KnowledgeEntity, eid) for eid in params.entity_ids) if e]
    else:
        entities = db.all(KnowledgeEntity)
    if params.claim_ids:
        claims = [c for c in (db.get(KnowledgeClaim, cid) for cid in params.claim_ids) if c]
    else:
        claims = db.all(KnowledgeClaim)

    entities_indexed = db.embed_entities(entities) if entities else 0
    claims_indexed = db.embed_claims(claims) if claims else 0
    result = {
        "entities_indexed": entities_indexed,
        "claims_indexed": claims_indexed,
    }
    # Emit the supplied subset (lean): for a full reindex the bare type signals a
    # global semantic-index refresh without flooding the event with every id.
    spec = ChangeSpec(
        domains=["search"],
        target_ids=[],
        before=None,
        after=result,
        emit_type="search.reindexed",
        entity_ids=list(params.entity_ids or []),
        claim_ids=list(params.claim_ids or []),
    )
    return result, spec


# =============================================================================
# search.query (#4115) — search as ONE audited action
# =============================================================================
#
# The chat/agent tool loop (#1847) exposes read_only actions as tools, but
# until now search itself was not an action — the model could REINDEX the
# library yet never RUN a search. search.query wraps the SAME retrieval
# pipeline /api/search uses (_run_content_search_sync → Database.search:
# hybrid vector+FTS with RRF fusion, honest total_count, typed failures), so
# the results grid and the chat agent share one implementation with one audit
# trail. This is the first read_only action in the registry.


class SearchQueryParams(BaseModel):
    """``search.query`` — run a library search and return ranked hits."""

    query: str = Field(description="The search query text")
    limit: int = Field(default=10, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
    search_type: str = Field(
        default="hybrid", description="'hybrid', 'semantic', or 'fulltext'"
    )
    # 0.55 mirrors SearchRequest.min_score — the engine's noise floor (#1054).
    min_score: float = Field(default=0.55, ge=0.0, le=1.0)
    folder_id: str | None = Field(
        default=None, description="Scope to a folder (descendants included)"
    )
    sort_by: str = Field(default="relevance")
    sort_direction: str = Field(default="desc")


@action(
    "search.query",
    SearchQueryParams,
    domains=["search"],
    undoable=False,
    read_only=True,
)
def _action_search_query(
    db: Database, params: SearchQueryParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    """Run the library's hybrid search — the one retrieval tool (#4115)."""
    request = SearchRequest(
        query=params.query,
        limit=params.limit,
        offset=params.offset,
        search_type=params.search_type,
        min_score=params.min_score,
        filters={"folder_id": params.folder_id} if params.folder_id else None,
        sort_by=params.sort_by,
        sort_direction=params.sort_direction,
        include=[SearchInclude.content],
    )
    results, total_count, _stats = _run_content_search_sync(
        db, request, params.query
    )
    # db.SearchResult is a dataclass, not a pydantic model.
    result = {
        "results": [asdict(r) for r in results],
        "total_results": total_count,
        "has_more": params.offset + len(results) < total_count,
    }
    # Read-only: nothing changed, nothing to emit — the audit row invoke()
    # writes is the point (what was searched, by whom).
    spec = ChangeSpec(domains=["search"])
    return result, spec
