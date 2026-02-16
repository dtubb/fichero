"""Unit tests for model comparison engine."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from langchain_core.messages import AIMessage

from fichero.workflows.model_comparison import (
    ModelResult,
    ComparisonResult,
    ModelSpec,
    ComparisonRequest,
    ModelComparisonEngine,
    estimate_cost,
    model_comparison,
    get_comparison_engine,
)
from fichero.llm import LLMConfig


class TestModelResult:
    """Tests for ModelResult dataclass."""

    def test_create_model_result(self):
        """Test creating a model result."""
        result = ModelResult(
            provider="openai",
            model="gpt-4o",
            response="Test response",
            latency_ms=500.0,
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.005,
        )
        assert result.provider == "openai"
        assert result.model == "gpt-4o"
        assert result.response == "Test response"
        assert result.latency_ms == 500.0
        assert result.error is None

    def test_model_result_to_dict(self):
        """Test converting result to dict."""
        result = ModelResult(
            provider="anthropic",
            model="claude-3-5-sonnet",
            response="Hello",
            latency_ms=300.0,
        )
        d = result.to_dict()
        assert d["provider"] == "anthropic"
        assert "timestamp" in d


class TestComparisonResult:
    """Tests for ComparisonResult dataclass."""

    def test_create_comparison_result(self):
        """Test creating a comparison result."""
        result = ComparisonResult(
            prompt="Test prompt",
            models_compared=["openai/gpt-4o", "anthropic/claude"],
            results=[],
        )
        assert result.prompt == "Test prompt"
        assert len(result.models_compared) == 2

    def test_comparison_result_to_dict(self):
        """Test converting comparison to dict."""
        result = ComparisonResult(
            prompt="Test",
            models_compared=["openai/gpt-4o"],
            results=[
                ModelResult(
                    provider="openai",
                    model="gpt-4o",
                    response="Response",
                    latency_ms=100.0,
                )
            ],
            fastest_model="openai/gpt-4o",
        )
        d = result.to_dict()
        assert d["fastest_model"] == "openai/gpt-4o"
        assert len(d["results"]) == 1


class TestEstimateCost:
    """Tests for cost estimation."""

    def test_estimate_cost_gpt4o(self):
        """Test cost estimation for GPT-4o."""
        cost = estimate_cost("gpt-4o", 1000, 500)
        assert cost > 0
        # Expected: (1000/1M)*5 + (500/1M)*15 = 0.005 + 0.0075 = 0.0125
        assert 0.01 < cost < 0.02  # Expected around $0.0125

    def test_estimate_cost_unknown_model(self):
        """Test cost estimation for unknown model returns 0."""
        cost = estimate_cost("unknown-model-xyz", 1000, 500)
        assert cost == 0.0

    def test_estimate_cost_local_model(self):
        """Test local models are free."""
        cost = estimate_cost("llama3.2", 10000, 5000)
        assert cost == 0.0


class TestModelSpec:
    """Tests for ModelSpec."""

    def test_create_model_spec(self):
        """Test creating a model spec."""
        spec = ModelSpec(provider="openai", model="gpt-4o")
        assert spec.provider == "openai"
        assert spec.model == "gpt-4o"
        assert spec.temperature == 0.7  # default

    def test_model_spec_with_options(self):
        """Test model spec with custom options."""
        spec = ModelSpec(
            provider="anthropic",
            model="claude-3-5-sonnet",
            temperature=0.5,
            max_tokens=1000,
        )
        assert spec.temperature == 0.5
        assert spec.max_tokens == 1000


class TestModelComparisonEngine:
    """Tests for ModelComparisonEngine."""

    def test_init_engine(self):
        """Test initializing the engine."""
        engine = ModelComparisonEngine()
        assert engine.comparison_history == []

    @pytest.mark.asyncio
    async def test_compare_single_model(self):
        """Test comparison with single model."""
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Test response"
        mock_response.response_metadata = {}
        mock_model.ainvoke = AsyncMock(return_value=mock_response)

        with patch("fichero.workflows.model_comparison.get_langchain_model", return_value=mock_model):
            engine = ModelComparisonEngine()
            request = ComparisonRequest(
                prompt="Hello",
                models=[ModelSpec(provider="openai", model="gpt-4o")],
            )
            result = await engine.compare(request)

            assert len(result.results) == 1
            assert result.results[0].response == "Test response"
            assert result.fastest_model == "openai/gpt-4o"

    @pytest.mark.asyncio
    async def test_compare_multiple_models(self):
        """Test comparison with multiple models."""
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Response"
        mock_response.response_metadata = {}
        mock_model.ainvoke = AsyncMock(return_value=mock_response)

        with patch("fichero.workflows.model_comparison.get_langchain_model", return_value=mock_model):
            engine = ModelComparisonEngine()
            request = ComparisonRequest(
                prompt="Test",
                models=[
                    ModelSpec(provider="openai", model="gpt-4o"),
                    ModelSpec(provider="anthropic", model="claude-3-5-sonnet"),
                ],
            )
            result = await engine.compare(request)

            assert len(result.results) == 2
            assert len(result.models_compared) == 2

    @pytest.mark.asyncio
    async def test_compare_handles_timeout(self):
        """Test comparison handles timeout gracefully."""
        import asyncio

        async def slow_response(*args):
            await asyncio.sleep(10)
            return MagicMock(content="Slow")

        mock_model = MagicMock()
        mock_model.ainvoke = slow_response

        with patch("fichero.workflows.model_comparison.get_langchain_model", return_value=mock_model):
            engine = ModelComparisonEngine()
            request = ComparisonRequest(
                prompt="Test",
                models=[ModelSpec(provider="openai", model="gpt-4o")],
                timeout_seconds=1,
            )
            result = await engine.compare(request)

            assert len(result.results) == 1
            assert "Timeout" in result.results[0].error

    @pytest.mark.asyncio
    async def test_compare_handles_error(self):
        """Test comparison handles errors gracefully."""
        mock_model = MagicMock()
        mock_model.ainvoke = AsyncMock(side_effect=Exception("API Error"))

        with patch("fichero.workflows.model_comparison.get_langchain_model", return_value=mock_model):
            engine = ModelComparisonEngine()
            request = ComparisonRequest(
                prompt="Test",
                models=[ModelSpec(provider="openai", model="gpt-4o")],
            )
            result = await engine.compare(request)

            assert len(result.results) == 1
            assert "API Error" in result.results[0].error

    def test_get_history(self):
        """Test getting comparison history."""
        engine = ModelComparisonEngine()
        engine.comparison_history.append(
            ComparisonResult(
                prompt="Test 1",
                models_compared=["openai/gpt-4o"],
                results=[],
                comparison_id="abc123",
            )
        )
        engine.comparison_history.append(
            ComparisonResult(
                prompt="Test 2",
                models_compared=["anthropic/claude"],
                results=[],
                comparison_id="def456",
            )
        )

        history = engine.get_history(limit=1)
        assert len(history) == 1
        assert history[0]["comparison_id"] == "def456"  # Most recent

    def test_get_comparison(self):
        """Test getting specific comparison."""
        engine = ModelComparisonEngine()
        engine.comparison_history.append(
            ComparisonResult(
                prompt="Test",
                models_compared=["openai/gpt-4o"],
                results=[],
                comparison_id="test123",
            )
        )

        result = engine.get_comparison("test123")
        assert result is not None
        assert result.comparison_id == "test123"

        result = engine.get_comparison("nonexistent")
        assert result is None


class TestModelComparisonTool:
    """Tests for model_comparison workflow tool."""

    @pytest.fixture
    def llm_config(self):
        return LLMConfig(provider="openai", model="gpt-4o")

    @pytest.fixture
    def mock_state(self):
        return {
            "task_id": "test-123",
            "workflow_id": "wf-1",
            "inputs": {},
            "outputs": {},
            "current_node": "",
            "completed_nodes": [],
            "error": None,
            "input_files": [],
            "output_files": [],
        }

    @pytest.mark.asyncio
    async def test_model_comparison_no_prompt(self, llm_config, mock_state):
        """Test tool with no prompt."""
        result = await model_comparison(
            inputs={},
            state=mock_state,
            llm_config=llm_config,
        )
        assert result["error"] == "No prompt provided"

    @pytest.mark.asyncio
    async def test_model_comparison_with_prompt(self, llm_config, mock_state):
        """Test tool with prompt and models."""
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Test response"
        mock_response.response_metadata = {}
        mock_model.ainvoke = AsyncMock(return_value=mock_response)

        with patch("fichero.workflows.model_comparison.get_langchain_model", return_value=mock_model):
            result = await model_comparison(
                inputs={
                    "prompt": "Hello",
                    "models": [
                        {"provider": "openai", "model": "gpt-4o"},
                    ],
                },
                state=mock_state,
                llm_config=llm_config,
            )

            assert "results" in result
            assert "summary" in result
            assert result["summary"]["models_compared"] == 1


class TestGetComparisonEngine:
    """Tests for global engine accessor."""

    def test_get_engine_singleton(self):
        """Test that get_comparison_engine returns same instance."""
        engine1 = get_comparison_engine()
        engine2 = get_comparison_engine()
        assert engine1 is engine2
