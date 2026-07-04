"""Unit tests for model comparison engine."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

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
        """Test cost estimation for unknown model returns unavailable."""
        cost = estimate_cost("unknown-model-xyz", 1000, 500)
        assert cost is None

    def test_estimate_cost_local_model(self):
        """Test local models are free."""
        cost = estimate_cost("llama3.2", 10000, 5000)
        assert cost == 0.0

    def test_estimate_cost_gemini_25_flash(self):
        """Test newer Gemini pricing is recognized."""
        cost = estimate_cost("gemini-2.5-flash", 1000, 500)
        assert cost > 0

    def test_estimate_cost_apple_is_free(self):
        """Test Apple/local models are treated as free."""
        cost = estimate_cost("apple", 10000, 5000)
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
        with patch(
            "fichero.workflows.model_comparison.chat_workflow",
            new=AsyncMock(return_value="Test response"),
        ):
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
        with patch(
            "fichero.workflows.model_comparison.chat_workflow",
            new=AsyncMock(return_value="Response"),
        ):
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

        async def slow_response(*args, **kwargs):
            await asyncio.sleep(10)
            return "Slow"

        with patch(
            "fichero.workflows.model_comparison.chat_workflow",
            new=AsyncMock(side_effect=slow_response),
        ):
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
        with patch(
            "fichero.workflows.model_comparison.chat_workflow",
            new=AsyncMock(side_effect=Exception("API Error")),
        ):
            engine = ModelComparisonEngine()
            request = ComparisonRequest(
                prompt="Test",
                models=[ModelSpec(provider="openai", model="gpt-4o")],
            )
            result = await engine.compare(request)

            assert len(result.results) == 1
            assert "API Error" in result.results[0].error

    @pytest.mark.asyncio
    async def test_compare_vision_awaits_async_vision(self):
        """Regression: compare_vision must AWAIT the async ``vision`` coroutine.

        Previously ``_run_vision_model`` wrapped the async ``vision`` in
        ``asyncio.to_thread`` which only built the coroutine without awaiting it,
        so every model failed with "object of type 'coroutine' has no len()".
        """
        async_vision = AsyncMock(return_value="Numero 2. En la ciudad de Novita...")

        with patch("fichero.workflows.model_comparison.vision", async_vision):
            engine = ModelComparisonEngine()
            result = await engine.compare_vision(
                images=["data:image/png;base64,AAAA"],
                prompt="Transcribe",
                models=[ModelSpec(provider="openai", model="gpt-4o")],
            )

        assert len(result.results) == 1
        assert result.results[0].error is None
        assert result.results[0].response.startswith("Numero 2.")
        assert result.fastest_model == "openai/gpt-4o"
        async_vision.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_compare_workflow_fans_out_and_aggregates_cost(self):
        engine = ModelComparisonEngine()
        workflow = MagicMock()
        workflow.id = "wf-1"
        workflow.name = "Transcribe"
        workflow.nodes = [MagicMock(tool="transcribe")]
        workflow_variant = MagicMock()

        state_one = {
            "completed_nodes": ["node-1"],
            "outputs": {"node-1": {"text": "First model output"}},
        }
        state_two = {
            "completed_nodes": ["node-1"],
            "outputs": {"node-1": {"text": "Second model output is longer"}},
        }

        execute_mock = AsyncMock(side_effect=[state_one, state_two])
        with patch.object(
            engine,
            "_workflow_with_model_override",
            return_value=workflow_variant,
        ), patch.object(
            engine,
            "_execute_workflow_variant",
            execute_mock,
        ):
            result = await engine.compare_workflow(
                workflow=workflow,
                inputs={"selected_doc_ids": ["doc-1"]},
                models=[
                    ModelSpec(provider="openai", model="gpt-4o"),
                    ModelSpec(provider="google", model="gemini-2.5-flash"),
                ],
                library_path="/tmp/test.fichero",
            )

        assert len(result.results) == 2
        assert result.total_cost_usd == sum(item.cost_usd for item in result.results)
        assert result.total_latency_ms == sum(item.latency_ms for item in result.results)
        assert result.fastest_model in {"openai/gpt-4o", "google/gemini-2.5-flash"}
        assert result.cheapest_model in {"openai/gpt-4o", "google/gemini-2.5-flash"}
        assert result.results[0].response == "First model output"
        assert result.results[1].response == "Second model output is longer"
        assert execute_mock.await_count == 2

    @pytest.mark.asyncio
    async def test_compare_workflow_returns_error_result_for_failed_variant(self):
        engine = ModelComparisonEngine()
        workflow = MagicMock()
        workflow.id = "wf-1"
        workflow.name = "Translate"
        workflow.nodes = [MagicMock(tool="translate")]
        workflow_variant = MagicMock()

        with patch.object(
            engine,
            "_workflow_with_model_override",
            return_value=workflow_variant,
        ), patch.object(
            engine,
            "_execute_workflow_variant",
            AsyncMock(side_effect=RuntimeError("boom")),
        ):
            result = await engine.compare_workflow(
                workflow=workflow,
                inputs={"selected_doc_ids": ["doc-9"]},
                models=[ModelSpec(provider="openai", model="gpt-4o")],
                library_path="/tmp/test.fichero",
            )

        assert len(result.results) == 1
        assert result.results[0].error == "boom"
        assert result.fastest_model is None
        assert result.cheapest_model is None

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

    # ------------------------------------------------------------------
    # #2211: _execute_workflow_variant must resolve .fichero dir → .duckdb file
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_execute_workflow_variant_resolves_fichero_dir_to_duckdb(self, tmp_path):
        """Passing a .fichero DIRECTORY as library_path must NOT reach create_compiled_app
        as-is — it must be resolved to the fichero.duckdb file inside the bundle (#2211).

        Before the fix: db_path=library_path (a directory) was passed directly, which
        caused duckdb.connect() to raise "IOException: Is a directory" and every
        compare-workflow variant returned error=str(exc) instead of running.
        """
        import pathlib

        bundle = tmp_path / "MyLib.fichero"
        bundle.mkdir()

        captured_db_paths = []

        mock_app = MagicMock()
        mock_app.ainvoke = AsyncMock(return_value={"outputs": {}, "completed_nodes": []})
        mock_checkpointer = MagicMock()

        def fake_create_compiled_app(workflow_def, *, db_path, **_kwargs):
            captured_db_paths.append(pathlib.Path(str(db_path)))
            return mock_app, mock_checkpointer

        engine = ModelComparisonEngine()
        workflow_variant = MagicMock()
        workflow_variant.id = "wf-test"

        with patch(
            "fichero.workflows.model_comparison.create_compiled_app",
            side_effect=fake_create_compiled_app,
        ):
            await engine._execute_workflow_variant(
                workflow_variant=workflow_variant,
                inputs={"selected_doc_ids": []},
                library_path=str(bundle),
                timeout_seconds=10,
            )

        assert len(captured_db_paths) == 1, "create_compiled_app should be called once"
        resolved = captured_db_paths[0]
        assert not resolved.is_dir(), "db_path must not be a directory"
        assert resolved.name == "fichero.duckdb", (
            f"Expected fichero.duckdb, got {resolved.name}"
        )
        assert resolved.parent == bundle, "db_path must be inside the .fichero bundle"

    @pytest.mark.asyncio
    async def test_execute_workflow_variant_plain_file_path_unchanged(self, tmp_path):
        """When library_path is already a .duckdb file (not a bundle dir), it passes through
        unchanged — the fix must not affect non-bundle paths (#2211 guard)."""
        import pathlib

        db_file = tmp_path / "fichero.duckdb"
        db_file.touch()

        captured_db_paths = []

        mock_app = MagicMock()
        mock_app.ainvoke = AsyncMock(return_value={"outputs": {}, "completed_nodes": []})

        def fake_create_compiled_app(workflow_def, *, db_path, **_kwargs):
            captured_db_paths.append(pathlib.Path(str(db_path)))
            return mock_app, MagicMock()

        engine = ModelComparisonEngine()
        workflow_variant = MagicMock()
        workflow_variant.id = "wf-test-2"

        with patch(
            "fichero.workflows.model_comparison.create_compiled_app",
            side_effect=fake_create_compiled_app,
        ):
            await engine._execute_workflow_variant(
                workflow_variant=workflow_variant,
                inputs={"selected_doc_ids": []},
                library_path=str(db_file),
                timeout_seconds=10,
            )

        assert captured_db_paths[0] == pathlib.Path(str(db_file))

    # ------------------------------------------------------------------
    # #2212: empty / failed vision calls must NOT count as successful
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_compare_vision_empty_response_is_error(self):
        """vision() returning '' must produce an error result, not a success.

        Before #2212 the empty string passed the len() check and the result had
        error=None, making it a "successful" comparison despite no useful output.
        """
        async_vision = AsyncMock(return_value="")

        with patch("fichero.workflows.model_comparison.vision", async_vision):
            engine = ModelComparisonEngine()
            result = await engine.compare_vision(
                images=["data:image/png;base64,AAAA"],
                prompt="Describe",
                models=[ModelSpec(provider="openai", model="gpt-4o")],
            )

        assert len(result.results) == 1
        r = result.results[0]
        assert r.error is not None, "Empty vision response must surface as an error"
        assert "empty" in r.error.lower()
        # An empty-response failure must not appear in successful_results,
        # so fastest/cheapest model should be None.
        assert result.fastest_model is None
        assert result.cheapest_model is None

    @pytest.mark.asyncio
    async def test_compare_vision_none_response_is_error(self):
        """vision() returning None must also produce an error result (#2212)."""
        async_vision = AsyncMock(return_value=None)

        with patch("fichero.workflows.model_comparison.vision", async_vision):
            engine = ModelComparisonEngine()
            result = await engine.compare_vision(
                images=["data:image/png;base64,AAAA"],
                prompt="Describe",
                models=[ModelSpec(provider="openai", model="gpt-4o")],
            )

        assert len(result.results) == 1
        r = result.results[0]
        assert r.error is not None, "None vision response must surface as an error"
        assert result.fastest_model is None

    @pytest.mark.asyncio
    async def test_compare_vision_successful_result_not_affected(self):
        """A real non-empty response must still be counted as successful (#2212)."""
        async_vision = AsyncMock(return_value="The image shows a cathedral facade.")

        with patch("fichero.workflows.model_comparison.vision", async_vision):
            engine = ModelComparisonEngine()
            result = await engine.compare_vision(
                images=["data:image/png;base64,AAAA"],
                prompt="Describe",
                models=[ModelSpec(provider="openai", model="gpt-4o")],
            )

        assert len(result.results) == 1
        r = result.results[0]
        assert r.error is None
        assert r.response == "The image shows a cathedral facade."
        assert result.fastest_model == "openai/gpt-4o"


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
        with patch(
            "fichero.workflows.model_comparison.chat_workflow",
            new=AsyncMock(return_value="Test response"),
        ):
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
