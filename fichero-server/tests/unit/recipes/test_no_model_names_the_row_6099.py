"""`ai.cloud.no-model-names-the-missing-row` (#6099): a key is set for a provider that has no row in Settings > AI > Providers; the
"no model" line says so and names the place."""
from __future__ import annotations

from types import SimpleNamespace

from fichero_server import llm
from fichero_server.db import app as app_module
from fichero_server.recipes import start


def _app_with_rows(monkeypatch, *types):
    rows = [SimpleNamespace(provider_type=SimpleNamespace(value=t)) for t in types]
    monkeypatch.setattr(app_module, "get_app_db", lambda: SimpleNamespace(list_providers=lambda: rows))


def test_a_keyed_provider_with_no_row_is_named(monkeypatch):
    _app_with_rows(monkeypatch)
    monkeypatch.setattr(llm, "get_api_key", lambda provider: "sk-x" if provider == "openai" else None)
    assert start.keyed_provider_without_row() == ["OpenAI"]


def test_a_provider_that_has_its_row_is_not_named(monkeypatch):
    _app_with_rows(monkeypatch, "openai")
    monkeypatch.setattr(llm, "get_api_key", lambda provider: "sk-x" if provider == "openai" else None)
    assert start.keyed_provider_without_row() == []


def test_the_no_model_line_says_add_the_row(monkeypatch):
    from tests.unit.recipes.test_start_plan import READ, _recipe

    monkeypatch.setattr(start, "keyed_provider_without_row", lambda: ["OpenAI"])
    plan = start.plan_start(_recipe({**READ, "model": None, "gap": "no model fits"}), stays_local=False)
    why = " ".join(s["why"] for s in plan["skipped"])
    assert "a key is set for OpenAI but Settings > AI > Providers has no row for it; add the row" in why, plan["skipped"]
