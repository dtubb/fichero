"""`source.onboard.start-works-in-first-run` (#5477), the engine half: first run plans and starts through the same
routes as Set Up from a project -- the plan has no refusals once the answers are saved over material, Start records the
first yes in that project, and the plan then shows it."""
from __future__ import annotations

from tests.unit.recipes.test_bakeoff_readers import _set_up, folder  # noqa: F401
from tests.unit.recipes.test_recipe_execution_to_spec import engine, pages  # noqa: F401


def test_start_enables_on_a_saved_setup_and_records_the_first_yes(client, db, folder, pages, engine):  # noqa: F811
    _set_up(client)
    plan = client.get("/api/recipes/project/start")
    assert plan.status_code == 200, plan.text
    assert plan.json()["refusals"] == [] and plan.json()["started"] is None

    pressed = client.post("/api/recipes/project/start", json={})
    assert pressed.status_code == 200, pressed.text
    assert pressed.json()["started"] is not None
    assert client.get("/api/recipes/project/start").json()["started"] is not None


def test_start_with_no_saved_setup_is_refused_in_words(client, db, folder):  # noqa: F811
    plan = client.get("/api/recipes/project/start").json()
    assert plan["refusals"] and "recipe" in plan["refusals"][0]
    assert client.post("/api/recipes/project/start", json={}).status_code == 422
