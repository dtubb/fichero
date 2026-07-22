"""Tests for NetworkX graph reasoning (Issue #430)."""

import pytest

from fichero.graph_reasoning import (
    AlgorithmType,
    CommunityAlgorithm,
    CentralityResult,
    CommunityResult,
    GraphMetrics,
    NetworkXReasoner,
    get_reasoner,
    set_reasoner_enabled,
)
from fichero.models.knowledge import (
    KnowledgeEntity,
    KnowledgeClaim,
    EntityType,
    EpistemicStatus,
)

try:
    import networkx as nx  # noqa: F401
    NETWORKX_AVAILABLE = True
except ImportError:
    NETWORKX_AVAILABLE = False


def _create_claim(text: str, confidence: float, entity_ids: list[str]) -> KnowledgeClaim:
    """Create a test KnowledgeClaim with required fields."""
    return KnowledgeClaim(
        text=text,
        source_document_id="test-doc",
        confidence=confidence,
        epistemic_status=EpistemicStatus.confirmed,
        entity_ids=entity_ids,
    )


class TestAlgorithmType:
    """Test algorithm type enum."""

    def test_enum_values(self):
        """Test algorithm enum values."""
        assert AlgorithmType.degree_centrality.value == "degree_centrality"
        assert AlgorithmType.betweenness_centrality.value == "betweenness_centrality"
        assert AlgorithmType.closeness_centrality.value == "closeness_centrality"
        assert AlgorithmType.eigenvector_centrality.value == "eigenvector_centrality"
        assert AlgorithmType.pagerank.value == "pagerank"


class TestCommunityAlgorithm:
    """Test community algorithm enum."""

    def test_enum_values(self):
        """Test community algorithm enum values."""
        assert CommunityAlgorithm.louvain.value == "louvain"
        assert CommunityAlgorithm.greedy_modularity.value == "greedy_modularity"
        assert CommunityAlgorithm.label_propagation.value == "label_propagation"


class TestCentralityResult:
    """Test centrality result model."""

    def test_result_creation(self):
        """Test creating centrality result."""
        result = CentralityResult(
            node_id="node-1",
            node_type="entity",
            node_label="Test Entity",
            score=0.8,
            rank=1,
        )
        assert result.node_id == "node-1"
        assert result.score == 0.8
        assert result.rank == 1


class TestCommunityResult:
    """Test community result model."""

    def test_result_creation(self):
        """Test creating community result."""
        result = CommunityResult(
            community_id=0,
            nodes=["n1", "n2", "n3"],
            node_labels=["Node 1", "Node 2", "Node 3"],
            size=3,
            density=0.5,
            cohesion_score=1.5,
        )
        assert result.community_id == 0
        assert result.size == 3


class TestGraphMetrics:
    """Test graph metrics model."""

    def test_metrics_creation(self):
        """Test creating graph metrics."""
        metrics = GraphMetrics(
            node_count=100,
            edge_count=250,
            density=0.05,
            clustering_coefficient=0.3,
            connected_components=5,
            largest_component_size=80,
        )
        assert metrics.node_count == 100
        assert metrics.density == 0.05


