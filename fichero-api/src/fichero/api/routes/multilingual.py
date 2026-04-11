"""Multilingual API Routes for cross-language search and language detection.

Provides REST endpoints for:
- Language detection
- Cross-language entity search
- Language-aware claim filtering
- Transliteration matching
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, Header, Query
from pydantic import BaseModel, Field

from fichero.db import db_manager
from fichero.knowledge_models import KnowledgeEntity, KnowledgeClaim
from fichero.multilingual import (
    detect_language,
    find_cross_language_matches,
    get_transliteration_variants,
    normalize_text,
    stem_text,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/multilingual", tags=["multilingual"])


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
    x_fichero_library_path: str = Header(..., description="Library path"),
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
    x_fichero_library_path: str = Header(..., description="Library path"),
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
    x_fichero_library_path: str = Header(..., description="Library path"),
) -> CrossLanguageSearchResponse:
    """Search entities across languages."""
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
    response_model=dict,
    summary="Get claims by language",
    description="Filter claims by source language.",
)
async def get_claims_by_language(
    source_language: str = Query(..., description="ISO 639-1 language code"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    x_fichero_library_path: str = Header(..., description="Library path"),
) -> dict:
    """Get claims filtered by source language."""
    db = db_manager.get_database(x_fichero_library_path)

    # Get all claims and filter by language
    all_claims = db.all(KnowledgeClaim)
    filtered = []

    for claim in all_claims:
        # Check if claim language matches or if source_languages contains the language
        claim_langs = claim.source_languages or []
        if claim.language == source_language or source_language in claim_langs:
            filtered.append(claim)

    # Apply pagination
    total = len(filtered)
    paginated = filtered[offset : offset + limit]

    return {
        "claims": [
            {
                "id": c.id,
                "text": c.text,
                "language": c.language,
                "source_languages": c.source_languages,
                "source_document_id": c.source_document_id,
            }
            for c in paginated
        ],
        "total": total,
        "language": source_language,
        "limit": limit,
        "offset": offset,
    }


@router.get(
    "/entities",
    response_model=dict,
    summary="Get entities by language",
    description="Filter entities by language.",
)
async def get_entities_by_language(
    language: str = Query(..., description="ISO 639-1 language code"),
    entity_type: Optional[str] = Query(None, description="Filter by entity type"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    x_fichero_library_path: str = Header(..., description="Library path"),
) -> dict:
    """Get entities filtered by language."""
    db = db_manager.get_database(x_fichero_library_path)

    # Get all entities and filter
    all_entities = db.all(KnowledgeEntity)
    filtered = []

    for entity in all_entities:
        if entity.language == language:
            if entity_type and entity.entity_type.value != entity_type:
                continue
            filtered.append(entity)

    # Apply pagination
    total = len(filtered)
    paginated = filtered[offset : offset + limit]

    return {
        "entities": [
            {
                "id": e.id,
                "canonical_name": e.canonical_name,
                "entity_type": e.entity_type.value,
                "language": e.language,
                "aliases": e.aliases,
            }
            for e in paginated
        ],
        "total": total,
        "language": language,
        "limit": limit,
        "offset": offset,
    }


@router.post(
    "/normalize",
    response_model=dict,
    summary="Normalize text",
    description="Normalize text for the given language.",
)
async def normalize_endpoint(
    request: dict,
    x_fichero_library_path: str = Header(..., description="Library path"),
) -> dict:
    """Normalize text for a language."""
    text = request.get("text", "")
    language = request.get("language", "en")
    apply_stemming = request.get("stemming", False)

    normalized = normalize_text(text, language)

    if apply_stemming:
        normalized = stem_text(normalized, language)

    return {
        "original": text,
        "normalized": normalized,
        "language": language,
        "stemming": apply_stemming,
    }
