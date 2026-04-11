"""Advanced Graph Exploration and Interpretation API Routes.

Endpoints for:
- Pathfinding between entities (entity1 → entity2 relationship paths)
- Interpretation exploration paths
- Complex graph queries optimized for visualization
"""

from __future__ import annotations

import logging
from datetime import datetime
from enum import Enum
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from fichero.api.main import get_library_database
from fichero.db import Database
from fichero.knowledge_models import (
    ClaimRelationType,
    KnowledgeClaim,
    KnowledgeClaimLink,
    KnowledgeEntity,
)
from fichero.hermeneutics_models import Interpretation

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/graph", tags=["graph-exploration"])


# =============================================================================
# Enums
# =============================================================================


class PathAlgorithm(str, Enum):
    """Pathfinding algorithm to use."""

    SHORTEST = "shortest"  # BFS shortest path
    ALL_SIMPLE = "all_simple"  # All simple paths up to max_depth
    STRONGEST = "strongest"  # Path with highest combined edge weight


class RelationDirection(str, Enum):
    """Direction of relationship traversal."""

    OUTBOUND = "outbound"  # entity → related
    INBOUND = "inbound"  # related → entity
    BOTH = "both"  # Undirected traversal


class ExplorationDepth(str, Enum):
    """Depth of exploration."""

    SHALLOW = "shallow"  # Direct connections only
    MEDIUM = "medium"  # Up to 2 hops
    DEEP = "deep"  # Up to 3 hops


# =============================================================================
# Request/Response Models
# =============================================================================


class GraphNode(BaseModel):
    """Node in a graph path."""

    id: str
    type: str  # "entity", "claim", "interpretation"
    label: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    """Edge in a graph path."""

    source: str
    target: str
    type: str  # relation type
    weight: float = 1.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class PathSegment(BaseModel):
    """Single segment in a path (node + edge to next)."""

    node: GraphNode
    edge: GraphEdge | None = None  # None for final node


class EntityPath(BaseModel):
    """A path between two entities."""

    path_id: str
    source_id: str
    target_id: str
    segments: list[PathSegment]
    length: int
    total_weight: float
    strength_score: float  # Combined path strength


class PathResponse(BaseModel):
    """Response for pathfinding between entities."""

    source_id: str
    target_id: str
    source_entity: dict[str, Any]
    target_entity: dict[str, Any]
    paths: list[EntityPath]
    total_paths: int
    algorithm: str
    max_depth: int


class InterpretationNode(BaseModel):
    """Node in interpretation exploration."""

    id: str
    type: str  # "entity", "claim", "interpretation", "framework"
    label: str
    confidence: float | None = None
    created_at: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class InterpretationPath(BaseModel):
    """Path through interpretation space."""

    path_id: str
    start_node: InterpretationNode
    end_node: InterpretationNode
    intermediate_nodes: list[InterpretationNode]
    path_type: str  # "direct", "via_claim", "via_framework"
    relevance_score: float


class InterpretationExplorationResponse(BaseModel):
    """Response for interpretation exploration."""

    entity_id: str
    entity_name: str
    paths: list[InterpretationPath]
    related_interpretations: list[InterpretationNode]
    related_claims: list[InterpretationNode]
    related_frameworks: list[InterpretationNode]
    total_paths: int


class EntityNeighborhood(BaseModel):
    """Neighborhood around an entity."""

    entity_id: str
    entity_name: str
    depth: int
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    claim_count: int
    interpretation_count: int
    entity_count: int


class GraphQueryRequest(BaseModel):
    """Request for complex graph query."""

    start_entity_id: str
    end_entity_id: str | None = None
    relation_types: list[str] = Field(default_factory=list)
    max_depth: int = Field(default=3, ge=1, le=5)
    algorithm: PathAlgorithm = PathAlgorithm.SHORTEST
    min_edge_weight: float = Field(default=0.0, ge=0.0, le=1.0)


