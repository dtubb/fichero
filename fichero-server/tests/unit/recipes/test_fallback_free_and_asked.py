"""A step whose model this Mac cannot run falls back to another place only when that place is free, and only when
the person presses it (#5592), tested to the spec (docs/contributor_manual/specs/ai/where-models-run.md:
`ai.where.fallback-free-and-asked`).

WHY: the maintainer's ruling 2026-10-08: a fallback to another place happens only when that place costs nothing,
and only after asking the person, never silently; a paid place is never the fallback. Through the public routes the
app calls (`PUT /api/recipes/project`, `GET /api/recipes/project/start`, `POST /api/recipes/project/start/use-instead`,
`POST /api/recipes/project/start`); this Mac's model store and memory (a 16 GB Mac) and the price list are stubbed:
nothing is downloaded, loaded or fetched.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from fichero_server.models import Model, Provider, ProviderType
from tests.unit.recipes.test_installed_model_first_to_spec import LINES, READ, mac  # noqa: F401
from tests.unit.recipes.test_recipe_execution_to_spec import _recipe, _save, engine, pages  # noqa: F401

EIGHT = "mlx-community/Qwen3-VL-8B-Instruct-4bit"
CORRECT = {"id": "correct", "job": "correct", "model": {"hf": EIGHT, "revision": "main"}, "runs_on": "this-mac"}


@pytest.fixture
def place(app_db, monkeypatch):
    """One provider row off this Mac that lists the 8B by its repository id; `place.price` is what the price list
    says it costs per token (None: the list does not price it)."""
    saved = app_db.save_provider(Provider(name="Free Endpoint", provider_type=ProviderType.openrouter))
    app_db.save_model(Model(provider_id=saved.id, name="Qwen3-VL 8B", model_id=EIGHT))
    row = SimpleNamespace(id=saved.id, price=0.0)

    def entry(model, provider=""):
        if model != EIGHT or row.price is None:
            return None
        return {"input_cost_per_token": row.price, "output_cost_per_token": row.price}

    monkeypatch.setattr("fichero_server.llm.usage._registry_entry", entry)
    return row


def _elsewhere(plan: dict) -> dict:
    [entry] = plan["elsewhere"]
    assert entry["steps"] == ["correct"] and entry["runtime"] == "mlx"
    return entry


def test_ai_where_fallback_free_and_asked_offers_a_free_place_and_applies_it_only_on_the_press(
        client, db, pages, mac, place):
    """ai.where.fallback-free-and-asked: "a step whose model this Mac cannot run is offered the same model at a
    free place … in the plan's `instead`, never applied without the person's press." Start stays refused until
    the press; the press sets the step to that place, said "chosen by you"; Start then has nothing to refuse."""
    _save(client, _recipe(None, LINES, READ, CORRECT), cloud_allowed=True)
    plan = client.get("/api/recipes/project/start").json()

    entry = _elsewhere(plan)
    [offer] = entry["instead"]
    assert offer["provider"] == place.id and offer["provider_name"] == "Free Endpoint"
    assert offer["free"] is True and offer["place"] == "provider" and offer["model"] == EIGHT
    [refusal] = [r for r in plan["refusals"] if "cannot run on this Mac" in r]
    assert "Or run it free at Free Endpoint instead, if you choose to" in refusal
    # Offered, not applied: the step still asks this Mac's server for the 8B, and Start is refused.
    run = next(w for w in plan["workflows"] if w["steps"] == ["correct"])
    assert run["provider_override"] == "omlx"
    started = client.post("/api/recipes/project/start", json={})
    assert started.status_code == 422, started.text

    used = client.post("/api/recipes/project/start/use-instead",
                       json={"model": entry["model"], "provider": place.id})
    assert used.status_code == 200, used.text
    step = next(s for s in used.json()["recipe"]["steps"] if s["id"] == "correct")
    assert step["model"] == {"cloud": "openrouter", "model": EIGHT} and step["runs_on"] == "cloud:openrouter"
    [override] = used.json()["recipe"]["overrides"]
    assert override["step"] == "correct" and override["free"] is True and override["provider"] == place.id
    assert override["because"].startswith("chosen by you") and "free" in override["because"]

    plan = client.get("/api/recipes/project/start").json()
    assert plan["refusals"] == [] and plan["elsewhere"] == []
    run = next(w for w in plan["workflows"] if w["steps"] == ["correct"])
    assert (run["provider_override"], run["model_override"]) == ("openrouter", EIGHT)


@pytest.mark.parametrize("price", [2e-6, None], ids=["paid", "unpriced"])
def test_a_paid_or_unpriced_place_is_never_offered(client, db, pages, mac, place, price):
    """A place the price list does not say is free (it costs money, or its price is not known) is not offered; the
    refusal says why, and the use-instead press for it is refused."""
    place.price = price
    _save(client, _recipe(None, LINES, READ, CORRECT), cloud_allowed=True)
    plan = client.get("/api/recipes/project/start").json()

    entry = _elsewhere(plan)
    assert entry["instead"] == []
    [refusal] = [r for r in plan["refusals"] if "cannot run on this Mac" in r]
    assert "Free Endpoint runs it, but not free" in refusal and "only when that place is free" in refusal
    r = client.post("/api/recipes/project/start/use-instead", json={"model": entry["model"], "provider": place.id})
    assert r.status_code == 422 and "not one offered free" in r.json()["detail"]


def test_a_local_only_project_is_offered_no_place_off_this_mac(client, db, pages, mac, place):
    """A project that keeps its pages on this Mac is offered nothing elsewhere, a free place included."""
    _save(client, _recipe(None, LINES, READ, CORRECT), cloud_allowed=False)
    plan = client.get("/api/recipes/project/start").json()

    entry = _elsewhere(plan)
    assert entry["instead"] == []
    [refusal] = [r for r in plan["refusals"] if "cannot run on this Mac" in r]
    assert "keeps its pages on this Mac, so no other place is offered" in refusal
    r = client.post("/api/recipes/project/start/use-instead", json={"model": entry["model"], "provider": place.id})
    assert r.status_code == 422


@pytest.mark.parametrize("cloud_allowed", [True, False], ids=["pages-may-leave", "local-only"])
def test_the_persons_own_machine_is_a_free_place(client, db, pages, mac, app_db, monkeypatch, cloud_allowed):
    """ai.where.fallback-free-and-asked: the person's own machine (a model server at an address off this Mac) costs
    nothing, so it is offered like a $0 place, whatever the price list says (here it prices nothing); still never
    applied without the press, and never in a project that keeps its pages on this Mac."""
    monkeypatch.setattr("fichero_server.llm.usage._registry_entry", lambda model, provider="": None)
    row = app_db.save_provider(Provider(name="Studio Mac", provider_type=ProviderType.ollama,
                                        api_base="http://10.0.0.5:11434"))
    app_db.save_model(Model(provider_id=row.id, name="Qwen3-VL 8B", model_id=EIGHT))
    _save(client, _recipe(None, LINES, READ, CORRECT), cloud_allowed=cloud_allowed)
    plan = client.get("/api/recipes/project/start").json()

    entry = _elsewhere(plan)
    run = next(w for w in plan["workflows"] if w["steps"] == ["correct"])
    assert run["provider_override"] == "omlx", "offered, never applied without the press"
    if not cloud_allowed:
        assert entry["instead"] == []
        return
    [offer] = entry["instead"]
    assert offer["provider"] == row.id and offer["place"] == "own_machine" and offer["free"] is True
    used = client.post("/api/recipes/project/start/use-instead", json={"model": entry["model"], "provider": row.id})
    assert used.status_code == 200, used.text
    step = next(s for s in used.json()["recipe"]["steps"] if s["id"] == "correct")
    assert step["model"] == {"cloud": "ollama", "model": EIGHT}


def test_use_instead_takes_a_card_or_a_place_never_both(client, db, pages, mac, place):
    _save(client, _recipe(None, LINES, READ, CORRECT), cloud_allowed=True)
    r = client.post("/api/recipes/project/start/use-instead",
                    json={"model": "x", "card": "mlx:hf/x@unpinned", "provider": place.id})
    assert r.status_code == 422 and "either" in r.json()["detail"]
