"""Tests for Hugging Face model browser routes.

These routes proxy the HuggingFace Hub API for model discovery.
Tests mock httpx to avoid real external API calls.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_hf_response(models: list[dict] | None = None, tasks: list[dict] | None = None):
    """Build a mock httpx response."""
    mock = MagicMock()
    mock.raise_for_status = MagicMock()
    if models is not None:
        mock.json.return_value = models
    elif tasks is not None:
        mock.json.return_value = {"pipeline_tag": tasks}
    return mock


HF_SAMPLE_MODELS = [
    {
        "modelId": "meta-llama/Llama-3.1-8B-Instruct",
        "downloads": 1000000,
        "likes": 5000,
        "pipeline_tag": "text-generation",
        "library_name": "transformers",
        "createdAt": "2024-01-01T00:00:00.000Z",
        "tags": ["text-generation", "transformers"],
    },
    {
        "modelId": "openai-community/gpt2",
        "downloads": 500000,
        "likes": 3000,
        "pipeline_tag": "text-generation",
        "library_name": "transformers",
        "createdAt": "2020-01-01T00:00:00.000Z",
        "tags": ["text-generation"],
    },
]

HF_SAMPLE_TASKS = [
    {"id": "text-generation", "label": "Text Generation"},
    {"id": "image-to-text", "label": "Image to Text"},
    {"id": "feature-extraction", "label": "Feature Extraction"},
]


@pytest.fixture(autouse=True)
def clear_model_cache():
    """Clear the HF model cache between tests."""
    from fichero.api.routes import models as models_module
    models_module._cache.clear()
    yield
    models_module._cache.clear()


# ---------------------------------------------------------------------------
# Tests: GET /api/models/huggingface/tasks
# ---------------------------------------------------------------------------


class TestListHFTasks:
    def test_returns_task_list(self, client):
        mock_resp = _make_hf_response(tasks=HF_SAMPLE_TASKS)
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            r = client.get("/api/models/huggingface/tasks")

        assert r.status_code == 200
        data = r.json()["items"]
        assert isinstance(data, list)
        assert len(data) == 3
        assert data[0]["id"] == "text-generation"
        assert data[0]["label"] == "Text Generation"

    def test_tasks_use_cache_on_second_call(self, client):
        mock_resp = _make_hf_response(tasks=HF_SAMPLE_TASKS)
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            client.get("/api/models/huggingface/tasks")
            client.get("/api/models/huggingface/tasks")

        # Only one real HTTP call because of cache
        assert mock_client.get.call_count == 1


# ---------------------------------------------------------------------------
# Tests: GET /api/models/huggingface
# ---------------------------------------------------------------------------


class TestSearchHFModels:
    def test_returns_model_list(self, client):
        mock_resp = _make_hf_response(models=HF_SAMPLE_MODELS)
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            r = client.get("/api/models/huggingface")

        assert r.status_code == 200
        data = r.json()
        assert "models" in data
        assert len(data["models"]) == 2
        assert data["models"][0]["id"] == "meta-llama/Llama-3.1-8B-Instruct"

    def test_has_more_flag(self, client):
        # Return limit+1 models to trigger has_more
        extra_models = HF_SAMPLE_MODELS + [
            {
                "modelId": f"test/model-{i}",
                "downloads": 0, "likes": 0,
                "pipeline_tag": None, "library_name": None,
                "createdAt": None, "tags": [],
            }
            for i in range(25)
        ]
        mock_resp = _make_hf_response(models=extra_models)
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            r = client.get("/api/models/huggingface?limit=20")

        assert r.status_code == 200
        data = r.json()
        assert data["has_more"] is True
        assert len(data["models"]) == 20

    def test_filter_by_task(self, client):
        mock_resp = _make_hf_response(models=HF_SAMPLE_MODELS)
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            r = client.get("/api/models/huggingface?task=text-generation")

        assert r.status_code == 200
        # Verify the task param was passed to HF API
        call_kwargs = mock_client.get.call_args
        assert "pipeline_tag" in str(call_kwargs)


# ---------------------------------------------------------------------------
# Tests: GET /api/models/huggingface/{model_id}
# ---------------------------------------------------------------------------


class TestGetHFModel:
    def test_get_specific_model(self, client):
        model_data = HF_SAMPLE_MODELS[0]
        # The route calls response.json() and then wraps in a list for caching
        # so mock.json() should return the raw model dict
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = model_data
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            r = client.get("/api/models/huggingface/meta-llama/Llama-3.1-8B-Instruct")

        assert r.status_code == 200
        data = r.json()
        assert data["id"] == "meta-llama/Llama-3.1-8B-Instruct"
        assert data["downloads"] == 1000000
