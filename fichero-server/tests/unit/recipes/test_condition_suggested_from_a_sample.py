"""`designer.material.condition-suggested-from-a-sample`: a measure ticks a condition beforehand, labelled with the sample's count;
a condition no measure can see is never ticked."""
from __future__ import annotations

import pytest

from fichero_server.recipes import condition, prepare, prepare_suggest
from tests.unit.recipes.test_prepare_answers_per_folder import ROWS, _fake_db, _mirror, _page

pytestmark = pytest.mark.recipe_designer


def _none_working_lines(monkeypatch):
    from fichero_server.llm import working_lines as module

    monkeypatch.setattr(module, "working_lines", lambda _db, doc_id: None)


def test_faded_pages_tick_faded_from_three_of_five(monkeypatch, tmp_path):
    _none_working_lines(monkeypatch)
    db = _fake_db(monkeypatch, tmp_path, [_page(strong=ROWS)] * 5)
    monkeypatch.setattr(prepare, "is_faded", lambda path: True)
    got = prepare_suggest.suggest(db)
    assert got["condition.faded"] == {"value": True, "agree": "5 of 5", "why": "from 5 of 5 sample pages"}
    monkeypatch.setattr(prepare, "is_faded", lambda path: False)
    assert "condition.faded" not in prepare_suggest.suggest(db)


def test_show_through_and_ruled_lines_tick_from_their_measures(monkeypatch, tmp_path):
    _none_working_lines(monkeypatch)
    front = _page(strong=ROWS)
    back = _page(strong=[(60, 100 + 90 * i + 45) for i in range(10)], faint=_mirror(ROWS))
    db = _fake_db(monkeypatch, tmp_path, [front, back, front, back, front])
    assert prepare_suggest.suggest(db)["condition.show-through"]["value"] is True
    monkeypatch.setattr(prepare_suggest, "is_ruled", lambda image: True)
    assert prepare_suggest.suggest(db)["condition.ruled-lines"]["agree"] == "5 of 5"


def test_a_condition_no_measure_can_see_is_never_suggested(monkeypatch, tmp_path):
    _none_working_lines(monkeypatch)
    db = _fake_db(monkeypatch, tmp_path, [_page(strong=ROWS)] * 5)
    monkeypatch.setattr(prepare, "is_faded", lambda path: True)
    monkeypatch.setattr(prepare_suggest, "is_ruled", lambda image: True)
    ticked = {k.split(".", 1)[1] for k in prepare_suggest.suggest(db) if k.startswith("condition.")}
    assert ticked <= {"faded", "show-through", "ruled-lines"} and not ticked & {"torn", "stains", "water-damage", "tight-binding"}
    assert ticked <= set(condition.IDS)
