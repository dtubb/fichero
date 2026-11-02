"""`designer.how.answers-pick-the-card` (#6052)."""
from __future__ import annotations

import pytest

from fichero_server.recipes import how

pytestmark = pytest.mark.recipe_designer


@pytest.mark.parametrize("given, pages, card", [
    ({"places": ["this-mac"], "matters": "privacy"}, 10, "d"), ({"places": ["cloud"], "matters": "quality"}, 100, "c"),
    ({"places": ["cluster"], "matters": "cost"}, 100, "b"), ({"places": ["cloud"], "matters": "cost"}, 9000, "a"),
    ({}, 100, None)])
def test_the_answers_pick_the_card(given, pages, card):
    assert how.proposed_card(given, pages) == card


def test_the_questions_route_serves_conditions_and_how():
    from fastapi.testclient import TestClient

    from fichero_server.api.main import app

    body = TestClient(app).get("/api/recipes/questions?places=cluster&matters=cost&pages=50").json()
    assert body["how"]["default_model_kind"] == "compare" and body["how"]["proposed_card"] == "b"
    assert [m for m in body["how"]["matters"]] == ["speed", "cost", "quality", "privacy"] and body["conditions"]
