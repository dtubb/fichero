"""Knowledge graph API routes (dev tier, backend-first 0.0.2 slice)."""

from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from pykeen.pipeline import pipeline
from pykeen.predict import predict_target
from pykeen.triples import TriplesFactory

from fichero.api.main import get_library_database
from fichero.db import Database
from fichero.knowledge_models import (
    ClaimCurationState,
    ClaimRelationType,
    ClaimType,
    EntityMergeAudit,
    EntityMergeOperationType,
    EntityType,
    EpistemicStatus,
    InclusionScopeType,
    KnowledgeClaim,
    KnowledgeClaimLink,
    KnowledgeEntity,
    KnowledgeGraphInclusion,
    KnowledgePredictionRun,
    MutationLog,
    MutationOperationType,
    PredictionMetadata,
    PredictionModelType,
    SourceType,
)
from fichero.models import DocType, Document

router = APIRouter()

KG_CLAIM_EMBEDDINGS_TABLE = "kg_claim_embeddings"
KG_ENTITY_EMBEDDINGS_TABLE = "kg_entity_embeddings"


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


class ClaimCreateRequest(BaseModel):
    text: str
    source_document_id: str
    source_segment_id: str | None = None
    source_page_label: str | None = None
    source_excerpt: str | None = None
    source_ref: str | None = None
    entity_ids: list[str] = Field(default_factory=list)
    curation_state: ClaimCurationState = ClaimCurationState.unreviewed
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    predicted_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    predicted_by: list[str] = Field(default_factory=list)
    prediction: PredictionMetadata | None = None
    language: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_by: str = "human"
    # --- multi-source ---
    source_type: SourceType = SourceType.document
    source_ids: list[str] = Field(default_factory=list)
    source_page_labels: list[str] = Field(default_factory=list)
    source_languages: list[str] = Field(default_factory=list)
    # --- claim classification ---
    claim_type: ClaimType | None = None
    epistemic_status: EpistemicStatus | None = None


class ClaimPatchRequest(BaseModel):
    text: str | None = None
    source_segment_id: str | None = None
    source_page_label: str | None = None
    source_excerpt: str | None = None
    source_ref: str | None = None
    entity_ids: list[str] | None = None
    curation_state: ClaimCurationState | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    predicted_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    predicted_by: list[str] | None = None
    prediction: PredictionMetadata | None = None
    language: str | None = None
    metadata: dict[str, Any] | None = None
    source_type: SourceType | None = None
    source_ids: list[str] | None = None
    source_page_labels: list[str] | None = None
    source_languages: list[str] | None = None
    claim_type: ClaimType | None = None
    epistemic_status: EpistemicStatus | None = None


class ClaimLinkCreateRequest(BaseModel):
    related_claim_id: str
    relation_type: ClaimRelationType
    link_quality: float = Field(default=0.5, ge=0.0, le=1.0)
    evidence: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class InclusionUpsertRequest(BaseModel):
    scope_type: InclusionScopeType
    target_id: str
    included: bool
    reason: str | None = None
    updated_by: str = "human"


def _normalize_text(value: str | None) -> str:
    return (value or "").strip().lower()


def _descendant_ids_for_folder(db: Database, folder_id: str) -> set[str]:
    documents = db.all(Document)
    children_by_parent: dict[str | None, list[Document]] = {}
    for doc in documents:
        children_by_parent.setdefault(doc.parent_id, []).append(doc)

    result: set[str] = set()
    stack: list[str] = [folder_id]
    while stack:
        current = stack.pop()
        result.add(current)
        for child in children_by_parent.get(current, []):
            stack.append(child.id)
    return result


def _resolve_scope_document_ids(
    db: Database,
    scope_type: InclusionScopeType | None,
    target_id: str | None,
) -> set[str] | None:
    if scope_type is None:
        return None
    if scope_type == InclusionScopeType.library:
        return None
    if not target_id:
        raise HTTPException(
            status_code=400, detail="target_id is required for non-library scopes"
        )

    if scope_type == InclusionScopeType.document:
        return {target_id}

    folder = db.get(Document, target_id)
    if not folder or folder.doc_type != DocType.folder:
        raise HTTPException(status_code=404, detail=f"Folder not found: {target_id}")
    return _descendant_ids_for_folder(db, target_id)


def _load_entity_map(db: Database) -> dict[str, KnowledgeEntity]:
    return {entity.id: entity for entity in db.all(KnowledgeEntity)}


def _build_alias_to_entity_id_map(
    db: Database,
) -> dict[str, str]:
    """Build a lowercase alias → canonical entity ID lookup map."""
    result: dict[str, str] = {}
    for entity in db.all(KnowledgeEntity):
        norm = _normalize_text(entity.canonical_name)
        result[norm] = entity.id
        for alias in entity.aliases:
            result[_normalize_text(alias)] = entity.id
    return result


def _resolve_entity_id(db: Database, value: str) -> str | None:
    """Resolve a lookup value (id, canonical name, or alias) to a canonical entity ID.

    Returns the entity ID if found, None otherwise.
    """
    # Try direct ID match first
    if db.get(KnowledgeEntity, value) is not None:
        return value
    # Try canonical name / alias match
    alias_map = _build_alias_to_entity_id_map(db)
    resolved = alias_map.get(_normalize_text(value))
    return resolved


def _resolve_entity_ids(db: Database, values: list[str]) -> list[str]:
    """Resolve a list of lookup values (ids, names, aliases) to canonical entity IDs."""
    result: list[str] = []
    for v in values:
        resolved = _resolve_entity_id(db, v)
        if resolved is not None:
            result.append(resolved)
    return result


