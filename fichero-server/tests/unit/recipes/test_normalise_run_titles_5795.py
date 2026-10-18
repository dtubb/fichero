"""`source.onboard.normalise-runs-named-by-the-engine` (#5795): the Normalise step's runs are named by the engine,
one title for each reading level asked and one for a translation, in the order Start makes them.

WHY: the Set Up row worked the titles out in Swift (`RecipeSetupAnswers.runTitles`), recomputing the runs
`recipes/start.py` makes, so the row would drift when the engine's rule changed (review 99).
"""
from __future__ import annotations

import pytest

from fichero_server.recipes.answers import normalise_run_titles
from fichero_server.recipes.start import plan_start
from tests.unit.recipes.test_installed_model_first_to_spec import mac  # noqa: F401  (fixture)
from tests.unit.recipes.test_recipe_execution_to_spec import pages  # noqa: F401  (fixture)
from tests.unit.recipes.test_set_up_steps_5660 import _level_runs, _normalise


def test_each_level_and_a_translation_has_its_title_in_starts_order():
    assert normalise_run_titles(["normalised", "as-written", "translation:en"]) == [
        "As written", "Normalised spelling", "Translation into English"]
    assert normalise_run_titles(None) == ["Normalised spelling"]  # nothing asked: Start writes regularised
    assert normalise_run_titles(["sideways", "expanded"]) == ["Abbreviations expanded"]  # no run, no title


@pytest.mark.parametrize("target", [None, "normalised", ["as_written", "expanded", "regularised", "modernised"],
                                    ["expanded", "translation:en"], ["sideways", "modernised"]])
def test_the_titles_are_the_runs_start_makes(mac, target):  # noqa: F811
    assert len(normalise_run_titles(target)) == len(_level_runs(plan_start(_normalise(target), stays_local=True)))


def test_the_assembled_step_carries_its_run_titles(client, db, pages, mac):  # noqa: F811
    answers = {"purposes": ["translate-normalise"], "languages": ["es"], "scripts": ["Latn"],
               "materials": ["handwriting"], "mac_memory_gb": 32,
               "job_answers": {"normalise_how_far": ["as-written", "normalised", "translation:en"]}}
    recipe = client.post("/api/recipes/assemble", json=answers)
    assert recipe.status_code == 200, recipe.text
    steps = recipe.json()["steps"]
    [step] = [s for s in steps if s["job"] == "translate-transliterate-normalise"]
    assert step["run_titles"] == ["As written", "Normalised spelling", "Translation into English"]
    assert all(s.get("run_titles") is None for s in steps if s is not step)
