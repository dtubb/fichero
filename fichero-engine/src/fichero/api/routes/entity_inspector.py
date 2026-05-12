"""Aggregate entity inspector endpoint — same pattern as document_inspector.

Single call returns every KG row for an entity: claims, documents
that mention it, annotations linked to it, notes that reference it,
projects it belongs to, similar entities (via the LanceDB cosine
neighbours from #899 Phase B), triangulated facts about it.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from fichero.api.main import get_library_database
from fichero.db import Database
from fichero.knowledge_models import (
    Annotation,
    KnowledgeClaim,
    KnowledgeEntity,
    Note,
    Project,
    ProjectInclusion,
)
from fichero.models import Document

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/entities", tags=["knowledge-graph"])


class SimilarEntity(BaseModel):
    entity_id: str
    canonical_name: str
    cosine_score: float


class TriangulatedFact(BaseModel):
    predicate: str
    object_text: str
    support_count: int
    weighted_support: float
    corroboration: str
    source_document_ids: list[str]


class EntityInspectorResponse(BaseModel):
    """Everything the entity-detail view needs in one shot."""
    entity_id: str
    entity: KnowledgeEntity
    claim_count: int
    claims: list[KnowledgeClaim]
    documents: list[Document]
    annotations: list[Annotation]
    notes: list[Note]
    projects: list[Project]
    similar_entities: list[SimilarEntity]
    triangulated_facts: list[TriangulatedFact]


@router.get(
    "/{entity_id}/inspector",
    response_model=EntityInspectorResponse,
    summary="One-call aggregate of every KG row attached to this entity",
)
async def inspector(
    entity_id: str,
    db: Database = Depends(get_library_database),
) -> EntityInspectorResponse:
    entity = db.get(KnowledgeEntity, entity_id)
    if entity is None:
        raise HTTPException(404, f"Entity not found: {entity_id}")

    # Claims that reference this entity.
    all_claims = db.query(KnowledgeClaim)
    claims = [c for c in all_claims if entity_id in (c.entity_ids or [])]
    claims.sort(key=lambda c: c.created_at, reverse=True)

    # Documents those claims came from.
    doc_ids: set[str] = {c.source_document_id for c in claims if c.source_document_id}
    documents = [
        d for d in (db.get(Document, did) for did in doc_ids)
        if d is not None
    ]
    documents.sort(key=lambda d: d.name)

    # Annotations linked to this entity.
    annotations = [
        a for a in db.query(Annotation)
        if entity_id in (a.linked_entity_ids or [])
    ]

    # Notes that reference this entity.
    notes = [
        n for n in db.query(Note)
        if entity_id in (n.linked_entity_ids or [])
    ]
    notes.sort(key=lambda n: n.updated_at, reverse=True)

    # Project memberships (entity-typed inclusions).
    inclusions = [
        incl for incl in db.query(ProjectInclusion)
        if incl.target_id == entity_id and incl.target_type == "entity"
    ]
    project_ids = {incl.project_id for incl in inclusions}
    projects = [
        p for p in (db.get(Project, pid) for pid in project_ids)
        if p is not None
    ]

    # Similar entities via LanceDB cosine.
    similar: list[SimilarEntity] = []
    try:
        from fichero.kg import entity_vectors
        hits = entity_vectors.find_similar(
            db=db,
            canonical_name=entity.canonical_name,
            entity_type=entity.entity_type,
            description=entity.description,
            top_k=10,
        )
        for hit_id, score, hit_name in hits:
            if hit_id == entity_id:
                continue
            similar.append(SimilarEntity(
                entity_id=hit_id,
                canonical_name=hit_name,
                cosine_score=score,
            ))
    except Exception as exc:
        logger.warning("entity_inspector: similarity lookup failed: %s", exc)

    # Triangulated facts about this entity as subject.
    triangulated: list[TriangulatedFact] = []
    try:
        from fichero.kg.triangulation import triples_for_entity
        for support in triples_for_entity(db, entity_id):
            triangulated.append(TriangulatedFact(
                predicate=support.key.predicate,
                object_text=support.key.object_text,
                support_count=support.support_count,
                weighted_support=support.weighted_support,
                corroboration=support.corroboration,
                source_document_ids=list(support.source_document_ids),
            ))
    except Exception as exc:
        logger.warning("entity_inspector: triangulation lookup failed: %s", exc)

    return EntityInspectorResponse(
        entity_id=entity_id,
        entity=entity,
        claim_count=len(claims),
        claims=claims,
        documents=documents,
        annotations=annotations,
        notes=notes,
        projects=projects,
        similar_entities=similar,
        triangulated_facts=triangulated,
    )
