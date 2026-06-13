"""Tests for model comparison routes.

Model comparison lets you run the same prompt against multiple LLM providers
and compare outputs. Routes live at /api/model-comparison/... (router
prefix="/model-comparison" mounted at "/api"). Engine calls are mocked.
"""

from unittest.mock import MagicMock, patch, AsyncMock

from fichero.models import Model, Provider, ProviderType, Workflow
from fichero.workflows.model_comparison import ComparisonResult, ModelResult


def _seed_model(
    app_db,
    *,
    provider_type=ProviderType.openai,
    provider_name="OpenAI",
    model_id="gpt-4o-mini",
    input_cost=0.15,
    output_cost=0.60,
):
    provider = Provider(name=provider_name, provider_type=provider_type)
    app_db.save_provider(provider)
    app_db.save_model(
        Model(
            provider_id=provider.id,
            name=model_id,
            model_id=model_id,
            input_cost=input_cost,
            output_cost=output_cost,
        )
    )
    return provider


# ---------------------------------------------------------------------------
# GET /api/model-comparison/models
# ---------------------------------------------------------------------------


class TestListModels:
    def test_returns_model_list(self, client, app_db):
        _seed_model(app_db)
        r = client.get("/api/model-comparison/models")
        assert r.status_code == 200
        data = r.json()
        assert "models" in data
        assert len(data["models"]) > 0

    def test_models_have_required_fields(self, client, app_db):
        _seed_model(app_db)
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
    def test_returns_presets(self, client, app_db):
        _seed_model(app_db)
        r = client.get("/api/model-comparison/presets")
        assert r.status_code == 200
        data = r.json()
        assert "presets" in data
        assert len(data["presets"]) > 0

    def test_presets_have_models(self, client, app_db):
        _seed_model(app_db)
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

    def test_compare_uses_settings_models_when_request_omits_models(
        self, client, app_db
    ):
        _seed_model(app_db)
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
            comparison_id="cmp-settings",
        )
        mock_engine = MagicMock()
        mock_engine.compare = AsyncMock(return_value=comparison)

        with patch(
            "fichero.api.routes.model_comparison.get_comparison_engine",
            return_value=mock_engine,
        ):
            r = client.post(
                "/api/model-comparison/compare",
                json={"prompt": "Hello"},
            )

        assert r.status_code == 200
        request = mock_engine.compare.await_args.args[0]
        assert request.models[0].provider == "openai"
        assert request.models[0].model == "gpt-4o-mini"


class TestCompareWorkflow:
    def test_compare_workflow_returns_results(self, client):
        comparison = ComparisonResult(
            prompt="[Workflow: Transcribe] {'selected_doc_ids': ['doc-1']}",
            models_compared=["openai/gpt-4o-mini"],
            results=[
                ModelResult(
                    provider="openai",
                    model="gpt-4o-mini",
                    response="Transcript text",
                    latency_ms=42.0,
                    cost_usd=0.0123,
                )
            ],
            fastest_model="openai/gpt-4o-mini",
            cheapest_model="openai/gpt-4o-mini",
            comparison_id="cmp-workflow",
        )
        mock_engine = MagicMock()
        mock_engine.compare_workflow = AsyncMock(return_value=comparison)

        with patch(
            "fichero.api.routes.model_comparison.get_comparison_engine",
            return_value=mock_engine,
        ):
            r = client.post(
                "/api/model-comparison/compare-workflow",
                json={
                    "workflow": {
                        "id": "wf-1",
                        "name": "Transcribe",
                        "nodes": [{"id": "node-1", "tool": "transcribe"}],
                        "edges": [],
                    },
                    "doc_id": "doc-1",
                    "models": [{"provider": "openai", "model": "gpt-4o-mini"}],
                },
            )

        assert r.status_code == 200
        payload = r.json()
        assert payload["comparison_id"] == "cmp-workflow"
        assert payload["results"][0]["response"] == "Transcript text"
        assert mock_engine.compare_workflow.await_args.kwargs["inputs"] == {
            "selected_doc_ids": ["doc-1"]
        }

    def test_compare_workflow_resolves_saved_workflow(self, client, db):
        workflow = Workflow(
            name="Translate",
            format="nodes",
            nodes=[{"id": "node-1", "tool": "translate"}],
            edges=[],
        )
        db.save(workflow)
        comparison = ComparisonResult(
            prompt="[Workflow: Translate] {'selected_doc_ids': ['doc-7']}",
            models_compared=["openai/gpt-4o-mini"],
            results=[],
            comparison_id="cmp-saved",
        )
        mock_engine = MagicMock()
        mock_engine.compare_workflow = AsyncMock(return_value=comparison)

        with patch(
            "fichero.api.routes.model_comparison.get_comparison_engine",
            return_value=mock_engine,
        ):
            r = client.post(
                "/api/model-comparison/compare-workflow",
                json={
                    "workflow_id": workflow.id,
                    "doc_id": "doc-7",
                    "models": [{"provider": "openai", "model": "gpt-4o-mini"}],
                },
            )

        assert r.status_code == 200
        workflow_arg = mock_engine.compare_workflow.await_args.kwargs["workflow"]
        assert workflow_arg.id == workflow.id


