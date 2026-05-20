"""Entities API - Canonical FastAPI routes for knowledge entities.

This module implements dedicated routes for knowledge entity operations,
providing a clean separation from the broader knowledge graph functionality.
"""

from __future__ import annotations

import logging
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
from fichero.models import EntityListResponse, EntityCoOccurrenceListResponse, EntityDocumentListResponse, TopEntityListResponse

logger = logging.getLogger(__name__)

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


@router.get("", response_model=EntityListResponse)
async def list_entities(
    q: Annotated[str | None, Query()] = None,
    entity_type: Annotated[EntityType | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    db: Database = Depends(get_library_database),
) -> EntityListResponse:
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
    items = entities[:limit]
    return EntityListResponse(items=items, count=len(items))


# =============================================================================
# Entity Alias Management
# =============================================================================


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


class TopEntityRow(BaseModel):
    """One row of /entities/top — most-claimed entity in the library
    with name, kind, alias list, and claim count.
    """

    entity_id: str
    name: str
    kind: str | None = None
    aliases: list[str] = []
    claim_count: int


@router.get("/top", response_model=TopEntityListResponse)
async def top_entities(
    entity_type: Annotated[EntityType | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 30,
    db: Database = Depends(get_library_database),
) -> TopEntityListResponse:
    """Top-N entities by claim count across the whole library.

    Powers a 'Who's in this archive?' entry-point — the catalogue
    workflow extracts entities per page; this aggregates per-entity
    claim counts so the user can browse by salience instead of
    typing a name they already know.

    Optional `entity_type` filter (people / places / organizations
    / dates / events / other) restricts the cloud to one kind.
    """
    try:
        rows = db.conn.execute(
            "SELECT entity_ids FROM knowledgeclaims",
        ).fetchall()
    except Exception as exc:  # noqa: BLE001
        logger.warning("top-entities lookup failed: %s", exc)
        return TopEntityListResponse(items=[], count=0)

    import json as _json
    from collections import Counter

    counter: Counter[str] = Counter()
    for (raw,) in rows:
        if not raw:
            continue
        try:
            ids = _json.loads(raw) if isinstance(raw, str) else raw
        except (TypeError, ValueError):
            continue
        if isinstance(ids, list):
            for eid in ids:
                if isinstance(eid, str) and eid:
                    counter[eid] += 1

    if not counter:
        return TopEntityListResponse(items=[], count=0)

    type_filter = entity_type.value if entity_type else None
    out: list[TopEntityRow] = []
    for eid, count in counter.most_common(limit * 2 if type_filter else limit):
        ent = db.get(KnowledgeEntity, eid)
        if ent is None:
            continue
        kind_val = getattr(ent, "entity_type", None)
        kind_str = kind_val.value if hasattr(kind_val, "value") else (
            str(kind_val) if kind_val else None
        )
        if type_filter and kind_str != type_filter:
            continue
        out.append(
            TopEntityRow(
                entity_id=ent.id,
                name=ent.canonical_name,
                kind=kind_str,
                aliases=list(getattr(ent, "aliases", []) or []),
                claim_count=count,
            )
        )
        if len(out) >= limit:
            break
    return TopEntityListResponse(items=out, count=len(out))


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


class EntityPatchRequest(BaseModel):
    """Partial update — only fields present in the payload are written.

    Every editable attribute is here as ``Optional`` so PATCH can
    target a single field without losing the rest. (#901)
    """
    canonical_name: str | None = None
    entity_type: EntityType | None = None
    aliases: list[str] | None = None
    description: str | None = None
    language: str | None = None
    metadata: dict | None = None


@router.patch("/{entity_id}", response_model=KnowledgeEntity)
async def patch_entity(
    entity_id: str,
    request: EntityPatchRequest,
    db: Database = Depends(get_library_database),
) -> KnowledgeEntity:
    """Partial-update a knowledge entity.

    Refreshes the entity's vector in LanceDB after the write so
    semantic-dedup keeps working. (#899 Phase B + #901)
    """
    entity = db.get(KnowledgeEntity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail=f"Entity not found: {entity_id}")

    # Snapshot the before-state for the MutationLog so this edit is
    # reversible via /api/kg/undo. (#901)
    before_state = entity.model_dump(mode="json")

    changed_fields: list[str] = []
    if request.canonical_name is not None:
        entity.canonical_name = request.canonical_name.strip()
        changed_fields.append("canonical_name")
    if request.entity_type is not None:
        entity.entity_type = request.entity_type
        changed_fields.append("entity_type")
    if request.aliases is not None:
        entity.aliases = sorted(set(a.strip() for a in request.aliases if a.strip()))
        changed_fields.append("aliases")
    if request.description is not None:
        entity.description = request.description
        changed_fields.append("description")
    if request.language is not None:
        entity.language = request.language
        changed_fields.append("language")
    if request.metadata is not None:
        entity.metadata = request.metadata
        changed_fields.append("metadata")
    entity.updated_at = datetime.now()
    db.save(entity)

    # Mutation log row — captures before + after for undo.
    try:
        from fichero.knowledge_models import MutationLog, MutationOperationType
        db.save(MutationLog(
            entity_type="KnowledgeEntity",
            entity_id=entity.id,
            operation=MutationOperationType.update,
            before_state=before_state,
            after_state=entity.model_dump(mode="json"),
            changed_fields=changed_fields,
        ))
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning(
            "patch_entity: mutation log write failed: %s", exc
        )

    # Refresh the LanceDB vector so cosine search reflects the edit.
    try:
        from fichero.kg import entity_vectors
        entity_vectors.index_entity(
            db=db,
            entity_id=entity.id,
            entity_type=entity.entity_type,
            canonical_name=entity.canonical_name,
            description=entity.description,
        )
    except Exception as exc:
        # Don't fail the API call if vector refresh fails — the
        # DuckDB row is the canonical store.
        import logging
        logging.getLogger(__name__).warning(
            "patch_entity: vector refresh failed for %s: %s", entity.id, exc
        )

    return entity


@router.delete("/{entity_id}", status_code=204)
async def delete_entity(
    entity_id: str,
    cascade_claims: bool = Query(
        default=False,
        description=(
            "When true, also delete every claim that references this "
            "entity. When false (default), claims keep their entity_ids "
            "list intact but with this id stripped — preserves "
            "provenance for claims that mention multiple entities."
        ),
    ),
    db: Database = Depends(get_library_database),
) -> None:
    """Hard-delete a knowledge entity.

    Side effects:
    - Removes the entity's vector from LanceDB.
    - Either cascades to dependent claims (``cascade_claims=true``)
      or strips this id from each claim's ``entity_ids`` (default).
    (#901)
    """
    entity = db.get(KnowledgeEntity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail=f"Entity not found: {entity_id}")

    # Snapshot before-state for undo. (#901)
    before_state = entity.model_dump(mode="json")

    # Find dependent claims.
    from fichero.knowledge_models import KnowledgeClaim
    all_claims = db.query(KnowledgeClaim)
    dependent = [c for c in all_claims if entity_id in (c.entity_ids or [])]

    if cascade_claims:
        for claim in dependent:
            db.delete(claim)
    else:
        # Strip the id but keep the claim row.
        for claim in dependent:
            claim.entity_ids = [eid for eid in (claim.entity_ids or []) if eid != entity_id]
            claim.updated_at = datetime.now()
            db.save(claim)

    # Drop the vector.
    try:
        from fichero.kg import entity_vectors
        entity_vectors.remove(db=db, entity_id=entity_id)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning(
            "delete_entity: vector remove failed for %s: %s", entity_id, exc
        )

    db.delete(entity)

    # Mutation log row.
    try:
        from fichero.knowledge_models import MutationLog, MutationOperationType
        db.save(MutationLog(
            entity_type="KnowledgeEntity",
            entity_id=entity_id,
            operation=MutationOperationType.delete,
            before_state=before_state,
            after_state=None,
        ))
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning(
            "delete_entity: mutation log write failed: %s", exc
        )


class EntityDocumentLink(BaseModel):
    """One row of /entities/{id}/documents — document that mentions
    this entity at least once via a knowledge claim, with the smallest
    relevant excerpt and the count of claims linking them.
    """

    document_id: str
    document_name: str | None = None
    doc_type: str | None = None
    file_type: str | None = None
    claim_count: int
    first_excerpt: str | None = None


class EntityCoOccurrence(BaseModel):
    """One row of /entities/{id}/co-occurrence — another entity that
    appears in at least one claim alongside this one, with the count
    of shared claims.
    """

    entity_id: str
    name: str
    kind: str | None = None
    aliases: list[str] = []
    shared_claims: int


@router.get("/{entity_id}/documents", response_model=EntityDocumentListResponse)
async def get_entity_documents(
    entity_id: str,
    limit: int = 100,
    db: Database = Depends(get_library_database),
) -> EntityDocumentListResponse:
    """Documents that mention `entity_id` via a knowledge claim.

    Powers the cross-document entity drill-down (#729): clicking
    "Asprilla" should show every document where Asprilla appears,
    sorted by claim density. The result includes a small excerpt so
    the UI can render context preview without a second fetch.

    JSON-LIKE filter on claim.entity_ids is the simplest path that
    works across DuckDB versions — exact-match for the entity id
    embedded in the JSON-serialised list. Returns deduped per-doc
    rows with claim counts as a second-pass aggregation.
    """
    entity = db.get(KnowledgeEntity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail=f"Entity not found: {entity_id}")

    needle = f'%"{entity_id}"%'
    try:
        rows = db.conn.execute(
            """
            SELECT c.source_document_id,
                   d.name,
                   d.doc_type,
                   d.file_type,
                   COUNT(*) AS claim_count,
                   MIN(c.source_excerpt) AS first_excerpt
            FROM knowledgeclaims c
            LEFT JOIN documents d ON d.id = c.source_document_id
            WHERE c.entity_ids LIKE $needle
            GROUP BY c.source_document_id, d.name, d.doc_type, d.file_type
            ORDER BY claim_count DESC, d.name
            LIMIT $limit
            """,
            {"needle": needle, "limit": limit},
        ).fetchall()
    except Exception as exc:  # noqa: BLE001
        logger.warning("entity-documents lookup failed: %s", exc)
        return EntityDocumentListResponse(items=[], count=0)

    items = [
        EntityDocumentLink(
            document_id=row[0],
            document_name=row[1],
            doc_type=row[2],
            file_type=row[3],
            claim_count=int(row[4] or 0),
            first_excerpt=row[5],
        )
        for row in rows
        if row[0]
    ]
    return EntityDocumentListResponse(items=items, count=len(items))


@router.get("/{entity_id}/co-occurrence", response_model=EntityCoOccurrenceListResponse)
async def get_entity_co_occurrence(
    entity_id: str,
    limit: int = 50,
    db: Database = Depends(get_library_database),
) -> EntityCoOccurrenceListResponse:
    """Entities that share at least one claim with `entity_id`.

    Powers a 'related entities' rail in the entity drill-down — see
    Asprilla → also see the people, places, organisations who appear
    in the same claims. Sorted by number of shared claims.

    Walks claims rather than entities. JSON-LIKE on entity_ids is the
    same shape as get_entity_documents.
    """
    entity = db.get(KnowledgeEntity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail=f"Entity not found: {entity_id}")

    needle = f'%"{entity_id}"%'
    try:
        claim_rows = db.conn.execute(
            "SELECT entity_ids FROM knowledgeclaims WHERE entity_ids LIKE $needle",
            {"needle": needle},
        ).fetchall()
    except Exception as exc:  # noqa: BLE001
        logger.warning("co-occurrence lookup failed: %s", exc)
        return EntityCoOccurrenceListResponse(items=[], count=0)

    import json as _json
    from collections import Counter

    counter: Counter[str] = Counter()
    for (raw,) in claim_rows:
        if not raw:
            continue
        try:
            ids = _json.loads(raw) if isinstance(raw, str) else raw
        except (TypeError, ValueError):
            continue
        if not isinstance(ids, list):
            continue
        for other in ids:
            if isinstance(other, str) and other and other != entity_id:
                counter[other] += 1

    if not counter:
        return EntityCoOccurrenceListResponse(items=[], count=0)

    top_ids = [eid for eid, _count in counter.most_common(limit)]
    out: list[EntityCoOccurrence] = []
    for other_id in top_ids:
        other = db.get(KnowledgeEntity, other_id)
        if other is None:
            continue
        kind_val = getattr(other, "entity_type", None)
        kind_str = kind_val.value if hasattr(kind_val, "value") else (
            str(kind_val) if kind_val else None
        )
        out.append(
            EntityCoOccurrence(
                entity_id=other.id,
                name=other.canonical_name,
                kind=kind_str,
                aliases=list(getattr(other, "aliases", []) or []),
                shared_claims=counter[other_id],
            )
        )
    return EntityCoOccurrenceListResponse(items=out, count=len(out))


class EntityDrillDownResponse(BaseModel):
    """Bundle response for /entities/{id}/drill-down — three lists in
    one call so the inspector renders an entity-detail view from one
    fetch instead of three round-trips.
    """

    entity: KnowledgeEntity
    documents: list[EntityDocumentLink]
    co_occurring: list[EntityCoOccurrence]
    claim_excerpts: list[str]


@router.get("/{entity_id}/drill-down", response_model=EntityDrillDownResponse)
async def entity_drill_down(
    entity_id: str,
    documents_limit: int = 20,
    co_occurrence_limit: int = 10,
    excerpts_limit: int = 5,
    db: Database = Depends(get_library_database),
) -> EntityDrillDownResponse:
    """Three-rail entity detail in one fetch.

    Combines /documents (where this entity appears), /co-occurrence
    (related entities), and a list of representative claim excerpts.
    Frontend renders an Inspector panel with three sections from
    a single round-trip — useful for the cross-doc entity navigation
    UI tracked in #729.
    """
    entity = db.get(KnowledgeEntity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail=f"Entity not found: {entity_id}")

    documents = await get_entity_documents(entity_id, limit=documents_limit, db=db)
    co_occurring = await get_entity_co_occurrence(
        entity_id, limit=co_occurrence_limit, db=db
    )

    needle = f'%"{entity_id}"%'
    excerpts: list[str] = []
    try:
        rows = db.conn.execute(
            """
            SELECT source_excerpt FROM knowledgeclaims
            WHERE entity_ids LIKE $needle
              AND source_excerpt IS NOT NULL
              AND length(source_excerpt) > 0
            ORDER BY length(source_excerpt) ASC
            LIMIT $limit
            """,
            {"needle": needle, "limit": excerpts_limit},
        ).fetchall()
    except Exception as exc:  # noqa: BLE001
        logger.warning("excerpt lookup failed: %s", exc)
        rows = []
    for (excerpt,) in rows:
        if excerpt:
            excerpts.append(excerpt)

    return EntityDrillDownResponse(
        entity=entity,
        documents=documents,
        co_occurring=co_occurring,
        claim_excerpts=excerpts,
    )


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

