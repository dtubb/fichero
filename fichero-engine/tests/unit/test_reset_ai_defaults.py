"""Regression tests for #933 — Reset AI Defaults must repopulate with
Apple Intelligence baseline (not leave fields blank) AND must NOT
touch the providers / models tables.

Pre-fix: reset_ai_defaults() just deleted all default_* keys. The
user was left with empty fields; the next Catalogue run failed with
the same first-run blocker that #932 fixed for fresh launches,
regressing on every Reset click.

Post-fix: reset_ai_defaults() deletes the bag AND immediately
re-seeds Apple Intelligence factory defaults across the AI tier
keys the resolver consumes. Providers and Models tables untouched.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from fichero.db.app import AppDatabase
from fichero.api.main import _ensure_default_ai_defaults, _repair_known_bad_ai_defaults
from fichero.models import Provider, Model
from fichero.llm.providers import ProviderType


@pytest.fixture
def app_db(tmp_path: Path) -> AppDatabase:
    return AppDatabase(tmp_path / "reset_test.duckdb")


class TestResetAIDefaults:
    def test_reset_repopulates_with_apple_baseline(self, app_db):
        # Simulate prior state — user has custom defaults
        app_db.set_setting("default_text_provider", "openai")
        app_db.set_setting("default_text_model", "gpt-4o")
        app_db.set_setting("default_small_provider", "anthropic")
        app_db.set_setting("default_small_model", "claude-haiku")

        app_db.reset_ai_defaults()

        defaults = app_db.get_ai_defaults()
        assert defaults["default_text_provider"] == "apple"
        assert defaults["default_text_model"] == "apple-intelligence"
        assert defaults["default_small_provider"] == "apple"
        assert defaults["default_small_model"] == "apple-intelligence"
        assert defaults["default_medium_provider"] == "openrouter"
        assert defaults["default_medium_model"] == "openai/gpt-4o-mini"
        assert defaults["default_vision_provider"] == "apple"
        assert defaults["default_vision_model"] == "apple-vision"
        for tier in ("small", "medium", "large"):
            assert defaults[f"default_vision_{tier}_provider"] == "apple"
            assert defaults[f"default_vision_{tier}_model"] == "apple-vision"
        assert defaults["default_audio_provider"] == "apple"
        assert defaults["default_audio_model"] == "apple-speech"

    def test_reset_populates_all_tiers_text_small_large(self, app_db):
        """The LLM tiers the resolver actually consumes today (text,
        small, medium, large) need defaults so workflow placeholders
        resolve. $medium is OpenRouter cloud; the rest stay Apple.
        """
        app_db.reset_ai_defaults()
        defaults = app_db.get_ai_defaults()
        for tier in ("text", "small", "large"):
            assert defaults.get(f"default_{tier}_provider") == "apple", (
                f"Tier {tier} should be Apple Intelligence after reset"
            )
            assert defaults.get(f"default_{tier}_model") == "apple-intelligence"
        assert defaults["default_medium_provider"] == "openrouter"
        assert defaults["default_medium_model"] == "openai/gpt-4o-mini"

    def test_reset_populates_all_vision_tiers(self, app_db):
        """Vision aliases need settings defaults so #2200 preflight can resolve them."""
        app_db.reset_ai_defaults()
        defaults = app_db.get_ai_defaults()
        for tier in ("small", "medium", "large"):
            assert defaults.get(f"default_vision_{tier}_provider") == "apple"
            assert defaults.get(f"default_vision_{tier}_model") == "apple-vision"

    def test_bootstrap_populates_all_vision_tiers_without_overwriting(self, app_db):
        app_db.set_setting("default_vision_large_provider", "openai")
        app_db.set_setting("default_vision_large_model", "gpt-4o")

        _ensure_default_ai_defaults(app_db, "ignored-provider-id")

        defaults = app_db.get_ai_defaults()
        assert defaults["default_vision_small_provider"] == "apple"
        assert defaults["default_vision_small_model"] == "apple-vision"
        assert defaults["default_vision_medium_provider"] == "apple"
        assert defaults["default_vision_medium_model"] == "apple-vision"
        assert defaults["default_vision_large_provider"] == "openai"
        assert defaults["default_vision_large_model"] == "gpt-4o"

    def test_repair_known_bad_large_default_rewrites_openrouter_free(self, app_db):
        app_db.set_setting("default_large_provider", "openrouter")
        app_db.set_setting("default_large_model", "openrouter/free")

        _repair_known_bad_ai_defaults(app_db)

        defaults = app_db.get_ai_defaults()
        assert defaults["default_large_provider"] == "apple"
        assert defaults["default_large_model"] == "apple-intelligence"

    def test_reset_does_not_touch_providers(self, app_db):
        """The #933 scope guarantee: Reset Defaults must leave the
        Providers / Models tables alone. A user with a configured
        OpenAI provider + API key shouldn't lose it on Reset.
        """
        # Seed a user-added provider
        custom = Provider(
            provider_type=ProviderType.openai,
            name="My OpenAI",
        )
        custom = app_db.save_provider(custom)
        # And a model attached to it
        custom_model = Model(
            id=str(uuid.uuid4()),
            provider_id=custom.id,
            name="gpt-4o",
            model_id="gpt-4o",
            capabilities=["text"],
        )
        app_db.save_model(custom_model)

        app_db.reset_ai_defaults()

        # Provider still exists
        providers = app_db.list_providers()
        provider_names = {p.name for p in providers}
        assert "My OpenAI" in provider_names

        # Model still exists
        models = app_db.list_models(custom.id)
        model_ids = {m.model_id for m in models}
        assert "gpt-4o" in model_ids

    def test_reset_clears_stale_per_field_overrides(self, app_db):
        """Reset is also delete-first: stale fields the user had
        configured (e.g. an older default_video_provider) should be
        gone, replaced with nothing (no factory default for video).
        """
        # User had video defaults at some point
        app_db.set_setting("default_video_provider", "some-old-provider")
        app_db.set_setting("default_video_model", "some-old-model")

        app_db.reset_ai_defaults()

        defaults = app_db.get_ai_defaults()
        # Video isn't in the factory baseline → cleared, no value
        assert "default_video_provider" not in defaults
        assert "default_video_model" not in defaults

    def test_reset_clears_primary_language_override(self, app_db):
        app_db.set_setting("default_primary_language", "Spanish")

        app_db.reset_ai_defaults()

        defaults = app_db.get_ai_defaults()
        assert "default_primary_language" not in defaults