class TestNetworkXReasoner:
    """Test NetworkX reasoner."""

    def setup_method(self):
        """Setup fresh reasoner for each test."""
        import fichero.graph_reasoning as gr
        gr._reasoner = None
        self.reasoner = get_reasoner(enabled=True)

    def test_is_available(self):
        """Test availability check."""
        assert self.reasoner.is_available() == NETWORKX_AVAILABLE

    @pytest.mark.skipif(not NETWORKX_AVAILABLE, reason="NetworkX not available")
    def test_build_graph(self):
        """Test building graph from knowledge data."""
        entity = KnowledgeEntity(
            canonical_name="Test Entity",
            entity_type=EntityType.person,
        )
        claim = _create_claim("Test claim", 0.9, [entity.id])

        entities = [entity]
        claims = [claim]
        links = []

        G = self.reasoner._build_graph(entities, claims, links)
        assert G is not None or not NETWORKX_AVAILABLE
        if G is not None:
            assert len(G.nodes) >= 2  # Entity + claim

    @pytest.mark.skipif(not NETWORKX_AVAILABLE, reason="NetworkX not available")
    def test_calculate_centrality_degree(self):
        """Test degree centrality calculation."""
        entity1 = KnowledgeEntity(canonical_name="Entity 1", entity_type=EntityType.person)
        entity2 = KnowledgeEntity(canonical_name="Entity 2", entity_type=EntityType.person)
        claim = _create_claim("Test", 0.9, [entity1.id, entity2.id])

        entities = [entity1, entity2]
        claims = [claim]
        links = []

        result = self.reasoner.calculate_centrality(
            AlgorithmType.degree_centrality,
            entities,
            claims,
            links,
        )

        if NETWORKX_AVAILABLE:
            assert result is not None
            assert len(result.results) > 0
            assert result.algorithm == "degree_centrality"

    @pytest.mark.skipif(not NETWORKX_AVAILABLE, reason="NetworkX not available")
    def test_calculate_centrality_empty_graph(self):
        """Test centrality with empty graph."""
        result = self.reasoner.calculate_centrality(
            AlgorithmType.degree_centrality,
            [],
            [],
            [],
        )

        assert result is not None
        assert result.node_count == 0
        assert len(result.results) == 0

    @pytest.mark.skipif(not NETWORKX_AVAILABLE, reason="NetworkX not available")
    def test_detect_communities_greedy(self):
        """Test greedy modularity community detection."""
        entities = [
            KnowledgeEntity(canonical_name=f"Entity {i}", entity_type=EntityType.person)
            for i in range(5)
        ]

        claims = [
            _create_claim(f"Claim {i}", 0.9, [entities[0].id, entities[i].id])
            for i in range(1, 5)
        ]

        result = self.reasoner.detect_communities(
            CommunityAlgorithm.greedy_modularity,
            entities,
            claims,
            [],
        )

        if NETWORKX_AVAILABLE:
            assert result is not None
            assert result.community_count >= 1

    @pytest.mark.skipif(not NETWORKX_AVAILABLE, reason="NetworkX not available")
    def test_detect_communities_empty_graph(self):
        """Test community detection with empty graph."""
        result = self.reasoner.detect_communities(
            CommunityAlgorithm.greedy_modularity,
            [],
            [],
            [],
        )

        assert result is not None
        assert result.community_count == 0

    @pytest.mark.skipif(not NETWORKX_AVAILABLE, reason="NetworkX not available")
    def test_get_graph_metrics(self):
        """Test graph metrics calculation."""
        entity1 = KnowledgeEntity(canonical_name="Entity 1", entity_type=EntityType.person)
        entity2 = KnowledgeEntity(canonical_name="Entity 2", entity_type=EntityType.person)
        claim = _create_claim("Test", 0.9, [entity1.id, entity2.id])

        metrics = self.reasoner.get_graph_metrics([entity1, entity2], [claim], [])

        if NETWORKX_AVAILABLE:
            assert metrics is not None
            assert metrics.node_count >= 3
            assert metrics.density >= 0.0

    @pytest.mark.skipif(not NETWORKX_AVAILABLE, reason="NetworkX not available")
    def test_get_graph_metrics_empty(self):
        """Test metrics with empty graph."""
        metrics = self.reasoner.get_graph_metrics([], [], [])

        assert metrics is not None
        assert metrics.node_count == 0


class TestGetReasoner:
    """Test get_reasoner singleton."""

    def test_singleton(self):
        """Test reasoner is a singleton."""
        import fichero.graph_reasoning as gr
        gr._reasoner = None

        reasoner1 = get_reasoner()
        reasoner2 = get_reasoner()
        assert reasoner1 is reasoner2


class TestSetReasonerEnabled:
    """Test enable/disable functionality."""

    def test_set_enabled(self):
        """Test enabling/disabling reasoner."""
        import fichero.graph_reasoning as gr
        gr._reasoner = None

        set_reasoner_enabled(True)
        reasoner = get_reasoner()
        assert reasoner.enabled == NETWORKX_AVAILABLE

        set_reasoner_enabled(False)
        assert reasoner.enabled is False


class TestNetworkXNotAvailable:
    """Test behavior when NetworkX is not available."""

    def test_reasoner_disabled_without_networkx(self, monkeypatch):
        """Test that reasoner reports not available when NetworkX missing."""
        import fichero.graph_reasoning as gr

        original_available = gr.NETWORKX_AVAILABLE
        original_nx = gr.nx
        original_reasoner = gr._reasoner

        gr.NETWORKX_AVAILABLE = False
        gr.nx = None
        gr._reasoner = None

        reasoner = NetworkXReasoner(enabled=True)
        assert reasoner.is_available() is False

        # Restore
        gr.NETWORKX_AVAILABLE = original_available
        gr.nx = original_nx
        gr._reasoner = original_reasoner


