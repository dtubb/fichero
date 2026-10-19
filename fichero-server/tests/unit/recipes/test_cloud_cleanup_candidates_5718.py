"""The clean-up (Correct) half of `source.try.cloud-models-are-compared-for-reading-and-cleanup` (#5718, ruled
2026-10-18, option b): a frontier cloud text model (Claude, Gemini, OpenAI, OpenRouter) counts as multilingual, so it
is never refused for a language it is not listed with; it is offered only (never the rules' choice), priced first,
and only where pages may leave this Mac. The frontier list is a default the owner can change
(`recipes/seed/frontier-cloud-providers.txt`)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fichero_server.recipes import discovery
from fichero_server.recipes.assemble import Answers, Card, _refusal

ARABIC = Answers(purposes=("transcribe",), languages=frozenset({"ar"}), scripts=frozenset({"Arab"}),
                 materials=("handwriting",), cloud_allowed=True)


class _AppDb:
    def __init__(self, kinds):
        self.rows = [SimpleNamespace(id=k, provider_type=SimpleNamespace(value=k), enabled=True, api_base=None,
                                     name=k.title()) for k in kinds]

    def list_providers(self):
        return self.rows

    def list_models(self, row_id):
        return [SimpleNamespace(model_id=f"{row_id}-model", name=f"{row_id} model", enabled=True, kind="chat")]


@pytest.fixture
def providers(monkeypatch):
    def use(*kinds):
        monkeypatch.setattr("fichero_server.db.app.get_app_db", lambda: _AppDb(kinds))
        return {c.pin["cloud"]: c for c in discovery._cloud_text_cards() if "model" in c.pin and c.runs_here}

    return use


@pytest.mark.parametrize("kind", ["anthropic", "google", "openai", "openrouter"])
def test_a_frontier_cloud_model_may_correct_in_any_language(providers, kind):
    card = providers(kind)[kind]
    assert "correct" in card.jobs and card.multilingual
    assert _refusal("correct", card, ARABIC, "handwriting") is None


def test_it_is_offered_only_and_named_as_leaving_the_mac(providers):
    card = providers("openai")["openai"]
    assert card.offered_only is True and card.runs_on == "cloud:openai" and "leave this Mac" in card.offered_because


def test_a_model_that_is_not_frontier_still_does_not_rewrite_a_language_it_does_not_list(providers):
    card = providers("ollama")["ollama"] if "ollama" in providers("ollama") else None
    stranger = Card(id="x", pin={"hf": "x/y"}, jobs=frozenset({"correct"}), scripts=None, languages=None,
                    material=frozenset())
    assert not stranger.multilingual
    assert _refusal("correct", stranger, ARABIC, "handwriting")[0] == "no-model-for-language"
    assert card is None or not card.multilingual


def test_the_owner_can_change_the_frontier_list(providers, monkeypatch, tmp_path):
    (tmp_path / "frontier.txt").write_text("# the owner's list\nopenai\n")
    monkeypatch.setattr(discovery, "FRONTIER_PROVIDERS_FILE", tmp_path / "frontier.txt")
    discovery.frontier_providers.cache_clear()
    try:
        cards = providers("openai", "anthropic")
        assert cards["openai"].multilingual and not cards["anthropic"].multilingual
        assert "correct" not in cards["anthropic"].jobs
    finally:
        discovery.frontier_providers.cache_clear()


def test_a_cloud_cleanup_card_waits_for_permission_while_pages_stay_here(providers):
    from fichero_server.recipes.assemble import needs_permission

    card = providers("openai")["openai"]
    assert needs_permission(card, ARABIC.__class__(**{**ARABIC.__dict__, "cloud_allowed": False}))
    assert not needs_permission(card, ARABIC)
