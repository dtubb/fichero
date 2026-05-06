"""Tests for $small / $large model alias resolution (#810)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from fichero.llm import resolve_model_alias


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
        with patch("fichero.app_db.get_app_db") as mock_db:
            mock_db.return_value.get_setting.side_effect = lambda k: {
                "default_small_provider": "apple",
                "default_small_model": "apple-intelligence",
            }.get(k)
            assert resolve_model_alias("$small", "ignored") == (
                "apple",
                "apple-intelligence",
            )

    def test_resolves_large_alias(self):
        with patch("fichero.app_db.get_app_db") as mock_db:
            mock_db.return_value.get_setting.side_effect = lambda k: {
                "default_large_provider": "anthropic",
                "default_large_model": "claude-sonnet-4-6",
            }.get(k)
            assert resolve_model_alias("$large", "") == (
                "anthropic",
                "claude-sonnet-4-6",
            )

    def test_unset_small_raises_actionable_error(self):
        with patch("fichero.app_db.get_app_db") as mock_db:
            mock_db.return_value.get_setting.return_value = None
            with pytest.raises(ValueError, match="Default small model"):
                resolve_model_alias("$small", "")

    def test_unset_large_raises_actionable_error(self):
        with patch("fichero.app_db.get_app_db") as mock_db:
            mock_db.return_value.get_setting.return_value = None
            with pytest.raises(ValueError, match="Default large model"):
                resolve_model_alias("$large", "")

    def test_partial_setting_raises(self):
        # Provider set but model missing — still an error.
        with patch("fichero.app_db.get_app_db") as mock_db:
            mock_db.return_value.get_setting.side_effect = lambda k: (
                "anthropic" if k == "default_large_provider" else None
            )
            with pytest.raises(ValueError, match="Default large model"):
                resolve_model_alias("$large", "")
