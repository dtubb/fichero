"""Graph Traversal and Subgraph Extraction routes.

BFS traversal, entity interpretations, and subgraph extraction.
Included by graph_exploration.py via router.include_router().
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from fichero.api.main import get_library_database
from fichero.db import Database
from fichero.knowledge_models import KnowledgeClaim, KnowledgeClaimLink, KnowledgeEntity
from fichero.hermeneutics_models import Interpretation, InterpretiveFramework

logger = logging.getLogger(__name__)
router = APIRouter()


class RelationDirection(str, Enum):
    """Direction of relationship traversal."""

    OUTBOUND = "outbound"  # entity → related
    INBOUND = "inbound"  # related → entity
    BOTH = "both"  # Undirected traversal


# =============================================================================
# Traversal Models
# =============================================================================


class TraverseRequest(BaseModel):
    """Request for graph traversal."""

    max_depth: int = Field(default=2, ge=1, le=5)
    direction: RelationDirection = RelationDirection.BOTH
    include_claims: bool = Field(default=True)
    include_interpretations: bool = Field(default=False)


class TraversedNode(BaseModel):
    """Node discovered during traversal."""

    id: str
    type: str
    label: str
    depth: int
    metadata: dict[str, Any] = Field(default_factory=dict)


class TraversedEdge(BaseModel):
    """Edge discovered during traversal."""

    source: str
    target: str
    type: str
    depth: int


class GraphTraversalResponse(BaseModel):
    """Response for graph traversal."""

    entity_id: str
    start_node: TraversedNode
    nodes: list[TraversedNode]
    edges: list[TraversedEdge]
    max_depth: int
    total_nodes: int
    total_edges: int


class InterpretationView(BaseModel):
    """Simplified interpretation view."""

    id: str
    framework_id: str
    framework_name: str
    text: str
    confidence: float
    created_at: str


class EntityInterpretationsResponse(BaseModel):
    """Response for entity interpretations."""

    entity_id: str
    entity_name: str
    interpretations: list[InterpretationView]
    frameworks: list[dict[str, Any]]
    total: int


class SubgraphRequest(BaseModel):
    """Request for subgraph extraction."""

    center_entity_ids: list[str]
    max_depth: int = Field(default=2, ge=1, le=4)
    include_nodes: list[str] | None = None
    exclude_nodes: list[str] | None = None


class SubgraphResponse(BaseModel):
    """Response for subgraph extraction."""

    nodes: list[TraversedNode]
    edges: list[TraversedEdge]
    center_nodes: list[str]
    max_depth: int
    optimization: str


# =============================================================================
# Routes
# =============================================================================


@router.get(
    "/traverse/{entity_id}",
    response_model=GraphTraversalResponse,
    summary="Traverse graph from entity",
    description="BFS traversal from an entity to discover connected nodes.",
)
async def traverse_graph(
    entity_id: str,
    max_depth: int = Query(default=2, ge=1, le=5),
    direction: RelationDirection = Query(default=RelationDirection.BOTH),
    include_claims: bool = Query(default=True),
    include_interpretations: bool = Query(default=False),
    db: Database = Depends(get_library_database),
) -> GraphTraversalResponse:
    """Traverse graph from starting entity."""
    entity = db.get(KnowledgeEntity, entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail=f"Entity not found: {entity_id}")

    start_node = TraversedNode(
        id=entity.id,
        type="entity",
        label=entity.canonical_name,
        depth=0,
        metadata={
            "aliases": entity.aliases,
            "entity_type": entity.entity_type.value if entity.entity_type else None,
        },
    )

    visited: set[str] = {entity_id}
    nodes: list[TraversedNode] = [start_node]
    edges: list[TraversedEdge] = []
    queue: list[tuple[str, int]] = [(entity_id, 0)]

    while queue:
        current_id, current_depth = queue.pop(0)

        if current_depth >= max_depth:
            continue

        if include_claims:
            claims = db.query(KnowledgeClaim, entity_ids=current_id)
            for claim in claims:
                if claim.id not in visited:
                    visited.add(claim.id)
                    nodes.append(
                        TraversedNode(
                            id=claim.id,
                            type="claim",
                            label=claim.text[:100],
                            depth=current_depth + 1,
                            metadata={
                                "confidence": claim.confidence,
                                "epistemic_status": claim.epistemic_status.value if claim.epistemic_status else None,
                            },
                        )
                    )
                    queue.append((claim.id, current_depth + 1))

                edges.append(
                    TraversedEdge(
                        source=current_id,
                        target=claim.id,
                        type="mentioned_in",
                        depth=current_depth + 1,
                    )
                )

        # Get claim links (if current is a claim)
        if direction in (RelationDirection.OUTBOUND, RelationDirection.BOTH):
            links = db.query(KnowledgeClaimLink, claim_id=current_id)
            for link in links:
                target_id = link.related_claim_id
                if target_id not in visited:
                    target_claim = db.get(KnowledgeClaim, target_id)
                    if target_claim:
                        visited.add(target_id)
                        nodes.append(
                            TraversedNode(
                                id=target_claim.id,
                                type="claim",
                                label=target_claim.text[:100],
                                depth=current_depth + 1,
                                metadata={
                                    "relation": link.relation_type.value if link.relation_type else None,
                                    "link_quality": link.link_quality,
                                },
                            )
                        )
                        queue.append((target_id, current_depth + 1))

                edges.append(
                    TraversedEdge(
                        source=current_id,
                        target=target_id,
                        type=link.relation_type.value if link.relation_type else "linked",
                        depth=current_depth + 1,
                    )
                )

    return GraphTraversalResponse(
        entity_id=entity_id,
        start_node=start_node,
        nodes=nodes,
        edges=edges,
        max_depth=max_depth,
        total_nodes=len(nodes),
        total_edges=len(edges),
    )


@router.get(
    "/interpretations/{entity_id}",
    response_model=EntityInterpretationsResponse,
    summary="Get interpretations for entity",
    description="Get all interpretations related to an entity.",
)
async def get_entity_interpretations(
    entity_id: str,
    db: Database = Depends(get_library_database),
) -> EntityInterpretationsResponse:
    """Get interpretations for an entity."""
    entity = db.get(KnowledgeEntity, entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail=f"Entity not found: {entity_id}")

    all_interpretations = db.all(Interpretation)
    entity_interpretations: list[Interpretation] = []

    for interp in all_interpretations:
        if interp.claim_id:
            claim = db.get(KnowledgeClaim, interp.claim_id)
            if claim and entity_id in (claim.entity_ids or []):
                entity_interpretations.append(interp)

    interpretations: list[InterpretationView] = []
    framework_ids: set[str] = set()

    for interp in entity_interpretations:
        framework_ids.add(interp.framework_id)
        framework = db.get(InterpretiveFramework, interp.framework_id)
        framework_name = framework.name if framework else "Unknown"

        interpretations.append(
            InterpretationView(
                id=interp.id,
                framework_id=interp.framework_id,
                framework_name=framework_name,
                text=interp.interpretation_text[:200],
                confidence=interp.confidence,
                created_at=interp.created_at.isoformat() if interp.created_at else "",
            )
        )

    frameworks: list[dict[str, Any]] = []
    for fid in framework_ids:
        framework = db.get(InterpretiveFramework, fid)
        if framework:
            frameworks.append({
                "id": framework.id,
                "name": framework.name,
                "type": framework.framework_type.value if framework.framework_type else None,
            })

    return EntityInterpretationsResponse(
        entity_id=entity_id,
        entity_name=entity.canonical_name,
        interpretations=interpretations,
        frameworks=frameworks,
        total=len(interpretations),
    )


@router.post(
    "/subgraph",
    response_model=SubgraphResponse,
    summary="Extract subgraph",
    description="Extract a subgraph around specified center nodes, optimized for visualization.",
)
async def extract_subgraph(
    request: SubgraphRequest,
    db: Database = Depends(get_library_database),
) -> SubgraphResponse:
    """Extract a subgraph for visualization."""
    nodes: list[TraversedNode] = []
    edges: list[TraversedEdge] = []
    visited: set[str] = set()

    for center_id in request.center_entity_ids:
        entity = db.get(KnowledgeEntity, center_id)
        if not entity:
            raise HTTPException(status_code=404, detail=f"Entity not found: {center_id}")

    for center_id in request.center_entity_ids:
        if center_id in visited:
            continue

        center_entity = db.get(KnowledgeEntity, center_id)
        if not center_entity:
            continue

        visited.add(center_id)
        nodes.append(
            TraversedNode(
                id=center_entity.id,
                type="entity",
                label=center_entity.canonical_name,
                depth=0,
                metadata={"is_center": True},
            )
        )

        queue: list[tuple[str, int]] = [(center_id, 0)]

        while queue:
            current_id, current_depth = queue.pop(0)

            if current_depth >= request.max_depth:
                continue

            claims = db.query(KnowledgeClaim, entity_ids=current_id)
            for claim in claims:
                if claim.id not in visited:
                    if request.exclude_nodes and claim.id in request.exclude_nodes:
                        continue

                    visited.add(claim.id)
                    nodes.append(
                        TraversedNode(
                            id=claim.id,
                            type="claim",
                            label=claim.text[:80],
                            depth=current_depth + 1,
                            metadata={},
                        )
                    )
                    queue.append((claim.id, current_depth + 1))

                edges.append(
                    TraversedEdge(
                        source=current_id,
                        target=claim.id,
                        type="has_claim",
                        depth=current_depth + 1,
                    )
                )

    return SubgraphResponse(
        nodes=nodes,
        edges=edges,
        center_nodes=request.center_entity_ids,
        max_depth=request.max_depth,
        optimization="breadth-first with depth limit",
    )
