"""Tests for model comparison routes.

Model comparison lets you run the same prompt against multiple LLM providers
and compare outputs. Routes live at /api/model-comparison/... (router
prefix="/model-comparison" mounted at "/api"). Engine calls are mocked.
"""

from unittest.mock import MagicMock, patch, AsyncMock

from fichero.workflows.model_comparison import ComparisonResult, ModelResult


# ---------------------------------------------------------------------------
# GET /api/model-comparison/models
# ---------------------------------------------------------------------------


class TestListModels:
    def test_returns_model_list(self, client):
        r = client.get("/api/model-comparison/models")
        assert r.status_code == 200
        data = r.json()
        assert "models" in data
        assert len(data["models"]) > 0

    def test_models_have_required_fields(self, client):
        r = client.get("/api/model-comparison/models")
        assert r.status_code == 200
        for model in r.json()["models"]:
            assert "provider" in model
            assert "model" in model
            assert "input_price_per_million" in model


# ---------------------------------------------------------------------------
# GET /api/model-comparison/presets
# ---------------------------------------------------------------------------


class TestGetPresets:
    def test_returns_presets(self, client):
        r = client.get("/api/model-comparison/presets")
        assert r.status_code == 200
        data = r.json()
        assert "presets" in data
        assert len(data["presets"]) > 0

    def test_presets_have_models(self, client):
        r = client.get("/api/model-comparison/presets")
        assert r.status_code == 200
        for preset in r.json()["presets"]:
            assert "name" in preset
            assert "models" in preset
            assert len(preset["models"]) > 0


# ---------------------------------------------------------------------------
# GET /api/model-comparison/history
# ---------------------------------------------------------------------------


class TestGetHistory:
    def test_returns_history(self, client):
        mock_engine = MagicMock()
        mock_engine.get_history.return_value = []

        with patch("fichero.api.routes.model_comparison.get_comparison_engine", return_value=mock_engine):
            r = client.get("/api/model-comparison/history")
        assert r.status_code == 200
        data = r.json()
        assert "history" in data

    def test_returns_non_empty_history(self, client):
        comparison = ComparisonResult(
            prompt="Summarize this",
            models_compared=["openai/gpt-4o-mini"],
            results=[
                ModelResult(
                    provider="openai",
                    model="gpt-4o-mini",
                    response="Summary",
                    latency_ms=12.0,
                )
            ],
            fastest_model="openai/gpt-4o-mini",
            cheapest_model="openai/gpt-4o-mini",
            comparison_id="cmp-1",
        )
        mock_engine = MagicMock()
        mock_engine.get_history.return_value = [comparison.to_dict()]

        with patch(
            "fichero.api.routes.model_comparison.get_comparison_engine",
            return_value=mock_engine,
        ):
            r = client.get("/api/model-comparison/history")

        assert r.status_code == 200
        assert r.json()["history"][0]["comparison_id"] == "cmp-1"


# ---------------------------------------------------------------------------
# GET /api/model-comparison/comparison/{id}
# ---------------------------------------------------------------------------


class TestGetComparison:
    def test_get_missing_returns_404(self, client):
        mock_engine = MagicMock()
        mock_engine.get_comparison.return_value = None

        with patch("fichero.api.routes.model_comparison.get_comparison_engine", return_value=mock_engine):
            r = client.get("/api/model-comparison/comparison/no-such-id")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/model-comparison/estimate-cost
# ---------------------------------------------------------------------------


class TestEstimateCost:
    def test_estimate_returns_cost_breakdown(self, client):
        with patch("fichero.workflows.model_comparison.estimate_cost", return_value=0.01):
            r = client.post("/api/model-comparison/estimate-cost", json={
                "prompt": "What is the capital of France?",
                "models": [
                    {"provider": "openai", "model": "gpt-4o"},
                    {"provider": "anthropic", "model": "claude-3-5-sonnet-20241022"},
                ],
            })
        assert r.status_code == 200
        data = r.json()
        assert "model_estimates" in data
        assert "total_estimated_cost_usd" in data
        assert len(data["model_estimates"]) == 2


# ---------------------------------------------------------------------------
# POST /api/model-comparison/compare
# ---------------------------------------------------------------------------


class TestCompareModels:
    def test_compare_returns_results(self, client):
        comparison = ComparisonResult(
            prompt="Hello",
            models_compared=["openai/gpt-4o-mini"],
            results=[
                ModelResult(
                    provider="openai",
                    model="gpt-4o-mini",
                    response="Hi",
                    latency_ms=5.0,
                )
            ],
            fastest_model="openai/gpt-4o-mini",
            cheapest_model="openai/gpt-4o-mini",
            comparison_id="cmp-route",
        )
        mock_engine = MagicMock()
        mock_engine.compare = AsyncMock(return_value=comparison)

        with patch(
            "fichero.api.routes.model_comparison.get_comparison_engine",
            return_value=mock_engine,
        ):
            r = client.post(
                "/api/model-comparison/compare",
                json={
                    "prompt": "Hello",
                    "models": [{"provider": "openai", "model": "gpt-4o-mini"}],
                },
            )

        assert r.status_code == 200
        data = r.json()
        assert data["comparison_id"] == "cmp-route"
        assert data["results"][0]["response"] == "Hi"
