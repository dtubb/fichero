"""A model its provider no longer serves can never be run by Fichero's choice (#6096, `source.recipe.cloud-text-pick`): its card says
it cannot run (the menu shows why), use-candidate refuses it, no rule picks it, the vision catalogue never offers it, and a pick
saved before it was retired is skipped at Check with words instead of failing every page. Fake rows only: no key, no call."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from fichero_server.recipes import discovery, start

RETIRED, LIVE = "gemini-2.5-flash", "gemini-3-flash-preview"


@pytest.fixture
def google_row(monkeypatch):
    model = lambda mid: SimpleNamespace(model_id=mid, enabled=True, name=mid, capabilities=["vision", "text"],  # noqa: E731
                                        embedding=False, kind="chat")
    row = SimpleNamespace(id="row1", name="Google", enabled=True, api_base=None, provider_type=SimpleNamespace(value="google"))
    app = SimpleNamespace(list_providers=lambda: [row], list_models=lambda _rid: [model(RETIRED), model(LIVE)])
    monkeypatch.setattr("fichero_server.db.app.get_app_db", lambda: app)
    monkeypatch.setattr(discovery, "_is_embedder", lambda m: False)


@pytest.mark.parametrize("make", ["_cloud_text_cards", "remote_reader_cards"])
def test_a_retired_models_card_says_it_cannot_run(google_row, make):
    cards = {c.pin["model"]: c for c in getattr(discovery, make)() if c.pin.get("cloud") == "google"}
    assert cards[RETIRED].runs_here is False and cards[RETIRED].cannot_run_because.startswith("retired:")
    assert not cards[LIVE].cannot_run_because


def test_use_candidate_refuses_a_retired_model(google_row):
    card = next(c for c in discovery._cloud_text_cards() if c.pin.get("model") == RETIRED)
    recipe = {"steps": [{"id": "translate", "job": "translate-transliterate-normalise"}]}
    with pytest.raises(ValueError, match="cannot run: retired"):
        start.use_candidate(recipe, "translate", card, now="2026-10-24T20:00:00")


def test_a_saved_pick_of_a_retired_model_is_skipped_at_check_with_why():
    recipe = {"steps": [{"id": "translate", "job": "translate-transliterate-normalise", "runs_on": "cloud:google",
                         "model": {"cloud": "google", "model": RETIRED}}]}
    plan = start.plan_start(recipe, stays_local=False)
    (skipped,) = [s for s in plan["skipped"] if s["step"] == "translate"]
    assert "retired" in skipped["why"] and "choose another model" in skipped["why"]
    assert not any(r.get("step") == "translate" or "translate" in (r.get("steps") or []) for r in plan["runs"])


def test_the_vision_catalogue_never_offers_a_retired_model(monkeypatch):
    monkeypatch.setattr("fichero_server.llm.model_types.list_models_for_provider",
                        lambda p: [{"model_id": RETIRED, "supports_vision": True}])  # the newest flash on its list
    assert discovery.frontier_catalog_models("gemini") == []
