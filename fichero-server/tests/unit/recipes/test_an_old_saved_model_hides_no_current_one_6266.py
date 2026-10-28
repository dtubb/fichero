"""WHY (`source.find.current-models-offered-beside-an-old-saved-one`, #6266): a claude-3-5-sonnet saved long ago under Settings › Anthropic
covered the whole sonnet family, so the current Sonnet was missing from every step's model list and a pick of it was
refused. The current model of a family is offered beside an older saved one; the saved one stays listed; a saved model
as new as the current one still covers its family (no second card for it)."""
from __future__ import annotations

from fichero_server.recipes import discovery


def _models(app_db, *saved):
    from fichero_server.models import Model, Provider, ProviderType

    row = app_db.save_provider(Provider(name="Anthropic", provider_type=ProviderType("anthropic")))
    for model_id in saved:
        app_db.save_model(Model(provider_id=row.id, name=model_id, model_id=model_id))
    return [c.pin["model"] for c in discovery.remote_reader_cards() if c.pin["cloud"] == "anthropic"]


def _current_sonnet():
    return next(m for m in discovery.frontier_catalog_models("anthropic") if "sonnet" in m)


def test_an_old_saved_sonnet_leaves_the_current_one_offered(app_db):
    models = _models(app_db, "claude-3-5-sonnet-latest")
    assert "claude-3-5-sonnet-latest" in models
    assert _current_sonnet() in models


def test_a_saved_current_sonnet_is_listed_once(app_db):
    models = _models(app_db, _current_sonnet())
    assert len([m for m in models if "sonnet" in m]) == 1


def test_an_older_sonnet_still_served_leaves_the_current_one_offered(app_db):
    """Not only a retired one (#6259): claude-sonnet-4-5 is still served, and claude-sonnet-4-6 is offered beside it."""
    models = _models(app_db, "claude-sonnet-4-5")
    assert "claude-sonnet-4-5" in models and _current_sonnet() in models
