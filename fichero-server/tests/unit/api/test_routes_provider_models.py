"""Coverage for provider-model discovery helpers."""

from __future__ import annotations

from types import SimpleNamespace

from fichero_server.api.routes.ai import provider_models as routes


def test_generate_model_description_lists_capabilities_and_context():
    description = routes.generate_model_description(
        {
            "max_input_tokens": 1_000_000,
            "supports_vision": True,
            "supports_reasoning": True,
            "supports_function_calling": True,
            "input_cost_per_million": 0,
            "output_cost_per_million": 0,
        }
    )

    assert description == "1M token context, vision, reasoning, tool use, free"


def test_generate_model_description_returns_none_without_metadata():
    assert routes.generate_model_description({}) is None


def test_provider_url_helpers_normalize_version_suffixes():
    assert routes._openai_models_url("https://api.example/v1") == "https://api.example/v1/models"
    assert routes._openai_models_url("https://api.example/") == "https://api.example/v1/models"
    assert routes._local_server_root("http://localhost:11434/v1/") == "http://localhost:11434"


def test_local_model_vision_detection_is_case_insensitive():
    assert routes._local_model_is_vision("Qwen3-VL")
    assert routes._local_model_is_vision("chandra-ocr-2")
    assert not routes._local_model_is_vision("llama-3")


def test_configured_api_base_prefers_matching_provider(monkeypatch):
    app_db = SimpleNamespace(
        list_providers=lambda: [
            SimpleNamespace(provider_type=SimpleNamespace(value="openai"), api_base="https://configured/v1/"),
            SimpleNamespace(provider_type=SimpleNamespace(value="anthropic"), api_base="https://other"),
        ]
    )
    monkeypatch.setattr(routes, "get_app_db", lambda: app_db)

    assert routes._configured_api_base("openai", "https://default/") == "https://configured/v1"
    assert routes._configured_api_base("google", "https://default/") == "https://default"
