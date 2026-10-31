"""Prepare Images on its own: two owner reports, reproduced (nothing is fixed here).

Report A: "Prepare Images doesn't seem to do anything."
Report B: "I can't run just that one step as image preparation: it won't let me start."

What the tests below found (each says so; a test marked xfail(strict=True) is a real bug, named, and turns the
suite red the day it is fixed, so the marker is removed with the fix):

* B. The engine plans a Prepare-only recipe correctly (one `prepare` card, nothing skipped, nothing refused). But the
  app offers Start only when `refusals` is empty AND `workflows` is not (`RecipeSetupStore.canStart`,
  `FocusedCommandButtons+Recipe.swift` disabledReason). `workflows` lists only the cards of kind `workflow`; Prepare
  Images' own card is kind `prepare`, so with the stage ticked alone the person sees "Nothing to run yet".
* A. The stage's Try runs the plan's cards on a copy of the sample pages, and skips any card that is not a `workflow`
  ("not tried on samples yet", samples._run_one). Prepare's card is kind `prepare`: the Try ends "done" having prepared
  nothing, and shows no picture.
* A (run side). A real Start does prepare: a rendition is written and the next step reads it. That part is right.
"""
# ruff: noqa: F811  (fixtures imported from the execution tests are re-taken as arguments: pytest's idiom)
from __future__ import annotations

import pytest

from fichero_server.models import Rendition
from fichero_server.recipes.start import plan_start
from tests.unit.recipes.test_prepare_images_step import (  # noqa: F401  (fixtures and helpers)
    _faded_and_clear,
    _page,
    _save,
)
from tests.unit.recipes.test_recipe_execution_to_spec import (  # noqa: F401  (fixtures)
    _finished,
    _start,
    engine,
    pages,
)
from tests.unit.recipes.test_stage_try_words_5687 import _run, _set_up  # noqa: F401

#: Prepare Images' stage ticked and nothing else: what Set Up saves, as the answers the app sends.
ONLY_PREPARE = {"purposes": [], "jobs": ["prepare-the-image"]}
VARIANTS = {
    "plain": {},
    "photographs": {"photographs": True},
    "faded pages": {"faded_pages": True},
}


def _assemble_alone(client, **extra) -> tuple[dict, dict]:
    answers = {"languages": ["es"], "scripts": ["Latn"], "materials": ["handwriting"], "cloud_allowed": False,
               **ONLY_PREPARE, **extra}
    r = client.post("/api/recipes/assemble", json=answers)
    assert r.status_code == 200, r.text
    return answers, r.json()


@pytest.mark.parametrize("variant", VARIANTS)
def test_ticking_the_stage_alone_puts_the_step_in_the_recipe(client, db, tmp_path, variant):
    """Not the cause: the assembler keeps a ticked Prepare Images with no reading step beside it, with or without the
    photographs and faded-pages answers (those two only ADD it when a reading or line step is ticked, and a stage that
    is ticked is in)."""
    from tests.unit.recipes.test_stage_try_words_5687 import _pages

    _pages(db, tmp_path, 2)
    _, recipe = _assemble_alone(client, **VARIANTS[variant])
    assert [s["job"] for s in recipe["steps"]] == ["prepare-the-image"], recipe["steps"]
    assert recipe["by_hand"] == [] and recipe["problems"] == []


@pytest.mark.parametrize("variant", VARIANTS)
def test_the_plan_of_the_stage_alone_has_a_run_and_no_refusal(client, db, tmp_path, variant):
    """Not the cause: `plan_start(..., only=<the stage's steps>)` runs the step, skips nothing and refuses nothing
    (the same plan the stage's Try and the project's Start build)."""
    from tests.unit.recipes.test_stage_try_words_5687 import _pages

    _pages(db, tmp_path, 2)
    _, recipe = _assemble_alone(client, **VARIANTS[variant])
    plan = plan_start(recipe, stays_local=True, only={s["id"] for s in recipe["steps"]}, db=db)
    assert [(r["card"], r["job"]) for r in plan["runs"]] == [("prepare", "prepare-the-image")]
    assert plan["skipped"] == [] and plan["refusals"] == []


@pytest.mark.parametrize("variant", VARIANTS)
@pytest.mark.xfail(strict=True, reason=(
    "BUG B: a plan that runs only Prepare Images has runs=[prepare] but workflows=[] (`workflows` is the cards of kind "
    "workflow only, start.py plan_start's return). The app starts only on `refusals.isEmpty && !workflows.isEmpty` "
    "(RecipeSetupStore.canStart; FocusedCommandButtons+Recipe.swift disabledReason: 'Nothing to run yet'), so Start "
    "stays off. Should see: Start offered whenever the plan has something to run."))
