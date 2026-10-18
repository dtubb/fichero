"""`source.recipe.check-names-every-fault` (#5364, R6 exit): the check of a hand-edited recipe names each fault in it,
one sentence each, and one fault never hides another or stops the check with an error.

WHY: a recipe is a file people edit by hand and pass on. A check that stopped at the first fault, or raised on a step
written as a bare word, sent the person back for one fault at a time, or said nothing they could fix.
"""
from __future__ import annotations

from pathlib import Path

import fichero_server.recipes as recipes_pkg
from fichero_server.recipes.recipe import check_recipe, load_recipe

FLAGSHIP = Path(recipes_pkg.__file__).parent / "seed" / "spanish-hands"


def _hand_edited() -> dict:
    r = load_recipe(FLAGSHIP)
    steps = r["steps"]
    steps[1]["layer"] = "graph"  # find-lines is a lines job
    steps[2]["id"] = "lines"  # the same id twice
    steps[3]["model"] = {"hf": "some/model"}  # not pinned
    steps[3]["when"] = {"moon_phase": "full"}
    steps[4]["runs_on"] = "the-basement"
    steps[5]["job"] = "guess-the-weather"
    steps[6]["settings"] = {"api_key": "sk-..."}
    steps.append("read-it-again")  # a step written as a bare word
    steps.append({"job": "export"})  # a step with no id
    r["overrides"] = [{"step": "nowhere", "scope": "project", "card": "x"},
                      {"step": "read", "scope": "galaxy", "card": "x"}]
    return r


def test_a_hand_edited_recipe_has_each_fault_named():
    found = check_recipe(_hand_edited())
    said = "\n".join(found)
    for fault in ("says layer 'graph'", "another step already has this id", "its model is not named",
                  "moon_phase", "runs_on 'the-basement'", "no job 'guess-the-weather'", "steps.6.settings.api_key",
                  "step 11: is not a step", "step 12 (?): has no id",
                  "override 1: names step 'nowhere', which this recipe does not have",
                  "override 2: scope 'galaxy' is not project or folder"):
        assert fault in said, f"{fault!r} not named in:\n{said}"


def test_steps_that_are_not_a_list_are_named_not_raised():
    r = load_recipe(FLAGSHIP)
    r["steps"] = {"read": "kraken"}
    assert "recipe.yaml: steps is not a list of steps" in check_recipe(r)
