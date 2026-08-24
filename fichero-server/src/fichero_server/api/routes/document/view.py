"""fichero_server.api.routes.document.view — the ONE outline endpoint.

Mandate 1 (approved 2026-08-24): the front end built the containment/
attachment tree at least five ways — sidebar child cache, grid loadChildren,
entry-ladder walk, two breadcrumb walks, dataset router — each with its own
cache and its own bugs (the sidebar 3-of-151 class, crumbs missing middle
ancestors). This route answers the whole question ONCE:

    GET /api/documents/{doc_id}/view?level=stored&children=true&attachments=true

    { ancestors: [...root-first], document: {...},
      children: [...level-aware, server-sorted],
      attachments: { renditions, artifacts, annotation_count, entity_count } }

Composes the SAME pieces the split routes use — the guarded ancestor walk,
`resolve_level` for the tier, `order_renditions`, the lean artifact list
shape — so an outline answer can never disagree with the per-piece answers
while both exist. The flags let a cheap caller skip halves; `attachments`
describes the ANCHOR document only (children carry `child_count`, not
payloads).
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from fichero_server.api.main import get_library_database
from fichero_server.db import Database
from fichero_server.db.node_levels import NodeLevel, resolve_level
from fichero_server.media.rendition_order import order_renditions
from fichero_server.models import Artifact, Document, Rendition
from fichero_server.models.knowledge import Annotation, KnowledgeEntity
from fichero_server.core.perf import perf_span

from .artifacts import ArtifactResponse, _artifact_response
from .documents import (
    _filter_resolvable_documents,
    _get_document_row,
    _list_documents,
    _normalize_document_id,
    _ordered_by_sort_order,
    _with_child_counts,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class DocumentViewAttachments(BaseModel):
    """What the anchor document HAS — the attachment summary consumers read
    instead of fanning out to the renditions/artifacts/annotations routes."""

    renditions: list[Rendition]
    artifacts: list[ArtifactResponse]
    annotation_count: int
    entity_count: int


class DocumentViewResponse(BaseModel):
    """One document's whole neighbourhood: where it sits, what it holds,
    what hangs off it."""

    ancestors: list[Document]
    document: Document
    children: list[Document]
    attachments: DocumentViewAttachments | None = None


def _ancestor_rows(db: Database, anchor: Document) -> list[Document]:
    """The parent chain, root-first — the same cycle-guarded walk
    `get_ancestors` does (a malformed parent cycle must not loop; a lookup
    that answers with a different row than asked must not defeat the guard)."""
    ancestors: list[Document] = []
    seen = {anchor.id}
    current = anchor
    while current.parent_id and current.parent_id not in seen:
        seen.add(current.parent_id)
        parent = _get_document_row(db, current.parent_id)
        if parent is None:
            break
        ancestors.append(parent)
        seen.add(parent.id)
        current = parent
    ancestors.reverse()
    return ancestors


def _anchor_attachments(db: Database, doc_id: str) -> DocumentViewAttachments:
    renditions = order_renditions(db.query(Rendition, document_id=doc_id))
    artifacts = [
        _artifact_response(a) for a in db.query(Artifact, document_id=doc_id)
    ]
    annotation_count = len(db.query(Annotation, document_id=doc_id))
    # Entities record the pages they were extracted from
    # (`source_document_ids`, #1562); membership is the honest per-document
    # count. A full-table scan, like the inspector's — one anchor at a time.
    entity_count = sum(
        1 for entity in db.query(KnowledgeEntity) if doc_id in entity.source_document_ids
    )
    return DocumentViewAttachments(
        renditions=renditions,
        artifacts=artifacts,
        annotation_count=annotation_count,
        entity_count=entity_count,
    )


@router.get(
    "/{doc_id}/view",
    response_model=DocumentViewResponse,
    # Declared, not merely raised (the renditions-route rule): an undeclared
    # 404 reaches the generated Swift client as `.undocumented` it cannot name.
    responses={404: {"description": "No document with this id exists"}},
)
async def get_document_view(
    doc_id: str,
    level: NodeLevel = Query(
        NodeLevel.stored,
        description=(
            "Which tier `children` returns. 'stored' (default) is the tree as "
            "held — the sidebar's STRUCTURAL view (ruled 2026-08-24); "
            "'content' looks through containers to their pages, the grid's "
            "view."
        ),
    ),
    children: bool = Query(True, description="Include the children list."),
    attachments: bool = Query(
        True, description="Include the anchor's attachment summary."
    ),
    db: Database = Depends(get_library_database),
) -> DocumentViewResponse:
    """One response for 'where am I, what's in here, what does it have'."""
    with perf_span("library.document_view", logger=logger, doc_id=doc_id) as perf:
        normalized_id = _normalize_document_id(doc_id)

        # Off the event loop, like get_children: this is synchronous DuckDB
        # work, and inline it would serialize every concurrent GET.
        def _fetch() -> DocumentViewResponse:
            anchor = _get_document_row(db, normalized_id)
            if anchor is None:
                raise HTTPException(
                    status_code=404, detail=f"Document not found: {doc_id}"
                )

            child_rows: list[Document] = []
            if children:
                rows = _filter_resolvable_documents(
                    db,
                    _list_documents(db, parent_id=normalized_id),
                    parent_id=normalized_id,
                )
                rows = _ordered_by_sort_order(rows)
                child_rows = resolve_level(
                    db,
                    rows,
                    level,
                    children_of=lambda doc: _filter_resolvable_documents(
                        db,
                        _list_documents(db, parent_id=doc.id),
                        parent_id=doc.id,
                    ),
                )
                child_rows = _with_child_counts(db, child_rows)

            return DocumentViewResponse(
                ancestors=_ancestor_rows(db, anchor),
                document=anchor,
                children=child_rows,
                attachments=(
                    _anchor_attachments(db, normalized_id) if attachments else None
                ),
            )

        response = await asyncio.to_thread(_fetch)
        perf["ancestors"] = len(response.ancestors)
        perf["children"] = len(response.children)
        return response
