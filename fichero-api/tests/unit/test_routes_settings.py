"""Tests for settings routes.

Settings store app-wide AI model defaults (vision, text, audio, video, embeddings).
SwiftUI reads these on launch to populate the model selection dropdowns.
"""

import pytest
from unittest.mock import MagicMock, patch


class TestGetAIDefaults:
    def test_returns_all_fields(self, client):
        r = client.get("/api/settings/ai-defaults")
        assert r.status_code == 200
        data = r.json()
        expected_keys = {
            "vision_provider", "vision_model",
            "text_provider", "text_model",
            "audio_provider", "audio_model",
            "video_provider", "video_model",
            "temperature", "max_tokens",
            "prompt_prefix", "embeddings_model",
        }
        assert expected_keys.issubset(data.keys())

    def test_defaults_are_empty_strings(self, client):
        r = client.get("/api/settings/ai-defaults")
        assert r.status_code == 200
        data = r.json()
        # Fresh db should have all empty strings
        assert all(v == "" for v in data.values())


class TestSetAIDefaults:
    def test_set_model_fields(self, client):
        payload = {
            "vision_provider": "openai",
            "vision_model": "gpt-4o",
            "text_provider": "anthropic",
            "text_model": "claude-3-5-sonnet",
            "audio_provider": "",
            "audio_model": "",
            "video_provider": "",
            "video_model": "",
            "temperature": "0.7",
            "max_tokens": "1000",
            "prompt_prefix": "",
            "embeddings_model": "",
        }
        r = client.put("/api/settings/ai-defaults", json=payload)
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_set_then_get_roundtrip(self, client):
        payload = {
            "vision_provider": "openai",
            "vision_model": "gpt-4o",
            "text_provider": "",
            "text_model": "",
            "audio_provider": "",
            "audio_model": "",
            "video_provider": "",
            "video_model": "",
            "temperature": "",
            "max_tokens": "",
            "prompt_prefix": "",
            "embeddings_model": "text-embedding-3-small",
        }
        client.put("/api/settings/ai-defaults", json=payload)
        r = client.get("/api/settings/ai-defaults")
        assert r.status_code == 200
        data = r.json()
        assert data["vision_provider"] == "openai"
        assert data["vision_model"] == "gpt-4o"
        assert data["embeddings_model"] == "text-embedding-3-small"

    def test_empty_values_clear_setting(self, client):
        # Set then clear
        payload_set = {
            "vision_provider": "openai", "vision_model": "gpt-4o",
            "text_provider": "", "text_model": "",
            "audio_provider": "", "audio_model": "",
            "video_provider": "", "video_model": "",
            "temperature": "", "max_tokens": "",
            "prompt_prefix": "", "embeddings_model": "",
        }
        client.put("/api/settings/ai-defaults", json=payload_set)
        payload_clear = {k: "" for k in payload_set}
        client.put("/api/settings/ai-defaults", json=payload_clear)
        r = client.get("/api/settings/ai-defaults")
        assert r.json()["vision_provider"] == ""
        assert r.json()["vision_model"] == ""


class TestResetAIDefaults:
    def test_reset_clears_all_settings(self, client):
        payload = {
            "vision_provider": "openai", "vision_model": "gpt-4o",
            "text_provider": "anthropic", "text_model": "claude-3",
            "audio_provider": "", "audio_model": "",
            "video_provider": "", "video_model": "",
            "temperature": "0.5", "max_tokens": "",
            "prompt_prefix": "", "embeddings_model": "",
        }
        client.put("/api/settings/ai-defaults", json=payload)
        r = client.delete("/api/settings/ai-defaults")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
        r2 = client.get("/api/settings/ai-defaults")
        data = r2.json()
        assert all(v == "" for v in data.values())
