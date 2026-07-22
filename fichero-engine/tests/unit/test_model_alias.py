"""Tests for $small / $medium / $large model alias resolution (#810/#1308)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from fichero.llm import resolve_model_alias, resolve_model_alias_for_capability


class TestResolveModelAlias:
    def test_passthrough_when_not_an_alias(self):
        assert resolve_model_alias("anthropic", "claude-sonnet-4-6") == (
            "anthropic",
            "claude-sonnet-4-6",
        )

    def test_passthrough_handles_empty(self):
        assert resolve_model_alias("", "") == ("", "")

    def test_passthrough_ignores_dollar_in_model(self):
        # Only the provider field is checked for aliases.
        assert resolve_model_alias("openai", "$small") == ("openai", "$small")

    def test_resolves_small_alias(self):
        with patch("fichero.db.app.get_app_db") as mock_db:
            mock_db.return_value.get_setting.side_effect = lambda k: {
                "default_small_provider": "apple",
                "default_small_model": "apple-intelligence",
            }.get(k)
            assert resolve_model_alias("$small", "ignored") == (
                "apple",
                "apple-intelligence",
            )

    def test_resolves_large_alias(self):
        with patch("fichero.db.app.get_app_db") as mock_db:
            mock_db.return_value.get_setting.side_effect = lambda k: {
                "default_large_provider": "anthropic",
                "default_large_model": "claude-sonnet-4-6",
            }.get(k)
            assert resolve_model_alias("$large", "") == (
                "anthropic",
                "claude-sonnet-4-6",
            )

    def test_resolves_medium_alias(self):
        with patch("fichero.db.app.get_app_db") as mock_db:
            mock_db.return_value.get_setting.side_effect = lambda k: {
                "default_medium_provider": "openrouter",
                "default_medium_model": "openai/gpt-4o-mini",
            }.get(k)
            assert resolve_model_alias("$medium", "") == (
                "openrouter",
                "openai/gpt-4o-mini",
            )

    def test_unset_small_raises_actionable_error(self):
        with patch("fichero.db.app.get_app_db") as mock_db:
            mock_db.return_value.get_setting.return_value = None
            with pytest.raises(ValueError, match="Default small model"):
                resolve_model_alias("$small", "")

    def test_unset_large_raises_actionable_error(self):
        with patch("fichero.db.app.get_app_db") as mock_db:
            mock_db.return_value.get_setting.return_value = None
            with pytest.raises(ValueError, match="Default large model"):
                resolve_model_alias("$large", "")

    def test_unset_medium_raises_actionable_error(self):
        with patch("fichero.db.app.get_app_db") as mock_db:
            mock_db.return_value.get_setting.return_value = None
            with pytest.raises(ValueError, match="Default medium model"):
                resolve_model_alias("$medium", "")

    def test_partial_setting_raises(self):
        # Provider set but model missing — still an error.
        with patch("fichero.db.app.get_app_db") as mock_db:
            mock_db.return_value.get_setting.side_effect = lambda k: (
                "anthropic" if k == "default_large_provider" else None
            )
            with pytest.raises(ValueError, match="Default large model"):
                resolve_model_alias("$large", "")

    def test_env_override_wins_for_large(self, monkeypatch):
        monkeypatch.setenv("FICHERO_LARGE_PROVIDER", "openai")
        monkeypatch.setenv("FICHERO_LARGE_MODEL", "mlx-local")
        assert resolve_model_alias("$large", "") == ("openai", "mlx-local")

    def test_env_override_wins_for_medium(self, monkeypatch):
        monkeypatch.setenv("FICHERO_MEDIUM_PROVIDER", "openrouter")
        monkeypatch.setenv("FICHERO_MEDIUM_MODEL", "openai/gpt-4o-mini")
        assert resolve_model_alias("$medium", "") == (
            "openrouter",
            "openai/gpt-4o-mini",
        )

    def test_capability_wrapper_accepts_two_argument_test_resolver(self, monkeypatch):
        monkeypatch.setattr(
            "fichero.llm.resolve_model_alias",
            lambda provider, model: ("fake", "fake-model"),
        )

        assert resolve_model_alias_for_capability(
            "$small",
            "",
            required_capability="text",
        ) == ("fake", "fake-model")
