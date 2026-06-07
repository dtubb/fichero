"""Entity merge/split with audit trail + semantic entity search.

Ported from the deprecated ``/api/knowledge-graph/entities/{merge,split,audit,semantic}``
endpoints. Lives under ``/api/kg/entity-curation``. The audit table is
what the Swift curation UI shows when displaying "Davidson absorbed
3 aliases" — see EntityMergeAudit in knowledge_models.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from fichero.api.main import get_library_database
from fichero.db import Database
from fichero.knowledge_models import (
    EntityMergeAudit,
    EntityMergeOperationType,
    EntityCurationState,
    EntityType,
    KnowledgeEntity,
    KnowledgeClaim,
    MutationLog,
    MutationOperationType,
)
from fichero.models import EntityAuditListResponse, KGGraphListResponse

router = APIRouter(prefix="/kg/entity-curation")
kg_entities_router = APIRouter(prefix="/kg/entities", tags=["knowledge-graph"])

KG_ENTITY_EMBEDDINGS_TABLE = "kg_entity_embeddings"
LEGACY_KG_ENTITY_EMBEDDINGS_TABLE = "kg_entities"


class EntityMergeRequest(BaseModel):
    absorbing_entity_id: str = Field(description="Entity that absorbs the others (survivor)")
    absorbed_entity_ids: list[str] = Field(description="Entities merged into the absorber")
    merged_aliases: list[str] = Field(default_factory=list)
    merged_description: str | None = None


class EntitySplitRequest(BaseModel):
    primary_entity_id: str
    split_off_entity_ids: list[str]
    aliases_to_move: list[str] = Field(default_factory=list)


class EntityAuditResponse(BaseModel):
    id: str
    operation_type: EntityMergeOperationType
    source_entity_ids: list[str]
    target_entity_id: str
    alias_changes: dict
    reversal_id: str | None
    created_by: str
    created_at: datetime


class EmbedEntitiesResponse(BaseModel):
    embedded: int
    table: str


class BatchEntityCurationRequest(BaseModel):
    entity_ids: list[str] = Field(min_length=1, description="Entity IDs to update.")
    curation_state: EntityCurationState = Field(description="New curation state for every listed entity.")


class BatchEntityCurationResponse(BaseModel):
    updated: int
    entity_ids: list[str] = Field(default_factory=list, description="Entity IDs whose state actually changed.")


class _EmbedEntityRequest(BaseModel):
    entity_ids: list[str] | None = None


def _entity_embeddings_table_name(db: Database) -> str | None:
    """Resolve the entity vector table for semantic search.

    `kg_entities` is the long-lived table populated by entity upserts and KG
    rebuilds. `kg_entity_embeddings` is the newer batch-embed route's table.
    Keep semantic search readable across both so older libraries with existing
    vectors do not 503.
    """
    tables = set(db._lance_tables())
    if KG_ENTITY_EMBEDDINGS_TABLE in tables:
        return KG_ENTITY_EMBEDDINGS_TABLE
    if LEGACY_KG_ENTITY_EMBEDDINGS_TABLE in tables:
        return LEGACY_KG_ENTITY_EMBEDDINGS_TABLE
    return None


def _audit_response(audit: EntityMergeAudit) -> EntityAuditResponse:
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


def _log_entity_curation_mutation(
    *,
    db: Database,
    entity: KnowledgeEntity,
    before_state: dict[str, Any],
) -> None:
    db.save(
        MutationLog(
            entity_type="KnowledgeEntity",
            entity_id=entity.id,
            operation=MutationOperationType.update,
            before_state=before_state,
            after_state=entity.model_dump(mode="json"),
            changed_fields=["curation_state"],
        )
    )


@router.post("/merge", response_model=EntityAuditResponse)
async def merge_entities(
    request: EntityMergeRequest,
    db: Database = Depends(get_library_database),
) -> EntityAuditResponse:
    """Merge multiple entities into a single absorbing entity, with audit."""
    absorber = db.get(KnowledgeEntity, request.absorbing_entity_id)
    if absorber is None:
        raise HTTPException(status_code=404, detail=f"Absorbing entity not found: {request.absorbing_entity_id}")

    absorbed: list[KnowledgeEntity] = []
    for eid in request.absorbed_entity_ids:
        ent = db.get(KnowledgeEntity, eid)
        if ent is None:
            raise HTTPException(status_code=404, detail=f"Absorbed entity not found: {eid}")
        if ent.merged_into_id is not None:
            raise HTTPException(
                status_code=409,
                detail=f"Entity {eid} was already merged into {ent.merged_into_id}",
            )
        absorbed.append(ent)

    alias_changes: dict[str, Any] = {"added": [], "removed": [], "moved_to": {}}
    absorber_aliases = set(absorber.aliases)
    now = datetime.now()
    for ent in absorbed:
        for alias in ent.aliases:
            if alias not in absorber_aliases:
                alias_changes["added"].append(alias)
                absorber_aliases.add(alias)
            alias_changes["moved_to"][alias] = absorber.id
        alias_changes["removed"].extend(ent.aliases)
        ent.merged_into_id = absorber.id
        ent.updated_at = now

    for alias in request.merged_aliases:
        stripped = alias.strip()
        if stripped and stripped not in absorber_aliases:
            alias_changes["added"].append(stripped)
            absorber_aliases.add(stripped)

    absorber.aliases = sorted(absorber_aliases)
    if request.merged_description:
        absorber.description = request.merged_description
    absorber.updated_at = now

    # Re-point claims: replace absorbed entity IDs with the absorber ID so
    # claim queries on the absorber surface all previously-absorbed evidence.
    absorbed_ids = {e.id for e in absorbed}
    for claim in db.query(KnowledgeClaim):
        old_ids = claim.entity_ids or []
        if any(eid in absorbed_ids for eid in old_ids):
            new_ids = [absorber.id if eid in absorbed_ids else eid for eid in old_ids]
            seen: set[str] = set()
            claim.entity_ids = [eid for eid in new_ids if not (eid in seen or seen.add(eid))]  # type: ignore[func-returns-value]
            claim.updated_at = now
            db.save(claim)

    audit = EntityMergeAudit(
        operation_type=EntityMergeOperationType.merge,
        source_entity_ids=[e.id for e in absorbed],
        target_entity_id=absorber.id,
        alias_changes=alias_changes,
        created_by="human",
        created_at=now,
    )
    db.save(audit)
    audit.reversal_id = audit.id
    db.save(audit)
    for ent in absorbed:
        db.save(ent)
    db.save(absorber)
    return _audit_response(audit)


@kg_entities_router.patch(
    "/batch-curation",
    response_model=BatchEntityCurationResponse,
    summary="Batch set entity curation state",
)
async def batch_set_entity_curation_state(
    request: BatchEntityCurationRequest,
    db: Database = Depends(get_library_database),
) -> BatchEntityCurationResponse:
    entities: list[KnowledgeEntity] = []
    for entity_id in request.entity_ids:
        entity = db.get(KnowledgeEntity, entity_id)
        if entity is None:
            raise HTTPException(status_code=404, detail=f"Entity not found: {entity_id}")
        entities.append(entity)

    now = datetime.now()
    updated_ids: list[str] = []
    for entity in entities:
        if entity.curation_state == request.curation_state:
            continue
        before_state = entity.model_dump(mode="json")
        entity.curation_state = request.curation_state
        entity.updated_at = now
        db.save(entity)
        _log_entity_curation_mutation(db=db, entity=entity, before_state=before_state)
        updated_ids.append(entity.id)

    return BatchEntityCurationResponse(updated=len(updated_ids), entity_ids=updated_ids)


@router.post("/split", response_model=EntityAuditResponse)
async def split_entity(
    request: EntitySplitRequest,
    db: Database = Depends(get_library_database),
) -> EntityAuditResponse:
    """Split one entity into a primary + new split-off entities."""
    primary = db.get(KnowledgeEntity, request.primary_entity_id)
    if primary is None:
        raise HTTPException(status_code=404, detail=f"Primary entity not found: {request.primary_entity_id}")

    moved = {a.strip() for a in request.aliases_to_move if a.strip()}
    alias_changes: dict[str, Any] = {
        "restored_from": list(moved),
        "moved_to": {},
    }
    primary.aliases = [a for a in primary.aliases if a not in moved]
    now = datetime.now()
    primary.updated_at = now

    split_ids: list[str] = []
    for sid in request.split_off_entity_ids:
        sp = db.get(KnowledgeEntity, sid)
        if sp is None:
            raise HTTPException(status_code=404, detail=f"Split-off entity not found: {sid}")
        sp.merged_into_id = None
        sp.updated_at = now
        db.save(sp)
        split_ids.append(sp.id)
        alias_changes["moved_to"][sp.id] = []

    audit = EntityMergeAudit(
        operation_type=EntityMergeOperationType.split,
        source_entity_ids=split_ids,
        target_entity_id=primary.id,
        alias_changes=alias_changes,
        created_by="human",
        created_at=now,
    )
    db.save(audit)
    audit.reversal_id = audit.id
    db.save(audit)
    db.save(primary)
    return _audit_response(audit)


@router.post("/audit/{audit_id}/undo", response_model=EntityAuditResponse)
async def undo_entity_operation(
    audit_id: str,
    db: Database = Depends(get_library_database),
) -> EntityAuditResponse:
    """Undo a previous merge or split using its audit record."""
    audit = db.get(EntityMergeAudit, audit_id)
    if audit is None:
        raise HTTPException(status_code=404, detail=f"Audit record not found: {audit_id}")
    if audit.reversal_id != audit.id:
        raise HTTPException(
            status_code=409,
            detail="This operation was already undone or is not directly reversible",
        )

    now = datetime.now()
    if audit.operation_type == EntityMergeOperationType.merge:
        absorber = db.get(KnowledgeEntity, audit.target_entity_id)
        if absorber is None:
            raise HTTPException(status_code=404, detail=f"Target entity not found: {audit.target_entity_id}")
        restored: list[str] = []
        for eid in audit.source_entity_ids:
            ent = db.get(KnowledgeEntity, eid)
            if ent is None:
                raise HTTPException(status_code=404, detail=f"Source entity not found: {eid}")
            ent.merged_into_id = None
            ent.updated_at = now
            db.save(ent)
            for alias, target in audit.alias_changes.get("moved_to", {}).items():
                if target == absorber.id and alias in ent.aliases:
                    restored.append(alias)
        absorbed_aliases = set(audit.alias_changes.get("added", []))
        absorber.aliases = [a for a in absorber.aliases if a not in absorbed_aliases]
        absorber.updated_at = now
        db.save(absorber)
        undo = EntityMergeAudit(
            operation_type=EntityMergeOperationType.undo_merge,
            source_entity_ids=audit.source_entity_ids,
            target_entity_id=audit.target_entity_id,
            alias_changes={"added": [], "removed": [], "moved_to": {}, "restored_from": restored},
            reversal_id=audit_id,
            created_by="human",
            created_at=now,
        )
    elif audit.operation_type == EntityMergeOperationType.split:
        primary = db.get(KnowledgeEntity, audit.target_entity_id)
        if primary is None:
            raise HTTPException(status_code=404, detail=f"Primary entity not found: {audit.target_entity_id}")
        moved = audit.alias_changes.get("restored_from", [])
        primary.aliases = sorted(set(primary.aliases) | set(moved))
        primary.updated_at = now
        db.save(primary)
        undo = EntityMergeAudit(
            operation_type=EntityMergeOperationType.undo_split,
            source_entity_ids=audit.source_entity_ids,
            target_entity_id=audit.target_entity_id,
            alias_changes={"restored_from": [], "moved_to": {}},
            reversal_id=audit_id,
            created_by="human",
            created_at=now,
        )
    else:
        raise HTTPException(status_code=409, detail=f"Cannot undo operation type: {audit.operation_type}")

    db.save(undo)
    audit.reversal_id = undo.id
    db.save(audit)
    return _audit_response(undo)


@router.get("/audit", response_model=EntityAuditListResponse)
async def list_entity_audits(
    entity_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: Database = Depends(get_library_database),
) -> EntityAuditListResponse:
    """List entity merge/split audit records, optionally filtered by entity."""
    audits = db.all(EntityMergeAudit)
    if entity_id:
        audits = [
            a for a in audits
            if a.target_entity_id == entity_id or entity_id in a.source_entity_ids
        ]
    audits.sort(key=lambda a: a.created_at, reverse=True)
    items = [_audit_response(a) for a in audits[:limit]]
    return EntityAuditListResponse(items=items, count=len(items))


def _embed_entities_sync(
    db: Database,
    entities: list[KnowledgeEntity],
) -> int:
    """CPU-bound work for embed_entities. Runs off the event loop."""
    texts = [
        e.canonical_name + (" " + " ".join(e.aliases) if e.aliases else "")
        for e in entities
    ]
    vectors = db._embed_texts(texts)  # type: ignore[attr-defined]
    records = [
        {
            "id": e.id, "text": e.canonical_name, "aliases": e.aliases,
            "entity_type": e.entity_type.value, "vector": v,
        }
        for e, v in zip(entities, vectors)
    ]
    db.save_vectors(KG_ENTITY_EMBEDDINGS_TABLE, records)
    return len(records)


@router.post("/semantic/embed", response_model=EmbedEntitiesResponse)
async def embed_entities(
    request: _EmbedEntityRequest | None = None,
    db: Database = Depends(get_library_database),
) -> EmbedEntitiesResponse:
    """Embed entities into LanceDB for semantic search.

    The FastEmbed call is CPU-bound and (for a real corpus) runs hundreds
    of synchronous invocations. Off-load to a worker thread so the FastAPI
    event loop can keep serving other endpoints (e.g. /api/health) while
    embedding is in flight (#1004).
    """
    if request and request.entity_ids:
        entities = [db.get(KnowledgeEntity, eid) for eid in request.entity_ids]
        entities = [e for e in entities if e is not None]
    else:
        entities = db.all(KnowledgeEntity)
    if not entities:
        return EmbedEntitiesResponse(embedded=0, table=KG_ENTITY_EMBEDDINGS_TABLE)

    embedded = await asyncio.to_thread(_embed_entities_sync, db, entities)
    return EmbedEntitiesResponse(embedded=embedded, table=KG_ENTITY_EMBEDDINGS_TABLE)


@router.get("/semantic", response_model=KGGraphListResponse)
async def search_entities_semantic(
    q: str = Query(..., description="Natural language query"),
    entity_type: EntityType | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    db: Database = Depends(get_library_database),
) -> KGGraphListResponse:
    """Semantic entity search via LanceDB."""
    table_name = _entity_embeddings_table_name(db)
    if table_name is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "Entity embeddings not yet indexed. POST /kg/entity-curation/semantic/embed "
                "first or rebuild KG vectors."
            ),
        )
    try:
        query_vector = db._embed_text(q)  # type: ignore[attr-defined]
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Embedding generation failed: {exc}") from exc
    results = db.search_vectors(table_name, query_vector, limit=limit)
    entity_ids = [r["id"] for r in results]
    if not entity_ids:
        return KGGraphListResponse(items=[], count=0)
    entities = {e.id: e for e in db.all(KnowledgeEntity) if e.id in entity_ids}
    score_map = {r["id"]: r.get("_score", 0.0) for r in results}
    items = [
        {**entities[eid].model_dump(), "similarity_score": score_map.get(eid, 0.0)}
        for eid in entity_ids
        if eid in entities and (entity_type is None or entities[eid].entity_type == entity_type)
    ]
    return KGGraphListResponse(items=items, count=len(items))


# ---------------------------------------------------------------------------
# Entity-resolution candidate pairs via graph-context Jaccard (#988)
# ---------------------------------------------------------------------------
#
# Neo4j's entity-resolution playbook calls out *graph-based methods* as the
# missing link beyond name-similarity + deterministic rules: two entities
# with overlapping neighborhoods are likely the same real-world entity.
# We already had vector-similar (`/semantic`) which catches name + alias
# overlap; this endpoint adds the structural-similarity signal.


class CandidatePair(BaseModel):
    """One candidate merge pair surfaced by graph-context similarity."""
    entity_a_id: str
    entity_a_name: str
    entity_b_id: str
    entity_b_name: str
    jaccard: float = Field(ge=0.0, le=1.0)
    shared_neighbors: int
    entity_type: str | None = None


@router.get(
    "/candidates",
    response_model=KGGraphListResponse,
    summary="Graph-context merge candidates (Jaccard over co-occurrence neighborhoods)",
    description=(
        "Surfaces entity pairs whose claim-neighborhoods overlap heavily — "
        "the structural-similarity signal Neo4j calls out as the third leg "
        "of entity resolution after rule-based (alias dedup) and "
        "probabilistic / vector (the /semantic endpoint above). "
        "Pairs are filtered to same entity_type by default — cross-type "
        "merges (e.g. Person ↔ Place) are almost always wrong. (#988)"
    ),
)
async def candidate_pairs(
    min_jaccard: float = Query(default=0.5, ge=0.0, le=1.0),
    top_k: int = Query(default=20, ge=1, le=200),
    same_type_only: bool = Query(default=True),
    db: Database = Depends(get_library_database),
) -> KGGraphListResponse:
    """Compute Jaccard similarity over the co-occurrence graph between
    every pair of entities of the same type. O(E²) in the entity count
    but bounded by the shared networkx graph cache (#990).
    """
    import networkx as nx
    from fichero.kg.graph import build_full_cooccurrence

    graph = build_full_cooccurrence(db)
    if graph.number_of_nodes() < 2:
        return KGGraphListResponse(items=[], count=0)
    by_id: dict[str, KnowledgeEntity] = {e.id: e for e in db.query(KnowledgeEntity)}
    nodes = [n for n in graph.nodes() if n in by_id]
    candidate_node_pairs = [
        (a, b)
        for i, a in enumerate(nodes)
        for b in nodes[i + 1:]
        if (not same_type_only)
        or (by_id[a].entity_type == by_id[b].entity_type)
    ]
    if not candidate_node_pairs:
        return KGGraphListResponse(items=[], count=0)
    scored = nx.jaccard_coefficient(graph, candidate_node_pairs)
    rows: list[CandidatePair] = []
    for u, v, coef in scored:
        if coef < min_jaccard:
            continue
        # Count shared neighbors directly so the response carries an
        # interpretable number alongside the score (helps reviewers
        # decide: 8 shared > 0.6 → trust; 1 shared > 0.6 → barely).
        shared = len(set(graph.neighbors(u)) & set(graph.neighbors(v)))
        ent_a = by_id.get(u)
        ent_b = by_id.get(v)
        if ent_a is None or ent_b is None:
            continue
        rows.append(CandidatePair(
            entity_a_id=u,
            entity_a_name=ent_a.canonical_name,
            entity_b_id=v,
            entity_b_name=ent_b.canonical_name,
            jaccard=float(coef),
            shared_neighbors=shared,
            entity_type=(
                ent_a.entity_type.value if ent_a.entity_type
                and hasattr(ent_a.entity_type, "value") else None
            ),
        ))
    rows.sort(key=lambda r: r.jaccard, reverse=True)
    rows = rows[:top_k]
    return KGGraphListResponse(items=rows, count=len(rows))


# Resolve forward refs in EntityAuditListResponse (declared in models.py with
# items: list["EntityAuditResponse"]). See #1144.
from fichero.models import EntityAuditListResponse  # noqa: E402

EntityAuditListResponse.model_rebuild(_types_namespace={"EntityAuditResponse": EntityAuditResponse})