def _passes_query_filter(
    claim: KnowledgeClaim, q: str | None, entity_map: dict[str, KnowledgeEntity]
) -> bool:
    if not q:
        return True
    needle = _normalize_text(q)
    if needle in _normalize_text(claim.text):
        return True
    for entity_id in claim.entity_ids:
        entity = entity_map.get(entity_id)
        if not entity:
            continue
        if needle in _normalize_text(entity.canonical_name):
            return True
        if any(needle in _normalize_text(alias) for alias in entity.aliases):
            return True
    return False


def _is_source_included(db: Database, source_document_id: str) -> bool:
    rows = db.query(
        KnowledgeGraphInclusion,
        scope_type=InclusionScopeType.document,
        target_id=source_document_id,
    )
    if not rows:
        return True
    latest = max(rows, key=lambda row: row.updated_at)
    return latest.included


def _log_mutation(
    db: Database,
    entity_type: str,
    entity_id: str,
    operation: MutationOperationType,
    before_state: dict | None,
    after_state: dict | None,
    changed_fields: list[str] | None,
    run_id: str | None = None,
    agent_id: str | None = None,
    created_by: str = "human",
) -> MutationLog:
    """Create a mutation log entry for a knowledge graph entity change."""
    log = MutationLog(
        entity_type=entity_type,
        entity_id=entity_id,
        operation=operation,
        before_state=before_state,
        after_state=after_state,
        changed_fields=changed_fields,
        run_id=run_id,
        agent_id=agent_id,
        created_by=created_by,
        created_at=datetime.now(),
    )
    db.save(log)
    return log


class MutationLogResponse(BaseModel):
    id: str
    entity_type: str
    entity_id: str
    operation: MutationOperationType
    before_state: dict | None
    after_state: dict | None
    changed_fields: list[str] | None
    run_id: str | None
    agent_id: str | None
    created_by: str
    reversal_id: str | None
    created_at: datetime


class UndoRequest(BaseModel):
    run_id: str | None = Field(
        default=None, description="Rollback all mutations in this AI run"
    )
    mutation_id: str | None = Field(
        default=None, description="Undo a specific mutation"
    )


@router.post("/knowledge-mutations/undo", response_model=list[MutationLogResponse])
async def undo_mutations(
    request: UndoRequest,
    db: Database = Depends(get_library_database),
) -> list[MutationLogResponse]:
    """Undo specific mutation(s) by replaying before_state.

    Either provide a mutation_id to undo one, or a run_id to undo all mutations
    from an AI agent run as a group.
    """
    if not request.mutation_id and not request.run_id:
        raise HTTPException(
            status_code=400, detail="Provide either mutation_id or run_id"
        )

    if request.mutation_id:
        logs = [db.get(MutationLog, request.mutation_id)]
    else:
        all_mlogs = db.all(MutationLog)
        logs = [
            mlog
            for mlog in all_mlogs
            if mlog.run_id == request.run_id and mlog.reversal_id is None
        ]
        logs.sort(key=lambda mlog: mlog.created_at, reverse=True)

    undone: list[MutationLogResponse] = []
    for log in logs:
        if log is None or log.reversal_id is not None:
            continue

        entity_cls = _entity_class_for_type(log.entity_type)
        if entity_cls is None:
            raise HTTPException(
                status_code=400, detail=f"Unknown entity type: {log.entity_type}"
            )

        entity = db.get(entity_cls, log.entity_id)
        if entity is None:
            raise HTTPException(
                status_code=404,
                detail=f"Entity {log.entity_id} ({log.entity_type}) not found — cannot undo",
            )

        # Replay before_state
        before = log.before_state
        if before is None:
            raise HTTPException(
                status_code=409,
                detail=f"Mutation {log.id} has no before_state — cannot undo a create",
            )

        for key, value in before.items():
            if key not in ("id", "created_at"):
                setattr(entity, key, value)
        from datetime import datetime as dt

        entity.updated_at = dt.now()
        db.save(entity)

        # Create reversal log entry
        after = {
            k: v
            for k, v in entity.model_dump().items()
            if k not in ("id", "created_at")
        }
        reverse = MutationLog(
            entity_type=log.entity_type,
            entity_id=log.entity_id,
            operation=MutationOperationType.restore,
            before_state=log.after_state,
            after_state=after,
            changed_fields=log.changed_fields,
            run_id=log.run_id,
            agent_id=log.agent_id,
            created_by=log.created_by,
            reversal_id=log.id,
            created_at=dt.now(),
        )
        db.save(reverse)

        log.reversal_id = reverse.id
        db.save(log)

        undone.append(
            MutationLogResponse(
                id=reverse.id,
                entity_type=reverse.entity_type,
                entity_id=reverse.entity_id,
                operation=reverse.operation,
                before_state=reverse.before_state,
                after_state=reverse.after_state,
                changed_fields=reverse.changed_fields,
                run_id=reverse.run_id,
                agent_id=reverse.agent_id,
                created_by=reverse.created_by,
                reversal_id=reverse.reversal_id,
                created_at=reverse.created_at,
            )
        )

    return undone


