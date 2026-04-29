"""Shared helpers, constants, and models for knowledge graph route sub-modules."""

from datetime import datetime

from fastapi import HTTPException

from fichero.db import Database
from fichero.multilingual import normalize_text as multilingual_normalize
from fichero.knowledge_models import (
    ClaimCurationState,
    ClaimType,
    EntityType,
    EpistemicStatus,
    InclusionScopeType,
    KnowledgeClaim,
    KnowledgeEntity,
    KnowledgeGraphInclusion,
    MutationLog,
    MutationOperationType,
    SourceType,
)
from fichero.models import DocType, Document

KG_CLAIM_EMBEDDINGS_TABLE = "kg_claim_embeddings"
KG_ENTITY_EMBEDDINGS_TABLE = "kg_entity_embeddings"


def _normalize_text(value: str | None, language: str = "en") -> str:
    """Normalize text using language-aware normalization."""
    if not value:
        return ""
    return multilingual_normalize(value, language)


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


def _build_alias_to_entity_id_map(db: Database) -> dict[str, str]:
    """Build a lowercase alias → canonical entity ID lookup map."""
    result: dict[str, str] = {}
    for entity in db.all(KnowledgeEntity):
        norm = _normalize_text(entity.canonical_name)
        result[norm] = entity.id
        for alias in entity.aliases:
            result[_normalize_text(alias)] = entity.id
    return result


def _resolve_entity_id(db: Database, value: str) -> str | None:
    """Resolve a lookup value (id, canonical name, or alias) to a canonical entity ID."""
    if db.get(KnowledgeEntity, value) is not None:
        return value
    alias_map = _build_alias_to_entity_id_map(db)
    return alias_map.get(_normalize_text(value))


def _resolve_entity_ids(db: Database, values: list[str]) -> list[str]:
    """Resolve a list of lookup values to canonical entity IDs."""
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
        resolved_id = _resolve_entity_id(db, entity_id)
        if resolved_id:
            claims = [c for c in claims if resolved_id in c.entity_ids]
        else:
            claims = []
    if entity:
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
