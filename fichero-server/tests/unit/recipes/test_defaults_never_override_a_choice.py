"""`designer.defaults.person-wins` (#6052): a choice stays when an answer changes; the changed default is offered beside it."""
from __future__ import annotations

import pytest

from fichero_server.recipes import defaults

pytestmark = pytest.mark.recipe_designer


def test_a_choice_survives_a_changed_answer_and_the_new_suggestion_is_offered():
    mine = {"model_kind": "a large vision-language model"}
    before = defaults.with_choices(defaults.resolve({"materials": ["print"], "how": {"places": ["this-mac"]}}), mine)
    after = defaults.with_choices(defaults.resolve({"materials": ["handwriting"], "how": {"places": ["cluster"], "matters": "cost"}}), mine)
    for got in (before, after):
        assert got["effective"]["model_kind"] == "a large vision-language model"
    assert after["offers"][0]["suggested"] == "the readers you chose, run there" and "keep" in after["offers"][0]["words"]


def test_no_choice_takes_the_table_and_a_matching_choice_offers_nothing():
    base = defaults.resolve({"materials": ["print"], "how": {"places": ["this-mac"]}})
    assert defaults.with_choices(base, None)["effective"]["steps"] == base["steps"]
    assert defaults.with_choices(base, {"review": base["review"]})["offers"] == []