@router.get("/knowledge-mutations", response_model=list[MutationLogResponse])
async def list_mutations(
    entity_type: str | None = Query(default=None),
    entity_id: str | None = Query(default=None),
    run_id: str | None = Query(default=None),
    created_by: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: Database = Depends(get_library_database),
) -> list[MutationLogResponse]:
    """List mutation log entries, optionally filtered."""
    all_logs = db.all(MutationLog)
    if entity_type:
        all_logs = [mlog for mlog in all_logs if mlog.entity_type == entity_type]
    if entity_id:
        all_logs = [mlog for mlog in all_logs if mlog.entity_id == entity_id]
    if run_id:
        all_logs = [mlog for mlog in all_logs if mlog.run_id == run_id]
    if created_by:
        all_logs = [mlog for mlog in all_logs if mlog.created_by == created_by]
    all_logs.sort(key=lambda mlog: mlog.created_at, reverse=True)
    return [
        MutationLogResponse(
            id=mlog.id,
            entity_type=mlog.entity_type,
            entity_id=mlog.entity_id,
            operation=mlog.operation,
            before_state=mlog.before_state,
            after_state=mlog.after_state,
            changed_fields=mlog.changed_fields,
            run_id=mlog.run_id,
            agent_id=mlog.agent_id,
            created_by=mlog.created_by,
            reversal_id=mlog.reversal_id,
            created_at=mlog.created_at,
        )
        for mlog in all_logs[:limit]
    ]


def _entity_class_for_type(entity_type: str):
    """Map entity type string to the actual model class."""
    mapping = {
        "KnowledgeClaim": KnowledgeClaim,
        "KnowledgeEntity": KnowledgeEntity,
    }
    return mapping.get(entity_type)


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


@router.post("/entities/merge", response_model=EntityAuditResponse)
async def merge_entities(
    request: EntityMergeRequest,
    db: Database = Depends(get_library_database),
) -> EntityAuditResponse:
    """Merge multiple entities into a single absorbing entity.

    The absorbing entity survives and gains all aliases from absorbed entities.
    Absorbed entities are marked with merged_into_id so queries redirect properly.
    """
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

    # Build alias changes record
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

    # Merge requested aliases too
    for alias in request.merged_aliases:
        stripped = alias.strip()
        if stripped and stripped not in absorber_aliases:
            alias_changes["added"].append(stripped)
            absorber_aliases.add(stripped)

    absorber.aliases = sorted(absorber_aliases)
    if request.merged_description:
        absorber.description = request.merged_description
    absorber.updated_at = datetime.now()

    # Create audit record first (immutable)
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

    # Mark reversal_id on the audit record
    # (save audit again with reversal_id populated after we know it — but since
    # audit id is auto-generated, we can set it now as the reverse points to this)
    # Actually, we need the audit's own ID to reference it — it already has one
    audit.reversal_id = audit.id  # temporary; will be updated by the undo operation
    db.save(audit)  # save again with reversal_id

    # Save absorbed entities (soft-deleted)
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
    """Split one entity into a primary + new split-off entities.

    The primary entity keeps some aliases; split-off entities get the rest.
    """
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

    # Aliases being moved: remove from primary, track in audit
    remaining_aliases = [a for a in primary.aliases if a not in moved_alias_set]
    for alias in moved_alias_set:
        alias_changes["restored_from"].append(alias)

    # Primary keeps the un-moved aliases
    primary.aliases = remaining_aliases
    primary.updated_at = datetime.now()

    # Create split-off entities
    split_entity_ids: list[str] = []
    for split_off_id in request.split_off_entity_ids:
        split_off = db.get(KnowledgeEntity, split_off_id)
        if split_off is None:
            raise HTTPException(
                status_code=404, detail=f"Split-off entity not found: {split_off_id}"
            )
        split_off.merged_into_id = None  # ensure it's active
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
        # Restore absorbed entities (un-merge)
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
            # Restore aliases that were added from this entity to absorber
            for alias, target in alias_changes.get("moved_to", {}).items():
                if target == absorber.id and alias in entity.aliases:
                    restored_aliases.append(alias)

        # Remove absorbed aliases from absorber
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

        # Mark original audit as reversed
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
        # Re-merge: reassign aliases back to primary entity
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

        undo_alias_changes: dict[str, list[str]] = {
            "restored_from": [],
            "moved_to": {},
        }

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


@router.get("/entities/alias-map", response_model=EntityAliasMapResponse)
async def get_entity_alias_map(
    db: Database = Depends(get_library_database),
) -> EntityAliasMapResponse:
    """Return the full alias → entity mapping for reviewer decisions.

    Shows every alias and its canonical entity, useful for:
    - Reviewing which aliases map to the same entity
    - Detecting duplicate/conflicting aliases
    - Understanding entity name variations in the corpus
    """
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


@router.post("/claims", response_model=KnowledgeClaim)
async def create_claim(
    request: ClaimCreateRequest,
    run_id: str | None = Query(default=None),
    agent_id: str | None = Query(default=None),
    db: Database = Depends(get_library_database),
) -> KnowledgeClaim:
    source_doc = db.get(Document, request.source_document_id)
    if source_doc is None:
        raise HTTPException(
            status_code=404,
            detail=f"Source document not found: {request.source_document_id}",
        )

    missing_entities = [
        entity_id
        for entity_id in request.entity_ids
        if db.get(KnowledgeEntity, entity_id) is None
    ]
    if missing_entities:
        raise HTTPException(
            status_code=404, detail=f"Unknown entities: {missing_entities}"
        )

    now = datetime.now()
    claim = KnowledgeClaim(
        text=request.text.strip(),
        source_document_id=request.source_document_id,
        source_segment_id=request.source_segment_id,
        source_page_label=request.source_page_label,
        source_excerpt=request.source_excerpt,
        source_ref=request.source_ref,
        entity_ids=request.entity_ids,
        curation_state=request.curation_state,
        confidence=request.confidence,
        predicted_confidence=request.predicted_confidence,
        predicted_by=request.predicted_by,
        prediction=request.prediction,
        language=request.language,
        metadata=request.metadata,
        created_by=request.created_by,
        created_at=now,
        updated_at=now,
        source_type=request.source_type,
        source_ids=request.source_ids,
        source_page_labels=request.source_page_labels,
        source_languages=request.source_languages,
        claim_type=request.claim_type,
        epistemic_status=request.epistemic_status,
    )
    db.save(claim)

    # Log the mutation
    _log_mutation(
        db=db,
        entity_type="KnowledgeClaim",
        entity_id=claim.id,
        operation=MutationOperationType.create,
        before_state=None,
        after_state={
            k: v for k, v in claim.model_dump().items() if k not in ("id", "created_at")
        },
        changed_fields=None,
        run_id=run_id,
        agent_id=agent_id,
        created_by=agent_id if agent_id else "human",
    )

    return claim


