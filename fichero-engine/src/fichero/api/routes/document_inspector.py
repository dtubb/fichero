"""Aggregate document inspector endpoint.

Returns everything the right-side inspector needs about a document
in a single response: claims, entities mentioned, annotations,
notes that reference it, citations in + out, source metadata,
project memberships. Replaces the 6-7 separate API calls a naive
SwiftUI inspector would make.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from fichero.api.main import get_library_database
from fichero.db import Database
from fichero.hermeneutics_models import Interpretation
from fichero.knowledge_models import (
    Annotation,
    DocumentCitation,
    KnowledgeClaim,
    KnowledgeEntity,
    Note,
    Project,
    ProjectInclusion,
)
from fichero.models import Document

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents")


class DocumentInspectorResponse(BaseModel):
    """Everything the inspector needs in one shot."""
    document_id: str
    document: dict[str, Any] | None
    source_metadata: dict[str, Any] | None
    claim_count: int
    claims: list[KnowledgeClaim]
    entities: list[KnowledgeEntity]
    annotations: list[Annotation]
    notes: list[Note]
    citations_outbound: list[DocumentCitation]  # what this doc cites
    citations_inbound: list[DocumentCitation]  # what cites this doc
    interpretations: list[Interpretation]
    projects: list[Project]


@router.get(
    "/{document_id}/inspector",
    response_model=DocumentInspectorResponse,
    summary="One-call aggregate of every KG row attached to this document",
    description=(
        "Returns claims, entities, annotations, notes, citations "
        "(both directions), interpretations, and project memberships. "
        "Use this to populate the right-side inspector with a single "
        "request instead of 7 separate ones. (#902 prep)"
    ),
)
async def inspector(
    document_id: str,
    db: Database = Depends(get_library_database),
) -> DocumentInspectorResponse:
    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(404, f"Document not found: {document_id}")

    # Claims for this document.
    all_claims = db.query(KnowledgeClaim)
    doc_claims = [c for c in all_claims if c.source_document_id == document_id]

    # Entities referenced by those claims.
    entity_ids: set[str] = set()
    for c in doc_claims:
        entity_ids.update(c.entity_ids or [])
    entities = [
        e for e in (db.get(KnowledgeEntity, eid) for eid in entity_ids)
        if e is not None
    ]
    entities.sort(key=lambda e: e.canonical_name)

    # Annotations on this document.
    annotations = [
        a for a in db.query(Annotation)
        if a.document_id == document_id
    ]
    annotations.sort(key=lambda a: a.created_at, reverse=True)

    # Notes that reference this document.
    notes = [
        n for n in db.query(Note)
        if document_id in (n.linked_document_ids or [])
    ]
    notes.sort(key=lambda n: n.updated_at, reverse=True)

    # Citations both directions.
    all_citations = db.query(DocumentCitation)
    citations_outbound = [
        c for c in all_citations if c.source_document_id == document_id
    ]
    citations_inbound = [
        c for c in all_citations if c.target_document_id == document_id
    ]

    # Interpretations attached to this document or to its claims.
    claim_id_set = {c.id for c in doc_claims}
    interpretations = [
        i for i in db.query(Interpretation)
        if i.document_id == document_id
        or (i.claim_id and i.claim_id in claim_id_set)
    ]
    interpretations.sort(key=lambda i: i.created_at, reverse=True)

    # Project memberships.
    inclusions = [
        incl for incl in db.query(ProjectInclusion)
        if incl.target_id == document_id and incl.target_type == "document"
    ]
    project_ids = {incl.project_id for incl in inclusions}
    projects = [
        p for p in (db.get(Project, pid) for pid in project_ids)
        if p is not None
    ]

    return DocumentInspectorResponse(
        document_id=document_id,
        document=doc.model_dump(mode="json"),
        source_metadata=doc.source_metadata,
        claim_count=len(doc_claims),
        claims=doc_claims,
        entities=entities,
        annotations=annotations,
        notes=notes,
        citations_outbound=citations_outbound,
        citations_inbound=citations_inbound,
        interpretations=interpretations,
        projects=projects,
    )
