"""`source.recipe.page-reader-is-an-add-on` (#6250 ruling 3, #6259): a page reader chosen for a recipe that has no Read the
whole page step ADDS that step (tied to the lines), never "override N: names step 'read-a-page', which this recipe does not
have". Any other kept choice for a step the recipe no longer has is dropped with a note in the plan, never a refusal."""
from __future__ import annotations

import copy

from fichero_server.recipes.recipe import check_recipe, fit_overrides

from tests.unit.recipes.test_installed_model_first_to_spec import mac  # noqa: F401  (fixture)
from tests.unit.recipes.test_recipe_execution_to_spec import pages  # noqa: F401  (fixture)

KRAKEN = {"zenodo": "10.5281/zenodo.13788177"}
PAGE_READER = {"cloud": "anthropic", "model": "claude-sonnet-5-5"}
LINES_ONLY = {"fichero_recipe": 1, "id": "t", "version": 1, "title": "t", "purposes": ["transcribe"], "steps": [
    {"id": "find-lines", "job": "find-lines", "model": {"kraken": "blla", "kraken_version": "bundled"}},
    {"id": "read-a-line", "job": "read-a-line", "model": KRAKEN},
]}


def _override(step, model):
    return {"step": step, "scope": "project", "folder_id": None, "model": model, "card": f"x:{step}",
            "runs_on": "cloud:anthropic", "because": "chosen by you", "at": "2026-10-28T00:00:00Z"}


def test_a_page_reader_on_a_lines_only_recipe_adds_the_page_step_tied_to_the_lines():
    recipe = {**copy.deepcopy(LINES_ONLY), "overrides": [_override("read-a-page", PAGE_READER)]}
    notes = fit_overrides(recipe)
    jobs = [s["job"] for s in recipe["steps"]]
    assert jobs == ["find-lines", "read-a-line", "read-a-page", "tie-text-to-lines"]
    assert recipe["steps"][2]["model"] == PAGE_READER, "the chosen reader is the page step's model"
    assert check_recipe(recipe) == []
    assert any("Read the whole page" in n for n in notes)


def test_a_choice_for_a_step_the_person_removed_is_dropped_with_a_note():
    recipe = {**copy.deepcopy(LINES_ONLY), "overrides": [_override("translate-transliterate-normalise", PAGE_READER)]}
    notes = fit_overrides(recipe)
    assert not recipe.get("overrides") and check_recipe(recipe) == []
    assert any("translate-transliterate-normalise" in n for n in notes)


def test_start_plans_the_page_step_for_a_saved_lines_only_recipe_with_a_page_reader(client, db, mac, pages):  # noqa: F811
    from fichero_server.api.routes.system import recipes as routes
    from fichero_server.recipes.project import write_project_setup

    answers = {"purposes": ["transcribe"], "languages": ["es"], "scripts": ["Latn"], "materials": ["handwriting"],
               "cloud_allowed": True}
    write_project_setup(routes._library(db), answers,
                        {**copy.deepcopy(LINES_ONLY), "overrides": [_override("read-a-page", PAGE_READER)]})
    plan = client.get("/api/recipes/project/start")
    assert plan.status_code == 200, plan.text
    body = plan.json()
    assert not [r for r in body["refusals"] if "which this recipe does not have" in r], body["refusals"]
    assert any("read-a-page" in r["steps"] for r in body["runs"]), body["runs"]
    assert any("Read the whole page" in n for n in body["notes"])


def _page_reader(runs_on="this-mac"):
    from fichero_server.recipes.assemble import Card

    return Card(id="mlx:vision/x/Qwen3-VL@1", pin={"hf": "x/Qwen3-VL", "revision": "abc123"}, jobs=frozenset({"read-a-page"}), scripts=None,
                languages=None, material=frozenset(), runs_on=runs_on, note="Qwen3-VL", open_licence=True)


def test_use_this_with_a_page_reader_on_a_lines_only_recipe_adds_the_page_step():
    from fichero_server.recipes.bakeoff import use_this

    card = _page_reader()
    table = {"id": "b1", "step": "read-a-page", "lines": 40, "rows": [
        {"card": card.id, "measured": True, "cer": 0.08, "policy": "strict", "pages_read": 3, "pages_total": 3, "rank": 1}]}
    out = use_this(copy.deepcopy(LINES_ONLY), table, card, scope="project", folder_id=None, now="2026-10-28T00:00:00Z")
    page = next(s for s in out["steps"] if s["job"] == "read-a-page")
    assert page["model"] == card.pin and check_recipe(out) == []


def test_use_candidate_with_a_local_page_reader_on_the_line_step_adds_the_page_step():
    from fichero_server.recipes.start import use_candidate

    out = use_candidate(copy.deepcopy(LINES_ONLY), "read-a-line", _page_reader(), now="2026-10-28T00:00:00Z")
    assert [s["job"] for s in out["steps"]] == ["find-lines", "read-a-line", "read-a-page", "tie-text-to-lines"]
    assert next(s for s in out["steps"] if s["job"] == "read-a-line")["model"] == KRAKEN, "the line reader stays"
    assert [o["step"] for o in out["overrides"]] == ["read-a-page"] and check_recipe(out) == []
