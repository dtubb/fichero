"""NetworkX-backed KG analytics routes (#376).

Exposes the ``fichero.kg.graph`` module as HTTP endpoints:

- ``GET /api/kg/graph/centrality`` — top-k most central entities,
  optionally filtered by entity type.
- ``GET /api/kg/graph/cooccurrence/{entity_id}`` — neighbours of an
  entity in the co-occurrence graph, sorted by edge weight.
- ``GET /api/kg/graph/path?source=X&target=Y`` — shortest path
  between two entities through the directed claim graph.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from fichero.api.main import get_library_database
from fichero.db import Database

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/kg/graph")


class CentralityRow(BaseModel):
    """One entity in the centrality ranking."""
    entity_id: str
    canonical_name: str
    degree: int
    betweenness: float
    eigenvector: float


@router.get(
    "/centrality",
    response_model=list[CentralityRow],
    summary="Top-k entities by composite centrality",
    description=(
        "Ranks entities by degree + betweenness + eigenvector "
        "centrality (z-score normalised). Optionally filter to one "
        "EntityType to ask 'who is most central among the people' "
        "vs 'which places connect the most claims'. (#376)"
    ),
)
async def centrality(
    top_k: int = Query(default=20, ge=1, le=200),
    entity_type: str | None = Query(
        default=None,
        description="Filter to one EntityType (person/location/...).",
    ),
    db: Database = Depends(get_library_database),
) -> list[CentralityRow]:
    from fichero.kg.graph import build_full_cooccurrence, centrality as compute_centrality

    g = build_full_cooccurrence(db)
    scores = compute_centrality(g, top_k=top_k, only_type=entity_type)
    return [
        CentralityRow(
            entity_id=s.entity_id,
            canonical_name=s.canonical_name,
            degree=s.degree,
            betweenness=s.betweenness,
            eigenvector=s.eigenvector,
        )
        for s in scores
    ]


class CooccurrenceNeighbour(BaseModel):
    """One entity adjacent to the query entity in the co-occurrence graph."""
    entity_id: str
    canonical_name: str
    entity_type: str
    weight: int  # number of shared source documents


@router.get(
    "/cooccurrence/{entity_id}",
    response_model=list[CooccurrenceNeighbour],
    summary="Co-occurrence neighbours of an entity",
    description=(
        "Returns every other entity that shares a source document "
        "with the target, sorted by descending co-occurrence count. "
        "Use case: 'who appears alongside Eugenio Córdoba in the "
        "archive?' (#376)"
    ),
)
async def cooccurrence_neighbours(
    entity_id: str,
    db: Database = Depends(get_library_database),
) -> list[CooccurrenceNeighbour]:
    from fichero.kg.graph import build_full_cooccurrence, NODE_NAME, NODE_TYPE

    g = build_full_cooccurrence(db)
    if entity_id not in g:
        raise HTTPException(status_code=404, detail=f"Entity not found in graph: {entity_id}")

    rows = []
    for other in g.neighbors(entity_id):
        attrs = g.nodes[other]
        rows.append(CooccurrenceNeighbour(
            entity_id=other,
            canonical_name=attrs.get(NODE_NAME, ""),
            entity_type=attrs.get(NODE_TYPE, ""),
            weight=g[entity_id][other]["weight"],
        ))
    rows.sort(key=lambda r: -r.weight)
    return rows


class PathResponse(BaseModel):
    """Shortest path between two entities as a list of entity IDs."""
    source_id: str
    target_id: str
    path: list[str]
    length: int  # path length in edges; 0 means no path


class GraphMetricsResponse(BaseModel):
    """Library-wide KG counts + averages. Drives the inspector summary."""
    entity_count: int
    claim_count: int
    annotation_count: int
    note_count: int
    interpretation_count: int
    document_citation_count: int
    project_count: int
    avg_claims_per_entity: float
    avg_entities_per_claim: float


@router.get(
    "/metrics",
    response_model=GraphMetricsResponse,
    summary="Library-wide KG metrics (counts + averages)",
    description=(
        "One-call summary for the KG sidebar overview. Ported from "
        "the now-deprecated /api/graph/metrics into the canonical "
        "/api/kg namespace with the modern model shapes. (#919 5b)"
    ),
)
async def metrics(
    db: Database = Depends(get_library_database),
) -> GraphMetricsResponse:
    from fichero.hermeneutics_models import Interpretation
    from fichero.knowledge_models import (
        Annotation,
        DocumentCitation,
        KnowledgeClaim,
        KnowledgeEntity,
        Note,
        Project,
    )

    entities = db.query(KnowledgeEntity)
    claims = db.query(KnowledgeClaim)

    total_claim_links_per_entity = sum(1 for c in claims for _ in (c.entity_ids or []))
    avg_cpe = (
        (total_claim_links_per_entity / len(entities)) if entities else 0.0
    )
    avg_epc = (
        (total_claim_links_per_entity / len(claims)) if claims else 0.0
    )

    return GraphMetricsResponse(
        entity_count=len(entities),
        claim_count=len(claims),
        annotation_count=len(db.query(Annotation)),
        note_count=len(db.query(Note)),
        interpretation_count=len(db.query(Interpretation)),
        document_citation_count=len(db.query(DocumentCitation)),
        project_count=len(db.query(Project)),
        avg_claims_per_entity=round(avg_cpe, 2),
        avg_entities_per_claim=round(avg_epc, 2),
    )


class TraverseNode(BaseModel):
    id: str
    type: str  # "entity" or "claim"
    label: str
    depth: int
    metadata: dict | None = None


class TraverseEdge(BaseModel):
    source: str
    target: str
    type: str
    depth: int


class TraverseResponse(BaseModel):
    entity_id: str
    nodes: list[TraverseNode]
    edges: list[TraverseEdge]
    max_depth: int


@router.get(
    "/traverse/{entity_id}",
    response_model=TraverseResponse,
    summary="BFS traversal — entity neighbourhood",
    description=(
        "Breadth-first walk from the entity through its claims and "
        "claim-linked relations, up to ``max_depth`` hops. Use for the "
        "SwiftUI force-directed neighbourhood view (#902). Ported "
        "from the now-deprecated /api/graph/traverse — same shape, "
        "lives under the canonical /api/kg/graph namespace. (#919 5b)"
    ),
)
async def traverse(
    entity_id: str,
    max_depth: int = Query(default=2, ge=1, le=5),
    include_claims: bool = Query(default=True),
    db: Database = Depends(get_library_database),
) -> TraverseResponse:
    from fichero.knowledge_models import (
        KnowledgeClaim,
        KnowledgeClaimLink,
        KnowledgeEntity,
    )

    root = db.get(KnowledgeEntity, entity_id)
    if root is None:
        raise HTTPException(404, f"Entity not found: {entity_id}")

    visited: set[str] = {entity_id}
    nodes: list[TraverseNode] = [
        TraverseNode(
            id=root.id, type="entity", label=root.canonical_name,
            depth=0,
            metadata={
                "entity_type": (
                    root.entity_type.value
                    if hasattr(root.entity_type, "value")
                    else str(root.entity_type)
                ),
                "aliases": root.aliases or [],
            },
        )
    ]
    edges: list[TraverseEdge] = []
    queue: list[tuple[str, int]] = [(entity_id, 0)]

    while queue:
        current_id, current_depth = queue.pop(0)
        if current_depth >= max_depth:
            continue

        if include_claims:
            for claim in db.query(KnowledgeClaim):
                if current_id not in (claim.entity_ids or []):
                    continue
                if claim.id not in visited:
                    visited.add(claim.id)
                    nodes.append(TraverseNode(
                        id=claim.id, type="claim", label=claim.text[:120],
                        depth=current_depth + 1,
                        metadata={
                            "epistemic_status": (
                                claim.epistemic_status.value
                                if claim.epistemic_status
                                else None
                            ),
                        },
                    ))
                    queue.append((claim.id, current_depth + 1))
                edges.append(TraverseEdge(
                    source=current_id, target=claim.id,
                    type="mentioned_in", depth=current_depth + 1,
                ))

        # Walk claim-to-claim links one hop further.
        for link in db.query(KnowledgeClaimLink):
            if link.source_claim_id == current_id and link.target_claim_id not in visited:
                target = db.get(KnowledgeClaim, link.target_claim_id)
                if target is None:
                    continue
                visited.add(target.id)
                nodes.append(TraverseNode(
                    id=target.id, type="claim", label=target.text[:120],
                    depth=current_depth + 1,
                    metadata={
                        "relation": (
                            link.relation.value
                            if hasattr(link.relation, "value")
                            else str(link.relation)
                        ),
                    },
                ))
                queue.append((target.id, current_depth + 1))
                edges.append(TraverseEdge(
                    source=current_id, target=target.id,
                    type=(
                        link.relation.value
                        if hasattr(link.relation, "value")
                        else str(link.relation)
                    ),
                    depth=current_depth + 1,
                ))

    return TraverseResponse(
        entity_id=entity_id, nodes=nodes, edges=edges, max_depth=max_depth,
    )


@router.get(
    "/path",
    response_model=PathResponse,
    summary="Shortest path between two entities",
    description=(
        "Finds the shortest sequence of claim edges connecting "
        "source → target. Returns an empty path with length 0 "
        "when no connection exists. (#376)"
    ),
)
async def shortest_path(
    source: str = Query(..., description="Source entity ID"),
    target: str = Query(..., description="Target entity ID"),
    db: Database = Depends(get_library_database),
) -> PathResponse:
    from fichero.kg.graph import build_full_graph, shortest_path_entities

    g = build_full_graph(db)
    path = shortest_path_entities(g, source, target)
    return PathResponse(
        source_id=source,
        target_id=target,
        path=path,
        length=max(0, len(path) - 1),
    )


# ---------------------------------------------------------------------------
# GET /api/kg/graph/neighborhood/{entity_id} — focus-neighborhood viz feed
# ---------------------------------------------------------------------------
#
# Returns a focus entity + its k-hop neighbor entities + the SVO-labeled
# claim edges connecting them. Each edge carries the verb/object as the
# predicate, plus full source provenance (source_document_id +
# source_page_label + source_char_start/end + source_excerpt) so the
# SwiftUI focus-neighborhood view (#976) can render "open source"
# affordances per edge. (#983 / #987)


class NeighborEntity(BaseModel):
    """A neighbor entity surfaced in the focus-neighborhood view."""
    id: str
    canonical_name: str
    entity_type: str | None = None
    aliases: list[str] = []
    description: str | None = None
    hop: int  # 1 = direct neighbor, 2 = neighbor-of-neighbor, …


class NeighborhoodEdge(BaseModel):
    """One SVO-labeled edge between two entities. Carries the predicate
    (verb) + the full source provenance so the UI can navigate to the
    exact span in the source document."""
    source_id: str
    target_id: str
    target_label: str  # canonical_name if target_id is an entity; literal object phrase otherwise
    target_is_entity: bool
    predicate: str  # verb from claim.metadata, or "mentions" fallback
    claim_id: str
    claim_text: str
    source_document_id: str
    source_page_label: str | None = None
    source_char_start: int | None = None
    source_char_end: int | None = None
    source_excerpt: str | None = None
    claim_type: str | None = None
    epistemic_status: str | None = None
    confidence: float | None = None


class NeighborhoodResponse(BaseModel):
    """Focus entity + neighbors + SVO edges. Bounded by `hops` + `limit`."""
    focus_entity_id: str
    focus_canonical_name: str
    focus_entity_type: str | None = None
    focus_description: str | None = None
    focus_aliases: list[str] = []
    neighbors: list[NeighborEntity]
    edges: list[NeighborhoodEdge]
    truncated: bool  # True if `limit` cut off neighbors that would otherwise have been included


@router.get(
    "/neighborhood/{entity_id}",
    response_model=NeighborhoodResponse,
    summary="Focus entity + k-hop neighbors + SVO edges",
    description=(
        "Returns the focus entity, its k-hop neighbor entities, and the "
        "SVO-labeled claim edges connecting them. Predicate = the claim's "
        "verb from metadata; target = an entity when the object resolves "
        "to a known canonical_name/alias, else the literal object phrase. "
        "Backs the SwiftUI focus-neighborhood viz (#976). Bounded — "
        "the focus + ~50 neighbors at the default settings, never the "
        "whole library."
    ),
)
async def neighborhood(
    entity_id: str,
    hops: int = Query(default=1, ge=1, le=3),
    limit: int = Query(default=50, ge=1, le=500),
    db: Database = Depends(get_library_database),
) -> NeighborhoodResponse:
    from fichero.knowledge_models import KnowledgeClaim, KnowledgeEntity

    focus = db.get(KnowledgeEntity, entity_id)
    if focus is None:
        raise HTTPException(404, f"Entity not found: {entity_id}")

    # Build an entity-id → entity lookup so we can decorate neighbor
    # nodes with canonical_name / type / aliases without re-querying.
    entities_all = db.query(KnowledgeEntity)
    by_id: dict[str, KnowledgeEntity] = {ent.id: ent for ent in entities_all}

    # Name → entity_id lookup for resolving literal `object` phrases
    # against known entities. Case-insensitive, canonical-name + aliases.
    name_to_id: dict[str, str] = {}
    for ent in entities_all:
        name_to_id[ent.canonical_name.lower()] = ent.id
        for alias in (ent.aliases or []):
            name_to_id.setdefault(alias.lower(), ent.id)

    # BFS over entity IDs, recording which hop we reached each at, AND
    # collecting the claim-edges that connect them. We re-walk the
    # claims iterable per hop because the per-claim filter is the same
    # query; for typical 0.0.2 corpora the cost is fine. At scale, this
    # is the spot to swap in the cached networkx graph.
    claims_all = db.query(KnowledgeClaim)
    edges: list[NeighborhoodEdge] = []
    neighbor_ids: dict[str, int] = {}  # entity_id → hop
    frontier: set[str] = {entity_id}
    visited: set[str] = {entity_id}
    truncated = False

    for current_hop in range(1, hops + 1):
        next_frontier: set[str] = set()
        for claim in claims_all:
            cl_entities = list(claim.entity_ids or [])
            if not any(eid in frontier for eid in cl_entities):
                continue
            meta = claim.metadata or {}
            verb = (meta.get("verb") or "").strip() or "mentions"
            obj_text = (meta.get("object") or "").strip()
            object_entity_id = name_to_id.get(obj_text.lower()) if obj_text else None

            for source_id in cl_entities:
                if source_id not in frontier:
                    continue
                # Edge 1: subject → object-entity (when the object
                # resolves to a known entity).
                if object_entity_id and object_entity_id != source_id:
                    if object_entity_id not in visited:
                        if len(neighbor_ids) >= limit:
                            truncated = True
                            continue
                        neighbor_ids[object_entity_id] = current_hop
                        visited.add(object_entity_id)
                        next_frontier.add(object_entity_id)
                    edges.append(_make_edge(
                        source_id=source_id,
                        target_id=object_entity_id,
                        target_label=by_id[object_entity_id].canonical_name
                        if object_entity_id in by_id else obj_text,
                        target_is_entity=True,
                        predicate=verb,
                        claim=claim,
                    ))
                # Edge 2: subject → other-entity-in-same-claim (when
                # the claim mentions multiple entities and the object
                # didn't resolve). Treats the claim as a hyperedge.
                if not object_entity_id:
                    for other in cl_entities:
                        if other == source_id or other not in by_id:
                            continue
                        if other not in visited:
                            if len(neighbor_ids) >= limit:
                                truncated = True
                                continue
                            neighbor_ids[other] = current_hop
                            visited.add(other)
                            next_frontier.add(other)
                        edges.append(_make_edge(
                            source_id=source_id,
                            target_id=other,
                            target_label=by_id[other].canonical_name,
                            target_is_entity=True,
                            predicate=verb,
                            claim=claim,
                        ))
                    # If the claim had ONLY this entity and a literal
                    # object, emit an edge to the literal so the viz
                    # can still show "X — verb — <object phrase>".
                    if obj_text and not any(
                        o for o in cl_entities if o != source_id and o in by_id
                    ):
                        edges.append(_make_edge(
                            source_id=source_id,
                            target_id=f"literal:{obj_text}",
                            target_label=obj_text,
                            target_is_entity=False,
                            predicate=verb,
                            claim=claim,
                        ))
        frontier = next_frontier
        if not frontier:
            break

    neighbors = [
        NeighborEntity(
            id=eid,
            canonical_name=by_id[eid].canonical_name,
            entity_type=(
                by_id[eid].entity_type.value
                if by_id[eid].entity_type and hasattr(by_id[eid].entity_type, "value")
                else str(by_id[eid].entity_type) if by_id[eid].entity_type else None
            ),
            aliases=list(by_id[eid].aliases or []),
            description=by_id[eid].description,
            hop=hop,
        )
        for eid, hop in neighbor_ids.items()
        if eid in by_id
    ]

    return NeighborhoodResponse(
        focus_entity_id=focus.id,
        focus_canonical_name=focus.canonical_name,
        focus_entity_type=(
            focus.entity_type.value
            if focus.entity_type and hasattr(focus.entity_type, "value")
            else str(focus.entity_type) if focus.entity_type else None
        ),
        focus_description=focus.description,
        focus_aliases=list(focus.aliases or []),
        neighbors=neighbors,
        edges=edges,
        truncated=truncated,
    )


def _make_edge(
    *,
    source_id: str,
    target_id: str,
    target_label: str,
    target_is_entity: bool,
    predicate: str,
    claim,
) -> NeighborhoodEdge:
    """Build a NeighborhoodEdge from a claim row, copying source provenance."""
    return NeighborhoodEdge(
        source_id=source_id,
        target_id=target_id,
        target_label=target_label,
        target_is_entity=target_is_entity,
        predicate=predicate,
        claim_id=claim.id,
        claim_text=claim.text,
        source_document_id=claim.source_document_id,
        source_page_label=claim.source_page_label,
        source_char_start=claim.source_char_start,
        source_char_end=claim.source_char_end,
        source_excerpt=claim.source_excerpt,
        claim_type=(
            claim.claim_type.value if claim.claim_type
            and hasattr(claim.claim_type, "value")
            else str(claim.claim_type) if claim.claim_type else None
        ),
        epistemic_status=(
            claim.epistemic_status.value if claim.epistemic_status
            and hasattr(claim.epistemic_status, "value")
            else str(claim.epistemic_status) if claim.epistemic_status else None
        ),
        confidence=claim.confidence,
    )