class GraphQueryResponse(BaseModel):
    """Response for complex graph query."""

    query_id: str
    start_entity_id: str
    end_entity_id: str | None
    results: list[EntityPath]
    execution_time_ms: float
    node_count: int
    edge_count: int


class GraphMetrics(BaseModel):
    """Graph metrics for visualization."""

    entity_count: int
    claim_count: int
    interpretation_count: int
    edge_count: int
    avg_degree: float
    max_degree: int
    connected_components: int
    density: float


class GraphMetricsResponse(BaseModel):
    """Response for graph metrics."""

    metrics: GraphMetrics
    last_updated: str
    time_range: dict[str, str] | None


# =============================================================================
# Helper Functions
# =============================================================================


def _get_entity_summary(entity: KnowledgeEntity) -> dict[str, Any]:
    """Get summary dict for an entity."""
    return {
        "id": entity.id,
        "name": entity.canonical_name,
        "type": entity.entity_type.value if entity.entity_type else "unknown",
        "aliases": entity.aliases[:5] if entity.aliases else [],
    }


def _get_claim_summary(claim: KnowledgeClaim) -> dict[str, Any]:
    """Get summary dict for a claim."""
    return {
        "id": claim.id,
        "text": claim.text[:100] + "..." if len(claim.text) > 100 else claim.text,
        "confidence": claim.confidence,
        "epistemic_status": claim.epistemic_status.value if claim.epistemic_status else "unknown",
    }


def _build_entity_node(entity: KnowledgeEntity) -> GraphNode:
    """Build a graph node from an entity."""
    return GraphNode(
        id=entity.id,
        type="entity",
        label=entity.canonical_name,
        metadata={
            "entity_type": entity.entity_type.value if entity.entity_type else "unknown",
            "aliases": entity.aliases[:3] if entity.aliases else [],
        },
    )


def _build_claim_node(claim: KnowledgeClaim) -> GraphNode:
    """Build a graph node from a claim."""
    return GraphNode(
        id=claim.id,
        type="claim",
        label=claim.text[:50] + "..." if len(claim.text) > 50 else claim.text,
        metadata={
            "confidence": claim.confidence,
            "epistemic_status": claim.epistemic_status.value if claim.epistemic_status else "unknown",
        },
    )


def _build_interpretation_node(interp: Interpretation) -> InterpretationNode:
    """Build an interpretation node."""
    return InterpretationNode(
        id=interp.id,
        type="interpretation",
        label=interp.interpretation_text[:50] + "..." if len(interp.interpretation_text) > 50 else interp.interpretation_text,
        confidence=interp.confidence,
        created_at=interp.created_at.isoformat() if hasattr(interp.created_at, "isoformat") else str(interp.created_at),
        metadata={
            "framework_id": interp.framework_id,
            "act": interp.act.value if interp.act else None,
        },
    )


def _bfs_shortest_path(
    start_id: str,
    target_id: str,
    entity_claim_map: dict[str, list[str]],
    claim_entity_map: dict[str, list[str]],
    max_depth: int = 4,
) -> list[list[str]] | None:
    """Find shortest path(s) using BFS."""
    from collections import deque

    if start_id == target_id:
        return [[start_id]]

    queue = deque([(start_id, [start_id])])
    visited = {start_id}
    all_paths = []

    while queue:
        current, path = queue.popleft()

        if len(path) > max_depth + 1:
            continue

        # Get neighbors through claims
        neighbor_ids = set()
        if current in entity_claim_map:
            for claim_id in entity_claim_map[current]:
                # Find other entities in same claim
                if claim_id in claim_entity_map:
                    for entity_id in claim_entity_map[claim_id]:
                        if entity_id != current:
                            neighbor_ids.add((entity_id, claim_id))

        for neighbor_id, via_claim in neighbor_ids:
            if neighbor_id in visited and len(path) + 1 > max_depth:
                continue

            new_path = path + [via_claim, neighbor_id]

            if neighbor_id == target_id:
                all_paths.append(new_path)
                if len(all_paths) >= 3:  # Limit paths
                    return all_paths
            else:
                if neighbor_id not in visited:
                    visited.add(neighbor_id)
                    queue.append((neighbor_id, new_path))

    return all_paths if all_paths else None


