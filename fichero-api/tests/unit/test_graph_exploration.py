"""Tests for graph exploration API (Issue #431)."""

from fichero.api.routes.graph_exploration import (
    PathAlgorithm,
    RelationDirection,
    ExplorationDepth,
    GraphNode,
    GraphEdge,
    PathSegment,
    EntityPath,
    InterpretationNode,
    InterpretationPath,
    EntityNeighborhood,
    GraphMetrics,
    GraphMetricsResponse,
    _get_entity_summary,
)
from fichero.knowledge_models import KnowledgeEntity, EntityType


class TestPathAlgorithm:
    """Test path algorithm enum."""

    def test_enum_values(self):
        """Test path algorithm enum values."""
        assert PathAlgorithm.SHORTEST.value == "shortest"
        assert PathAlgorithm.ALL_SIMPLE.value == "all_simple"
        assert PathAlgorithm.STRONGEST.value == "strongest"


class TestRelationDirection:
    """Test relation direction enum."""

    def test_direction_values(self):
        """Test direction enum values."""
        assert RelationDirection.OUTBOUND.value == "outbound"
        assert RelationDirection.INBOUND.value == "inbound"
        assert RelationDirection.BOTH.value == "both"


class TestExplorationDepth:
    """Test exploration depth enum."""

    def test_depth_values(self):
        """Test depth enum values."""
        assert ExplorationDepth.SHALLOW.value == "shallow"
        assert ExplorationDepth.MEDIUM.value == "medium"
        assert ExplorationDepth.DEEP.value == "deep"


class TestGraphNode:
    """Test graph node model."""

    def test_node_creation(self):
        """Test creating graph node."""
        node = GraphNode(
            id="node-1",
            type="entity",
            label="Test Entity",
            metadata={"key": "value"},
        )
        assert node.id == "node-1"
        assert node.type == "entity"
        assert node.label == "Test Entity"


class TestGraphEdge:
    """Test graph edge model."""

    def test_edge_creation(self):
        """Test creating graph edge."""
        edge = GraphEdge(
            source="node-1",
            target="node-2",
            type="related_to",
            weight=0.8,
        )
        assert edge.source == "node-1"
        assert edge.target == "node-2"
        assert edge.weight == 0.8


class TestPathSegment:
    """Test path segment model."""

    def test_segment_creation(self):
        """Test creating path segment."""
        node = GraphNode(id="n1", type="entity", label="Node 1")
        edge = GraphEdge(source="n1", target="n2", type="related", weight=0.5)

        segment = PathSegment(node=node, edge=edge)
        assert segment.node.id == "n1"
        assert segment.edge.source == "n1"

    def test_segment_no_edge(self):
        """Test segment with no edge (final node)."""
        node = GraphNode(id="n1", type="entity", label="Node 1")
        segment = PathSegment(node=node, edge=None)
        assert segment.node.id == "n1"
        assert segment.edge is None


class TestEntityPath:
    """Test entity path model."""

    def test_path_creation(self):
        """Test creating entity path."""
        node = GraphNode(id="n1", type="entity", label="Node 1")
        segment = PathSegment(node=node, edge=None)

        path = EntityPath(
            path_id="path-1",
            source_id="entity-1",
            target_id="entity-2",
            segments=[segment],
            length=1,
            total_weight=1.0,
            strength_score=0.5,
        )
        assert path.path_id == "path-1"
        assert path.source_id == "entity-1"
        assert path.strength_score == 0.5


class TestInterpretationNode:
    """Test interpretation node model."""

    def test_node_creation(self):
        """Test creating interpretation node."""
        node = InterpretationNode(
            id="interp-1",
            type="interpretation",
            label="Test Interpretation",
            confidence=0.85,
            created_at="2024-01-15T10:00:00",
        )
        assert node.id == "interp-1"
        assert node.confidence == 0.85
        assert node.label == "Test Interpretation"


class TestInterpretationPath:
    """Test interpretation path model."""

    def test_path_creation(self):
        """Test creating interpretation path."""
        start = InterpretationNode(id="e1", type="entity", label="Entity 1", created_at="2024-01-15T10:00:00")
        end = InterpretationNode(id="i1", type="interpretation", label="Interp 1", created_at="2024-01-15T10:00:00")

        path = InterpretationPath(
            path_id="path-1",
            start_node=start,
            end_node=end,
            intermediate_nodes=[],
            path_type="direct",
            relevance_score=0.75,
        )
        assert path.path_id == "path-1"
        assert path.path_type == "direct"
        assert path.relevance_score == 0.75


class TestEntityNeighborhood:
    """Test entity neighborhood model."""

    def test_neighborhood_creation(self):
        """Test creating entity neighborhood."""
        neighborhood = EntityNeighborhood(
            entity_id="entity-1",
            entity_name="Test Entity",
            depth=2,
            nodes=[],
            edges=[],
            claim_count=5,
            interpretation_count=3,
            entity_count=2,
        )
        assert neighborhood.entity_id == "entity-1"
        assert neighborhood.depth == 2
        assert neighborhood.claim_count == 5


class TestGraphMetrics:
    """Test graph metrics model."""

    def test_metrics_creation(self):
        """Test creating graph metrics."""
        metrics = GraphMetrics(
            entity_count=100,
            claim_count=200,
            interpretation_count=50,
            edge_count=150,
            avg_degree=2.5,
            max_degree=10,
            connected_components=5,
            density=0.15,
        )
        assert metrics.entity_count == 100
        assert metrics.claim_count == 200
        assert metrics.density == 0.15


class TestGraphMetricsResponse:
    """Test graph metrics response model."""

    def test_response_creation(self):
        """Test creating metrics response."""
        metrics = GraphMetrics(
            entity_count=50,
            claim_count=100,
            interpretation_count=25,
            edge_count=75,
            avg_degree=1.5,
            max_degree=8,
            connected_components=3,
            density=0.1,
        )

        response = GraphMetricsResponse(
            metrics=metrics,
            last_updated="2024-01-15T10:00:00",
            time_range=None,
        )
        assert response.metrics.entity_count == 50
        assert response.last_updated == "2024-01-15T10:00:00"


class TestGetEntitySummary:
    """Test entity summary helper."""

    def test_summary_creation(self):
        """Test creating entity summary."""
        entity = KnowledgeEntity(
            canonical_name="Test Entity",
            entity_type=EntityType.person,
            aliases=["Alias 1", "Alias 2"],
        )
        summary = _get_entity_summary(entity)
        assert summary["name"] == "Test Entity"
        assert summary["type"] == "person"


class TestBuildEntityNode:
    """Test entity node builder."""

    def test_entity_node(self):
        """Test building entity node."""
        entity = KnowledgeEntity(
            canonical_name="Test Entity",
            entity_type=EntityType.person,
        )
        node = GraphNode(
            id=entity.id,
            type="entity",
            label=entity.canonical_name,
            metadata={"entity_type": entity.entity_type.value if entity.entity_type else "unknown"},
        )
        assert node.type == "entity"
        assert node.label == "Test Entity"
