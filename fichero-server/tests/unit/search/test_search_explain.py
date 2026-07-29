"""Unit tests for search explanation functionality.

Tests cover:
- RAG mode configurations
- Search explanation generation
- Metrics calculation
- Query refinement suggestions
- Source attribution building
"""

import pytest

from fichero_server.api.routes.search_explain import (
    RAGMode,
    SearchType,
    RAG_MODE_CONFIGS,
    _generate_explanation,
    _calculate_metrics,
    _suggest_refinements,
    SearchExplainRequest,
    SourceAttribution,
    SearchMetrics,
)


class TestRAGModes:
    """Test RAG mode configurations."""

    def test_conservative_mode_exists(self):
        """Test conservative mode configuration."""
        config = RAG_MODE_CONFIGS[RAGMode.CONSERVATIVE]
        assert config.mode == RAGMode.CONSERVATIVE
        assert config.min_score_threshold == 0.8
        assert config.max_results == 5

    def test_balanced_mode_exists(self):
        """Test balanced mode configuration."""
        config = RAG_MODE_CONFIGS[RAGMode.BALANCED]
        assert config.mode == RAGMode.BALANCED
        assert config.min_score_threshold == 0.5
        assert config.max_results == 10
        assert config.enable_hybrid is True

    def test_speculative_mode_exists(self):
        """Test speculative mode configuration."""
        config = RAG_MODE_CONFIGS[RAGMode.SPECULATIVE]
        assert config.mode == RAGMode.SPECULATIVE
        assert config.min_score_threshold == 0.3
        assert config.max_results == 20
        assert config.context_window_ratio == 0.8


class TestSearchTypes:
    """Test search type enum."""

    def test_semantic_type(self):
        """Test semantic search type."""
        assert SearchType.SEMANTIC.value == "semantic"

    def test_fulltext_type(self):
        """Test fulltext search type."""
        assert SearchType.FULLTEXT.value == "fulltext"

    def test_hybrid_type(self):
        """Test hybrid search type."""
        assert SearchType.HYBRID.value == "hybrid"


class TestExplanationGeneration:
    """Test explanation generation."""

    def test_generates_explanation_for_query(self):
        """Test that explanation is generated for a query."""
        explanation = _generate_explanation(
            "test query", SearchType.HYBRID, RAGMode.BALANCED, 5
        )
        assert "test query" in explanation
        assert "hybrid" in explanation.lower()

    def test_includes_search_type_description(self):
        """Test explanation includes search type description."""
        for search_type in SearchType:
            explanation = _generate_explanation(
                "query", search_type, RAGMode.BALANCED, 3
            )
            assert len(explanation) > 0

    def test_includes_rag_mode_description(self):
        """Test explanation includes RAG mode description."""
        for rag_mode in RAGMode:
            explanation = _generate_explanation(
                "query", SearchType.HYBRID, rag_mode, 3
            )
            # Check some mode-specific keywords
            if rag_mode == RAGMode.CONSERVATIVE:
                assert "precision" in explanation.lower() or "Conservative" in explanation

    def test_no_results_message(self):
        """Test explanation when no results found."""
        explanation = _generate_explanation(
            "obscure query", SearchType.SEMANTIC, RAGMode.BALANCED, 0
        )
        assert "no results" in explanation.lower() or "No results" in explanation

    def test_few_results_message(self):
        """Test explanation when few results."""
        explanation = _generate_explanation(
            "specific query", SearchType.SEMANTIC, RAGMode.BALANCED, 1
        )
        assert "highly relevant" in explanation.lower() or "1" in explanation


class TestMetricsCalculation:
    """Test metrics calculation."""

    def test_empty_results(self):
        """Test metrics with no results."""
        metrics = _calculate_metrics([], 100.0)
        assert metrics.total_candidates == 0
        assert metrics.avg_relevance_score == 0.0
        assert metrics.token_estimate == 0

    def test_calculates_average_score(self):
        """Test average relevance score calculation."""
        results = [
            {"relevance_score": 0.9},
            {"relevance_score": 0.7},
            {"relevance_score": 0.5},
        ]
        metrics = _calculate_metrics(results, 50.0)
        assert metrics.avg_relevance_score == pytest.approx(0.7)
        assert metrics.min_relevance_score == 0.5
        assert metrics.max_relevance_score == 0.9

    def test_token_estimate(self):
        """Test token estimation from text length."""
        results = [
            {"text": "a" * 400},  # ~100 tokens
            {"text": "b" * 400},  # ~100 tokens
        ]
        metrics = _calculate_metrics(results, 50.0)
        assert metrics.token_estimate == 200

    def test_precision_estimate(self):
        """Test precision estimate based on high scores."""
        # All high scores -> high precision
        high_results = [
            {"relevance_score": 0.9},
            {"relevance_score": 0.95},
        ]
        metrics = _calculate_metrics(high_results, 50.0)
        assert metrics.precision_estimate == 1.0

        # Mixed scores -> lower precision
        mixed_results = [
            {"relevance_score": 0.9},
            {"relevance_score": 0.4},
        ]
        metrics = _calculate_metrics(mixed_results, 50.0)
        assert metrics.precision_estimate == 0.5


class TestQueryRefinements:
    """Test query refinement suggestions."""

    def test_no_results_suggestions(self):
        """Test suggestions when no results."""
        suggestions = _suggest_refinements("obscure term", 0)
        assert len(suggestions) > 0
        assert any("broaden" in s.lower() for s in suggestions)

    def test_too_many_results_suggestions(self):
        """Test suggestions when too many results."""
        suggestions = _suggest_refinements("common", 100)
        assert len(suggestions) > 0
        # Should suggest narrowing

    def test_short_query_suggestions(self):
        """Test suggestions for short query."""
        suggestions = _suggest_refinements("x", 5)
        # Should suggest adding context
        assert any("context" in s.lower() for s in suggestions)


class TestSearchExplainRequest:
    """Test SearchExplainRequest model."""

    def test_create_request_defaults(self):
        """Test request with defaults."""
        request = SearchExplainRequest(query="test query")
        assert request.query == "test query"
        assert request.search_type == SearchType.HYBRID
        assert request.rag_mode == RAGMode.BALANCED
        assert request.limit == 10

    def test_create_request_custom(self):
        """Test request with custom values."""
        request = SearchExplainRequest(
            query="test",
            search_type=SearchType.SEMANTIC,
            rag_mode=RAGMode.CONSERVATIVE,
            limit=5,
        )
        assert request.search_type == SearchType.SEMANTIC
        assert request.rag_mode == RAGMode.CONSERVATIVE


class TestSourceAttribution:
    """Test SourceAttribution model."""

    def test_create_attribution(self):
        """Test creating source attribution."""
        attribution = SourceAttribution(
            source_id="doc-123",
            source_type="document",
            title="Test Document",
            excerpt="Test excerpt...",
            relevance_score=0.85,
            match_type="semantic",
            position=1,
        )
        assert attribution.source_id == "doc-123"
        assert attribution.relevance_score == 0.85
        assert attribution.position == 1


class TestSearchMetrics:
    """Test SearchMetrics model."""

    def test_create_metrics(self):
        """Test creating search metrics."""
        metrics = SearchMetrics(
            total_candidates=100,
            filtered_results=10,
            precision_estimate=0.8,
            recall_estimate=0.7,
            avg_relevance_score=0.75,
            min_relevance_score=0.5,
            max_relevance_score=0.95,
            token_estimate=500,
            execution_time_ms=150.0,
        )
        assert metrics.total_candidates == 100
        assert metrics.precision_estimate == 0.8
