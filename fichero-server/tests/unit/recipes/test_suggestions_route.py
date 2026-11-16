"""`wide.suggest.*`, `wide.review.on-for-a-large-cloud-reader` (#6052): the one list, from the answers and the sample, each row with its reason."""
from __future__ import annotations

import pytest

from fichero_server.recipes import suggestions

pytestmark = pytest.mark.recipe_designer

HAND = {"materials": ["handwriting"]}


def _ids(rows):
    return [r["id"] for r in rows]


def test_faded_on_three_of_five_gives_the_clarity_row_with_its_why_and_where_it_came_from():
    sample = {"condition.faded": {"value": True, "agree": "3 of 5", "why": "from 3 of 5 sample pages"}}
    (row,) = suggestions.build(HAND, 100, sample, None)
    assert row["id"] == "condition.faded" and "clarity" in row["what"] and "from 3 of 5 sample pages" in row["why"]
    assert row["from"] == "condition: faded" and row["applied"] is False and row["change"]


def test_a_ticked_condition_is_applied_and_no_answer_gives_no_row():
    (row,) = suggestions.build({**HAND, "condition": ["tight-binding"]}, 10, None, None)
    assert row["applied"] is True and "crop" in row["what"]
    assert suggestions.build({}, 0, {}, {}) == []


def test_a_script_with_readers_but_none_installed_names_them_and_offers_training():
    rows = suggestions.build({**HAND, "scripts": ["Cans"]}, 10, None, {"Cans": {"found": ["A reader"], "installed": []}})
    assert "A reader" in rows[0]["what"] and "none is installed" in rows[0]["what"] and "train" in rows[0]["why"]
    assert not suggestions.build({**HAND, "scripts": ["Latn"]}, 10, None, {"Latn": {"found": ["K"], "installed": ["K"]}})


def test_a_script_with_no_reader_says_so_and_names_the_nearest():
    (row,) = suggestions.build({**HAND, "scripts": ["Cans"]}, 10, None, {"Cans": {"found": [], "installed": [], "nearest": ["Near one"]}})
    assert "No reader found" in row["what"] and "Near one" in row["what"]


def test_damaged_handwriting_suggests_a_compare_and_never_sets_review_itself():
    rows = suggestions.build({**HAND, "condition": ["water-damage"]}, 10, None, None)
    assert "try.compare-with-review" in _ids(rows)
    assert next(r for r in rows if r["id"] == "try.compare-with-review")["applied"] is False


def test_a_large_reader_suggests_review_on_with_a_reason():
    rows = suggestions.build({**HAND, "how": {"places": ["cloud"], "matters": "quality"}}, 10, None, None)
    review = next(r for r in rows if r["id"] == "review.on-for-large-cloud-reader")
    assert review["why"] and review["change"]


def test_the_route_serves_the_list_from_an_empty_project(client, monkeypatch):
    from fichero_server.recipes import prepare_suggest

    monkeypatch.setattr(prepare_suggest, "suggest", lambda db: {})
    assert client.get("/api/recipes/suggestions").json() == {"items": []}