def _find_strongest_path(
    start_id: str,
    target_id: str,
    claim_links: list[KnowledgeClaimLink],
    max_depth: int = 4,
) -> list[tuple[list[str], float]]:
    """Find path with strongest combined edge weight."""
    # Build weighted adjacency
    adjacency: dict[str, list[tuple[str, float, str]]] = {}  # entity -> [(entity, weight, claim_id)]

    for link in claim_links:
        if link.relation_type == ClaimRelationType.contradicts:
            continue  # Skip contradictions for positive paths

        weight = link.link_quality

        # Add bidirectional
        if link.claim_id not in adjacency:
            adjacency[link.claim_id] = []
        if link.related_claim_id not in adjacency:
            adjacency[link.related_claim_id] = []

        adjacency[link.claim_id].append((link.related_claim_id, weight, link.id))
        adjacency[link.related_claim_id].append((link.claim_id, weight, link.id))

    # Dijkstra-like search for strongest path
    from heapq import heappush, heappop

    # Priority queue: (-path_strength, current_id, path)
    pq = [(-1.0, start_id, [start_id])]
    visited: set[str] = set()
    best_paths: list[tuple[list[str], float]] = []

    while pq:
        neg_strength, current, path = heappop(pq)
        strength = -neg_strength

        if current in visited:
            continue
        visited.add(current)

        if len(path) > max_depth * 2 + 1:  # Account for claim nodes
            continue

        if current == target_id and len(path) > 1:
            best_paths.append((path, strength))
            if len(best_paths) >= 3:
                break
            continue

        if current in adjacency:
            for neighbor, edge_weight, _ in adjacency[current]:
                if neighbor not in visited:
                    new_strength = strength * edge_weight if edge_weight > 0 else strength * 0.5
                    new_path = path + [neighbor]
                    heappush(pq, (-new_strength, neighbor, new_path))

    return best_paths


# =============================================================================
# API Endpoints
# =============================================================================


