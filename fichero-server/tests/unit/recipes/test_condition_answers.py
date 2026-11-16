"""`designer.material.condition-asked`: the list is the engine's, an unknown id is refused in words, none ticked saves []."""
from __future__ import annotations

import pytest

from fichero_server.recipes.answers import normalise
from fichero_server.recipes.condition import CONDITIONS, IDS

pytestmark = pytest.mark.recipe_designer


def test_the_list_has_a_name_and_one_line_of_help_each():
    assert [c[0] for c in CONDITIONS] == ["faded", "torn", "stains", "show-through", "water-damage", "tight-binding", "ruled-lines"]
    assert all(name and help_ and "\n" not in help_ for _, name, help_ in CONDITIONS)


def test_the_questions_route_serves_that_list():
    from fastapi.testclient import TestClient

    from fichero_server.api.main import app

    body = TestClient(app).get("/api/recipes/questions").json()
    assert [c["id"] for c in body["conditions"]] == list(IDS)


def test_ticked_ids_keep_the_lists_order():
    assert normalise({"condition": ["ruled-lines", "faded"]}, strict=True)["condition"] == ["faded", "ruled-lines"]


def test_an_unknown_id_is_refused_naming_the_valid_list():
    with pytest.raises(ValueError, match="show-through.*'mold'"):
        normalise({"condition": ["mold"]}, strict=True)


def test_none_ticked_saves_an_empty_list_and_unasked_saves_nothing():
    assert normalise({"condition": []}, strict=True)["condition"] == []
    assert normalise({"condition": None}, strict=True)["condition"] == []
    assert "condition" not in normalise({"materials": ["print"]}, strict=True)


def test_reading_a_saved_project_keeps_an_unknown_id():
    assert normalise({"condition": ["mold"]}, strict=False)["condition"] == ["mold"]