class TestCentralityAlgorithms:
    """Test different centrality algorithms."""

    def setup_method(self):
        """Ensure reasoner is enabled for each test."""
        set_reasoner_enabled(True)

    @pytest.mark.skipif(not NETWORKX_AVAILABLE, reason="NetworkX not available")
    def test_betweenness_centrality(self):
        """Test betweenness centrality."""
        reasoner = get_reasoner()

        entities = [
            KnowledgeEntity(canonical_name=f"Entity {i}", entity_type=EntityType.person)
            for i in range(4)
        ]
        claims = [
            _create_claim("Test", 0.9, [entities[0].id, entities[1].id]),
            _create_claim("Test 2", 0.8, [entities[2].id, entities[3].id]),
        ]

        result = reasoner.calculate_centrality(
            AlgorithmType.betweenness_centrality,
            entities,
            claims,
            [],
        )

        assert result is not None
        assert result.algorithm == "betweenness_centrality"

    @pytest.mark.skipif(not NETWORKX_AVAILABLE, reason="NetworkX not available")
    def test_pagerank(self):
        """Test PageRank centrality."""
        reasoner = get_reasoner()

        entities = [
            KnowledgeEntity(canonical_name="Hub", entity_type=EntityType.person),
            KnowledgeEntity(canonical_name="Spoke 1", entity_type=EntityType.person),
            KnowledgeEntity(canonical_name="Spoke 2", entity_type=EntityType.person),
        ]
        claims = [
            _create_claim("Claim", 0.9, [entities[0].id, entities[1].id]),
            _create_claim("Claim 2", 0.9, [entities[0].id, entities[2].id]),
        ]

        result = reasoner.calculate_centrality(
            AlgorithmType.pagerank,
            entities,
            claims,
            [],
        )

        assert result is not None


class TestCommunityDetection:
    """Test community detection."""

    def setup_method(self):
        """Ensure reasoner is enabled for each test."""
        set_reasoner_enabled(True)

    @pytest.mark.skipif(not NETWORKX_AVAILABLE, reason="NetworkX not available")
    def test_label_propagation(self):
        """Test label propagation community detection."""
        reasoner = get_reasoner()

        entities = [
            KnowledgeEntity(canonical_name=f"Cluster1-{i}", entity_type=EntityType.person)
            for i in range(3)
        ] + [
            KnowledgeEntity(canonical_name=f"Cluster2-{i}", entity_type=EntityType.person)
            for i in range(3)
        ]

        claims = [
            _create_claim("C1", 0.9, [entities[0].id, entities[1].id]),
            _create_claim("C2", 0.9, [entities[1].id, entities[2].id]),
            _create_claim("C3", 0.9, [entities[3].id, entities[4].id]),
            _create_claim("C4", 0.9, [entities[4].id, entities[5].id]),
        ]

        result = reasoner.detect_communities(
            CommunityAlgorithm.label_propagation,
            entities,
            claims,
            [],
        )

        assert result is not None
        assert result.community_count >= 1

    @pytest.mark.skipif(not NETWORKX_AVAILABLE, reason="NetworkX not available")
    def test_modularity_score(self):
        """Test that modularity is calculated."""
        reasoner = get_reasoner()

        entities = [
            KnowledgeEntity(canonical_name=f"E{i}", entity_type=EntityType.person)
            for i in range(4)
        ]
        claims = [
            _create_claim("Test", 0.9, [e.id for e in entities[:2]]),
        ]

        result = reasoner.detect_communities(
            CommunityAlgorithm.greedy_modularity,
            entities,
            claims,
            [],
        )

        if result and result.community_count > 0:
            assert -0.5 <= result.modularity <= 1.0


class TestShortestPaths:
    """Test shortest paths functionality."""

    def setup_method(self):
        """Ensure reasoner is enabled for each test."""
        set_reasoner_enabled(True)

    @pytest.mark.skipif(not NETWORKX_AVAILABLE, reason="NetworkX not available")
    def test_find_shortest_paths(self):
        """Test finding shortest paths."""
        reasoner = get_reasoner()

        entity_a = KnowledgeEntity(canonical_name="A", entity_type=EntityType.person)
        entity_b = KnowledgeEntity(canonical_name="B", entity_type=EntityType.person)
        entity_c = KnowledgeEntity(canonical_name="C", entity_type=EntityType.person)

        claim = _create_claim("Connects A and B", 0.9, [entity_a.id, entity_b.id])

        result = reasoner.find_shortest_paths(
            source_id=entity_a.id,
            target_ids=[entity_b.id, entity_c.id],
            entities=[entity_a, entity_b, entity_c],
            claims=[claim],
            links=[],
        )

        assert result is not None
        assert result.source_id == entity_a.id

    def test_find_shortest_paths_not_available(self, monkeypatch):
        """Test shortest paths when NetworkX not available."""
        import fichero.graph_reasoning as gr

        original = gr.NETWORKX_AVAILABLE
        original_nx = gr.nx
        original_reasoner = gr._reasoner

        gr.NETWORKX_AVAILABLE = False
        gr.nx = None
        gr._reasoner = None

        reasoner = get_reasoner(enabled=False)
        result = reasoner.find_shortest_paths("a", ["b"], [], [], [])

        assert result is None

        # Restore
        gr.NETWORKX_AVAILABLE = original
        gr.nx = original_nx
        gr._reasoner = original_reasoner
