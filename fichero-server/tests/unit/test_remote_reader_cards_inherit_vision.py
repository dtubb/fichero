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
    assert (tier("cloud:google"), tier("cloud:openrouter"), tier("this-mac")) == ("cloud", "cloud", "general")


def test_claude_and_gemini_through_openrouter_are_the_cloud_tier():
    from fichero_server.recipes.discovery import reader_tier

    card = NS(pin={"cloud": "openrouter", "model": "anthropic/claude-sonnet-4.5"}, runs_on="cloud:openrouter")
    assert reader_tier(card, "read-a-line") == "cloud"


def test_a_reader_for_another_script_or_language_is_not_listed():
    from fichero_server.api.routes.system.recipes import for_the_project
    from fichero_server.recipes.assemble import Answers, Card

    def card(cid, scripts, languages):
        return Card(id=cid, pin={"kraken": cid}, jobs=frozenset({"read-a-line"}), scripts=scripts, languages=languages,
                    material=frozenset())

    a = Answers(purposes=("transcribe",), languages=frozenset({"es"}), scripts=frozenset({"Latn"}), materials=("print",))
    cards = [card("es", frozenset({"Latn"}), frozenset({"es"})), card("zh", frozenset({"Hans"}), frozenset({"zh"})),
             card("de", frozenset({"Latn"}), frozenset({"de"})), card("own-zh", frozenset({"Hans"}), None)]
    kept = [c.id for c in for_the_project(cards, "read-a-line", a, "print", "own-zh")]
    assert kept == ["es", "own-zh"]  # Chinese and German readers left out; the step's own model stays


def test_only_rows_worth_using_are_listed_five_a_tier():
    from fichero_server.api.routes.system.recipes import worth_listing

    def row(i, tier="specialist", **kw):
        return NS(id=str(i), tier=tier, chosen=kw.get("chosen", False), cer_measured_here=kw.get("cer"),
                  availability=kw.get("availability", "download"), needs_permission=kw.get("perm", False),
                  refused=kw.get("refused"), availability_words=kw.get("words", ""))

    rows = [row(i) for i in range(8)] + [row("refused", refused="not enough memory"), row("chosen", chosen=True),
                                         row("licence", tier="general", refused="its licence needs accepting"),
                                         row("perm", tier="cloud", perm=True)]
    ids = [r.id for r in worth_listing(rows)]
    assert ids == ["0", "1", "2", "3", "4", "chosen", "licence", "perm"]


def test_a_key_with_no_saved_model_offers_the_newest_frontier_models(monkeypatch):
    from fichero_server.recipes.discovery import frontier_catalog_models

    listed = [{"model_id": m, "supports_vision": True} for m in
              ("claude-4-opus-20250514", "claude-opus-4-7", "gemini-3-flash", "gemini-3.1-flash-image-preview")]
    monkeypatch.setattr("fichero_server.llm.model_types.list_models_for_provider", lambda p: listed)
    assert frontier_catalog_models("x") == ["claude-opus-4-7", "gemini-3-flash"]  # a date is no version; no image model
