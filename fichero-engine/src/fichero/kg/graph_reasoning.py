"""NetworkX graph reasoning integration for knowledge graph analysis.

Provides algorithmic graph analysis including centrality metrics,
community detection, and derived relationship inference.
"""

from __future__ import annotations

import logging
import time
from enum import Enum

from pydantic import BaseModel

try:
    import networkx as nx
    NETWORKX_AVAILABLE = True
except ImportError:
    NETWORKX_AVAILABLE = False
    nx = None

from fichero.models.knowledge import (
    KnowledgeClaim,
    KnowledgeClaimLink,
    KnowledgeEntity,
)

logger = logging.getLogger(__name__)


class AlgorithmType(str, Enum):
    """Types of graph algorithms."""

    degree_centrality = "degree_centrality"
    betweenness_centrality = "betweenness_centrality"
    closeness_centrality = "closeness_centrality"
    eigenvector_centrality = "eigenvector_centrality"
    pagerank = "pagerank"


class CommunityAlgorithm(str, Enum):
    """Community detection algorithms."""

    louvain = "louvain"
    greedy_modularity = "greedy_modularity"
    label_propagation = "label_propagation"


class CentralityResult(BaseModel):
    """Centrality metric for a single node."""

    node_id: str
    node_type: str  # "entity", "claim"
    node_label: str
    score: float
    rank: int


class CentralityResponse(BaseModel):
    """Response for centrality analysis."""

    algorithm: str
    node_count: int
    results: list[CentralityResult]
    top_nodes: list[CentralityResult]
    execution_time_ms: float
    graph_density: float


class CommunityResult(BaseModel):
    """Detected community."""

    community_id: int
    nodes: list[str]  # node IDs
    node_labels: list[str]
    size: int
    density: float
    cohesion_score: float


class CommunitiesResponse(BaseModel):
    """Response for community detection."""

    algorithm: str
    community_count: int
    modularity: float
    communities: list[CommunityResult]
    execution_time_ms: float


class PathResult(BaseModel):
    """Path analysis result."""

    path_id: str
    source_id: str
    target_id: str
    path_length: int
    intermediate_nodes: list[str]
    weight: float


class ShortestPathsResponse(BaseModel):
    """Response for shortest paths analysis."""

    source_id: str
    paths: list[PathResult]
    diameter: int | None
    average_path_length: float | None


class GraphMetrics(BaseModel):
    """Basic graph metrics."""

    node_count: int
    edge_count: int
    density: float
    clustering_coefficient: float
    connected_components: int
    largest_component_size: int


