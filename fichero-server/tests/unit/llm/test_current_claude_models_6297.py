"""Tests for the 6297 update: current Claude models are priced (#6297)."""

from __future__ import annotations

import pytest

from fichero_server.llm.usage import price_call


class TestCurrentClaudeModels6297:
    """Test that the new Claude 5.x models are properly priced."""

    def test_claude_sonnet_5_5_prices(self):
        """claude-sonnet-5-5 prices a 1000-input/1000-output call correctly."""
        result = price_call({
            "provider": "anthropic",
            "model": "claude-sonnet-5-5",
            "input_tokens": 1000,
            "output_tokens": 1000,
        })
        assert result.priced is True
        # input: 1000 * 2e-06 = 0.002
        # output: 1000 * 1e-05 = 0.01
        # total: 0.012
        assert result.cost_usd == pytest.approx(0.012)

    def test_claude_haiku_5_5_prices(self):
        """claude-haiku-5-5 prices a 1000-input/1000-output call correctly."""
        result = price_call({
            "provider": "anthropic",
            "model": "claude-haiku-5-5",
            "input_tokens": 1000,
            "output_tokens": 1000,
        })
        assert result.priced is True
        # input: 1000 * 1e-07 = 0.0001
        # output: 1000 * 5e-07 = 0.0005
        # total: 0.0006
        assert result.cost_usd == pytest.approx(0.0006)

    def test_claude_opus_5_5_prices(self):
        """claude-opus-5-5 prices a 1000-input/1000-output call correctly."""
        result = price_call({
            "provider": "anthropic",
            "model": "claude-opus-5-5",
            "input_tokens": 1000,
            "output_tokens": 1000,
        })
        assert result.priced is True
        # input: 1000 * 4e-06 = 0.004
        # output: 1000 * 2e-05 = 0.02
        # total: 0.024
        assert result.cost_usd == pytest.approx(0.024)

    def test_claude_fable_5_1_prices(self):
        """claude-fable-5-1 prices a 1000-input/1000-output call correctly."""
        result = price_call({
            "provider": "anthropic",
            "model": "claude-fable-5-1",
            "input_tokens": 1000,
            "output_tokens": 1000,
        })
        assert result.priced is True
        # input: 1000 * 1e-05 = 0.01
        # output: 1000 * 5e-05 = 0.05
        # total: 0.06
        assert result.cost_usd == pytest.approx(0.06)

    def test_default_large_model_is_claude_sonnet_5_5(self):
        """The default large model alias resolves to claude-sonnet-5-5."""
        # Check that the Anthropic provider's default_model is claude-sonnet-5-5
        from fichero_server.llm.providers import ProviderInfo, ProviderType
        from fichero_server.llm.providers import get_provider_info
        
        anthropic_info = get_provider_info(ProviderType.anthropic)
        assert anthropic_info is not None
        assert anthropic_info.default_model == "claude-sonnet-5-5", (
            "Anthropic provider default model should be claude-sonnet-5-5"
        )