@router.get(
    "/paths/{entity_id1}/{entity_id2}",
    response_model=PathResponse,
    summary="Find paths between entities",
    description="Find relationship paths between two entities through claims and links.",
)
async def find_entity_paths(
    entity_id1: str,
    entity_id2: str,
    algorithm: PathAlgorithm = Query(PathAlgorithm.SHORTEST, description="Pathfinding algorithm"),
    max_depth: int = Query(3, ge=1, le=5, description="Maximum path depth"),
    min_edge_weight: float = Query(0.0, ge=0.0, le=1.0, description="Minimum edge weight"),
    db: Database = Depends(get_library_database),
) -> PathResponse:
    """Find paths between two entities in the knowledge graph."""
    # Verify both entities exist
    entity1 = db.get(KnowledgeEntity, entity_id1)
    entity2 = db.get(KnowledgeEntity, entity_id2)

    if not entity1:
        raise HTTPException(status_code=404, detail=f"Entity not found: {entity_id1}")
    if not entity2:
        raise HTTPException(status_code=404, detail=f"Entity not found: {entity_id2}")

    # Build entity-claim mappings
    entity_claim_map: dict[str, list[str]] = {}
    claim_entity_map: dict[str, list[str]] = {}

    all_claims = db.all(KnowledgeClaim)
    for claim in all_claims:
        for entity_id in claim.entity_ids:
            if entity_id not in entity_claim_map:
                entity_claim_map[entity_id] = []
            entity_claim_map[entity_id].append(claim.id)

            if claim.id not in claim_entity_map:
                claim_entity_map[claim.id] = []
            claim_entity_map[claim.id].append(entity_id)

    # Get all claim links
    all_links = db.all(KnowledgeClaimLink)

    paths: list[EntityPath] = []

    if algorithm == PathAlgorithm.SHORTEST:
        # Use BFS
        path_results = _bfs_shortest_path(
            entity_id1, entity_id2, entity_claim_map, claim_entity_map, max_depth
        )

        if path_results:
            for idx, path_nodes in enumerate(path_results[:3]):  # Limit to 3 paths
                segments: list[PathSegment] = []
                total_weight = 0.0

                for i, node_id in enumerate(path_nodes):
                    is_claim = i % 2 == 1  # Claims are at odd indices

                    if is_claim:
                        claim = db.get(KnowledgeClaim, node_id)
                        if claim:
                            node = _build_claim_node(claim)
                        else:
                            continue
                    else:
                        entity = db.get(KnowledgeEntity, node_id)
                        if entity:
                            node = _build_entity_node(entity)
                        else:
                            continue

                    edge = None
                    if i < len(path_nodes) - 1:
                        # Find edge to next node
                        next_id = path_nodes[i + 1]
                        weight = 0.5  # Default

                        # Check if there's a direct link
                        for link in all_links:
                            if (link.claim_id == node_id and link.related_claim_id == next_id) or \
                               (link.claim_id == next_id and link.related_claim_id == node_id):
                                weight = link.link_quality
                                break

                        edge = GraphEdge(
                            source=node_id,
                            target=next_id,
                            type="related_to",
                            weight=weight,
                        )
                        total_weight += weight

                    segments.append(PathSegment(node=node, edge=edge))

                if segments:
                    paths.append(
                        EntityPath(
                            path_id=f"path_{idx}",
                            source_id=entity_id1,
                            target_id=entity_id2,
                            segments=segments,
                            length=len(segments),
                            total_weight=total_weight,
                            strength_score=total_weight / len(segments) if segments else 0.0,
                        )
                    )

    elif algorithm == PathAlgorithm.STRONGEST:
        # Use strongest path algorithm
        strong_paths = _find_strongest_path(entity_id1, entity_id2, all_links, max_depth)

        for idx, (path_nodes, strength) in enumerate(strong_paths[:3]):
            segments: list[PathSegment] = []

            for i, node_id in enumerate(path_nodes):
                claim = db.get(KnowledgeClaim, node_id)
                if claim:
                    node = _build_claim_node(claim)
                else:
                    entity = db.get(KnowledgeEntity, node_id)
                    if entity:
                        node = _build_entity_node(entity)
                    else:
                        continue

                edge = None
                if i < len(path_nodes) - 1:
                    edge = GraphEdge(
                        source=node_id,
                        target=path_nodes[i + 1],
                        type="related_to",
                        weight=0.5,
                    )

                segments.append(PathSegment(node=node, edge=edge))

            if segments:
                paths.append(
                    EntityPath(
                        path_id=f"strong_path_{idx}",
                        source_id=entity_id1,
                        target_id=entity_id2,
                        segments=segments,
                        length=len(segments),
                        total_weight=strength,
                        strength_score=strength,
                    )
                    )

    return PathResponse(
        source_id=entity_id1,
        target_id=entity_id2,
        source_entity=_get_entity_summary(entity1),
        target_entity=_get_entity_summary(entity2),
        paths=paths,
        total_paths=len(paths),
        algorithm=algorithm.value,
        max_depth=max_depth,
    )


