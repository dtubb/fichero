"""#6811: a Start on chosen pages answers for those pages, and a Start with nothing to run is refused in the plan's words."""
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


def test_start_on_chosen_pages_answers_for_those_pages(client, db, pages, tmp_path, engine):
    _save(client, _recipe(tmp_path, *STEPS))
    r = client.post("/api/recipes/project/start", json={"documents": [pages[0].id]})
    assert r.status_code == 200, r.text
    answer = r.json()
    assert answer["estimate"]["pages"] == 1, "the answer is for the one page chosen, not the project's two"
    assert answer["cloud_cap"]["pages"] == 1
    assert _finished(client, answer["started"]["job_id"])["state"] == "done"
    assert engine.read == ["p0.png"]


def test_a_start_with_nothing_to_run_is_refused_and_queues_no_run(client, db, pages, tmp_path, engine):
    _save(client, _recipe(tmp_path, *STEPS))
    first = client.post("/api/recipes/project/start")
    assert first.status_code == 200, first.text
    _finished(client, first.json()["started"]["job_id"])
    ran = len(_runs(client))
    again = client.post("/api/recipes/project/start", json={"steps": ["read"]})
    assert again.status_code == 422, again.text
    assert "already done on all 2 pages; nothing to run" in again.text
    assert len(_runs(client)) == ran, "a refused Start queues no run"


def test_a_redo_that_stopped_counts_its_own_pages_and_offers_to_read_the_rest(client, db, pages, tmp_path, engine, monkeypatch):
    from pathlib import Path

    from fichero_server.llm import kraken_runtime

    _save(client, _recipe(tmp_path, *STEPS))
    _finished(client, client.post("/api/recipes/project/start").json()["started"]["job_id"])
    read_given = engine.read_given

    def fail_the_second(image_path, model_path, lines, **kw):
        if Path(image_path).name == "p1.png":
            raise RuntimeError("the page could not be opened")
        return read_given(image_path, model_path, lines, **kw)

    monkeypatch.setattr(kraken_runtime, "read_given_lines", fail_the_second)
    r = client.post("/api/recipes/project/start", json={"steps": ["read"], "redo": ["read"]})
    assert r.status_code == 200, r.text
    job = r.json()["started"]["job_id"]
    _finished(client, job)
    summary = client.get(f"/api/recipes/project/runs/{job}/summary").json()
    assert summary["pages_read"] == 1, "the one page this run read again"
    missed = summary["missed"]
    assert missed["words"].startswith("1 page not done"), missed
    assert missed["documents"] == [pages[1].id], "the page this run did not reach"
    assert missed["redo"] == ["read"], "the offer reads them again"
    assert summary["lines"][0].startswith("Read 1 of 2 pages"), summary["lines"]
    monkeypatch.setattr(kraken_runtime, "read_given_lines", read_given)
    engine.read.clear()
    again = client.post("/api/recipes/project/start", json={"documents": missed["documents"], "redo": missed["redo"],
                                                            "steps": missed["redo"]})
    assert again.status_code == 200, again.text
    assert _finished(client, again.json()["started"]["job_id"])["state"] == "done"
    assert engine.read == ["p1.png"], "the offer reads the page this run did not reach, and only it"
