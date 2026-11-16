"""`designer.how.chain-risk-on-ready` (#6052): one line per model step, from the job registry, the earliest marked check first."""
from __future__ import annotations

import pytest

from fichero_server.recipes import chain_risk

pytestmark = pytest.mark.recipe_designer

CHAIN = ["prepare-the-image", "find-lines", "read-a-line", "find-names-tag-words", "find-statements"]


def test_each_model_step_says_what_feeds_it_and_what_it_feeds():
    rows = {r["job"]: r["line"] for r in chain_risk.lines(CHAIN)}
    assert "prepare-the-image" not in rows  # no model, no line
    assert rows["read-a-line"] == ("Read each line takes what Find lines found; Find names and Find statements take what Read each line wrote.")
    assert rows["find-lines"] == "Read each line takes what Find lines wrote." or "Read each line" in rows["find-lines"]


def test_the_earliest_model_steps_say_check_first_and_later_ones_do_not():
    rows = chain_risk.lines(CHAIN)
    assert [r["check_first"] for r in rows] == [True, True, False, False]


def test_a_step_with_nothing_upstream_or_downstream_still_gets_a_line_and_the_route_serves_it():
    assert chain_risk.lines(["find-lines"])[0]["line"]
    from fastapi.testclient import TestClient

    from fichero_server.api.main import app

    body = TestClient(app).get("/api/recipes/chain-risk?jobs=find-lines,read-a-line").json()
    assert [s["job"] for s in body["steps"]] == ["find-lines", "read-a-line"]
