"""`source.recipe.conditions-fixed-list` (#4950): a step's `when` and `offered_when` use only a fixed list of conditions
(spreads detected, a confidence threshold, a corrected-line count); anything else is refused when the recipe is checked.

WHY: a recipe is data, not code; a condition Fichero cannot evaluate would be silently true or false.
"""
from __future__ import annotations

import pytest

from fichero_server.recipes.recipe import CONDITIONS, check_recipe

LINES = {"id": "lines", "job": "find-lines", "model": {"kraken": "blla", "kraken_version": "bundled"}}


def _recipe(**conditions):
    return {"fichero_recipe": 1, "id": "t/conditions", "version": "0.1.0", "title": "t",
            "steps": [LINES, {"id": "split", "job": "split-pages", **conditions}]}


def test_the_list_is_the_three_ruled_conditions():
    assert CONDITIONS == {"spreads_detected", "confidence_below", "corrected_lines_at_least"}


@pytest.mark.parametrize("key", ["when", "offered_when"])
def test_a_condition_off_the_list_is_refused_by_name(key):
    problems = check_recipe(_recipe(**{key: {"moon_is_full": True}}))
    assert any(f"{key} 'moon_is_full' is not one of the allowed conditions" in p for p in problems), problems


@pytest.mark.parametrize("key", ["when", "offered_when"])
def test_the_listed_conditions_pass(key):
    problems = check_recipe(_recipe(**{key: {"spreads_detected": True, "confidence_below": 0.8,
                                             "corrected_lines_at_least": 2000}}))
    assert not any("allowed conditions" in p for p in problems), problems
