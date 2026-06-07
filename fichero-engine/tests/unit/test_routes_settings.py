"""Tests for settings routes.

Settings store app-wide AI model defaults (vision, text, audio, video, embeddings).
SwiftUI reads these on launch to populate the model selection dropdowns.
"""

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
            "embeddings_provider", "embeddings_model",
            "small_provider", "small_model",
            "medium_provider", "medium_model",
            "large_provider", "large_model",
            "primary_language",
            "temperature", "max_tokens",
            "prompt_prefix",
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
            "embeddings_provider": "",
            "embeddings_model": "",
            "small_provider": "apple",
            "small_model": "apple-intelligence",
            "medium_provider": "openrouter",
            "medium_model": "openai/gpt-4o-mini",
            "large_provider": "apple",
            "large_model": "apple-intelligence",
            "primary_language": "Spanish",
            "temperature": "0.7",
            "max_tokens": "1000",
            "prompt_prefix": "",
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
            "embeddings_provider": "openai",
            "embeddings_model": "text-embedding-3-small",
            "small_provider": "apple",
            "small_model": "apple-intelligence",
            "medium_provider": "openrouter",
            "medium_model": "openai/gpt-4o-mini",
            "large_provider": "apple",
            "large_model": "apple-intelligence",
            "primary_language": "English",
            "temperature": "",
            "max_tokens": "",
            "prompt_prefix": "",
        }
        client.put("/api/settings/ai-defaults", json=payload)
        r = client.get("/api/settings/ai-defaults")
        assert r.status_code == 200
        data = r.json()
        assert data["vision_provider"] == "openai"
        assert data["vision_model"] == "gpt-4o"
        assert data["embeddings_provider"] == "openai"
        assert data["embeddings_model"] == "text-embedding-3-small"
        assert data["small_provider"] == "apple"
        assert data["small_model"] == "apple-intelligence"
        assert data["medium_provider"] == "openrouter"
        assert data["medium_model"] == "openai/gpt-4o-mini"
        assert data["large_provider"] == "apple"
        assert data["large_model"] == "apple-intelligence"
        assert data["primary_language"] == "English"

    def test_empty_values_clear_setting(self, client):
        # Set then clear
        payload_set = {
            "vision_provider": "openai", "vision_model": "gpt-4o",
            "text_provider": "", "text_model": "",
            "audio_provider": "", "audio_model": "",
            "video_provider": "", "video_model": "",
            "embeddings_provider": "", "embeddings_model": "",
            "small_provider": "apple", "small_model": "apple-intelligence",
            "medium_provider": "openrouter", "medium_model": "openai/gpt-4o-mini",
            "large_provider": "apple", "large_model": "apple-intelligence",
            "primary_language": "Spanish",
            "temperature": "", "max_tokens": "",
            "prompt_prefix": "",
        }
        client.put("/api/settings/ai-defaults", json=payload_set)
        payload_clear = {k: "" for k in payload_set}
        client.put("/api/settings/ai-defaults", json=payload_clear)
        r = client.get("/api/settings/ai-defaults")
        data = r.json()
        assert data["vision_provider"] == ""
        assert data["vision_model"] == ""
        # Tier aliases are intentionally preserved when empty payloads are sent.
        assert data["small_provider"] == "apple"
        assert data["small_model"] == "apple-intelligence"
        assert data["medium_provider"] == "openrouter"
        assert data["medium_model"] == "openai/gpt-4o-mini"
        assert data["large_provider"] == "apple"
        assert data["large_model"] == "apple-intelligence"
        assert data["primary_language"] == ""


class TestResetAIDefaults:
    def test_reset_clears_all_settings(self, client):
        payload = {
            "vision_provider": "openai", "vision_model": "gpt-4o",
            "text_provider": "anthropic", "text_model": "claude-3",
            "audio_provider": "", "audio_model": "",
            "video_provider": "", "video_model": "",
            "embeddings_provider": "", "embeddings_model": "",
            "primary_language": "Spanish",
            "temperature": "0.5", "max_tokens": "",
            "prompt_prefix": "",
        }
        client.put("/api/settings/ai-defaults", json=payload)
        r = client.delete("/api/settings/ai-defaults")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
        r2 = client.get("/api/settings/ai-defaults")
        data = r2.json()
        # After reset, factory defaults are re-seeded.
        # Only fields without factory defaults remain empty.
        non_empty_fields = {k: v for k, v in data.items() if v != ""}
        assert all(
            k.endswith(("_provider", "_model"))
            for k in non_empty_fields
        ), f"Unexpected non-empty fields after reset: {non_empty_fields}"
        assert data["primary_language"] == ""
        # Most typed categories use Apple Intelligence defaults.
        for key in ("text_provider", "small_provider", "large_provider",
                    "vision_provider", "audio_provider"):
            assert data[key] == "apple", f"{key} should be 'apple' after reset"
        for key in ("text_model", "small_model", "large_model"):
            assert data[key] == "apple-intelligence", f"{key} should be 'apple-intelligence' after reset"
        assert data["medium_provider"] == "openrouter"
        assert data["medium_model"] == "openai/gpt-4o-mini"