@router.patch("/claims/{claim_id}", response_model=KnowledgeClaim)
async def patch_claim(
    claim_id: str,
    request: ClaimPatchRequest,
    run_id: str | None = Query(default=None),
    agent_id: str | None = Query(default=None),
    db: Database = Depends(get_library_database),
) -> KnowledgeClaim:
    claim = db.get(KnowledgeClaim, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail=f"Claim not found: {claim_id}")

    # Capture before state for mutation log
    before_state = {
        k: v for k, v in claim.model_dump().items() if k not in ("id", "created_at")
    }

    data = request.model_dump(exclude_unset=True)
    if "entity_ids" in data and data["entity_ids"] is not None:
        missing_entities = [
            entity_id
            for entity_id in data["entity_ids"]
            if db.get(KnowledgeEntity, entity_id) is None
        ]
        if missing_entities:
            raise HTTPException(
                status_code=404, detail=f"Unknown entities: {missing_entities}"
            )

    changed_fields = list(data.keys())
    for key, value in data.items():
        setattr(claim, key, value)
    claim.updated_at = datetime.now()
    db.save(claim)

    # Log the mutation
    after_state = {
        k: v for k, v in claim.model_dump().items() if k not in ("id", "created_at")
    }
    _log_mutation(
        db=db,
        entity_type="KnowledgeClaim",
        entity_id=claim_id,
        operation=MutationOperationType.update,
        before_state=before_state,
        after_state=after_state,
        changed_fields=changed_fields,
        run_id=run_id,
        agent_id=agent_id,
        created_by=agent_id if agent_id else "human",
    )

    return claim


@router.get("/claims/filtered", response_model=list[KnowledgeClaim])
async def list_claims_filtered(
    q: str | None = Query(default=None),
    claim_type: ClaimType | None = Query(default=None),
    curation_state: ClaimCurationState | None = Query(default=None),
    epistemic_status: EpistemicStatus | None = Query(default=None),
    entity_id: str | None = Query(default=None),
    source_language: str | None = Query(default=None),
    source_type: SourceType | None = Query(default=None),
    scope_type: InclusionScopeType | None = Query(default=None),
    target_id: str | None = Query(default=None),
    included_only: bool = Query(default=False),
    curated_only: bool = Query(default=False),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Database = Depends(get_library_database),
) -> list[KnowledgeClaim]:
    """Advanced claim search with all Phase 1 filter types.

    Separate from /claims to keep the simple list endpoint clean for SwiftUI.
    """
    claims = db.all(KnowledgeClaim)
    claims = _filter_claims(
        claims,
        db,
        q=q,
        entity_id=entity_id,
        curation_state=curation_state,
        claim_type=claim_type,
        epistemic_status=epistemic_status,
        source_language=source_language,
        source_type=source_type,
        scope_type=scope_type,
        target_id=target_id,
        included_only=included_only,
        curated_only=curated_only,
    )
    return claims[offset : offset + limit]


# Static /claims sub-paths MUST be defined BEFORE /{claim_id} to avoid
# FastAPI's greedy path-parameter matching swallowing them.
class _EmbedClaimRequest(BaseModel):
    claim_ids: list[str] | None = None


class _EmbedEntityRequest(BaseModel):
    entity_ids: list[str] | None = None


@router.post("/claims/semantic/embed")
async def embed_claims(
    request: _EmbedClaimRequest | None = None,
    db: Database = Depends(get_library_database),
) -> dict[str, Any]:
    """Embed claims into LanceDB for semantic search.

    If claim_ids is provided, only those claims are embedded.
    Otherwise, all claims are embedded (idempotent — re-embeds existing).
    """
    if request and request.claim_ids:
        claims = [db.get(KnowledgeClaim, cid) for cid in request.claim_ids]
        claims = [c for c in claims if c is not None]
    else:
        claims = db.all(KnowledgeClaim)

    if not claims:
        return {"embedded": 0, "table": KG_CLAIM_EMBEDDINGS_TABLE}

    texts = [c.text for c in claims]
    vectors = db._embed_texts(texts)  # type: ignore[attr-defined]

    records = [
        {
            "id": c.id,
            "text": c.text,
            "vector": v,
            "claim_type": c.claim_type.value if c.claim_type else None,
        }
        for c, v in zip(claims, vectors)
    ]
    db.save_vectors(KG_CLAIM_EMBEDDINGS_TABLE, records)
    return {"embedded": len(records), "table": KG_CLAIM_EMBEDDINGS_TABLE}