class NetworkXReasoner:
    """NetworkX-based graph reasoning engine."""

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled and NETWORKX_AVAILABLE
        if not NETWORKX_AVAILABLE and enabled:
            logger.warning("NetworkX not available, reasoning disabled")

    def is_available(self) -> bool:
        """Check if NetworkX is available."""
        return self.enabled

    def _build_graph(
        self,
        entities: list[KnowledgeEntity],
        claims: list[KnowledgeClaim],
        links: list[KnowledgeClaimLink],
    ) -> nx.Graph | None:
        """Build a NetworkX graph from knowledge data."""
        if not NETWORKX_AVAILABLE:
            return None

        G = nx.Graph()

        # Add entity nodes
        for entity in entities:
            G.add_node(
                entity.id,
                type="entity",
                label=entity.canonical_name,
                entity_type=entity.entity_type.value if entity.entity_type else "unknown",
            )

        # Add claim nodes
        for claim in claims:
            G.add_node(
                claim.id,
                type="claim",
                label=claim.text[:50] + "..." if len(claim.text) > 50 else claim.text,
                confidence=claim.confidence,
            )

            # Entity-claim connections
            for entity_id in claim.entity_ids:
                if G.has_node(entity_id):
                    G.add_edge(entity_id, claim.id, relation="mentions", weight=claim.confidence)

        # Claim-claim connections via links
        for link in links:
            if G.has_node(link.claim_id) and G.has_node(link.related_claim_id):
                G.add_edge(
                    link.claim_id,
                    link.related_claim_id,
                    relation=link.relation_type.value if link.relation_type else "related",
                    weight=link.link_quality,
                )

        return G

    def calculate_centrality(
        self,
        algorithm: AlgorithmType,
        entities: list[KnowledgeEntity],
        claims: list[KnowledgeClaim],
        links: list[KnowledgeClaimLink],
    ) -> CentralityResponse | None:
        """Calculate centrality metrics for graph nodes."""
        if not self.enabled or not NETWORKX_AVAILABLE:
            return None

        start_time = time.time()

        G = self._build_graph(entities, claims, links)
        if G is None or len(G.nodes) <= 2:
            return CentralityResponse(
                algorithm=algorithm.value,
                node_count=0,
                results=[],
                top_nodes=[],
                execution_time_ms=0.0,
                graph_density=0.0,
            )

        # Calculate centrality
        try:
            if algorithm == AlgorithmType.degree_centrality:
                centrality = nx.degree_centrality(G)
            elif algorithm == AlgorithmType.betweenness_centrality:
                centrality = nx.betweenness_centrality(G, weight="weight")
            elif algorithm == AlgorithmType.closeness_centrality:
                centrality = nx.closeness_centrality(G)
            elif algorithm == AlgorithmType.eigenvector_centrality:
                centrality = nx.eigenvector_centrality(G, weight="weight", max_iter=1000)
            elif algorithm == AlgorithmType.pagerank:
                centrality = nx.pagerank(G, weight="weight")
            else:
                centrality = nx.degree_centrality(G)
        except Exception as e:
            logger.error(f"Centrality calculation failed: {e}")
            centrality = nx.degree_centrality(G)

        # Build results
        results: list[CentralityResult] = []
        for node_id, score in centrality.items():
            node_data = G.nodes.get(node_id, {})
            label = node_data.get("label", node_id)
            node_type = node_data.get("type", "unknown")

            results.append(
                CentralityResult(
                    node_id=node_id,
                    node_type=node_type,
                    node_label=label,
                    score=score,
                    rank=0,  # Will be set after sorting
                )
            )

        # Sort by score, assign ranks
        results.sort(key=lambda x: x.score, reverse=True)
        for i, r in enumerate(results):
            r.rank = i + 1

        execution_time = (time.time() - start_time) * 1000

        return CentralityResponse(
            algorithm=algorithm.value,
            node_count=len(results),
            results=results,
            top_nodes=results[:10],
            execution_time_ms=execution_time,
            graph_density=nx.density(G),
        )

    def detect_communities(
        self,
        algorithm: CommunityAlgorithm,
        entities: list[KnowledgeEntity],
        claims: list[KnowledgeClaim],
        links: list[KnowledgeClaimLink],
    ) -> CommunitiesResponse | None:
        """Detect communities in the knowledge graph."""
        if not self.enabled or not NETWORKX_AVAILABLE:
            return None

        start_time = time.time()

        G = self._build_graph(entities, claims, links)
        if G is None or len(G.nodes) <= 2:
            return CommunitiesResponse(
                algorithm=algorithm.value,
                community_count=0,
                modularity=0.0,
                communities=[],
                execution_time_ms=0.0,
            )

        try:
            if algorithm == CommunityAlgorithm.louvain:
                try:
                    import networkx.algorithms.community as nx_comm
                    communities = nx_comm.louvain_communities(G, weight="weight")
                except Exception:
                    # Fallback to greedy modularity
                    communities = nx.community.greedy_modularity_communities(G, weight="weight")
            elif algorithm == CommunityAlgorithm.greedy_modularity:
                communities = nx.community.greedy_modularity_communities(G, weight="weight")
            elif algorithm == CommunityAlgorithm.label_propagation:
                communities = nx.community.label_propagation_communities(G)
            else:
                communities = nx.community.greedy_modularity_communities(G, weight="weight")

            # Convert to proper format
            communities = [list(c) for c in communities]
        except Exception as e:
            logger.error(f"Community detection failed: {e}")
            communities = []

        # Build community results
        community_results: list[CommunityResult] = []
        for idx, community_nodes in enumerate(communities):
            node_labels = []
            for node_id in community_nodes:
                node_data = G.nodes.get(node_id, {})
                node_labels.append(node_data.get("label", node_id))

            # Calculate density for this community
            subgraph = G.subgraph(community_nodes)
            density = nx.density(subgraph) if len(community_nodes) > 1 else 0.0

            community_results.append(
                CommunityResult(
                    community_id=idx,
                    nodes=community_nodes,
                    node_labels=node_labels,
                    size=len(community_nodes),
                    density=density,
                    cohesion_score=density * len(community_nodes),  # Simple heuristic
                )
            )

        # Calculate modularity
        modularity = 0.0
        try:
            modularity = nx.community.modularity(
                G, [set(c) for c in communities], weight="weight"
            )
        except Exception as e:
            logger.debug("Modularity calculation failed: %s", e)

        execution_time = (time.time() - start_time) * 1000

        return CommunitiesResponse(
            algorithm=algorithm.value,
            community_count=len(communities),
            modularity=modularity,
            communities=sorted(community_results, key=lambda x: x.size, reverse=True),
            execution_time_ms=execution_time,
        )

    def find_shortest_paths(
        self,
        source_id: str,
        target_ids: list[str],
        entities: list[KnowledgeEntity],
        claims: list[KnowledgeClaim],
        links: list[KnowledgeClaimLink],
    ) -> ShortestPathsResponse | None:
        """Find shortest paths between nodes."""
        if not self.enabled or not NETWORKX_AVAILABLE:
            return None

        G = self._build_graph(entities, claims, links)
        if G is None or not G.has_node(source_id):
            return None

        paths: list[PathResult] = []

        for target_id in target_ids:
            if not G.has_node(target_id):
                continue

            try:
                path_nodes = nx.shortest_path(G, source_id, target_id, weight="weight")
                path_length = len(path_nodes) - 1

                paths.append(
                    PathResult(
                        path_id=f"{source_id}_to_{target_id}",
                        source_id=source_id,
                        target_id=target_id,
                        path_length=path_length,
                        intermediate_nodes=path_nodes[1:-1],
                        weight=1.0 / (path_length + 0.1),  # Shorter = higher weight
                    )
                )
            except nx.NetworkXNoPath:
                continue

        # Graph metrics
        diameter = None
        avg_path_length = None
        try:
            if nx.is_connected(G):
                diameter = nx.diameter(G)
                avg_path_length = nx.average_shortest_path_length(G)
        except Exception as e:
            logger.debug("Graph diameter/path calculation failed: %s", e)

        return ShortestPathsResponse(
            source_id=source_id,
            paths=sorted(paths, key=lambda p: p.path_length),
            diameter=diameter,
            average_path_length=avg_path_length,
        )

    def get_graph_metrics(
        self,
        entities: list[KnowledgeEntity],
        claims: list[KnowledgeClaim],
        links: list[KnowledgeClaimLink],
    ) -> GraphMetrics | None:
        """Get basic graph metrics."""
        if not self.enabled or not NETWORKX_AVAILABLE:
            return None

        G = self._build_graph(entities, claims, links)
        if G is None:
            return None

        node_count = len(G.nodes)
        edge_count = len(G.edges)

        density = nx.density(G) if node_count > 1 else 0.0

        clustering = 0.0
        try:
            clustering = nx.average_clustering(G)
        except Exception as e:
            logger.debug("Clustering calculation failed: %s", e)

        components = list(nx.connected_components(G))
        connected_components = len(components)
        largest_component_size = max(len(c) for c in components) if components else 0

        return GraphMetrics(
            node_count=node_count,
            edge_count=edge_count,
            density=density,
            clustering_coefficient=clustering,
            connected_components=connected_components,
            largest_component_size=largest_component_size,
        )


# Global reasoner instance
_reasoner: NetworkXReasoner | None = None


def get_reasoner(enabled: bool = True) -> NetworkXReasoner:
    """Get or create the global NetworkX reasoner."""
    global _reasoner
    if _reasoner is None:
        _reasoner = NetworkXReasoner(enabled=enabled)
    return _reasoner


def set_reasoner_enabled(enabled: bool) -> None:
    """Enable or disable the NetworkX reasoner."""
    global _reasoner
    if _reasoner is None:
        _reasoner = NetworkXReasoner(enabled=enabled)
    else:
        _reasoner.enabled = enabled and NETWORKX_AVAILABLE