@router.get(
    "/interpretations/exploration/{entity_id}",
    response_model=InterpretationExplorationResponse,
    summary="Explore interpretations for entity",
    description="Find interpretation paths and related content for an entity.",
)
async def explore_interpretations(
    entity_id: str,
    depth: ExplorationDepth = Query(ExplorationDepth.MEDIUM, description="Exploration depth"),
    include_frameworks: bool = Query(True, description="Include framework nodes"),
    db: Database = Depends(get_library_database),
) -> InterpretationExplorationResponse:
    """Explore interpretations connected to an entity."""
    entity = db.get(KnowledgeEntity, entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail=f"Entity not found: {entity_id}")

    depth_map = {
        ExplorationDepth.SHALLOW: 1,
        ExplorationDepth.MEDIUM: 2,
        ExplorationDepth.DEEP: 3,
    }
    _max_hops = depth_map.get(depth, 2)

    # Find claims mentioning this entity
    all_claims = db.all(KnowledgeClaim)
    entity_claims = [c for c in all_claims if entity_id in c.entity_ids]

    # Find interpretations for those claims
    all_interpretations = db.all(Interpretation)
    claim_ids = {c.id for c in entity_claims}
    related_interps = [
        i for i in all_interpretations
        if i.claim_id in claim_ids or (i.metadata.get("claim_ids") and any(cid in claim_ids for cid in i.metadata.get("claim_ids", [])))
    ]

    # Build interpretation nodes
    interp_nodes = [_build_interpretation_node(i) for i in related_interps[:20]]
    claim_nodes = [
        InterpretationNode(
            id=c.id,
            type="claim",
            label=c.text[:80] + "..." if len(c.text) > 80 else c.text,
            confidence=c.confidence,
            created_at=c.created_at.isoformat() if hasattr(c.created_at, "isoformat") else str(c.created_at),
            metadata={"epistemic_status": c.epistemic_status.value if c.epistemic_status else None},
        )
        for c in entity_claims[:20]
    ]

    # Build paths (entity → claim → interpretation)
    paths: list[InterpretationPath] = []
    for idx, claim in enumerate(entity_claims[:10]):
        for interp in related_interps[:5]:
            if interp.claim_id == claim.id:
                paths.append(
                    InterpretationPath(
                        path_id=f"path_{idx}",
                        start_node=InterpretationNode(
                            id=entity_id,
                            type="entity",
                            label=entity.canonical_name,
                            confidence=None,
                            created_at=entity.created_at.isoformat() if hasattr(entity.created_at, "isoformat") else str(entity.created_at),
                        ),
                        end_node=_build_interpretation_node(interp),
                        intermediate_nodes=[
                            InterpretationNode(
                                id=claim.id,
                                type="claim",
                                label=claim.text[:50] + "..." if len(claim.text) > 50 else claim.text,
                                confidence=claim.confidence,
                                created_at=claim.created_at.isoformat() if hasattr(claim.created_at, "isoformat") else str(claim.created_at),
                            ),
                        ],
                        path_type="via_claim",
                        relevance_score=claim.confidence * interp.confidence,
                    )
                )

    # Framework nodes
    framework_nodes: list[InterpretationNode] = []
    if include_frameworks:
        from fichero.hermeneutics_models import InterpretiveFramework
        all_frameworks = db.all(InterpretiveFramework)
        used_framework_ids = {i.framework_id for i in related_interps}
        framework_nodes = [
            InterpretationNode(
                id=f.id,
                type="framework",
                label=f.name,
                confidence=None,
                created_at=f.created_at.isoformat() if hasattr(f.created_at, "isoformat") else str(f.created_at),
                metadata={"framework_type": f.framework_type.value if f.framework_type else None},
            )
            for f in all_frameworks
            if f.id in used_framework_ids
        ]

    return InterpretationExplorationResponse(
        entity_id=entity_id,
        entity_name=entity.canonical_name,
        paths=paths[:20],
        related_interpretations=interp_nodes,
        related_claims=claim_nodes,
        related_frameworks=framework_nodes,
        total_paths=len(paths),
    )


