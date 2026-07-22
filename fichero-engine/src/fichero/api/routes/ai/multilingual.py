"""Multilingual API Routes for cross-language search and language detection.

Provides REST endpoints for:
- Language detection
- Cross-language entity search
- Language-aware claim filtering
- Transliteration matching
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from fichero.db import db_manager
from fichero.api.library_header import require_library_path
from fichero.api.main import assert_library_read_authorized
from fichero.models.knowledge import KnowledgeEntity, KnowledgeClaim
from fichero.multilingual import (
    detect_language,
    find_cross_language_matches,
    get_transliteration_variants,
    normalize_text,
    stem_text,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/multilingual", tags=["multilingual"])


class NormalizeRequest(BaseModel):
    text: str = ""
    language: str = "en"
    stemming: bool = False


class NormalizeResponse(BaseModel):
    original: str
    normalized: str
    language: str
    stemming: bool


class ClaimSummary(BaseModel):
    id: str
    text: str
    language: str | None
    source_languages: list[str]
    source_document_id: str


class ClaimsPageResponse(BaseModel):
    claims: list[ClaimSummary]
    total: int
    language: str
    limit: int
    offset: int


class EntitySummary(BaseModel):
    id: str
    canonical_name: str
    entity_type: str
    language: str | None
    aliases: list[str]


class EntitiesPageResponse(BaseModel):
    entities: list[EntitySummary]
    total: int
    language: str
    limit: int
    offset: int


# Request/Response Models


class DetectLanguageRequest(BaseModel):
    """Request to detect language of text."""

    text: str = Field(..., description="Text to analyze", min_length=1)


class DetectLanguageResponse(BaseModel):
    """Language detection result."""

    language: str = Field(..., description="ISO 639-1 language code")
    language_name: str = Field(..., description="Human-readable language name")
    confidence: float = Field(..., ge=0.0, le=1.0)
    is_reliable: bool = Field(..., description="Whether detection is reliable")


class TransliterationRequest(BaseModel):
    """Request to get transliteration variants."""

    text: str = Field(..., description="Text to transliterate")
    language: str = Field(..., description="Source language (ISO 639-1)")


class TransliterationResponse(BaseModel):
    """Transliteration variants."""

    original: str = Field(..., description="Original text")
    language: str = Field(..., description="Source language")
    variants: list[str] = Field(default_factory=list, description="Transliteration variants")


class CrossLanguageSearchRequest(BaseModel):
    """Request for cross-language entity search."""

    query: str = Field(..., description="Search query", min_length=1)
    entity_type: Optional[str] = Field(None, description="Filter by entity type")
    limit: int = Field(20, ge=1, le=100)


class CrossLanguageMatch(BaseModel):
    """A cross-language search match."""

    entity_id: str = Field(..., description="Entity ID")
    canonical_name: str = Field(..., description="Entity canonical name")
    entity_type: str = Field(..., description="Entity type")
    language: str = Field(..., description="Entity language")
    score: float = Field(..., ge=0.0, le=1.0, description="Match score")


class CrossLanguageSearchResponse(BaseModel):
    """Cross-language search results."""

    query: str = Field(..., description="Original query")
    detected_language: str = Field(..., description="Detected query language")
    matches: list[CrossLanguageMatch] = Field(default_factory=list)
    total: int = Field(..., description="Total matches")


class LanguageFilterResponse(BaseModel):
    """Response for language-filtered claims."""

    claims: list[dict[str, Any]] = Field(default_factory=list)
    total: int = Field(...)
    language: str = Field(...)


# Endpoints


@router.post(
    "/detect",
    response_model=DetectLanguageResponse,
    summary="Detect language",
    description="Detect the language of provided text.",
)
async def detect_language_endpoint(
    request: DetectLanguageRequest,
    x_fichero_library_path: str = Depends(require_library_path),
) -> DetectLanguageResponse:
    """Detect language of text."""
    result = detect_language(request.text)

    language_names = {
        "en": "English",
        "es": "Spanish",
        "fr": "French",
        "de": "German",
        "it": "Italian",
        "pt": "Portuguese",
        "nl": "Dutch",
        "ja": "Japanese",
        "ko": "Korean",
        "zh": "Chinese",
        "ar": "Arabic",
        "hi": "Hindi",
        "ru": "Russian",
        "tr": "Turkish",
        "vi": "Vietnamese",
        "th": "Thai",
        "sv": "Swedish",
        "da": "Danish",
        "no": "Norwegian",
        "fi": "Finnish",
        "pl": "Polish",
        "he": "Hebrew",
    }

    return DetectLanguageResponse(
        language=result.language,
        language_name=language_names.get(result.language, "Unknown"),
        confidence=result.confidence,
        is_reliable=result.is_reliable,
    )


@router.post(
    "/transliterate",
    response_model=TransliterationResponse,
    summary="Get transliteration variants",
    description="Get transliteration variants for cross-language matching.",
)
async def transliterate_endpoint(
    request: TransliterationRequest,
    x_fichero_library_path: str = Depends(require_library_path),
) -> TransliterationResponse:
    """Get transliteration variants."""
    variants = get_transliteration_variants(request.text, request.language)

    return TransliterationResponse(
        original=request.text,
        language=request.language,
        variants=variants,
    )


@router.post(
    "/entities/search",
    response_model=CrossLanguageSearchResponse,
    summary="Cross-language entity search",
    description="Search for entities across languages using transliteration matching.",
)
async def cross_language_entity_search(
    request: CrossLanguageSearchRequest,
    http_request: Request,
    x_fichero_library_path: str = Depends(require_library_path),
) -> CrossLanguageSearchResponse:
    """Search entities across languages."""
    assert_library_read_authorized(http_request, x_fichero_library_path)
    db = db_manager.get_database(x_fichero_library_path)

    # Detect query language
    lang_result = detect_language(request.query)
    query_lang = lang_result.language

    # Get all entities (in real implementation, this would use vector search first)
    entities = db.all(KnowledgeEntity)

    # Build candidates list
    candidates = []
    for entity in entities:
        # Use entity name and aliases for matching
        text = entity.canonical_name
        lang = entity.language or "en"

        if request.entity_type and entity.entity_type.value != request.entity_type:
            continue

        candidates.append((entity.id, text, lang))

        # Also check aliases
        for alias in entity.aliases:
            candidates.append((entity.id, alias, lang))

    # Find cross-language matches
    matches_data = find_cross_language_matches(
        request.query, candidates, threshold=0.5
    )

    # Build response
    seen_ids = set()
    matches = []

    for entity_id, score in matches_data[: request.limit]:
        if entity_id in seen_ids:
            continue
        seen_ids.add(entity_id)

        entity = db.get(KnowledgeEntity, entity_id)
        if entity:
            matches.append(
                CrossLanguageMatch(
                    entity_id=entity.id,
                    canonical_name=entity.canonical_name,
                    entity_type=entity.entity_type.value,
                    language=entity.language or "unknown",
                    score=score,
                )
            )

    return CrossLanguageSearchResponse(
        query=request.query,
        detected_language=query_lang,
        matches=matches,
        total=len(matches),
    )


@router.get(
    "/claims",
    summary="Get claims by language",
    description="Filter claims by source language.",
)
async def get_claims_by_language(
    request: Request,
    source_language: str = Query(..., description="ISO 639-1 language code"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    x_fichero_library_path: str = Depends(require_library_path),
) -> ClaimsPageResponse:
    """Get claims filtered by source language."""
    assert_library_read_authorized(request, x_fichero_library_path)
    db = db_manager.get_database(x_fichero_library_path)

    all_claims = db.all(KnowledgeClaim)
    filtered = [
        c for c in all_claims
        if c.language == source_language or source_language in (c.source_languages or [])
    ]

    total = len(filtered)
    paginated = filtered[offset : offset + limit]

    return ClaimsPageResponse(
        claims=[
            ClaimSummary(
                id=c.id,
                text=c.text,
                language=c.language,
                source_languages=c.source_languages or [],
                source_document_id=c.source_document_id,
            )
            for c in paginated
        ],
        total=total,
        language=source_language,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/entities",
    summary="Get entities by language",
    description="Filter entities by language.",
)
async def get_entities_by_language(
    request: Request,
    language: str = Query(..., description="ISO 639-1 language code"),
    entity_type: Optional[str] = Query(None, description="Filter by entity type"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    x_fichero_library_path: str = Depends(require_library_path),
) -> EntitiesPageResponse:
    """Get entities filtered by language."""
    assert_library_read_authorized(request, x_fichero_library_path)
    db = db_manager.get_database(x_fichero_library_path)

    all_entities = db.all(KnowledgeEntity)
    filtered = [
        e for e in all_entities
        if e.language == language
        and (not entity_type or e.entity_type.value == entity_type)
    ]

    total = len(filtered)
    paginated = filtered[offset : offset + limit]

    return EntitiesPageResponse(
        entities=[
            EntitySummary(
                id=e.id,
                canonical_name=e.canonical_name,
                entity_type=e.entity_type.value,
                language=e.language,
                aliases=e.aliases or [],
            )
            for e in paginated
        ],
        total=total,
        language=language,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/normalize",
    response_model=NormalizeResponse,
    summary="Normalize text",
    description="Normalize text for the given language.",
)
async def normalize_endpoint(
    request: NormalizeRequest,
    x_fichero_library_path: str = Depends(require_library_path),
) -> NormalizeResponse:
    """Normalize text for a language."""
    normalized = normalize_text(request.text, request.language)

    if request.stemming:
        normalized = stem_text(normalized, request.language)

    return NormalizeResponse(
        original=request.text,
        normalized=normalized,
        language=request.language,
        stemming=request.stemming,
    )
