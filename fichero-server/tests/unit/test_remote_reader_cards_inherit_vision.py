"""A cloud model saved with no capabilities (an OpenRouter or Google model added with a key) inherits its provider's
vision support, so the finder and the step menus offer it as a reader (`recipes.discovery.remote_reader_cards`)."""
from types import SimpleNamespace as NS

from fichero_server.recipes import discovery


def test_uncapped_models_inherit_provider_vision(monkeypatch):
    rows = [NS(id="r1", name="OpenRouter", enabled=True, api_base=None, provider_type=NS(value="openrouter")),
            NS(id="r2", name="Google", enabled=True, api_base=None, provider_type=NS(value="google"))]
    models = {"r1": [NS(model_id="qwen/qwen3-vl", name=None, enabled=True, capabilities=[]),
                     NS(model_id="text-only", name=None, enabled=True, capabilities=["text"])],
              "r2": [NS(model_id="gemini-2.5-pro", name=None, enabled=True, capabilities=None)]}
    db = NS(list_providers=lambda: rows, list_models=lambda rid: models[rid])
    monkeypatch.setattr("fichero_server.db.app.get_app_db", lambda: db)
    ids = {c.pin["model"] for c in discovery.remote_reader_cards() if c.pin["cloud"] != "anthropic"}
    assert ids == {"qwen/qwen3-vl", "gemini-2.5-pro"}


def test_frontier_cloud_readers_sort_first():
    from fichero_server.api.routes.system.recipes import _offered_order

    cards = [NS(runs_on="this-mac"), NS(runs_on="cloud:openrouter"), NS(runs_on="cloud:google")]
    assert [c.runs_on for c in sorted(cards, key=_offered_order)] == ["cloud:google", "cloud:openrouter", "this-mac"]  # cloud first, by provider


def test_every_cloud_model_is_the_top_tier():
    from fichero_server.recipes.discovery import reader_tier

    tier = lambda runs_on: reader_tier(NS(pin={"cloud": "x", "model": "m"}, runs_on=runs_on), "read-a-line")  # noqa: E731
    assert (tier("cloud:google"), tier("cloud:openrouter"), tier("this-mac")) == ("frontier", "frontier", "general")


def test_claude_and_gemini_through_openrouter_are_frontier():
    from fichero_server.recipes.discovery import reader_tier

    card = NS(pin={"cloud": "openrouter", "model": "anthropic/claude-sonnet-4.5"}, runs_on="cloud:openrouter")
    assert reader_tier(card, "read-a-line") == "frontier"