@router.get("/claims/semantic")
async def search_claims_semantic(
    q: str = Query(..., description="Natural language query"),
    claim_type: ClaimType | None = Query(default=None),
    curation_state: ClaimCurationState | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    db: Database = Depends(get_library_database),
) -> list[dict[str, Any]]:
    """Semantic claim search using LanceDB vectors."""
    if KG_CLAIM_EMBEDDINGS_TABLE not in db._lance_tables():
        raise HTTPException(
            status_code=503,
            detail="Claim embeddings not yet indexed. POST /claims/semantic/embed first.",
        )

    try:
        query_vector = db._embed_text(q)  # type: ignore[attr-defined]
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Embedding generation failed: {e}")

    results = db.search_vectors(KG_CLAIM_EMBEDDINGS_TABLE, query_vector, limit=limit)
    claim_ids = [r["id"] for r in results]

    if not claim_ids:
        return []

    # Load full claims and apply additional filters
    claims = {c.id: c for c in db.all(KnowledgeClaim) if c.id in claim_ids}
    filtered = [
        claims[cid]
        for cid in claim_ids
        if cid in claims
        and (claim_type is None or claims[cid].claim_type == claim_type)
        and (curation_state is None or claims[cid].curation_state == curation_state)
    ]

    # Attach similarity scores
    score_map = {r["id"]: r.get("_score", 0.0) for r in results}
    return [
        {**c.model_dump(), "similarity_score": score_map.get(c.id, 0.0)}
        for c in filtered
    ]


# Wildcard /{claim_id} must come AFTER all static /claims sub-paths.
@router.get("/claims/{claim_id}", response_model=KnowledgeClaim)
async def get_claim(
    claim_id: str, db: Database = Depends(get_library_database)
) -> KnowledgeClaim:
    claim = db.get(KnowledgeClaim, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail=f"Claim not found: {claim_id}")
    return claim


# /{claim_id}/sub paths must come AFTER /{claim_id} but /similar must be before /links
@router.get("/claims/{claim_id}/similar")
async def find_similar_claims(
    claim_id: str,
    limit: int = Query(default=10, ge=1, le=50),
    db: Database = Depends(get_library_database),
) -> list[dict[str, Any]]:
    """Find claims similar to a given claim."""
    claim = db.get(KnowledgeClaim, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail=f"Claim not found: {claim_id}")

    if KG_CLAIM_EMBEDDINGS_TABLE not in db._lance_tables():
        raise HTTPException(status_code=503, detail="Claims not embedded yet.")

    try:
        query_vector = db._embed_text(claim.text)  # type: ignore[attr-defined]
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Embedding failed: {e}")

    results = db.search_vectors(
        KG_CLAIM_EMBEDDINGS_TABLE, query_vector, limit=limit + 1
    )
    results = [r for r in results if r["id"] != claim_id]

    claim_map = {
        c.id: c for c in db.all(KnowledgeClaim) if c.id in [r["id"] for r in results]
    }
    score_map = {r["id"]: r.get("_score", 0.0) for r in results}

    return [
        {**claim_map[rid].model_dump(), "similarity_score": score_map.get(rid, 0.0)}
        for rid in [r["id"] for r in results]
        if rid in claim_map
    ][:limit]


@router.post("/claims/{claim_id}/links", response_model=KnowledgeClaimLink)
async def create_claim_link(
    claim_id: str,
    request: ClaimLinkCreateRequest,
    db: Database = Depends(get_library_database),
) -> KnowledgeClaimLink:
    claim = db.get(KnowledgeClaim, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail=f"Claim not found: {claim_id}")
    related_claim = db.get(KnowledgeClaim, request.related_claim_id)
    if related_claim is None:
        raise HTTPException(
            status_code=404,
            detail=f"Related claim not found: {request.related_claim_id}",
        )

    link = KnowledgeClaimLink(
        claim_id=claim_id,
        related_claim_id=request.related_claim_id,
        relation_type=request.relation_type,
        link_quality=request.link_quality,
        evidence=request.evidence,
        metadata=request.metadata,
        created_at=datetime.now(),
    )
    db.save(link)
    return link


@router.get("/claims/{claim_id}/links", response_model=list[KnowledgeClaimLink])
async def list_claim_links(
    claim_id: str, db: Database = Depends(get_library_database)
) -> list[KnowledgeClaimLink]:
    links = db.query(KnowledgeClaimLink, claim_id=claim_id)
    reverse_links = db.query(KnowledgeClaimLink, related_claim_id=claim_id)
    merged = {link.id: link for link in [*links, *reverse_links]}
    return sorted(merged.values(), key=lambda link: link.created_at, reverse=True)