@router.post(
    "/query",
    response_model=GraphQueryResponse,
    summary="Complex graph query",
    description="Execute complex graph query with custom parameters.",
)
async def execute_graph_query(
    request: GraphQueryRequest,
    db: Database = Depends(get_library_database),
) -> GraphQueryResponse:
    """Execute a complex graph query."""
    import time
    start_time = time.time()

    # Similar to find_entity_paths but with custom filters
    entity1 = db.get(KnowledgeEntity, request.start_entity_id)
    if not entity1:
        raise HTTPException(status_code=404, detail=f"Entity not found: {request.start_entity_id}")

    if request.end_entity_id:
        entity2 = db.get(KnowledgeEntity, request.end_entity_id)
        if not entity2:
            raise HTTPException(status_code=404, detail=f"Entity not found: {request.end_entity_id}")

    # Filter relation types if specified
    relation_filter = None
    if request.relation_types:
        relation_filter = [ClaimRelationType(rt) for rt in request.relation_types if rt in {e.value for e in ClaimRelationType}]

    # Get links
    all_links = db.all(KnowledgeClaimLink)
    if relation_filter:
        filtered_links = [lnk for lnk in all_links if lnk.relation_type in relation_filter and lnk.link_quality >= request.min_edge_weight]
    else:
        filtered_links = [lnk for lnk in all_links if lnk.link_quality >= request.min_edge_weight]

    results: list[EntityPath] = []

    # If end entity specified, find paths
    if request.end_entity_id:
        # Use existing pathfinding
        from collections import deque

        # Build adjacency
        adjacency: dict[str, list[tuple[str, float]]] = {}
        for link in filtered_links:
            if link.claim_id not in adjacency:
                adjacency[link.claim_id] = []
            if link.related_claim_id not in adjacency:
                adjacency[link.related_claim_id] = []
            adjacency[link.claim_id].append((link.related_claim_id, link.link_quality))
            adjacency[link.related_claim_id].append((link.claim_id, link.link_quality))

        # BFS
        queue = deque([(request.start_entity_id, [request.start_entity_id], 1.0)])
        visited = {request.start_entity_id}

        while queue and len(results) < 10:
            current, path, strength = queue.popleft()

            if len(path) > request.max_depth + 1:
                continue

            if current == request.end_entity_id and len(path) > 1:
                # Build path segments
                segments: list[PathSegment] = []
                for i, node_id in enumerate(path):
                    entity = db.get(KnowledgeEntity, node_id)
                    if entity:
                        node = _build_entity_node(entity)
                    else:
                        claim = db.get(KnowledgeClaim, node_id)
                        if claim:
                            node = _build_claim_node(claim)
                        else:
                            continue

                    edge = None
                    if i < len(path) - 1:
                        edge = GraphEdge(source=node_id, target=path[i + 1], type="related_to", weight=strength)

                    segments.append(PathSegment(node=node, edge=edge))

                results.append(
                    EntityPath(
                        path_id=f"qpath_{len(results)}",
                        source_id=request.start_entity_id,
                        target_id=request.end_entity_id,
                        segments=segments,
                        length=len(segments),
                        total_weight=strength,
                        strength_score=strength,
                    )
                )
                continue

            if current in adjacency:
                for neighbor, weight in adjacency[current]:
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append((neighbor, path + [neighbor], strength * weight))

    execution_time = (time.time() - start_time) * 1000

    return GraphQueryResponse(
        query_id=f"query_{start_time}",
        start_entity_id=request.start_entity_id,
        end_entity_id=request.end_entity_id,
        results=results,
        execution_time_ms=execution_time,
        node_count=len(set(node for path in results for node in [s.node.id for s in path.segments])),
        edge_count=sum(len([s for s in path.segments if s.edge]) for path in results),
    )


