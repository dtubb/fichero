"""Focused unit tests for llm_models helpers."""

from __future__ import annotations

import pytest

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fichero.llm_models import estimate_cost, get_model_cost


def test_get_model_cost_returns_known_cloud_model_cost() -> None:
    fake_litellm = SimpleNamespace(
        model_cost={
            "openai/gpt-5": {
                "input_cost_per_token": 0.00000125,
                "output_cost_per_token": 0.00001,
            }
        }
    )

    with patch("fichero.llm_models._get_litellm", return_value=fake_litellm):
        assert get_model_cost("openai/gpt-5") == {
            "input_cost_per_token": 0.00000125,
            "output_cost_per_token": 0.00001,
        }


def test_get_model_cost_returns_none_for_unknown_model() -> None:
    fake_litellm = SimpleNamespace(model_cost={})

    with patch("fichero.llm_models._get_litellm", return_value=fake_litellm):
        assert get_model_cost("openai/does-not-exist") is None


def test_estimate_cost_returns_known_cloud_model_cost() -> None:
    fake_litellm = MagicMock()
    fake_litellm.cost_per_token.return_value = (0.0125, 0.03)

    with patch("fichero.llm_models._get_litellm", return_value=fake_litellm):
        assert estimate_cost(
            "openai/gpt-5", input_tokens=1000, output_tokens=300
        ) == pytest.approx(0.0425)


def test_estimate_cost_returns_zero_for_unknown_model_without_crashing() -> None:
    fake_litellm = MagicMock()
    fake_litellm.cost_per_token.side_effect = KeyError("unknown model")

    with patch("fichero.llm_models._get_litellm", return_value=fake_litellm):
        assert (
            estimate_cost("openai/does-not-exist", input_tokens=1000, output_tokens=300)
            == 0.0
        )