def _filter_claims(
    claims: list[KnowledgeClaim],
    db: Database,
    q: str | None = None,
    entity_id: str | None = None,
    entity: str | None = None,
    entity_type: EntityType | None = None,
    curation_state: ClaimCurationState | None = None,
    curated_only: bool = False,
    claim_type: ClaimType | None = None,
    epistemic_status: EpistemicStatus | None = None,
    source_document_id: str | None = None,
    source_language: str | None = None,
    source_type: SourceType | None = None,
    scope_type: InclusionScopeType | None = None,
    target_id: str | None = None,
    included_only: bool = False,
) -> list[KnowledgeClaim]:
    """Apply all claim filters to an already-loaded list of claims."""
    entity_map = _load_entity_map(db)
    scoped_document_ids = _resolve_scope_document_ids(db, scope_type, target_id)

    if source_document_id:
        claims = [c for c in claims if c.source_document_id == source_document_id]
    if scoped_document_ids is not None:
        claims = [c for c in claims if c.source_document_id in scoped_document_ids]
    if entity_id:
        # Resolve entity_id: supports UUID, canonical name, or alias
        resolved_id = _resolve_entity_id(db, entity_id)
        if resolved_id:
            claims = [c for c in claims if resolved_id in c.entity_ids]
        else:
            claims = []
    if entity:
        # Resolve a name/alias string to entity ID, then filter
        resolved_entity_id = _resolve_entity_id(db, entity)
        if resolved_entity_id:
            claims = [c for c in claims if resolved_entity_id in c.entity_ids]
        else:
            claims = []
    if entity_type:
        claims = [
            c
            for c in claims
            if any(
                entity_map.get(eid) and entity_map[eid].entity_type == entity_type
                for eid in c.entity_ids
            )
        ]
    if curation_state:
        claims = [c for c in claims if c.curation_state == curation_state]
    if curated_only:
        claims = [c for c in claims if c.curation_state == ClaimCurationState.curated]
    if claim_type:
        claims = [c for c in claims if c.claim_type == claim_type]
    if epistemic_status:
        claims = [c for c in claims if c.epistemic_status == epistemic_status]
    if source_language:
        claims = [c for c in claims if source_language in c.source_languages]
    if source_type:
        claims = [c for c in claims if c.source_type == source_type]

    claims = [c for c in claims if _passes_query_filter(c, q, entity_map)]
    if included_only:
        claims = [c for c in claims if _is_source_included(db, c.source_document_id)]

    claims.sort(key=lambda c: c.updated_at, reverse=True)
    return claims


@router.get("/claims", response_model=list[KnowledgeClaim])
async def list_claims(
    q: str | None = Query(default=None),
    entity_id: str | None = Query(default=None),
    entity: str | None = Query(default=None),
    entity_type: EntityType | None = Query(default=None),
    curation_state: ClaimCurationState | None = Query(default=None),
    curated_only: bool = Query(default=False),
    claim_type: ClaimType | None = Query(default=None),
    epistemic_status: EpistemicStatus | None = Query(default=None),
    source_document_id: str | None = Query(default=None),
    source_language: str | None = Query(default=None),
    source_type: SourceType | None = Query(default=None),
    scope_type: InclusionScopeType | None = Query(default=None),
    target_id: str | None = Query(default=None),
    included_only: bool = Query(default=False),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Database = Depends(get_library_database),
) -> list[KnowledgeClaim]:
    claims = db.all(KnowledgeClaim)
    claims = _filter_claims(
        claims,
        db,
        q=q,
        entity_id=entity_id,
        entity=entity,
        entity_type=entity_type,
        curation_state=curation_state,
        curated_only=curated_only,
        claim_type=claim_type,
        epistemic_status=epistemic_status,
        source_document_id=source_document_id,
        source_language=source_language,
        source_type=source_type,
        scope_type=scope_type,
        target_id=target_id,
        included_only=included_only,
    )
    return claims[offset : offset + limit]


@router.post("/inclusion", response_model=KnowledgeGraphInclusion)
async def upsert_inclusion(
    request: InclusionUpsertRequest,
    db: Database = Depends(get_library_database),
) -> KnowledgeGraphInclusion:
    existing = db.query(
        KnowledgeGraphInclusion,
        scope_type=request.scope_type,
        target_id=request.target_id,
    )
    now = datetime.now()
    if existing:
        record = max(existing, key=lambda row: row.updated_at)
        record.included = request.included
        record.reason = request.reason
        record.updated_by = request.updated_by
        record.updated_at = now
    else:
        record = KnowledgeGraphInclusion(
            scope_type=request.scope_type,
            target_id=request.target_id,
            included=request.included,
            reason=request.reason,
            updated_by=request.updated_by,
            updated_at=now,
        )
    db.save(record)
    return record


@router.get("/inclusion", response_model=list[KnowledgeGraphInclusion])
async def list_inclusion(
    scope_type: InclusionScopeType | None = Query(default=None),
    target_id: str | None = Query(default=None),
    db: Database = Depends(get_library_database),
) -> list[KnowledgeGraphInclusion]:
    if scope_type and target_id:
        rows = db.query(
            KnowledgeGraphInclusion, scope_type=scope_type, target_id=target_id
        )
    elif scope_type:
        rows = db.query(KnowledgeGraphInclusion, scope_type=scope_type)
    elif target_id:
        rows = db.query(KnowledgeGraphInclusion, target_id=target_id)
    else:
        rows = db.all(KnowledgeGraphInclusion)
    rows.sort(key=lambda row: row.updated_at, reverse=True)
    return rows


@router.get("/overview")
async def overview(
    scope_type: InclusionScopeType | None = Query(default=None),
    target_id: str | None = Query(default=None),
    db: Database = Depends(get_library_database),
) -> dict[str, Any]:
    claims = db.all(KnowledgeClaim)
    claims = _filter_claims(
        claims,
        db,
        q=None,
        entity_id=None,
        entity_type=None,
        curation_state=None,
        scope_type=scope_type,
        target_id=target_id,
        included_only=False,
    )
    entities = db.all(KnowledgeEntity)
    claim_links = db.all(KnowledgeClaimLink)
    curated = sum(
        1 for claim in claims if claim.curation_state == ClaimCurationState.curated
    )
    shortlisted = sum(
        1 for claim in claims if claim.curation_state == ClaimCurationState.shortlisted
    )
    rejected = sum(
        1 for claim in claims if claim.curation_state == ClaimCurationState.rejected
    )
    unreviewed = sum(
        1 for claim in claims if claim.curation_state == ClaimCurationState.unreviewed
    )
    predicted = sum(1 for claim in claims if claim.predicted_by)
    included_claims = sum(
        1 for claim in claims if _is_source_included(db, claim.source_document_id)
    )
    average_confidence = (
        sum(claim.confidence for claim in claims) / len(claims) if claims else 0.0
    )

    return {
        "counts": {
            "claims": len(claims),
            "entities": len(entities),
            "claim_links": len(claim_links),
            "curated_claims": curated,
            "shortlisted_claims": shortlisted,
            "rejected_claims": rejected,
            "unreviewed_claims": unreviewed,
            "predicted_claims": predicted,
            "included_claims": included_claims,
        },
        "metrics": {
            "average_confidence": average_confidence,
        },
        "scope": {
            "scope_type": scope_type.value if scope_type else None,
            "target_id": target_id,
        },
    }


