"""The recipe format and the check before anything runs (`source.recipe.folder-format`,
`source.recipe.data-not-code`, `source.recipe.never-holds-keys`, `source.recipe.names-models-and-where`).

Why it matters: a recipe arrives from other people (the catalogue, a colleague). If the check stops
refusing code, credentials, unpinned models or unknown conditions, importing a recipe can run
something the person never chose, or silently use a different model than the one measured. If the
shipped flagship stops passing its own check, every new project starts broken.
"""
from __future__ import annotations

import copy
from pathlib import Path

import fichero_server.recipes as recipes_pkg
from fichero_server.recipes.recipe import check_recipe, cloud_steps, load_recipe

FLAGSHIP = Path(recipes_pkg.__file__).parent / "seed" / "spanish-hands"


def _flagship():
    return load_recipe(FLAGSHIP)


def test_the_shipped_flagship_passes_its_own_check():
    assert check_recipe(_flagship(), FLAGSHIP) == []


def test_a_newer_schema_is_refused_not_guessed_at():
    r = _flagship()
    r["fichero_recipe"] = 99
    assert check_recipe(r) == ["this recipe uses schema 99; this Fichero reads up to 1. Update Fichero to use it"]


def test_code_and_keys_anywhere_are_refused_by_name():
    r = _flagship()
    r["steps"][1]["settings"] = {"command": "rm -rf ~"}
    r["defaults"]["api_key"] = "sk-..."
    found = check_recipe(r, FLAGSHIP)
    assert any("steps.1.settings.command" in p for p in found)
    assert any("defaults.api_key" in p for p in found)


def test_suits_scripts_is_writing_systems_not_code():
    assert not any("scripts" in p for p in check_recipe(_flagship(), FLAGSHIP))


def test_an_unpinned_model_and_an_unknown_condition_are_refused():
    r = _flagship()
    r["steps"][3]["model"] = {"hf": "some/model"}  # no revision
    r["steps"][3]["when"] = {"moon_phase": "full"}
    found = check_recipe(r, FLAGSHIP)
    assert any("step 4 (correct): the model" in p for p in found)
    assert any("moon_phase" in p for p in found)


def test_a_missing_prompt_file_is_named():
    r = copy.deepcopy(_flagship())
    r["steps"][3]["prompt"] = "prompts/nope.prompt.md"
    assert "step 4 (correct): its prompt file prompts/nope.prompt.md is missing" in check_recipe(r, FLAGSHIP)


def test_a_step_out_of_order_is_named():
    r = _flagship()
    r["steps"] = [s for s in r["steps"] if s["id"] != "lines"]  # nothing finds the lines now
    assert any("needs lines" in p for p in check_recipe(r, FLAGSHIP))


def test_cloud_steps_are_listed_for_the_recipe_editor():
    r = _flagship()
    assert cloud_steps(r) == []
    r["steps"][6]["runs_on"] = "cloud: anthropic"
    assert cloud_steps(r) == ["statements"]
