"""Focused unit tests for llm_models helpers.

Since 2026-08-27 the registry is a VENDORED snapshot (resources/
model_prices.json), not the litellm package — tests stub the loaded table
via the `_PRICE_TABLE` module global (the lazy loader honors a pre-set
table).
"""

from __future__ import annotations

import pytest

from unittest.mock import patch

import fichero_server.llm.model_types as llm_models
from fichero_server.llm.model_types import estimate_cost, get_model_cost, get_model_info


def _with_table(table):
    return patch.object(llm_models, "_PRICE_TABLE", table)


def test_get_model_cost_returns_known_cloud_model_cost() -> None:
    table = {
        "openai/gpt-5": {
            "input_cost_per_token": 0.00000125,
            "output_cost_per_token": 0.00001,
        }
    }
    with _with_table(table):
        assert get_model_cost("openai/gpt-5") == {
            "input_cost_per_token": 0.00000125,
            "output_cost_per_token": 0.00001,
        }


def test_get_model_cost_resolves_unprefixed_registry_key() -> None:
    # The registry keys some models bare ("gpt-4o") — a provider-prefixed
    # lookup must still find them, as litellm's resolver did.
    table = {
        "gpt-5": {
            "input_cost_per_token": 0.00000125,
            "output_cost_per_token": 0.00001,
        }
    }
    with _with_table(table):
        assert get_model_cost("openai/gpt-5") is not None


def test_get_model_cost_returns_none_for_unknown_model() -> None:
    with _with_table({}):
        assert get_model_cost("openai/does-not-exist") is None


def test_get_model_cost_returns_none_for_incomplete_pricing_and_logs() -> None:
    table = {"openai/gpt-5": {"input_cost_per_token": 0.00000125}}
    with (
        _with_table(table),
        patch.object(llm_models.logger, "warning") as mock_warning,
    ):
        assert get_model_cost("openai/gpt-5") is None

    mock_warning.assert_called_once()


def test_estimate_cost_returns_known_cloud_model_cost() -> None:
    table = {
        "openai/gpt-5": {
            "input_cost_per_token": 0.0000125,
            "output_cost_per_token": 0.0001,
        }
    }
    with _with_table(table):
        assert estimate_cost(
            "openai/gpt-5", input_tokens=1000, output_tokens=300
        ) == pytest.approx(0.0125 + 0.03)


def test_estimate_cost_returns_none_for_missing_pricing_and_logs() -> None:
    with (
        _with_table({}),
        patch.object(llm_models.logger, "warning") as mock_warning,
    ):
        assert (
            estimate_cost("openai/does-not-exist", input_tokens=1000, output_tokens=300)
            is None
        )

    mock_warning.assert_called_once()


def test_get_model_info_raises_on_lookup_failure_and_logs() -> None:
    with (
        _with_table({}),
        patch.object(llm_models.logger, "error") as mock_error,
    ):
        with pytest.raises(RuntimeError, match="Could not load model info"):
            get_model_info("openai/gpt-5")

    mock_error.assert_called_once()


def test_real_vendored_registry_loads_and_prices_a_known_model() -> None:
    # The genuine snapshot: loads, drops litellm's sample_spec row, and
    # prices a long-stable model.
    llm_models._PRICE_TABLE = None
    try:
        table = llm_models._price_table()
        assert "sample_spec" not in table
        assert len(table) > 2000
        assert get_model_cost("gpt-4o") is not None
    finally:
        llm_models._PRICE_TABLE = None


def test_list_models_for_provider_preserves_unknown_pricing() -> None:
    table = {
        "openai/gpt-5": {
            "input_cost_per_token": None,
            "output_cost_per_token": 0.00001,
            "max_tokens": 128000,
        }
    }
    with _with_table(table):
        models = llm_models.list_models_for_provider("openai")

    assert len(models) == 1
    assert models[0]["input_cost_per_million"] is None
    assert models[0]["output_cost_per_million"] == pytest.approx(10.0)