# =============================================================================
# Semantic Search (Step 5)
# =============================================================================


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


# =============================================================================
# PyKEEN Predictions (Step 4)
# =============================================================================


class PredictionGenerateHeuristicRequest(BaseModel):
    """Generate heuristic link predictions based on embedding similarity."""

    top_k: int = Field(default=10, ge=1, le=100)
    entity_id: str | None = None  # limit predictions for specific entity


class PredictionGeneratePyKEENRequest(BaseModel):
    """Train a PyKEEN model and generate predictions."""

    model_type: PredictionModelType = PredictionModelType.transe
    training_epochs: int = Field(default=100, ge=1, le=1000)
    learning_rate: float = Field(default=0.001, ge=0.0001, le=1.0)
    batch_size: int = Field(default=256, ge=8, le=1024)


def _build_minimal_pykeen_triples(
    claims: list[KnowledgeClaim],
    claim_links: list[KnowledgeClaimLink],
) -> list[tuple[str, str, str]]:
    """Build a compact training graph from existing claim/entity/link data."""
    triples: list[tuple[str, str, str]] = []

    for claim in claims:
        entity_ids = sorted(set(claim.entity_ids))
        for entity_id in entity_ids:
            triples.append((claim.id, "mentions", entity_id))

        # Add simple co-occurrence edges so a model has typed relation structure.
        for index, left_entity_id in enumerate(entity_ids):
            for right_entity_id in entity_ids[index + 1 :]:
                triples.append((left_entity_id, "co_occurs_with", right_entity_id))
                triples.append((right_entity_id, "co_occurs_with", left_entity_id))

    for claim_link in claim_links:
        triples.append(
            (
                claim_link.claim_id,
                f"claim_{claim_link.relation_type.value}",
                claim_link.related_claim_id,
            )
        )

    # Stable dedupe while preserving insertion order.
    return list(dict.fromkeys(triples))


def _extract_pykeen_metrics(result: Any) -> dict[str, float | None]:
    """Extract realistic ranking metrics from a PyKEEN pipeline result."""
    metrics = result.metric_results.to_dict()
    realistic = metrics.get("both", {}).get("realistic", {})
    return {
        "mrr": realistic.get("inverse_harmonic_mean_rank"),
        "hits_at_10": realistic.get("hits_at_10"),
        "hits_at_5": realistic.get("hits_at_5"),
        "hits_at_1": realistic.get("hits_at_1"),
    }


def _prediction_artifacts_dir(db: Database) -> Path:
    """Return the directory used to persist PyKEEN run artifacts."""
    artifacts_dir = Path(db.path).parent / "knowledge-predictions"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    return artifacts_dir


def _build_claim_link_prediction_preview(
    result: Any,
    triples_factory: TriplesFactory,
    claims: list[KnowledgeClaim],
    claim_links: list[KnowledgeClaimLink],
    top_k: int = 10,
) -> list[dict[str, Any]]:
    """Create lightweight candidate links from real PyKEEN scores."""
    linked_pairs: set[tuple[str, str]] = set()
    for claim_link in claim_links:
        linked_pairs.add((claim_link.claim_id, claim_link.related_claim_id))
        linked_pairs.add((claim_link.related_claim_id, claim_link.claim_id))

    claim_ids = [claim.id for claim in claims]
    candidate_relations = [
        relation
        for relation in (
            "claim_supports",
            "claim_refines",
            "claim_contradicts",
            "mentions",
        )
        if relation in triples_factory.relation_to_id
    ]
    if not candidate_relations:
        return []

    candidates: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, str]] = set()
    for claim in claims:
        predictions = predict_target(
            result.model,
            head=claim.id,
            relation=candidate_relations[0],
            triples_factory=triples_factory,
            targets=claim_ids,
        )
        for row in predictions.df.itertuples(index=False):
            target_claim_id = row.tail_label
            if target_claim_id == claim.id:
                continue
            pair = tuple(sorted((claim.id, target_claim_id)))
            if pair in seen_pairs or (claim.id, target_claim_id) in linked_pairs:
                continue
            seen_pairs.add(pair)
            candidates.append(
                {
                    "source_claim_id": claim.id,
                    "target_claim_id": target_claim_id,
                    "predicted_relation": "supports",
                    "score": round(float(row.score), 6),
                }
            )

    candidates.sort(key=lambda item: item["score"], reverse=True)
    return candidates[:top_k]


