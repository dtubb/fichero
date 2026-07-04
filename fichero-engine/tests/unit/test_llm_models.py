"""Focused unit tests for llm_models helpers."""

from __future__ import annotations

import pytest

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import fichero.llm_models as llm_models
from fichero.llm_models import estimate_cost, get_model_cost, get_model_info


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


def test_get_model_cost_returns_none_for_incomplete_pricing_and_logs() -> None:
    fake_litellm = SimpleNamespace(
        model_cost={
            "openai/gpt-5": {
                "input_cost_per_token": 0.00000125,
            }
        }
    )

    with (
        patch("fichero.llm_models._get_litellm", return_value=fake_litellm),
        patch.object(llm_models.logger, "warning") as mock_warning,
    ):
        assert get_model_cost("openai/gpt-5") is None

    mock_warning.assert_called_once()


def test_estimate_cost_returns_known_cloud_model_cost() -> None:
    fake_litellm = MagicMock()
    fake_litellm.cost_per_token.return_value = (0.0125, 0.03)

    with patch("fichero.llm_models._get_litellm", return_value=fake_litellm):
        assert estimate_cost(
            "openai/gpt-5", input_tokens=1000, output_tokens=300
        ) == pytest.approx(0.0425)


def test_estimate_cost_returns_none_for_pricing_failure_and_logs() -> None:
    fake_litellm = MagicMock()
    fake_litellm.cost_per_token.side_effect = KeyError("unknown model")

    with (
        patch("fichero.llm_models._get_litellm", return_value=fake_litellm),
        patch.object(llm_models.logger, "exception") as mock_exception,
    ):
        assert (
            estimate_cost("openai/does-not-exist", input_tokens=1000, output_tokens=300)
            is None
        )

    mock_exception.assert_called_once()


def test_get_model_info_raises_on_lookup_failure_and_logs() -> None:
    fake_litellm = MagicMock()
    fake_litellm.get_model_info.side_effect = RuntimeError("registry unavailable")

    with (
        patch("fichero.llm_models._get_litellm", return_value=fake_litellm),
        patch.object(llm_models.logger, "exception") as mock_exception,
    ):
        with pytest.raises(RuntimeError, match="Could not load model info"):
            get_model_info("openai/gpt-5")

    mock_exception.assert_called_once()
