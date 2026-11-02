"""`designer.material.condition-feeds-the-defaults` (#6052): the condition answers choose preparation steps and Review, each saying which answer."""
from __future__ import annotations

import pytest

from fichero_server.recipes import defaults

pytestmark = pytest.mark.recipe_designer

HAND = {"materials": ["handwriting"], "how": {"places": ["this-mac"], "matters": "privacy"}}


def test_faded_and_tight_binding_choose_preparation_steps_and_say_which_answer():
    got = defaults.resolve({**HAND, "condition": ["faded", "tight-binding"]})
    assert got["prepare"] == ["clarity", "crop"]
    assert "faded" in defaults.says_why(got, "prepare") or "tight binding" in defaults.says_why(got, "prepare")


def test_damage_turns_review_on_and_leaves_out_the_damaged_areas():
    got = defaults.resolve({**HAND, "condition": ["water-damage"]})
    assert got["review"] == "on" and "leave-out" in got["steps"] and "water damage" in defaults.says_why(got, "review")


def test_no_condition_changes_nothing_and_an_unknown_one_is_ignored():
    plain = defaults.resolve(HAND)
    assert plain["prepare"] == [] and plain["review"] == "unsure-lines"
    assert defaults.resolve({**HAND, "condition": ["mold"]}) == plain
