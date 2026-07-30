"""Tests for model comparison routes.

Model comparison lets you run the same prompt against multiple LLM providers
and compare outputs. Routes live at /api/model-comparison/... (router
prefix="/model-comparison" mounted at "/api"). Engine calls are mocked.
"""

import json
from unittest.mock import MagicMock, patch, AsyncMock

from fichero_server.models import DocType, Document, Model, Provider, ProviderType, Workflow
from fichero_server.workflows.model_comparison import ComparisonResult, ModelResult


def _seed_model(
    app_db,
    *,
    provider_type=ProviderType.openai,
    provider_name="OpenAI",
    model_id="gpt-4o-mini",
    input_cost=0.15,
    output_cost=0.60,
    capabilities=None,
):
    provider = Provider(name=provider_name, provider_type=provider_type)
    app_db.save_provider(provider)
    app_db.save_model(
        Model(
            provider_id=provider.id,
            name=model_id,
            model_id=model_id,
            capabilities=capabilities or ["text"],
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
# GET /api/model-comparison/language-fit
# ---------------------------------------------------------------------------


class TestLanguageFit:
    def test_language_fit_scores_explicit_model(self, client, tmp_path, monkeypatch):
        monkeypatch.setenv("FICHERO_LANGUAGE_COVERAGE_DIR", str(tmp_path))

        r = client.get(
            "/api/model-comparison/language-fit",
            params={
                "language": "es",
                "provider": "openai",
                "model": "gpt-4o-mini",
            },
        )

        assert r.status_code == 200
        data = r.json()
        assert data["language"]["code"] == "es"
        assert data["results"][0]["provider"] == "openai"
        assert data["results"][0]["model"] == "gpt-4o-mini"
        assert data["results"][0]["status"] == "heuristic"
        assert data["results"][0]["source"]["kind"] == "heuristic_fallback"
        assert "No cloud calls" in data["privacy_note"]

    def test_language_fit_uses_settings_models_when_model_omitted(
        self, client, app_db, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("FICHERO_LANGUAGE_COVERAGE_DIR", str(tmp_path))
        _seed_model(app_db, model_id="gpt-4o-mini")
        _seed_model(
            app_db,
            provider_type=ProviderType.anthropic,
            provider_name="Anthropic",
            model_id="claude-3-5-sonnet",
        )

        r = client.get("/api/model-comparison/language-fit?language=es")

        assert r.status_code == 200
        models = {(item["provider"], item["model"]) for item in r.json()["results"]}
        assert ("openai", "gpt-4o-mini") in models
        assert ("anthropic", "claude-3-5-sonnet") in models

    def test_language_fit_uses_local_derived_coverage_file(
        self, client, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("FICHERO_LANGUAGE_COVERAGE_DIR", str(tmp_path))
        (tmp_path / "openai__gpt-4o-mini.json").write_text(
            json.dumps(
                {
                    "model_id": "gpt-4o-mini",
                    "coverage": {
                        "es": {
                            "score": 0.93,
                            "tier_counts": {"tier_0": 90, "tier_1": 3},
                            "fertility": {
                                "tokens_per_char": 0.33,
                                "tokens_per_word": 1.5,
                                "sample_chars": 120,
                                "sample_tokens": 40,
                            },
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

        r = client.get(
            "/api/model-comparison/language-fit",
            params={
                "language": "es",
                "provider": "openai",
                "model": "gpt-4o-mini",
            },
        )

        assert r.status_code == 200
        result = r.json()["results"][0]
        assert result["status"] == "derived"
        assert result["coverage_score"] == 0.93
        assert result["source"]["kind"] == "loove_derived_json"
        assert result["tier_counts"]["tier_0_native"] == 90
        assert result["fertility"]["tokens_per_word"] == 1.5

    def test_language_fit_unsupported_language_is_typed(
        self, client, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("FICHERO_LANGUAGE_COVERAGE_DIR", str(tmp_path))

        r = client.get(
            "/api/model-comparison/language-fit",
            params={
                "language": "zz",
                "provider": "openai",
                "model": "gpt-4o-mini",
            },
        )

        assert r.status_code == 200
        result = r.json()["results"][0]
        assert result["status"] == "unsupported_language"
        assert result["coverage_score"] is None
        assert result["warnings"]

    def test_language_fit_requires_provider_and_model_together(self, client):
        r = client.get(
            "/api/model-comparison/language-fit",
            params={"language": "es", "provider": "openai"},
        )

        assert r.status_code == 400


# ---------------------------------------------------------------------------
# POST /api/model-comparison/recommend-models
# ---------------------------------------------------------------------------


class TestRecommendModels:
    def test_recommend_models_scores_explicit_candidates(
        self, client, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("FICHERO_LANGUAGE_COVERAGE_DIR", str(tmp_path))
        (tmp_path / "apple__apple-foundation.json").write_text(
            json.dumps({"coverage": {"es": {"score": 0.94}}}),
            encoding="utf-8",
        )

        r = client.post(
            "/api/model-comparison/recommend-models",
            json={
                "language": "es",
                "task": "paleography",
                "private": True,
                "candidates": [
                    {
                        "provider": "openai",
                        "model": "gpt-4o",
                        "capabilities": ["text"],
                        "input_price_per_million": 5,
                        "output_price_per_million": 15,
                    },
                    {
                        "provider": "apple",
                        "model": "apple-foundation",
                        "capabilities": ["text"],
                        "input_price_per_million": 0,
                        "output_price_per_million": 0,
                    },
                ],
            },
        )

        assert r.status_code == 200
        data = r.json()
        assert data["items"][0]["provider"] == "apple"
        assert data["items"][0]["privacy_posture"] == "builtin_local"
        assert data["items"][0]["cost"]["status"] == "free"
        assert data["items"][1]["availability_status"] == "refused"
        assert "No cloud calls" in data["privacy_note"]

    def test_recommend_models_uses_settings_candidates(
        self, client, app_db, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("FICHERO_LANGUAGE_COVERAGE_DIR", str(tmp_path))
        _seed_model(
            app_db,
            provider_type=ProviderType.apple,
            provider_name="Apple Intelligence",
            model_id="apple-foundation",
            input_cost=0.0,
            output_cost=0.0,
        )

        r = client.post(
            "/api/model-comparison/recommend-models",
            json={"language": "fr", "local_only": True},
        )

        assert r.status_code == 200
        data = r.json()
        assert data["items"][0]["provider"] == "apple"
        assert data["items"][0]["source"] == "settings"
        assert data["items"][0]["available"] is True

    def test_recommend_models_keeps_unknown_settings_cost_typed(
        self, client, app_db, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("FICHERO_LANGUAGE_COVERAGE_DIR", str(tmp_path))
        _seed_model(
            app_db,
            provider_type=ProviderType.anthropic,
            provider_name="Anthropic",
            model_id="claude-unknown-price",
            input_cost=None,
            output_cost=None,
        )

        r = client.post(
            "/api/model-comparison/recommend-models",
            json={"language": "fr"},
        )

        assert r.status_code == 200
        item = r.json()["items"][0]
        assert item["cost"]["status"] == "unknown"
        assert item["cost"]["input_price_per_million"] is None
        assert item["cost"]["output_price_per_million"] is None
        assert any("not treated as free" in warning for warning in item["warnings"])

    def test_recommend_models_uses_loove_coverage_for_ranking(
        self, client, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("FICHERO_LANGUAGE_COVERAGE_DIR", str(tmp_path))
        (tmp_path / "openai__gpt-4o-mini.json").write_text(
            json.dumps({"coverage": {"ja": {"score": 0.98}}}),
            encoding="utf-8",
        )
        (tmp_path / "apple__apple-foundation.json").write_text(
            json.dumps({"coverage": {"ja": {"score": 0.55}}}),
            encoding="utf-8",
        )

        r = client.post(
            "/api/model-comparison/recommend-models",
            json={
                "language": "ja",
                "candidates": [
                    {
                        "provider": "apple",
                        "model": "apple-foundation",
                        "capabilities": ["text"],
                        "input_price_per_million": 0,
                        "output_price_per_million": 0,
                    },
                    {
                        "provider": "openai",
                        "model": "gpt-4o-mini",
                        "capabilities": ["text"],
                        "input_price_per_million": 0.15,
                        "output_price_per_million": 0.60,
                    },
                ],
            },
        )

        assert r.status_code == 200
        items = r.json()["items"]
        assert items[0]["provider"] == "openai"
        assert items[0]["language_fit"]["status"] == "derived"
        assert items[0]["language_fit"]["coverage_score"] == 0.98


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

        with patch("fichero_server.api.routes.ai.model_comparison.get_comparison_engine", return_value=mock_engine):
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
            "fichero_server.api.routes.ai.model_comparison.get_comparison_engine",
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

        with patch("fichero_server.api.routes.ai.model_comparison.get_comparison_engine", return_value=mock_engine):
            r = client.get("/api/model-comparison/comparison/no-such-id")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/model-comparison/estimate-cost
# ---------------------------------------------------------------------------


class TestEstimateCost:
    def test_estimate_returns_cost_breakdown(self, client):
        with patch("fichero_server.workflows.model_comparison.estimate_cost", return_value=0.01):
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
            "fichero_server.api.routes.ai.model_comparison.get_comparison_engine",
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
            "fichero_server.api.routes.ai.model_comparison.get_comparison_engine",
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


# ---------------------------------------------------------------------------
# POST /api/model-comparison/compare-vision
# ---------------------------------------------------------------------------


class TestCompareVision:
    def test_compare_vision_resolves_library_doc_ids(self, client, app_db, db, tmp_path):
        _seed_model(app_db, capabilities=["vision"])
        doc = Document(
            id="page-1",
            name="Page 1",
            doc_type=DocType.page,
            page_content=None,
        )
        db.save(doc, auto_embed=False)
        image = tmp_path / "page-1.jpg"
        image.write_bytes(b"fake-jpeg")
        comparison = ComparisonResult(
            prompt="[Vision: 1 images] Transcribe",
            models_compared=["openai/gpt-4o-mini"],
            results=[
                ModelResult(
                    provider="openai",
                    model="gpt-4o-mini",
                    response="Transcript",
                    latency_ms=5.0,
                )
            ],
            comparison_id="cmp-vision-doc",
        )
        mock_engine = MagicMock()
        mock_engine.compare_vision = AsyncMock(return_value=comparison)

        with (
            patch(
                "fichero_server.api.routes.ai.model_comparison.get_comparison_engine",
                return_value=mock_engine,
            ),
            patch("fichero_server.api.routes.ai.model_comparison.get_display", return_value=image),
        ):
            r = client.post(
                "/api/model-comparison/compare-vision",
                json={
                    "doc_ids": [doc.id],
                    "prompt": "Transcribe",
                    "models": [{"provider": "openai", "model": "gpt-4o-mini"}],
                },
            )

        assert r.status_code == 200
        assert r.json()["comparison_id"] == "cmp-vision-doc"
        assert mock_engine.compare_vision.await_args.kwargs["images"] == [
            "data:image/jpeg;base64,ZmFrZS1qcGVn"
        ]

    def test_compare_vision_requires_image_or_doc_id(self, client, app_db):
        _seed_model(app_db, capabilities=["vision"])

        r = client.post(
            "/api/model-comparison/compare-vision",
            json={
                "prompt": "Transcribe",
                "models": [{"provider": "openai", "model": "gpt-4o-mini"}],
            },
        )

        assert r.status_code == 422
        assert "At least one image" in r.json()["detail"]


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
            "fichero_server.api.routes.ai.model_comparison.get_comparison_engine",
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
            "fichero_server.api.routes.ai.model_comparison.get_comparison_engine",
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
            "fichero_server.api.routes.ai.model_comparison.get_comparison_engine",
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
