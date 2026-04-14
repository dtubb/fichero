"""Knowledge graph entity CRUD, merge, split, audit, alias, and semantic search routes."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from fichero.api.main import get_library_database
from fichero.db import Database
from fichero.knowledge_models import (
    EntityMergeAudit,
    EntityMergeOperationType,
    EntityType,
    KnowledgeEntity,
)
from fichero.api.routes.knowledge_graph._shared import (
    KG_ENTITY_EMBEDDINGS_TABLE,
    _normalize_text,
    _build_alias_to_entity_id_map,
)

router = APIRouter()


class EntityUpsertRequest(BaseModel):
    id: str | None = None
    canonical_name: str
    entity_type: EntityType = EntityType.other
    aliases: list[str] = Field(default_factory=list)
    description: str | None = None
    language: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EntityAliasRequest(BaseModel):
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
    primary_entity_id: str = Field(description="Entity that retains canonical identity")
    split_off_entity_ids: list[str] = Field(
        description="Entities to create from the split"
    )
    aliases_to_move: list[str] = Field(
        default_factory=list,
        description="Aliases from primary to move to the split-off entities",
    )


class EntityAuditResponse(BaseModel):
    id: str
    operation_type: EntityMergeOperationType
    source_entity_ids: list[str]
    target_entity_id: str
    alias_changes: dict
    reversal_id: str | None
    created_by: str
    created_at: datetime


class _EmbedEntityRequest(BaseModel):
    entity_ids: list[str] | None = None


# Static sub-paths MUST be defined BEFORE /{entity_id} to avoid
# FastAPI's greedy path-parameter matching swallowing them.

@router.post("/entities/merge", response_model=EntityAuditResponse)
async def merge_entities(
    request: EntityMergeRequest,
    db: Database = Depends(get_library_database),
) -> EntityAuditResponse:
    """Merge multiple entities into a single absorbing entity."""
    absorber = db.get(KnowledgeEntity, request.absorbing_entity_id)
    if absorber is None:
        raise HTTPException(
            status_code=404,
            detail=f"Absorbing entity not found: {request.absorbing_entity_id}",
        )

    absorbed_entities: list[KnowledgeEntity] = []
    for eid in request.absorbed_entity_ids:
        entity = db.get(KnowledgeEntity, eid)
        if entity is None:
            raise HTTPException(
                status_code=404, detail=f"Absorbed entity not found: {eid}"
            )
        if entity.merged_into_id is not None:
            raise HTTPException(
                status_code=409,
                detail=f"Entity {eid} was already merged into {entity.merged_into_id}",
            )
        absorbed_entities.append(entity)

    alias_changes: dict[str, list[str]] = {
        "added": [],
        "removed": [],
        "moved_to": {},
    }
    absorber_aliases = set(absorber.aliases)
    for entity in absorbed_entities:
        for alias in entity.aliases:
            if alias not in absorber_aliases:
                alias_changes["added"].append(alias)
                absorber_aliases.add(alias)
        for alias in entity.aliases:
            alias_changes["moved_to"][alias] = absorber.id
        entity.merged_into_id = absorber.id
        entity.updated_at = datetime.now()
        alias_changes["removed"].extend(entity.aliases)

    for alias in request.merged_aliases:
        stripped = alias.strip()
        if stripped and stripped not in absorber_aliases:
            alias_changes["added"].append(stripped)
            absorber_aliases.add(stripped)

    absorber.aliases = sorted(absorber_aliases)
    if request.merged_description:
        absorber.description = request.merged_description
    absorber.updated_at = datetime.now()

    now = datetime.now()
    audit = EntityMergeAudit(
        operation_type=EntityMergeOperationType.merge,
        source_entity_ids=[e.id for e in absorbed_entities],
        target_entity_id=absorber.id,
        alias_changes=alias_changes,
        created_by="human",
        created_at=now,
    )
    db.save(audit)
    audit.reversal_id = audit.id
    db.save(audit)

    for entity in absorbed_entities:
        db.save(entity)
    db.save(absorber)

    return EntityAuditResponse(
        id=audit.id,
        operation_type=audit.operation_type,
        source_entity_ids=audit.source_entity_ids,
        target_entity_id=audit.target_entity_id,
        alias_changes=audit.alias_changes,
        reversal_id=audit.reversal_id,
        created_by=audit.created_by,
        created_at=audit.created_at,
    )


@router.post("/entities/split", response_model=EntityAuditResponse)
async def split_entity(
    request: EntitySplitRequest,
    db: Database = Depends(get_library_database),
) -> EntityAuditResponse:
    """Split one entity into a primary + new split-off entities."""
    primary = db.get(KnowledgeEntity, request.primary_entity_id)
    if primary is None:
        raise HTTPException(
            status_code=404,
            detail=f"Primary entity not found: {request.primary_entity_id}",
        )

    alias_changes: dict[str, list[str]] = {
        "restored_from": [],
        "moved_to": {},
    }
    moved_alias_set = set(a.strip() for a in request.aliases_to_move if a.strip())
    remaining_aliases = [a for a in primary.aliases if a not in moved_alias_set]
    for alias in moved_alias_set:
        alias_changes["restored_from"].append(alias)

    primary.aliases = remaining_aliases
    primary.updated_at = datetime.now()

    split_entity_ids: list[str] = []
    for split_off_id in request.split_off_entity_ids:
        split_off = db.get(KnowledgeEntity, split_off_id)
        if split_off is None:
            raise HTTPException(
                status_code=404, detail=f"Split-off entity not found: {split_off_id}"
            )
        split_off.merged_into_id = None
        split_off.updated_at = datetime.now()
        db.save(split_off)
        split_entity_ids.append(split_off.id)
        alias_changes["moved_to"][split_off.id] = []

    now = datetime.now()
    audit = EntityMergeAudit(
        operation_type=EntityMergeOperationType.split,
        source_entity_ids=split_entity_ids,
        target_entity_id=primary.id,
        alias_changes=alias_changes,
        created_by="human",
        created_at=now,
    )
    db.save(audit)
    audit.reversal_id = audit.id
    db.save(audit)
    db.save(primary)

    return EntityAuditResponse(
        id=audit.id,
        operation_type=audit.operation_type,
        source_entity_ids=audit.source_entity_ids,
        target_entity_id=audit.target_entity_id,
        alias_changes=audit.alias_changes,
        reversal_id=audit.reversal_id,
        created_by=audit.created_by,
        created_at=audit.created_at,
    )


@router.post("/entities/audit/{audit_id}/undo", response_model=EntityAuditResponse)
async def undo_entity_operation(
    audit_id: str,
    db: Database = Depends(get_library_database),
) -> EntityAuditResponse:
    """Undo a previous merge or split operation using its audit record."""
    audit = db.get(EntityMergeAudit, audit_id)
    if audit is None:
        raise HTTPException(
            status_code=404, detail=f"Audit record not found: {audit_id}"
        )

    if audit.reversal_id != audit.id:
        raise HTTPException(
            status_code=409,
            detail="This operation was already undone or is not directly reversible",
        )

    now = datetime.now()
    if audit.operation_type == EntityMergeOperationType.merge:
        absorber = db.get(KnowledgeEntity, audit.target_entity_id)
        if absorber is None:
            raise HTTPException(
                status_code=404,
                detail=f"Target entity not found: {audit.target_entity_id}",
            )

        alias_changes = audit.alias_changes
        restored_aliases: list[str] = []

        for entity_id in audit.source_entity_ids:
            entity = db.get(KnowledgeEntity, entity_id)
            if entity is None:
                raise HTTPException(
                    status_code=404, detail=f"Source entity not found: {entity_id}"
                )
            entity.merged_into_id = None
            entity.updated_at = now
            db.save(entity)
            for alias, target in alias_changes.get("moved_to", {}).items():
                if target == absorber.id and alias in entity.aliases:
                    restored_aliases.append(alias)

        absorbed_aliases = set(alias_changes.get("added", []))
        absorber.aliases = [a for a in absorber.aliases if a not in absorbed_aliases]
        absorber.updated_at = now
        db.save(absorber)

        undo_alias_changes: dict[str, list[str]] = {
            "added": [],
            "removed": [],
            "moved_to": {},
            "restored_from": restored_aliases,
        }
        undo_audit = EntityMergeAudit(
            operation_type=EntityMergeOperationType.undo_merge,
            source_entity_ids=audit.source_entity_ids,
            target_entity_id=audit.target_entity_id,
            alias_changes=undo_alias_changes,
            reversal_id=audit_id,
            created_by="human",
            created_at=now,
        )
        db.save(undo_audit)
        audit.reversal_id = undo_audit.id
        db.save(audit)

        return EntityAuditResponse(
            id=undo_audit.id,
            operation_type=undo_audit.operation_type,
            source_entity_ids=undo_audit.source_entity_ids,
            target_entity_id=undo_audit.target_entity_id,
            alias_changes=undo_audit.alias_changes,
            reversal_id=undo_audit.reversal_id,
            created_by=undo_audit.created_by,
            created_at=undo_audit.created_at,
        )

    elif audit.operation_type == EntityMergeOperationType.split:
        primary = db.get(KnowledgeEntity, audit.target_entity_id)
        if primary is None:
            raise HTTPException(
                status_code=404,
                detail=f"Primary entity not found: {audit.target_entity_id}",
            )

        alias_changes = audit.alias_changes
        moved_aliases: list[str] = alias_changes.get("restored_from", [])

        primary.aliases = sorted(set(primary.aliases) | set(moved_aliases))
        primary.updated_at = now
        db.save(primary)

        undo_alias_changes = {"restored_from": [], "moved_to": {}}
        undo_audit = EntityMergeAudit(
            operation_type=EntityMergeOperationType.undo_split,
            source_entity_ids=audit.source_entity_ids,
            target_entity_id=audit.target_entity_id,
            alias_changes=undo_alias_changes,
            reversal_id=audit_id,
            created_by="human",
            created_at=now,
        )
        db.save(undo_audit)
        audit.reversal_id = undo_audit.id
        db.save(audit)

        return EntityAuditResponse(
            id=undo_audit.id,
            operation_type=undo_audit.operation_type,
            source_entity_ids=undo_audit.source_entity_ids,
            target_entity_id=undo_audit.target_entity_id,
            alias_changes=undo_audit.alias_changes,
            reversal_id=undo_audit.reversal_id,
            created_by=undo_audit.created_by,
            created_at=undo_audit.created_at,
        )

    else:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot undo operation type: {audit.operation_type}",
        )


@router.get("/entities/audit", response_model=list[EntityAuditResponse])
async def list_entity_audits(
    entity_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: Database = Depends(get_library_database),
) -> list[EntityAuditResponse]:
    """List entity merge/split audit records, optionally filtered by entity."""
    all_audits = db.all(EntityMergeAudit)
    if entity_id:
        all_audits = [
            a
            for a in all_audits
            if a.target_entity_id == entity_id or entity_id in a.source_entity_ids
        ]
    all_audits.sort(key=lambda a: a.created_at, reverse=True)
    return [
        EntityAuditResponse(
            id=a.id,
            operation_type=a.operation_type,
            source_entity_ids=a.source_entity_ids,
            target_entity_id=a.target_entity_id,
            alias_changes=a.alias_changes,
            reversal_id=a.reversal_id,
            created_by=a.created_by,
            created_at=a.created_at,
        )
        for a in all_audits[:limit]
    ]


@router.get("/entities/alias-map", response_model=EntityAliasMapResponse)
async def get_entity_alias_map(
    db: Database = Depends(get_library_database),
) -> EntityAliasMapResponse:
    """Return the full alias → entity mapping for reviewer decisions."""
    entries: list[EntityAliasMapEntry] = []
    seen: set[str] = set()
    for entity in db.all(KnowledgeEntity):
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


@router.get("/entities/resolve/{value}", response_model=EntityResolutionResponse)
async def resolve_entity(
    value: str,
    db: Database = Depends(get_library_database),
) -> EntityResolutionResponse:
    """Resolve a lookup value (UUID, canonical name, or alias) to a canonical entity."""
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


@router.post("/entities/semantic/embed")
async def embed_entities(
    request: _EmbedEntityRequest | None = None,
    db: Database = Depends(get_library_database),
) -> dict[str, Any]:
    """Embed entities into LanceDB for semantic search."""
    if request and request.entity_ids:
        entities = [db.get(KnowledgeEntity, eid) for eid in request.entity_ids]
        entities = [e for e in entities if e is not None]
    else:
        entities = db.all(KnowledgeEntity)

    if not entities:
        return {"embedded": 0, "table": KG_ENTITY_EMBEDDINGS_TABLE}

    texts = [
        e.canonical_name + (" " + " ".join(e.aliases) if e.aliases else "")
        for e in entities
    ]
    vectors = db._embed_texts(texts)  # type: ignore[attr-defined]

    records = [
        {
            "id": e.id,
            "text": e.canonical_name,
            "aliases": e.aliases,
            "entity_type": e.entity_type.value,
            "vector": v,
        }
        for e, v in zip(entities, vectors)
    ]
    db.save_vectors(KG_ENTITY_EMBEDDINGS_TABLE, records)
    return {"embedded": len(records), "table": KG_ENTITY_EMBEDDINGS_TABLE}


@router.get("/entities/semantic")
async def search_entities_semantic(
    q: str = Query(..., description="Natural language query"),
    entity_type: EntityType | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    db: Database = Depends(get_library_database),
) -> list[dict[str, Any]]:
    """Semantic entity search using LanceDB vectors."""
    if KG_ENTITY_EMBEDDINGS_TABLE not in db._lance_tables():
        raise HTTPException(
            status_code=503,
            detail="Entity embeddings not yet indexed. POST /entities/semantic/embed first.",
        )

    try:
        query_vector = db._embed_text(q)  # type: ignore[attr-defined]
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Embedding generation failed: {e}")

    results = db.search_vectors(KG_ENTITY_EMBEDDINGS_TABLE, query_vector, limit=limit)
    entity_ids = [r["id"] for r in results]

    if not entity_ids:
        return []

    entities = {e.id: e for e in db.all(KnowledgeEntity) if e.id in entity_ids}
    filtered = [
        entities[eid]
        for eid in entity_ids
        if eid in entities
        and (entity_type is None or entities[eid].entity_type == entity_type)
    ]

    score_map = {r["id"]: r.get("_score", 0.0) for r in results}
    return [
        {**e.model_dump(), "similarity_score": score_map.get(e.id, 0.0)}
        for e in filtered
    ]


@router.post("/entities", response_model=KnowledgeEntity)
async def upsert_entity(
    request: EntityUpsertRequest,
    db: Database = Depends(get_library_database),
) -> KnowledgeEntity:
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


@router.post("/entities/{entity_id}/aliases", response_model=KnowledgeEntity)
async def add_entity_aliases(
    entity_id: str,
    request: EntityAliasRequest,
    db: Database = Depends(get_library_database),
) -> KnowledgeEntity:
    entity = db.get(KnowledgeEntity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail=f"Entity not found: {entity_id}")
    merged = set(entity.aliases)
    merged.update(a.strip() for a in request.aliases if a.strip())
    entity.aliases = sorted(merged)
    entity.updated_at = datetime.now()
    db.save(entity)
    return entity


@router.get("/entities", response_model=list[KnowledgeEntity])
async def list_entities(
    q: str | None = Query(default=None),
    entity_type: EntityType | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    db: Database = Depends(get_library_database),
) -> list[KnowledgeEntity]:
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
