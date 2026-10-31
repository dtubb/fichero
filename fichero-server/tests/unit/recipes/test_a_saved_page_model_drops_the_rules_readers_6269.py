"""A page-read model the person saves replaces the readers the rules added by kind of material (#6269): claude-sonnet-4-6
was saved on read-a-page and the run read the handwriting pages with Apple Vision (`ai.where.no-silent-reader-fallback`)."""
from __future__ import annotations

from fichero_server.recipes.bakeoff import drop_readers_of_changed_models
from tests.unit.recipes.test_bakeoff_readers import _set_up, folder, readers  # noqa: F401  (fixtures)

CHOSEN = {"cloud": "anthropic", "model": "claude-sonnet-4-6"}
READERS = [{"material": "handwriting", "model": {"builtin": "apple-vision"}}]


def _recipe(model, job="read-a-page"):
    return {"steps": [{"id": "read", "job": job, "model": model, "readers": [dict(r) for r in READERS]}]}


def test_a_changed_model_drops_the_steps_readers():
    sent = drop_readers_of_changed_models(_recipe({"hf": "org/auto"}), _recipe(CHOSEN))
    assert not sent["steps"][0].get("readers")


def test_the_same_model_keeps_the_readers():
    sent = drop_readers_of_changed_models(_recipe(CHOSEN), _recipe(CHOSEN))
    assert sent["steps"][0]["readers"] == READERS


def test_a_new_step_keeps_its_readers_and_other_jobs_are_left_alone():
    assert drop_readers_of_changed_models(None, _recipe(CHOSEN))["steps"][0]["readers"] == READERS
    other = drop_readers_of_changed_models(_recipe({"hf": "a"}, "correct"), _recipe(CHOSEN, "correct"))
    assert other["steps"][0]["readers"] == READERS


def test_a_re_assembled_recipe_keeps_its_new_readers():
    fresh = _recipe(CHOSEN)
    fresh["steps"][0]["readers"] = [{"material": "printed", "model": {"hf": "org/print"}}]
    sent = drop_readers_of_changed_models(_recipe({"hf": "org/auto"}), fresh)
    assert sent["steps"][0]["readers"] == [{"material": "printed", "model": {"hf": "org/print"}}]


def test_through_the_save_a_stale_echo_loses_its_readers_and_a_fresh_proposal_keeps_them(client, db, folder, readers, with_material):  # noqa: F811
    recipe = _set_up(client)
    step = next(s for s in recipe["steps"] if s["job"] in ("read-a-line", "read-a-page"))
    answers = client.get("/api/recipes/project").json()["answers"]

    def put(model, readers):
        steps = [{**s, "model": model, "readers": readers} if s["id"] == step["id"] else s for s in recipe["steps"]]
        assert client.put("/api/recipes/project", json={"answers": answers, "recipe": {**recipe, "steps": steps}}).status_code == 200
        saved = client.get("/api/recipes/project").json()["recipe"]["steps"]
        return next(s for s in saved if s["id"] == step["id"])

    put({"hf": "org/auto"}, READERS)
    assert put(CHOSEN, READERS).get("readers") in (None, [])  # the person's pick; the old readers were echoed
    fresh = [{"material": "printed", "model": {"hf": "org/print"}}]
    assert put({"hf": "org/other"}, fresh)["readers"] == fresh  # a re-assembled proposal