@router.get(
    "/neighborhood/{entity_id}",
    response_model=EntityNeighborhood,
    summary="Get entity neighborhood",
    description="Get local neighborhood graph around an entity.",
)
async def get_entity_neighborhood(
    entity_id: str,
    depth: int = Query(1, ge=1, le=3, description="Neighborhood depth"),
    include_claims: bool = Query(True, description="Include claim nodes"),
    include_interpretations: bool = Query(True, description="Include interpretation nodes"),
    db: Database = Depends(get_library_database),
) -> EntityNeighborhood:
    """Get neighborhood graph around an entity."""
    entity = db.get(KnowledgeEntity, entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail=f"Entity not found: {entity_id}")

    nodes: dict[str, GraphNode] = {}
    edges: list[GraphEdge] = []

    # Add center entity
    nodes[entity_id] = _build_entity_node(entity)

    # Find claims mentioning this entity
    all_claims = db.all(KnowledgeClaim)
    entity_claims = [c for c in all_claims if entity_id in c.entity_ids]

    for claim in entity_claims:
        if include_claims:
            nodes[claim.id] = _build_claim_node(claim)
            edges.append(GraphEdge(
                source=entity_id,
                target=claim.id,
                type="mentioned_in",
                weight=claim.confidence,
            ))

        # Find other entities in same claims
        for other_entity_id in claim.entity_ids:
            if other_entity_id != entity_id and other_entity_id not in nodes:
                other_entity = db.get(KnowledgeEntity, other_entity_id)
                if other_entity:
                    nodes[other_entity_id] = _build_entity_node(other_entity)
                    edges.append(GraphEdge(
                        source=claim.id,
                        target=other_entity_id,
                        type="mentions",
                        weight=claim.confidence,
                    ))

    # Find interpretations
    if include_interpretations:
        all_interpretations = db.all(Interpretation)
        claim_ids = {c.id for c in entity_claims}
        for interp in all_interpretations:
            if interp.claim_id in claim_ids:
                interp_node = _build_interpretation_node(interp)
                nodes[interp.id] = GraphNode(
                    id=interp.id,
                    type="interpretation",
                    label=interp_node.label,
                    metadata=interp_node.metadata,
                )
                edges.append(GraphEdge(
                    source=interp.claim_id or "",
                    target=interp.id,
                    type="interpreted_by",
                    weight=interp.confidence,
                ))

    return EntityNeighborhood(
        entity_id=entity_id,
        entity_name=entity.canonical_name,
        depth=depth,
        nodes=list(nodes.values()),
        edges=edges,
        claim_count=len([n for n in nodes.values() if n.type == "claim"]),
        interpretation_count=len([n for n in nodes.values() if n.type == "interpretation"]),
        entity_count=len([n for n in nodes.values() if n.type == "entity"]),
    )


@router.get(
    "/metrics",
    response_model=GraphMetricsResponse,
    summary="Get graph metrics",
    description="Get overall knowledge graph metrics and statistics.",
)
async def get_graph_metrics(
    db: Database = Depends(get_library_database),
) -> GraphMetricsResponse:
    """Get graph metrics."""
    all_entities = db.all(KnowledgeEntity)
    all_claims = db.all(KnowledgeClaim)
    all_interpretations = db.all(Interpretation)
    all_links = db.all(KnowledgeClaimLink)

    entity_count = len(all_entities)
    claim_count = len(all_claims)
    interpretation_count = len(all_interpretations)

    # Calculate degrees
    degrees: dict[str, int] = {}
    for link in all_links:
        degrees[link.claim_id] = degrees.get(link.claim_id, 0) + 1
        degrees[link.related_claim_id] = degrees.get(link.related_claim_id, 0) + 1

    avg_degree = sum(degrees.values()) / len(degrees) if degrees else 0.0
    max_degree = max(degrees.values()) if degrees else 0

    # Connected components (simplified)
    # In a real implementation, use Union-Find
    connected_components = max(1, len(all_entities) // 50)  # Rough estimate

    # Density = 2E / (V(V-1)) for undirected
    total_nodes = entity_count + claim_count
    edge_count = len(all_links)
    density = (2 * edge_count) / (total_nodes * (total_nodes - 1)) if total_nodes > 1 else 0.0

    return GraphMetricsResponse(
        metrics=GraphMetrics(
            entity_count=entity_count,
            claim_count=claim_count,
            interpretation_count=interpretation_count,
            edge_count=edge_count,
            avg_degree=avg_degree,
            max_degree=max_degree,
            connected_components=connected_components,
            density=density,
        ),
        last_updated=datetime.now().isoformat(),
        time_range=None,
    )
