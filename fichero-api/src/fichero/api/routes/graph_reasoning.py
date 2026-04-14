"""NetworkX Graph Reasoning API Routes.

Endpoints for algorithmic graph analysis using NetworkX.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from fichero.api.main import get_library_database
from fichero.db import Database
from fichero.graph_reasoning import (
    AlgorithmType,
    CentralityResponse,
    CommunitiesResponse,
    CommunityAlgorithm,
    GraphMetrics,
    ShortestPathsResponse,
    get_reasoner,
    set_reasoner_enabled,
)
from fichero.knowledge_models import (
    KnowledgeClaim,
    KnowledgeClaimLink,
    KnowledgeEntity,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# =============================================================================
# Request/Response Models
# =============================================================================


class EnableRequest(BaseModel):
    """Request to enable/disable NetworkX reasoning."""

    enabled: bool


class EnableResponse(BaseModel):
    """Response for enable/disable operation."""

    enabled: bool
    available: bool
    message: str


class CentralityRequest(BaseModel):
    """Request for centrality analysis."""

    algorithm: AlgorithmType = AlgorithmType.degree_centrality
    entity_type: str | None = None  # Filter by entity type


class CommunitiesRequest(BaseModel):
    """Request for community detection."""

    algorithm: CommunityAlgorithm = CommunityAlgorithm.louvain
    min_community_size: int = Field(default=3, ge=2)


class ShortestPathsRequest(BaseModel):
    """Request for shortest paths analysis."""

    source_id: str
    target_ids: list[str]


class AlgorithmInfo(BaseModel):
    id: str
    name: str
    description: str


class AlgorithmsListResponse(BaseModel):
    networkx_available: bool
    reasoner_enabled: bool
    centrality_algorithms: list[AlgorithmInfo]
    community_algorithms: list[AlgorithmInfo]


class GraphMetricsResponse(BaseModel):
    """Response for graph metrics."""

    metrics: GraphMetrics | None
    networkx_available: bool
    reasoner_enabled: bool


# =============================================================================
# Helper Functions
# =============================================================================


def _load_graph_data(db: Database) -> tuple[list[KnowledgeEntity], list[KnowledgeClaim], list[KnowledgeClaimLink]]:
    """Load all knowledge graph data from database."""
    entities = db.all(KnowledgeEntity)
    claims = db.all(KnowledgeClaim)
    links = db.all(KnowledgeClaimLink)
    return entities, claims, links


# =============================================================================
# Enable/Disable Endpoints
# =============================================================================


@router.get(
    "/api/graph/networkx/status",
    response_model=EnableResponse,
    summary="Get NetworkX status",
    tags=["graph-reasoning"],
)
async def get_networkx_status() -> EnableResponse:
    """Get NetworkX availability and status."""
    reasoner = get_reasoner()
    return EnableResponse(
        enabled=reasoner.enabled,
        available=reasoner.is_available(),
        message="NetworkX is available" if reasoner.is_available() else "NetworkX not installed",
    )


@router.post(
    "/api/graph/networkx/enable",
    response_model=EnableResponse,
    summary="Enable or disable NetworkX reasoning",
    tags=["graph-reasoning"],
)
async def set_networkx_enabled(
    request: EnableRequest,
) -> EnableResponse:
    """Enable or disable NetworkX graph reasoning."""
    set_reasoner_enabled(request.enabled)
    reasoner = get_reasoner()

    if request.enabled and not reasoner.is_available():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="NetworkX is not available (not installed)",
        )

    return EnableResponse(
        enabled=reasoner.enabled,
        available=reasoner.is_available(),
        message=f"NetworkX reasoning {'enabled' if reasoner.enabled else 'disabled'}",
    )


# =============================================================================
# Centrality Endpoints
# =============================================================================


@router.post(
    "/api/graph/networkx/centrality",
    response_model=CentralityResponse,
    summary="Calculate centrality metrics",
    tags=["graph-reasoning"],
)
async def calculate_centrality(
    request: CentralityRequest,
    db: Database = Depends(get_library_database),
) -> CentralityResponse:
    """Calculate centrality metrics for the knowledge graph.

    Available algorithms:
    - degree_centrality: Node importance based on connections
    - betweenness_centrality: Nodes that act as bridges
    - closeness_centrality: How close a node is to all others
    - eigenvector_centrality: Influence based on neighbors' importance
    - pagerank: Google's PageRank algorithm
    """
    reasoner = get_reasoner()
    if not reasoner.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="NetworkX is not available",
        )

    entities, claims, links = _load_graph_data(db)

    result = reasoner.calculate_centrality(
        algorithm=request.algorithm,
        entities=entities,
        claims=claims,
        links=links,
    )

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Centrality calculation failed",
        )

    # Filter by entity type if requested
    if request.entity_type:
        result.results = [r for r in result.results if r.node_type == request.entity_type]
        result.top_nodes = result.top_nodes[:10]  # Re-filter top
        result.node_count = len(result.results)

    return result


@router.get(
    "/api/graph/networkx/centrality/{algorithm}",
    response_model=CentralityResponse,
    summary="Calculate centrality (GET endpoint)",
    tags=["graph-reasoning"],
)
async def get_centrality(
    algorithm: AlgorithmType,
    entity_type: str | None = Query(None, description="Filter by node type"),
    db: Database = Depends(get_library_database),
) -> CentralityResponse:
    """Calculate centrality metrics using specified algorithm."""
    reasoner = get_reasoner()
    if not reasoner.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="NetworkX is not available",
        )

    entities, claims, links = _load_graph_data(db)

    result = reasoner.calculate_centrality(
        algorithm=algorithm,
        entities=entities,
        claims=claims,
        links=links,
    )

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Centrality calculation failed",
        )

    if entity_type:
        result.results = [r for r in result.results if r.node_type == entity_type]
        result.top_nodes = result.results[:10]
        result.node_count = len(result.results)

    return result


# =============================================================================
# Communities Endpoints
# =============================================================================


@router.post(
    "/api/graph/networkx/communities",
    response_model=CommunitiesResponse,
    summary="Detect communities in the graph",
    tags=["graph-reasoning"],
)
async def detect_communities(
    request: CommunitiesRequest,
    db: Database = Depends(get_library_database),
) -> CommunitiesResponse:
    """Detect communities in the knowledge graph using community detection algorithms.

    Available algorithms:
    - louvain: Modularity optimization (default)
    - greedy_modularity: Greedy modularity maximization
    - label_propagation: Label propagation algorithm
    """
    reasoner = get_reasoner()
    if not reasoner.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="NetworkX is not available",
        )

    entities, claims, links = _load_graph_data(db)

    result = reasoner.detect_communities(
        algorithm=request.algorithm,
        entities=entities,
        claims=claims,
        links=links,
    )

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Community detection failed",
        )

    # Filter small communities
    if request.min_community_size > 2:
        result.communities = [
            c for c in result.communities if c.size >= request.min_community_size
        ]
        result.community_count = len(result.communities)

    return result


@router.get(
    "/api/graph/networkx/communities/{algorithm}",
    response_model=CommunitiesResponse,
    summary="Detect communities (GET endpoint)",
    tags=["graph-reasoning"],
)
async def get_communities(
    algorithm: CommunityAlgorithm,
    min_size: int = Query(3, ge=2, description="Minimum community size"),
    db: Database = Depends(get_library_database),
) -> CommunitiesResponse:
    """Detect communities using specified algorithm."""
    reasoner = get_reasoner()
    if not reasoner.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="NetworkX is not available",
        )

    entities, claims, links = _load_graph_data(db)

    result = reasoner.detect_communities(
        algorithm=algorithm,
        entities=entities,
        claims=claims,
        links=links,
    )

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Community detection failed",
        )

    if min_size > 2:
        result.communities = [c for c in result.communities if c.size >= min_size]
        result.community_count = len(result.communities)

    return result


# =============================================================================
# Shortest Paths Endpoints
# =============================================================================


@router.post(
    "/api/graph/networkx/paths",
    response_model=ShortestPathsResponse,
    summary="Find shortest paths",
    tags=["graph-reasoning"],
)
async def find_shortest_paths(
    request: ShortestPathsRequest,
    db: Database = Depends(get_library_database),
) -> ShortestPathsResponse:
    """Find shortest paths from source to multiple targets."""
    reasoner = get_reasoner()
    if not reasoner.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="NetworkX is not available",
        )

    entities, claims, links = _load_graph_data(db)

    result = reasoner.find_shortest_paths(
        source_id=request.source_id,
        target_ids=request.target_ids,
        entities=entities,
        claims=claims,
        links=links,
    )

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source node not found or graph empty",
        )

    return result


# =============================================================================
# Graph Metrics Endpoints
# =============================================================================


@router.get(
    "/api/graph/networkx/metrics",
    response_model=GraphMetricsResponse,
    summary="Get graph metrics",
    tags=["graph-reasoning"],
)
async def get_graph_metrics(
    db: Database = Depends(get_library_database),
) -> GraphMetricsResponse:
    """Get basic graph metrics using NetworkX."""
    reasoner = get_reasoner()

    if not reasoner.is_available():
        return GraphMetricsResponse(
            metrics=None,
            networkx_available=False,
            reasoner_enabled=reasoner.enabled,
        )

    entities, claims, links = _load_graph_data(db)

    metrics = reasoner.get_graph_metrics(
        entities=entities,
        claims=claims,
        links=links,
    )

    return GraphMetricsResponse(
        metrics=metrics,
        networkx_available=True,
        reasoner_enabled=reasoner.enabled,
    )


# =============================================================================
# Algorithms List Endpoint
# =============================================================================


@router.get(
    "/api/graph/networkx/algorithms",
    response_model=AlgorithmsListResponse,
    summary="List available algorithms",
    tags=["graph-reasoning"],
)
async def list_algorithms() -> AlgorithmsListResponse:
    """List all available NetworkX algorithms and their descriptions."""
    reasoner = get_reasoner()

    return AlgorithmsListResponse(
        networkx_available=reasoner.is_available(),
        reasoner_enabled=reasoner.enabled,
        centrality_algorithms=[
            AlgorithmInfo(id="degree_centrality", name="Degree Centrality", description="Node importance based on number of connections"),
            AlgorithmInfo(id="betweenness_centrality", name="Betweenness Centrality", description="Nodes that bridge different parts of the graph"),
            AlgorithmInfo(id="closeness_centrality", name="Closeness Centrality", description="Average distance to all other nodes"),
            AlgorithmInfo(id="eigenvector_centrality", name="Eigenvector Centrality", description="Influence based on neighbors' importance"),
            AlgorithmInfo(id="pagerank", name="PageRank", description="PageRank algorithm for node importance"),
        ],
        community_algorithms=[
            AlgorithmInfo(id="louvain", name="Louvain", description="Modularity optimization for community detection"),
            AlgorithmInfo(id="greedy_modularity", name="Greedy Modularity", description="Greedy modularity maximization"),
            AlgorithmInfo(id="label_propagation", name="Label Propagation", description="Fast label propagation community detection"),
        ],
    )