@router.post("/predictions/generate/pykeen", response_model=KnowledgePredictionRun)
async def generate_pykeen_predictions(
    request: PredictionGeneratePyKEENRequest,
    db: Database = Depends(get_library_database),
) -> KnowledgePredictionRun:
    """Train or simulate a minimal PyKEEN pipeline and persist run metadata."""
    claims = db.all(KnowledgeClaim)
    if not claims:
        raise HTTPException(
            status_code=400,
            detail="Cannot train predictions: no knowledge claims found.",
        )

    entities = db.all(KnowledgeEntity)
    if not entities:
        raise HTTPException(
            status_code=400,
            detail="Cannot train predictions: no knowledge entities found.",
        )

    claim_links = db.all(KnowledgeClaimLink)
    triples = _build_minimal_pykeen_triples(claims, claim_links)
    if not triples:
        raise HTTPException(
            status_code=400,
            detail="Cannot train predictions: no graph triples derived from claims/entities.",
        )

    relation_types = sorted({relation for _, relation, _ in triples})
    triples_array = np.array(triples, dtype=str)
    triples_factory = TriplesFactory.from_labeled_triples(triples_array)
    model_name = {
        PredictionModelType.transe: "TransE",
        PredictionModelType.rotate: "RotatE",
        PredictionModelType.complex: "ComplEx",
        PredictionModelType.hermite: "HolE",
    }[request.model_type]

    try:
        result = pipeline(
            training=triples_factory,
            testing=triples_factory,
            validation=triples_factory,
            model=model_name,
            epochs=request.training_epochs,
            training_kwargs={"batch_size": request.batch_size},
            optimizer_kwargs={"lr": request.learning_rate},
            random_seed=42,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail=f"PyKEEN training failed: {exc}"
        ) from exc

    metrics = _extract_pykeen_metrics(result)
    prediction_preview = _build_claim_link_prediction_preview(
        result, triples_factory, claims, claim_links
    )

    artifact_dir = (
        _prediction_artifacts_dir(db)
        / f"pykeen-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    )
    result.save_to_directory(str(artifact_dir))

    run = KnowledgePredictionRun(
        model_type=request.model_type,
        pykeen_config={
            "model_type": request.model_type.value,
            "pykeen_model": model_name,
            "training_epochs": request.training_epochs,
            "learning_rate": request.learning_rate,
            "batch_size": request.batch_size,
            "pipeline_mode": "pykeen",
        },
        trained_at=datetime.now(),
        num_entities=len(entities),
        num_claims=len(claims),
        num_relation_types=len(relation_types),
        mrr=metrics["mrr"],
        hits_at_10=metrics["hits_at_10"],
        hits_at_5=metrics["hits_at_5"],
        hits_at_1=metrics["hits_at_1"],
        model_path=str(artifact_dir),
        status="trained",
        metadata={
            "training_triples": len(triples),
            "relation_types": relation_types,
            "prediction_preview": prediction_preview,
            "prediction_preview_count": len(prediction_preview),
        },
    )
    db.save(run)
    return run


@router.post("/predictions/generate/heuristic")
async def generate_heuristic_predictions(
    request: PredictionGenerateHeuristicRequest,
    db: Database = Depends(get_library_database),
) -> dict[str, Any]:
    """Generate heuristic predictions using embedding similarity.

    Finds claim pairs with high embedding similarity but no existing link,
    treating high similarity as a weak signal for link existence.
    """
    if KG_CLAIM_EMBEDDINGS_TABLE not in db._lance_tables():
        raise HTTPException(
            status_code=503,
            detail="Claims not embedded. POST /claims/semantic/embed first.",
        )

    all_claims = db.all(KnowledgeClaim)
    existing_links = db.all(KnowledgeClaimLink)
    linked_pairs: set[tuple[str, str]] = set()
    for link in existing_links:
        linked_pairs.add((link.claim_id, link.related_claim_id))
        linked_pairs.add((link.related_claim_id, link.claim_id))

    # Get top-k similar for each claim
    predictions: list[dict[str, Any]] = []
    for claim in all_claims:
        try:
            query_vector = db._embed_text(claim.text)  # type: ignore[attr-defined]
        except Exception:
            continue

        similar = db.search_vectors(
            KG_CLAIM_EMBEDDINGS_TABLE, query_vector, limit=request.top_k + 1
        )
        for result in similar:
            other_id = result["id"]
            if other_id == claim.id:
                continue
            if (claim.id, other_id) in linked_pairs:
                continue
            if request.entity_id:
                other = db.get(KnowledgeClaim, other_id)
                if not other or request.entity_id not in other.entity_ids:
                    continue
            predictions.append(
                {
                    "source_claim_id": claim.id,
                    "target_claim_id": other_id,
                    "similarity_score": result.get("_score", 0.0),
                    "method": "heuristic",
                }
            )

    predictions.sort(key=lambda p: p["similarity_score"], reverse=True)
    return {
        "predictions": predictions[: request.top_k * 5],
        "method": "heuristic",
        "claims_embedded": len(all_claims),
    }


@router.get("/predictions", response_model=list[KnowledgePredictionRun])
async def list_predictions(
    status: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    db: Database = Depends(get_library_database),
) -> list[KnowledgePredictionRun]:
    """List PyKEEN prediction runs."""
    runs = db.all(KnowledgePredictionRun)
    if status:
        runs = [r for r in runs if r.status == status]
    runs.sort(key=lambda r: r.trained_at, reverse=True)
    return runs[:limit]


@router.post("/predictions/{run_id}/apply")
async def apply_prediction(
    run_id: str,
    db: Database = Depends(get_library_database),
) -> dict[str, Any]:
    """Apply a prediction run's top-scoring predictions as claim links.

    Creates KnowledgeClaimLink records for high-confidence predictions
    from a PyKEEN run (heuristic or trained model).
    """
    # For now, apply heuristic predictions that were stored in metadata
    # Full PyKEEN model training + application is Phase 2
    raise HTTPException(
        status_code=501,
        detail="Full PyKEEN apply requires trained model storage. Use heuristic predictions for now.",
    )
