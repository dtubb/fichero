"""Run one recipe step on a folder or one file (`recipes-run.journey.run-one-step-on-a-folder-or-file`, #7036).

WHY: the historian picks one step of the recipe and runs only that step on the folder they selected, or on one file.
The steps before it are not run: what they already wrote is what the step reads. The run is one step in Activity.
"""
# ruff: noqa: F811 -- pytest fixtures imported from the sibling tests are named as test arguments
from __future__ import annotations

from tests.unit.recipes.test_recipe_execution_to_spec import (  # noqa: F401  (fixtures)
    _finished,
    _recipe,
    _run_status,
    _save,
    engine,
    pages,
)
from tests.unit.recipes.test_step_rerun_on_folder import STEPS


def _two_folders(db, pages):
    from fichero_server.models import DocType, Document

    folders = []
    for name, page in zip(("A", "B"), pages):
        folder = Document(name=name, doc_type=DocType.folder)
        db.save(folder)
        page.parent_id = folder.id
        db.save(page)
        folders.append(folder)
    return folders


def test_one_step_runs_alone_on_a_folder_after_the_steps_before_it_ran(client, db, pages, tmp_path, engine):
    folders = _two_folders(db, pages)
    _save(client, _recipe(tmp_path, *STEPS))
    first = client.post("/api/recipes/project/start", json={"steps": ["lines"]})
    assert first.status_code == 200, first.text
    assert _finished(client, first.json()["started"]["job_id"])["state"] == "done"
    assert engine.read == [], "Find Lines alone reads nothing"

    r = client.post("/api/recipes/project/start", json={"steps": ["read"], "folder_id": folders[0].id})

    assert r.status_code == 200, r.text
    run = _finished(client, r.json()["started"]["job_id"])
    assert run["state"] == "done", run
    assert [s["steps"] for s in run["steps"]] == [["read"]], "the run is that one step; the step before it is not run again"
    assert engine.read == ["p0.png"], "folder A only; folder B is not read"


def test_one_step_runs_alone_on_one_file(client, db, pages, tmp_path, engine):
    _save(client, _recipe(tmp_path, *STEPS))
    first = client.post("/api/recipes/project/start", json={"steps": ["lines"]})
    assert _finished(client, first.json()["started"]["job_id"])["state"] == "done"

    r = client.post("/api/recipes/project/start", json={"steps": ["read"], "documents": [pages[1].id]})

    assert r.status_code == 200, r.text
    run = _finished(client, r.json()["started"]["job_id"])
    assert run["state"] == "done", run
    assert [s["steps"] for s in run["steps"]] == [["read"]]
    assert engine.read == ["p1.png"], "the one file only"


def test_a_step_the_recipe_lacks_is_refused_on_a_folder_in_words(client, db, pages, tmp_path):
    folders = _two_folders(db, pages)
    _save(client, _recipe(tmp_path, *STEPS))
    r = client.post("/api/recipes/project/start", json={"steps": ["nope"], "folder_id": folders[0].id})
    assert r.status_code == 422 and "no step nope" in r.text, r.text
