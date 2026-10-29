"""`ai.where.price-list-current-models` (#6259, maintainer's ruling 2026-10-28): Fichero has a price list for the current
models, from the providers' published prices, with dates; each added model prices a call. The Anthropic models setup offers
are the current ones, from the same source, and a retired model saved under a key never hides them."""
from __future__ import annotations

import pytest

from fichero_server.llm import model_types, usage

#: (provider, model as the engine records it, US$ per million input, per million output), as the price pages list them.
ROWS = [
    ("anthropic", "claude-fable-5-1", 10, 50), ("anthropic", "claude-fable-5", 10, 50),
    ("anthropic", "claude-opus-5-5", 4, 20), ("anthropic", "claude-sonnet-5-5", 2, 10),
    ("anthropic", "claude-haiku-5-5", 0.10, 0.50),
    ("google", "gemini-3.1-flash-lite", 0.25, 1.50), ("google", "gemini-3.5-flash-lite", 0.30, 2.50),
    ("google", "gemini-3-flash-preview", 0.50, 3.00), ("google", "gemini-3.1-pro-preview", 2.00, 12.00),
    ("openrouter", "anthropic/claude-sonnet-5.5", 2, 10), ("openrouter", "anthropic/claude-haiku-5.5", 0.10, 0.50),
    ("openrouter", "anthropic/claude-opus-5.5", 4, 20), ("openrouter", "anthropic/claude-fable-5.1", 10, 50),
    ("openrouter", "anthropic/claude-fable-5", 10, 50), ("openrouter", "google/gemini-3.1-flash-lite", 0.25, 1.50),
    ("openrouter", "google/gemini-3.5-flash-lite", 0.30, 2.50),
    ("openrouter", "google/gemini-3-flash-preview", 0.50, 3.00),
    ("openrouter", "google/gemini-3.1-pro-preview", 2.00, 12.00),
]


@pytest.fixture(autouse=True)
def _fresh_table(monkeypatch):
    monkeypatch.setattr(model_types, "_PRICE_TABLE", None)


@pytest.mark.parametrize("provider,model,per_m_in,per_m_out", ROWS)
def test_each_current_model_prices_a_call(provider, model, per_m_in, per_m_out):
    call = usage.price_call({"provider": provider, "model": model, "input_tokens": 1_000_000, "output_tokens": 1_000_000})
    assert call.priced and call.cost_usd == pytest.approx(per_m_in + per_m_out), (provider, model)


def test_each_added_row_names_its_source_and_the_date_fetched():
    import json
    from importlib import resources

    rows = json.loads((resources.files("fichero_server.resources") / "model_prices_local.json").read_text())
    for key, row in rows.items():
        if key.startswith("_"):
            continue
        assert row["source"].startswith("https://") and row["fetched"] == "2026-10-28", key


def test_the_anthropic_models_offered_are_the_current_ones():
    from fichero_server.api.routes.ai.provider_models import RECOMMENDED_MODELS
    from fichero_server.recipes.discovery import frontier_catalog_models

    offered = frontier_catalog_models("anthropic")
    assert {"claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"} <= set(offered), offered
    recommended = [m["model_id"] for m in RECOMMENDED_MODELS["anthropic"]]
    assert "claude-sonnet-5-5" in recommended and not [m for m in recommended if m.startswith("claude-3")]


@pytest.mark.parametrize("model", ["claude-3-5-sonnet-latest", "claude-3-5-haiku-latest"])
def test_a_retired_claude_is_said_to_be_retired(model):
    assert model_types.retired_because(model)
