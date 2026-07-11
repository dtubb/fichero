"""Aggregate document inspector endpoint.

Returns everything the right-side inspector needs about a document
in a single response: claims, entities mentioned, annotations,
notes that reference it, citations in + out, source metadata,
project memberships. Replaces the 6-7 separate API calls a naive
SwiftUI inspector would make.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from fichero.api.main import get_library_database
from fichero.api.routes.documents import _document_or_404, _normalize_document_id
from fichero.db import Database
from fichero.hermeneutics_models import Interpretation
from fichero.knowledge_models import (
    Annotation,
    BookStructureNode,
    DocumentCitation,
    EntityType,
    KnowledgeClaim,
    KnowledgeEntity,
    Note,
    Project,
    ProjectInclusion,
)
from fichero.models import Artifact, Document, DocType

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


class DocumentOutlineRow(BaseModel):
    id: str
    depth: int
    kind: str
    label: str
    count: int
    parent_id: str | None = None
    source_document_id: str | None = None
    page_label: str | None = None
    source_capability: str = "reveal"


class DocumentOutlineResponse(BaseModel):
    document_id: str
    rows: list[DocumentOutlineRow]
    count: int


class DocumentRollupResponse(BaseModel):
    """Cheap per-type child counts for a document (#2258).

    Populates a *collapsed* outline row in the library Table without
    assembling the full child payload — the SwiftUI library shows these
    counts on a collapsed document and only fetches the heavier per-type
    children when the disclosure is expanded. Counts roll up the
    document and every descendant page/chunk (mirroring the inspector
    aggregation scope), but skip all entity resolution / dedup /
    merge-chain walking so the query stays a handful of cheap COUNTs.
    """
    document_id: str
    artifacts: int
    entities: int
    notes: int
    claims: int
    pages: int


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
    document_id = _normalize_document_id(document_id)
    doc = _document_or_404(db, document_id)

    from fichero.api.routes.claims import _descendant_doc_ids

    doc_ids = _descendant_doc_ids(db, document_id)

    # Claims for this document and any descendant pages/chunks. Page
    # selections still resolve to {page_id}; parent PDFs/folders roll up
    # page-level extraction rows for display.
    all_claims = db.query(KnowledgeClaim)
    doc_claims = [c for c in all_claims if c.source_document_id in doc_ids]

    # Entities referenced by those claims.
    entity_ids: set[str] = set()
    for c in doc_claims:
        entity_ids.update(c.entity_ids or [])
    entities = [
        e for e in (db.get(KnowledgeEntity, eid) for eid in entity_ids)
        if e is not None
    ]
    # #1562 union: also include entities whose own per-page scope
    # (source_document_ids, recorded at upsert) intersects this doc — so
    # entities imported WITHOUT claims (e.g. IIIF/W3C tagging annotations,
    # which carry no SVO) still surface in the inspector. Mirrors the
    # /entities?document_id= list endpoint. Dedup by id.
    seen_ids = {e.id for e in entities}
    for entity in db.all(KnowledgeEntity):
        if entity.id in seen_ids:
            continue
        if doc_ids.intersection(entity.source_document_ids or []):
            entities.append(entity)
            seen_ids.add(entity.id)
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
        c for c in all_citations if c.source_document_id in doc_ids
    ]
    citations_inbound = [
        c for c in all_citations if c.target_document_id in doc_ids
    ]

    # Interpretations attached to this document or to its claims.
    claim_id_set = {c.id for c in doc_claims}
    interpretations = [
        i for i in db.query(Interpretation)
        if i.document_id in doc_ids
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


@router.get(
    "/{document_id}/outline",
    response_model=DocumentOutlineResponse,
    summary="Hierarchical source outline for document drill-down",
)
async def document_outline(
    document_id: str,
    db: Database = Depends(get_library_database),
) -> DocumentOutlineResponse:
    document_id = _normalize_document_id(document_id)
    _document_or_404(db, document_id)

    from fichero.api.routes.claims import _descendant_doc_ids

    doc_ids = _descendant_doc_ids(db, document_id)
    descendants = [d for d in db.query(Document) if d.id in doc_ids and d.id != document_id]
    pages = sorted(
        [d for d in descendants if d.doc_type == DocType.page],
        key=lambda d: (d.sequence or 0, d.name),
    )
    chunks = [d for d in descendants if d.doc_type == DocType.chunk]

    claims = [c for c in db.query(KnowledgeClaim) if c.source_document_id in doc_ids]
    annotations = [a for a in db.query(Annotation) if a.document_id in doc_ids]
    artifacts = [a for a in db.query(Artifact) if a.document_id in doc_ids]
    citations = [
        c for c in db.query(DocumentCitation)
        if c.source_document_id in doc_ids or c.target_document_id in doc_ids
    ]

    page_id_by_sequence = {p.sequence: p.id for p in pages if p.sequence is not None}
    claim_count_by_doc: dict[str, int] = {}
    for claim in claims:
        claim_count_by_doc[claim.source_document_id] = claim_count_by_doc.get(claim.source_document_id, 0) + 1
    annotation_count_by_doc: dict[str, int] = {}
    for ann in annotations:
        annotation_count_by_doc[ann.document_id] = annotation_count_by_doc.get(ann.document_id, 0) + 1
    artifact_count_by_doc: dict[str, int] = {}
    for artifact in artifacts:
        artifact_count_by_doc[artifact.document_id] = artifact_count_by_doc.get(artifact.document_id, 0) + 1
    citation_count_by_doc: dict[str, int] = {}
    for citation in citations:
        if citation.source_document_id in doc_ids:
            citation_count_by_doc[citation.source_document_id] = citation_count_by_doc.get(citation.source_document_id, 0) + 1
        if citation.target_document_id in doc_ids:
            citation_count_by_doc[citation.target_document_id] = citation_count_by_doc.get(citation.target_document_id, 0) + 1

    rows: list[DocumentOutlineRow] = []
    for page in pages:
        rows.append(
            DocumentOutlineRow(
                id=page.id,
                depth=1,
                kind="page",
                label=page.name,
                count=(
                    claim_count_by_doc.get(page.id, 0)
                    + annotation_count_by_doc.get(page.id, 0)
                    + artifact_count_by_doc.get(page.id, 0)
                    + citation_count_by_doc.get(page.id, 0)
                ),
                parent_id=document_id,
                source_document_id=page.id,
                page_label=str(page.sequence) if page.sequence is not None else None,
            )
        )

    for chunk in chunks:
        rows.append(
            DocumentOutlineRow(
                id=chunk.id,
                depth=2,
                kind="chunk",
                label=chunk.name,
                count=(
                    claim_count_by_doc.get(chunk.id, 0)
                    + annotation_count_by_doc.get(chunk.id, 0)
                    + artifact_count_by_doc.get(chunk.id, 0)
                    + citation_count_by_doc.get(chunk.id, 0)
                ),
                parent_id=chunk.parent_id,
                source_document_id=chunk.parent_id or document_id,
            )
        )

    structure_nodes = [
        s for s in db.query(BookStructureNode)
        if s.source_document_id == document_id
    ]
    structure_nodes.sort(key=lambda s: (s.level, s.start_sequence, s.title))
    for node in structure_nodes:
        in_range_doc_ids = {
            page_id_by_sequence.get(seq)
            for seq in range(node.start_sequence, (node.end_sequence or node.start_sequence) + 1)
        }
        in_range_doc_ids.discard(None)
        rows.append(
            DocumentOutlineRow(
                id=node.id,
                depth=node.level,
                kind=node.kind,
                label=node.title,
                count=sum(claim_count_by_doc.get(pid, 0) for pid in in_range_doc_ids),
                source_document_id=document_id,
            )
        )

    linked_entity_ids = {
        entity_id
        for claim in claims
        for entity_id in (claim.entity_ids or [])
        if entity_id
    }
    entities = [
        entity for entity in (db.get(KnowledgeEntity, entity_id) for entity_id in linked_entity_ids)
        if entity is not None
    ]
    rows.append(
        DocumentOutlineRow(
            id=f"{document_id}:annotations",
            depth=1,
            kind="annotation-group",
            label="Annotations",
            count=len(annotations),
            parent_id=document_id,
            source_capability="group",
        )
    )
    rows.append(
        DocumentOutlineRow(
            id=f"{document_id}:entities",
            depth=1,
            kind="entity-group",
            label="Entities",
            count=len(entities),
            parent_id=document_id,
            source_capability="group",
        )
    )

    return DocumentOutlineResponse(document_id=document_id, rows=rows, count=len(rows))


@router.get(
    "/{document_id}/rollup",
    response_model=DocumentRollupResponse,
    summary="Cheap per-type child counts for a collapsed library outline row",
    description=(
        "Returns per-type child counts (artifacts, entities, notes, "
        "claims, pages) for a document, rolled up over the document and "
        "every descendant page/chunk. The library Table renders these on "
        "a *collapsed* outline row so it can show 'N entities, M notes' "
        "without fetching the children; the heavier per-type payloads are "
        "loaded only when the disclosure is expanded (#2258).\n\n"
        "This is intentionally cheap — plain counts with no entity "
        "resolution, dedup, or merge-chain walking. The ``entities`` "
        "count therefore mirrors the inspector's union (entities linked "
        "by this document's claims plus entities whose per-page scope "
        "intersects the document) and is NOT the deduped/merge-resolved "
        "figure from /knowledge-graph. ``pages`` counts descendant page "
        "documents only (not the document itself)."
    ),
)
async def document_rollup(
    document_id: str,
    db: Database = Depends(get_library_database),
) -> DocumentRollupResponse:
    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(404, f"Document not found: {document_id}")

    from fichero.api.routes.claims import _descendant_doc_ids

    doc_ids = _descendant_doc_ids(db, document_id)

    pages = sum(
        1
        for d in db.query(Document)
        if d.id in doc_ids and d.id != document_id and d.doc_type == DocType.page
    )
    artifacts = sum(1 for a in db.query(Artifact) if a.document_id in doc_ids)
    claims = [c for c in db.query(KnowledgeClaim) if c.source_document_id in doc_ids]
    notes = sum(
        1
        for n in db.query(Note)
        if doc_ids.intersection(n.linked_document_ids or [])
    )

    # Entities: union of (entities linked by this doc's claims) and
    # (entities whose own per-page scope intersects this doc). Mirrors
    # the inspector union (#1562) so the collapsed count matches what
    # the expanded entity group will show, but counts ids only — no
    # entity fetch, dedup, or merge resolution.
    entity_ids: set[str] = set()
    for claim in claims:
        entity_ids.update(claim.entity_ids or [])
    for entity in db.query(KnowledgeEntity):
        if entity.id in entity_ids:
            continue
        if doc_ids.intersection(entity.source_document_ids or []):
            entity_ids.add(entity.id)

    return DocumentRollupResponse(
        document_id=document_id,
        artifacts=artifacts,
        entities=len(entity_ids),
        notes=notes,
        claims=len(claims),
        pages=pages,
    )


# =============================================================================
# Canonical document knowledge-graph endpoint (#1068)
#
# The list-view row and the KG inspector tab used to re-derive their
# entity groupings independently — the list view parsed raw artifact
# JSON, the inspector ran listClaims + an O(n) getEntity fan-out and
# grouped client-side. They drifted: the inspector dropped the Dates
# section, under-counted Events, and disagreed on the entity set.
#
# This endpoint is the single source of truth. It resolves entities,
# follows merge chains to the canonical entity (so absorbed entities'
# claims are NOT lost), groups by kind including a synthetic "date"
# kind for entity-less date claims, dedups within a kind, and returns
# the groups in display order. SwiftUI surfaces render this verbatim.
# =============================================================================

# Kind ids the UI groups by. "date" is synthetic — date-style claims
# carry no canonical entity (empty entity_ids), so they have no
# EntityType; they are bucketed here by the absence of an entity.
_KIND_LABELS: dict[str, str] = {
    "concept": "Keywords",
    "person": "People",
    "location": "Places",
    "organization": "Organizations",
    "event": "Events",
    "date": "Dates",
    "other": "Other",
}
# Densest-summary-first, matching the SwiftUI displayOrder intent but
# WITH the Dates section restored (its omission was the #1068 bug).
_KIND_DISPLAY_ORDER: list[str] = [
    "concept", "person", "location", "organization", "event", "date", "other",
]


class KGEntityItem(BaseModel):
    """One deduped row in a kind group.

    For entity-bearing claims this is a canonical KnowledgeEntity.
    For date-style claims (no entity) it is the claim itself, keyed
    on claim text. ``claim_ids`` collects every claim that collapsed
    into this row so callers can still reach the provenance.
    """
    entity_id: str | None
    canonical_name: str
    entity_type: str
    description: str | None
    aliases: list[str]
    claim_ids: list[str]
    source_document_id: str | None
    source_page_label: str | None
    source_excerpt: str | None


class KGEntityGroup(BaseModel):
    kind: str
    label: str
    items: list[KGEntityItem]


class DocumentKnowledgeGraphResponse(BaseModel):
    document_id: str
    include_children: bool
    groups: list[KGEntityGroup]
    claims: list[KnowledgeClaim]
    entity_count: int
    claim_count: int
    # Catalogue artifacts on this document (#1047). Empty for leaf docs;
    # a folder/container that has been catalogued carries its narrative /
    # timeline / keywords artifacts here so the KG tab can render the
    # readable synthesis as a header above the entity-kind sections.
    # Ordered narrative-first so the UI can take catalogue[0] as the headline.
    catalogue: list[Artifact]


def _resolve_canonical(
    db: Database, entity_id: str, _seen: set[str] | None = None
) -> KnowledgeEntity | None:
    """Follow ``merged_into_id`` to the canonical entity.

    Absorbed entities still carry their original claims; following the
    merge chain (instead of skipping merged entities, as the old
    SwiftUI code did) keeps those claims attributed rather than
    silently dropped. Guards against cycles in malformed merge data.
    """
    seen = _seen or set()
    entity = db.get(KnowledgeEntity, entity_id)
    while entity is not None and entity.merged_into_id:
        if entity.id in seen:
            break
        seen.add(entity.id)
        entity = db.get(KnowledgeEntity, entity.merged_into_id)
    return entity


# Catalogue artifact types, in the order the UI should surface them.
# The narrative is the headline; timeline and keywords follow. Legacy
# single-output "catalogue" shares slot 0 with the narrative — the
# catalogue tool deletes prior catalogue.* on rerun so the two only
# coexist transiently; if they do, the created_at tie-break wins.
_CATALOGUE_TYPE_ORDER: dict[str, int] = {
    "catalogue.narrative": 0,
    "catalogue": 0,
    "catalogue.timeline": 1,
    "catalogue.keywords": 2,
}


def _is_catalogue_artifact(artifact_type: str | None) -> bool:
    at = artifact_type or ""
    return at == "catalogue" or at.startswith("catalogue.")


def _catalogue_artifacts(db: Database, document_id: str) -> list[Artifact]:
    """Catalogue artifacts on this document, narrative-first (#1047).

    The catalogue workflow writes its synthesis (narrative / timeline /
    keywords — multi-output, #805) onto the container/folder document.
    Leaf documents have none, so this returns an empty list for them.
    """
    catalogue = [
        a for a in db.query(Artifact, document_id=document_id)
        if _is_catalogue_artifact(a.artifact_type)
    ]
    catalogue.sort(
        key=lambda a: (
            _CATALOGUE_TYPE_ORDER.get(a.artifact_type or "", 99),
            # created_at has a default_factory but unmigrated rows could
            # be null — don't let a missing timestamp 500 the whole KG
            # response and mask a catalogue that genuinely exists.
            -(a.created_at.timestamp() if a.created_at else 0.0),
        )
    )
    return catalogue


def _build_knowledge_graph(
    db: Database,
    document_id: str,
    doc_claims: list[KnowledgeClaim],
    include_children: bool,
    catalogue: list[Artifact],
) -> DocumentKnowledgeGraphResponse:
    """Group/dedup/merge-resolve a claim set into kind buckets.

    Shared by the leaf-document path and the include_children
    parent-PDF aggregation path.
    """
    # entity-id -> resolved canonical entity (cache: merge chains repeat).
    canonical_cache: dict[str, KnowledgeEntity | None] = {}

    # kind -> dedup-key -> KGEntityItem
    buckets: dict[str, dict[str, KGEntityItem]] = {}

    for claim in doc_claims:
        entity_id = (claim.entity_ids or [None])[0]
        entity: KnowledgeEntity | None = None
        if entity_id:
            if entity_id not in canonical_cache:
                canonical_cache[entity_id] = _resolve_canonical(db, entity_id)
            entity = canonical_cache[entity_id]

        if entity is not None:
            kind = (
                entity.entity_type.value
                if isinstance(entity.entity_type, EntityType)
                else str(entity.entity_type)
            )
            if kind not in _KIND_LABELS:
                kind = "other"
            dedup_key = entity.canonical_name
            display_name = entity.canonical_name
            description = (entity.description or "").strip() or None
            aliases = entity.aliases or []
        else:
            # Entity-less claim — date-style. Key on claim text.
            kind = "date"
            dedup_key = claim.text
            display_name = claim.text
            description = None
            aliases = []

        kind_bucket = buckets.setdefault(kind, {})
        existing = kind_bucket.get(dedup_key)
        if existing is not None:
            # Collapse into the existing row; keep the provenance trail.
            if claim.id:
                existing.claim_ids.append(claim.id)
            continue

        kind_bucket[dedup_key] = KGEntityItem(
            entity_id=entity.id if entity is not None else None,
            canonical_name=display_name,
            entity_type=kind,
            description=description,
            aliases=aliases,
            claim_ids=[claim.id] if claim.id else [],
            source_document_id=claim.source_document_id,
            source_page_label=claim.source_page_label,
            source_excerpt=(claim.source_excerpt or "").strip() or None,
        )

    groups: list[KGEntityGroup] = []
    entity_count = 0
    for kind in _KIND_DISPLAY_ORDER:
        items = list(buckets.get(kind, {}).values())
        if not items:
            continue
        items.sort(key=lambda i: i.canonical_name.lower())
        entity_count += len(items)
        groups.append(
            KGEntityGroup(kind=kind, label=_KIND_LABELS[kind], items=items)
        )

    return DocumentKnowledgeGraphResponse(
        document_id=document_id,
        include_children=include_children,
        groups=groups,
        claims=doc_claims,
        entity_count=entity_count,
        claim_count=len(doc_claims),
        catalogue=catalogue,
    )


@router.get(
    "/{document_id}/knowledge-graph",
    response_model=DocumentKnowledgeGraphResponse,
    summary="Canonical KG grouping for a document — deduped, merge-resolved",
    description=(
        "The single source of truth for a document's knowledge graph. "
        "Resolves entities, follows merge chains to the canonical "
        "entity (absorbed entities' claims are kept, not dropped), "
        "groups by kind — including a Dates group for entity-less "
        "date claims — dedups within each kind, and returns the "
        "groups in display order. The list-view row and the KG "
        "inspector tab both render this verbatim so they can no "
        "longer disagree (#1068).\n\n"
        "With ``include_children=true`` the query walks the document "
        "tree (BFS) and aggregates every descendant's claims onto the "
        "parent. extract_all writes claims to PAGE doc ids, never the "
        "parent PDF — so a parent PDF queried without this flag looks "
        "empty even though its pages are full of entities (#1069).\n\n"
        "The ``catalogue`` field carries any catalogue artifacts on the "
        "document (narrative / timeline / keywords), narrative-first, so "
        "a catalogued folder can render its readable synthesis above the "
        "entity-kind sections (#1047). Empty for leaf documents."
    ),
)
async def knowledge_graph(
    document_id: str,
    include_children: Annotated[bool, Query()] = False,
    db: Database = Depends(get_library_database),
) -> DocumentKnowledgeGraphResponse:
    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(404, f"Document not found: {document_id}")

    from fichero.api.routes.claims import _descendant_doc_ids

    descendant_ids = _descendant_doc_ids(db, document_id)
    should_include_children = include_children or len(descendant_ids) > 1
    doc_ids = descendant_ids if should_include_children else {document_id}

    doc_claims = [
        c for c in db.query(KnowledgeClaim)
        if c.source_document_id in doc_ids
    ]
    # Catalogue artifacts live on the inspected document itself (the
    # container), never its page children — so this is queried on
    # document_id directly, independent of include_children.
    catalogue = _catalogue_artifacts(db, document_id)
    return _build_knowledge_graph(
        db, document_id, doc_claims, should_include_children, catalogue
    )