class TestCompareWorkflowNode:
    def test_compare_node_returns_apply_patches(self, client, app_db):
        _seed_model(app_db)
        comparison = ComparisonResult(
            prompt="[Tool: model_comparison] {'prompt': 'Pinned'}",
            models_compared=["openai/gpt-4o-mini"],
            results=[
                ModelResult(
                    provider="openai",
                    model="gpt-4o-mini",
                    response="Best result",
                    latency_ms=7.0,
                    structured_decode_success=True,
                    raw_response={"text": "Best result"},
                )
            ],
            comparison_id="cmp-node",
        )
        mock_engine = MagicMock()
        mock_engine.compare_tool = AsyncMock(return_value=comparison)

        with patch(
            "fichero.api.routes.model_comparison.get_comparison_engine",
            return_value=mock_engine,
        ):
            r = client.post(
                "/api/model-comparison/compare-node",
                json={
                    "workflow": {
                        "id": "wf-1",
                        "name": "Workflow",
                        "nodes": [
                            {
                                "id": "node-1",
                                "tool": "model_comparison",
                                "inputs": {"prompt": "Pinned"},
                                "uses_llm": True,
                            }
                        ],
                        "edges": [],
                    },
                    "node_id": "node-1",
                },
            )

        assert r.status_code == 200
        data = r.json()
        assert data["node_id"] == "node-1"
        assert data["input_snapshot"]["prompt"] == "Pinned"
        assert data["choices"][0]["apply_patch"] == {
            "provider_name": "openai",
            "model_name": "gpt-4o-mini",
        }


class TestApplyNodeModel:
    def test_apply_model_persists_provider_and_model_on_node(self, client, db):
        workflow = Workflow(
            name="Compare Me",
            format="nodes",
            nodes=[
                {
                    "id": "node-a",
                    "tool": "model_comparison",
                    "uses_llm": True,
                    "provider_name": "",
                    "model_name": "",
                }
            ],
            edges=[],
        )
        db.save(workflow)

        r = client.post(
            "/api/model-comparison/compare-node/apply",
            json={
                "workflow_id": workflow.id,
                "node_id": "node-a",
                "provider_name": "openai",
                "model_name": "gpt-4o-mini",
            },
        )
        assert r.status_code == 200
        payload = r.json()
        assert payload["workflow_id"] == workflow.id
        assert payload["node_id"] == "node-a"
        assert payload["provider_name"] == "openai"
        assert payload["model_name"] == "gpt-4o-mini"

        refreshed = db.get(Workflow, workflow.id)
        node = refreshed.nodes[0]
        assert node["provider_name"] == "openai"
        assert node["model_name"] == "gpt-4o-mini"