def test_the_app_can_start_a_plan_that_only_prepares_images(client, db, tmp_path, variant):
    from tests.unit.recipes.test_stage_try_words_5687 import _pages

    _pages(db, tmp_path, 2)
    answers, recipe = _assemble_alone(client, **VARIANTS[variant])
    assert client.put("/api/recipes/project", json={"answers": answers, "recipe": recipe}).status_code == 200
    plan = client.get("/api/recipes/project/start").json()
    assert plan["runs"] and plan["refusals"] == []
    app_can_start = not plan["refusals"] and bool(plan["workflows"])  # the app's own rule, as written in Swift
    assert app_can_start, f"runs={[r['card'] for r in plan['runs']]} workflows={plan['workflows']}"


def test_the_engine_itself_starts_the_stage_alone(client, db, tmp_path):
    """Not the cause: the route Start posts to accepts the Prepare-only recipe (200, a run queued); only the app's
    button never sends it."""
    from tests.unit.recipes.test_stage_try_words_5687 import _pages

    _pages(db, tmp_path, 2)
    answers, recipe = _assemble_alone(client)
    assert client.put("/api/recipes/project", json={"answers": answers, "recipe": recipe}).status_code == 200
    started = client.post("/api/recipes/project/start")
    assert started.status_code == 200, started.text
    assert started.json()["started"]["job_id"]


@pytest.mark.xfail(strict=True, reason=(
    "BUG A: the stage's Try skips every card that is not a `workflow` (samples._run_one: 'not tried on samples yet'); "
    "Prepare Images' card is `prepare`. The Try ends 'done', made nothing, and says nothing. Should see: each sample "
    "page's prepared picture (before and after), or, for a clear page, 'looked at, left as it was'."))
def test_a_prepare_images_try_prepares_the_sample_pages(client, db, pages, tmp_path, jobs_run_by_the_test):
    _faded_and_clear(db, pages, tmp_path)
    _set_up(client, ["prepare-the-image"])
    started = client.post("/api/recipes/stages/prepare-images/try", json={})
    assert started.status_code == 200, started.text
    _run(db, started.json())
    result = client.get("/api/recipes/stages/prepare-images/try").json()
    assert result["state"] == "done", result
    ran = result.get("ran") or []
    assert ran and all(r["state"] != "skipped" for r in ran), f"the Try ran nothing: {ran}"
    assert result.get("per_page") or result.get("names"), "the Try made no picture to show"


def test_start_writes_a_prepared_rendition_and_the_next_step_reads_it(client, db, pages, tmp_path, engine):
    """The run side is right: Start with Prepare Images ahead of lines and reading writes a `prepared` rendition for
    the faded page (the original kept), and the current image every later step reads (#6296) is that rendition."""
    from pathlib import Path

    from fichero_server.media.current_image import RENDITION, current_page_image
    from tests.unit.recipes.test_prepare_images_step import LINES, PREP, READ
    from tests.unit.recipes.test_recipe_execution_to_spec import _recipe

    faded, clear = _faded_and_clear(db, pages, tmp_path)
    _save(client, _recipe(tmp_path, PREP, LINES, READ))
    run = _finished(client, _start(client))
    assert run["state"] == "done", run
    made = [r for r in db.query(Rendition, document_id=faded.id) if r.role == "prepared"]
    assert len(made) == 1
    seen = current_page_image(db, db.get(type(faded), faded.id), library_root=Path(db.path).parent)
    assert seen is not None and seen.path.endswith(Path(made[0].path).name) and seen.kind == RENDITION, seen
    assert sorted(engine.read) == sorted([Path(made[0].path).name, "clear.png"])  # reading read the prepared copy


def test_start_with_only_prepare_images_runs_and_does_not_fail(client, db, pages, tmp_path, engine):
    """Prepare alone, started (the engine route, not the app's button): the run finishes done and the faded page has
    its prepared rendition; a clear page is left as it was."""
    from tests.unit.recipes.test_prepare_images_step import PREP
    from tests.unit.recipes.test_recipe_execution_to_spec import _recipe

    faded, clear = _faded_and_clear(db, pages, tmp_path)
    _save(client, _recipe(tmp_path, PREP))
    run = _finished(client, _start(client))
    assert run["state"] == "done", run
    assert len([r for r in db.query(Rendition, document_id=faded.id) if r.role == "prepared"]) == 1
    assert [r for r in db.query(Rendition, document_id=clear.id) if r.role == "prepared"] == []
