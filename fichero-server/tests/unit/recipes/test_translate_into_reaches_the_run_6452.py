"""#6452 Translate does not work: the language chosen under Translate is a translation run, and the run is Translate's stage."""
from __future__ import annotations

from fichero_server.recipes import live_stages
from fichero_server.recipes.answers import normalise, with_translation
from fichero_server.recipes.stages import stage_of
from fichero_server.recipes.start import plan_start
from tests.unit.recipes.test_installed_model_first_to_spec import mac  # noqa: F401  (fixture)
from tests.unit.recipes.test_recipe_execution_to_spec import pages  # noqa: F401  (fixture)
from tests.unit.recipes.test_set_up_steps_5660 import _level_runs, _normalise


def test_the_language_answer_is_a_level_asked_once():
    assert with_translation({"translate_into": "en"}) == ["translation:en"]
    assert with_translation({"normalise_how_far": ["as_written"], "translate_into": "en"}) == ["as_written", "translation:en"]
    assert with_translation({"normalise_how_far": ["translation:en"], "translate_into": "en"}) == ["translation:en"]
    assert with_translation({"normalise_how_far": ["expanded"], "translate_into": ""}) == ["expanded"]


def test_the_stored_answers_carry_it():
    out = normalise({"job_answers": {"translate_into": "english"}}, strict=True)
    assert out["job_answers"]["normalise_how_far"] == ["translation:en"]


def test_the_plan_translates_into_the_language_answered(mac):  # noqa: F811
    plan = plan_start(_normalise(None), stays_local=True, job_answers={"translate_into": "en"})
    [run] = _level_runs(plan)
    analyze = run["tool_config"]["analyze"]
    assert analyze["reading_kind"] == "translation" and "English" in analyze["prompt"]
    assert run["translation"] == "en"


def test_a_translating_run_is_translates_stage_and_a_level_run_is_normalises():
    assert stage_of("translate-transliterate-normalise").id == "normalise"
    assert stage_of("translate-transliterate-normalise", translation=True).id == "translate"
    status = {"steps": [{"steps": ["normalise"], "job": "translate-transliterate-normalise", "translation": "en",
                         "state": "done"}], "skipped": []}
    assert [row["stage"] for row in live_stages.stage_counts(status)] == ["translate"]


def _listing(recipe, answers):
    from fichero_server.recipes.stages import listing

    return {s["id"]: s for s in listing(recipe, answers)}


STEP = {"id": "n", "job": "translate-transliterate-normalise", "settings": {}}


def test_translate_is_on_in_the_recipe_when_the_step_translates_and_normalise_when_it_writes_a_level():
    recipe = {"steps": [STEP]}
    both = _listing(recipe, {"job_answers": {"normalise_how_far": ["expanded"], "translate_into": "en"}})
    assert both["translate"]["on"] and both["normalise"]["on"]
    only_levels = _listing(recipe, {"job_answers": {"normalise_how_far": ["expanded"]}})
    assert only_levels["normalise"]["on"] and not only_levels["translate"]["on"]
    only_translation = _listing(recipe, {"job_answers": {"translate_into": "en"}})
    assert only_translation["translate"]["on"] and not only_translation["normalise"]["on"]
    assert not _listing({"steps": []}, None)["translate"]["on"]


def test_run_this_step_plans_that_steps_job_only_6456(mac):  # noqa: F811
    recipe = _normalise(["expanded"])
    whole = plan_start(recipe, stays_local=True)
    alone = plan_start(recipe, stays_local=True, only={"normalise"})
    assert {j for r in whole["runs"] for j in r["steps"]} > {"normalise"} and len(whole["runs"]) > len(alone["runs"])
    assert [s for r in alone["runs"] for s in r["steps"]] == ["normalise"]


def test_run_this_step_on_each_step_of_a_recipe_plans_that_step_alone_6456(mac):  # noqa: F811
    recipe = _normalise(["expanded"])
    for step in recipe["steps"]:
        alone = plan_start(recipe, stays_local=True, only={step["id"]})
        ran = [s for r in alone["runs"] for s in r["steps"]]
        assert ran and set(ran) == {step["id"]}, (step["id"], ran)
        assert len(alone["runs"]) <= 1, (step["id"], alone["runs"])
