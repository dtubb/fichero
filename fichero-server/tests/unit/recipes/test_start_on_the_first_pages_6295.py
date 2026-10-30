"""#6295: Start with `first_pages` queues a run on those pages alone (Finder order), and its answer describes that run, not the
whole project (the screen right after Start showed the whole project's pages and a cap refusal for a run that had started)."""
# ruff: noqa: F811 -- pytest fixtures imported from the sibling tests are named as test arguments
from __future__ import annotations

from tests.unit.recipes.test_recipe_execution_to_spec import (  # noqa: F401  (fixtures)
    _finished,
    _recipe,
    _runs,
    _save,
    engine,
    pages,
)
from tests.unit.recipes.test_step_rerun_on_folder import STEPS


def test_start_on_the_first_pages_runs_them_and_answers_for_them(client, db, pages, tmp_path, engine):
    _save(client, _recipe(tmp_path, *STEPS))
    whole = client.get("/api/recipes/project/start").json()
    assert whole["estimate"]["pages"] == 2

    r = client.post("/api/recipes/project/start", json={"first_pages": 1})
    assert r.status_code == 200, r.text
    answer = r.json()
    assert answer["estimate"]["pages"] == 1, "the answer is for the one page queued, not the project's two"
    assert answer["cloud_cap"]["pages"] == 1
    assert _finished(client, answer["started"]["job_id"])["state"] == "done"
    assert engine.read == ["p0.png"], "the first page in Finder order, and only it"
    assert len(_runs(client)) == 1


def test_start_takes_the_first_pages_or_a_folder_or_some_pages_not_two(client, db, pages, tmp_path, engine):
    _save(client, _recipe(tmp_path, *STEPS))
    both = client.post("/api/recipes/project/start", json={"first_pages": 1, "documents": [pages[0].id]})
    assert both.status_code == 422 and "one of them" in both.text
    assert client.post("/api/recipes/project/start", json={"first_pages": 0}).status_code == 422
