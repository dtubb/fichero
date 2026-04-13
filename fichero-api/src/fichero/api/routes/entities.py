"""Entities API - Canonical FastAPI routes for knowledge entities.

This module implements dedicated routes for knowledge entity operations,
providing a clean separation from the broader knowledge graph functionality.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from fichero.api.main import get_library_database
from fichero.db import Database
from fichero.knowledge_models import (
    EntityMergeOperationType,
    EntityType,
    KnowledgeEntity,
)

router = APIRouter(prefix="/entities", tags=["entities"])


# =============================================================================
# Request/Response Models
# =============================================================================


class EntityUpsertRequest(BaseModel):
    """Request to create or update a knowledge entity."""

    id: str | None = None
    canonical_name: str
    entity_type: EntityType = EntityType.other
    aliases: list[str] = Field(default_factory=list)
    description: str | None = None
    language: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EntityAliasRequest(BaseModel):
    """Request to add aliases to an entity."""

    aliases: list[str]


class EntityAliasMapEntry(BaseModel):
    """A single alias mapped to its entity."""

    alias: str
    entity_id: str
    canonical_name: str


class EntityAliasMapResponse(BaseModel):
    """Full alias → entity map for reviewer decisions."""

    entries: list[EntityAliasMapEntry]


class EntityResolutionResponse(BaseModel):
    """Response from resolving a lookup value to an entity."""

    resolved: bool
    value: str
    entity_id: str | None = None
    canonical_name: str | None = None
    entity_type: EntityType | None = None
    match_type: str | None = None  # "id", "canonical_name", "alias"


class EntityMergeRequest(BaseModel):
    """Request to merge multiple entities into one."""

    absorbing_entity_id: str = Field(
        description="Entity that absorbs the others (survivor)"
    )
    absorbed_entity_ids: list[str] = Field(
        description="Entities to be merged into the absorber"
    )
    merged_aliases: list[str] = Field(
        default_factory=list,
        description="Aliases from absorbed entities to add to the absorbing entity",
    )
    merged_description: str | None = Field(
        default=None,
        description="Optional override description for the absorbing entity",
    )


class EntitySplitRequest(BaseModel):
    """Request to split an entity into multiple entities."""

    primary_entity_id: str = Field(description="Entity that retains canonical identity")
    split_off_entity_ids: list[str] = Field(
        description="Entities to create from the split"
    )
    aliases_to_move: list[str] = Field(
        default_factory=list,
        description="Aliases from primary to move to the split-off entities",
    )


class EntityAuditResponse(BaseModel):
    """Response from entity merge/split/undo operations."""

    id: str
    operation_type: EntityMergeOperationType
    source_entity_ids: list[str]
    target_entity_id: str
    alias_changes: dict
    reversal_id: str | None
    created_by: str
    created_at: datetime


# =============================================================================
# Helper Functions
# =============================================================================


def _normalize_text(value: str | None) -> str:
    """Normalize text for comparison."""
    return (value or "").strip().lower()


def _build_alias_to_entity_id_map(db: Database) -> dict[str, str]:
    """Build a mapping of normalized aliases to entity IDs."""
    alias_map: dict[str, str] = {}
    for entity in db.all(KnowledgeEntity):
        # Map canonical name
        alias_map[_normalize_text(entity.canonical_name)] = entity.id
        # Map aliases
        for alias in entity.aliases:
            alias_map[_normalize_text(alias)] = entity.id
    return alias_map


# =============================================================================
# Entity CRUD Endpoints
# =============================================================================


@router.post("", response_model=KnowledgeEntity)
async def upsert_entity(
    request: EntityUpsertRequest,
    db: Database = Depends(get_library_database),
) -> KnowledgeEntity:
    """Create or update a knowledge entity."""
    entity = db.get(KnowledgeEntity, request.id) if request.id else None
    now = datetime.now()
    if entity is None:
        entity = KnowledgeEntity(
            canonical_name=request.canonical_name.strip(),
            entity_type=request.entity_type,
            aliases=sorted(set(a.strip() for a in request.aliases if a.strip())),
            description=request.description,
            language=request.language,
            metadata=request.metadata,
            created_at=now,
            updated_at=now,
        )
    else:
        entity.canonical_name = request.canonical_name.strip()
        entity.entity_type = request.entity_type
        entity.aliases = sorted(set(a.strip() for a in request.aliases if a.strip()))
        entity.description = request.description
        entity.language = request.language
        entity.metadata = request.metadata
        entity.updated_at = now
    db.save(entity)
    return entity


@router.get("", response_model=list[KnowledgeEntity])
async def list_entities(
    q: Annotated[str | None, Query()] = None,
    entity_type: Annotated[EntityType | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    db: Database = Depends(get_library_database),
) -> list[KnowledgeEntity]:
    """List knowledge entities with optional filtering."""
    entities = (
        db.query(KnowledgeEntity, entity_type=entity_type)
        if entity_type
        else db.all(KnowledgeEntity)
    )
    needle = _normalize_text(q)
    if needle:
        entities = [
            entity
            for entity in entities
            if needle in _normalize_text(entity.canonical_name)
            or any(needle in _normalize_text(alias) for alias in entity.aliases)
        ]
    entities.sort(key=lambda entity: entity.canonical_name.lower())
    return entities[:limit]


@router.get("/{entity_id}", response_model=KnowledgeEntity)
async def get_entity(
    entity_id: str,
    db: Database = Depends(get_library_database),
) -> KnowledgeEntity:
    """Get a knowledge entity by ID."""
    entity = db.get(KnowledgeEntity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail=f"Entity not found: {entity_id}")
    return entity


# =============================================================================
# Entity Alias Management
# =============================================================================


@router.post("/{entity_id}/aliases", response_model=KnowledgeEntity)
async def add_entity_aliases(
    entity_id: str,
    request: EntityAliasRequest,
    db: Database = Depends(get_library_database),
) -> KnowledgeEntity:
    """Add aliases to an existing entity."""
    entity = db.get(KnowledgeEntity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail=f"Entity not found: {entity_id}")
    merged = set(entity.aliases)
    merged.update(a.strip() for a in request.aliases if a.strip())
    entity.aliases = sorted(merged)
    entity.updated_at = datetime.now()
    db.save(entity)
    return entity


@router.get("/alias-map", response_model=EntityAliasMapResponse)
async def get_entity_alias_map(
    db: Database = Depends(get_library_database),
) -> EntityAliasMapResponse:
    """Return the full alias → entity mapping for reviewer decisions."""
    entries: list[EntityAliasMapEntry] = []
    seen: set[str] = set()
    for entity in db.all(KnowledgeEntity):
        # Canonical name as an alias entry
        norm_canonical = _normalize_text(entity.canonical_name)
        if norm_canonical not in seen:
            entries.append(
                EntityAliasMapEntry(
                    alias=entity.canonical_name,
                    entity_id=entity.id,
                    canonical_name=entity.canonical_name,
                )
            )
            seen.add(norm_canonical)
        # Alias entries
        for alias in entity.aliases:
            norm_alias = _normalize_text(alias)
            if norm_alias not in seen:
                entries.append(
                    EntityAliasMapEntry(
                        alias=alias,
                        entity_id=entity.id,
                        canonical_name=entity.canonical_name,
                    )
                )
                seen.add(norm_alias)
    entries.sort(key=lambda e: e.alias.lower())
    return EntityAliasMapResponse(entries=entries)


@router.get("/resolve/{value}", response_model=EntityResolutionResponse)
async def resolve_entity(
    value: str,
    db: Database = Depends(get_library_database),
) -> EntityResolutionResponse:
    """Resolve a lookup value (UUID, canonical name, or alias) to an entity."""
    entity = db.get(KnowledgeEntity, value)
    if entity is not None:
        return EntityResolutionResponse(
            resolved=True,
            value=value,
            entity_id=entity.id,
            canonical_name=entity.canonical_name,
            entity_type=entity.entity_type,
            match_type="id",
        )
    # Try canonical name / alias
    alias_map = _build_alias_to_entity_id_map(db)
    resolved_id = alias_map.get(_normalize_text(value))
    if resolved_id is not None:
        entity = db.get(KnowledgeEntity, resolved_id)
        if entity is not None:
            return EntityResolutionResponse(
                resolved=True,
                value=value,
                entity_id=entity.id,
                canonical_name=entity.canonical_name,
                entity_type=entity.entity_type,
                match_type="canonical_name"
                if _normalize_text(value) == _normalize_text(entity.canonical_name)
                else "alias",
            )
    return EntityResolutionResponse(resolved=False, value=value, match_type=None)
