"""`designer.defaults.table`, `designer.defaults.caps-proposed-from-the-table` (#6052)."""
from __future__ import annotations

import itertools

import pytest

from fichero_server.recipes import condition, defaults, prepare_operations
from fichero_server.recipes.assemble import MATERIALS, STEP_ORDER
from fichero_server.recipes.how import MATTERS

pytestmark = pytest.mark.recipe_designer


def test_every_row_loads_with_a_why_and_names_only_steps_and_operations_that_exist():
    t = defaults.table()
    assert t["base"][-1].get("when") is None  # the fallback is last
    for row in t["base"][:-1]:
        assert row["why"] and row["cap"]
    for row in [*t["base"], *t["adds"].values()]:
        assert set(row.get("steps", [])) <= set(STEP_ORDER) | {"find-lines"}
        assert set(row.get("prepare", [])) <= set(prepare_operations.IDS)
    assert set(t["adds"]) == set(condition.IDS)


def test_every_answer_combination_the_questions_can_produce_hits_one_base_row():
    for material, where, matters, large in itertools.product(MATERIALS, ("this-mac", "cloud", "cluster"), (*MATTERS, None), (True, False)):
        facts = {"material": [material], "where": where, "matters": matters, "large": large, "condition": []}
        assert defaults.base_row(facts)["id"]  # a row or the fallback, never an error


@pytest.mark.parametrize("answers, pages, row, cap", [
    ({"materials": ["print"], "how": {"places": ["this-mac"]}}, 10, "clean-print-this-mac", "none"),
    ({"materials": ["handwriting"], "how": {"places": ["this-mac"], "matters": "privacy"}}, 10, "handwriting-privacy", "none"),
    ({"materials": ["handwriting"], "how": {"places": ["cloud"], "matters": "quality"}}, 10, "cloud-quality", "estimate-rounded"),
    ({"materials": ["handwriting"], "how": {"places": ["cloud"], "matters": "cost"}}, 9000, "cloud-cost-large-archive", "first-pages-estimate"),
    ({"materials": ["handwriting"], "how": {"places": ["cluster"], "matters": "cost"}}, 10, "cluster-cost", "hf-cap-estimate"),
    ({"materials": ["handwriting"]}, 10, "fallback", "none")])
def test_the_chosen_defaults_match_the_table_row(answers, pages, row, cap):
    got = defaults.resolve(answers, pages)
    assert got["rows"][0] == row and got["cap"] == cap


def test_a_cap_is_proposed_from_the_row_and_writes_nothing():
    answers = {"materials": ["handwriting"], "how": {"places": ["cloud"], "matters": "quality"}}
    before = repr(answers)
    assert defaults.cap_proposal(defaults.resolve(answers), 3.2) == {"kind": "estimate-rounded", "usd": 4.0}
    assert defaults.cap_proposal(defaults.resolve({"materials": ["print"]}), 3.2)["usd"] is None
    assert repr(answers) == before
