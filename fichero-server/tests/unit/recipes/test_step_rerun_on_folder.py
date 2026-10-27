"""Run again on what was missed (#6170), tested to the spec: `source.recipe.run-again-on-what-was-missed`
(models-chains-and-projects.md), `recipes-run.journey.run-again-on-what-was-missed` (recipes-run.md).

WHY: the Istmina run failed on 112 pages, the app restarted, and nothing said what was missed or offered to run it
again. The run's summary now says what it did not finish and names its scope; the action is plain Start on that scope,
which runs only what is not done, so no page is read twice (`never-rerun-a-model-pass`).
"""
# ruff: noqa: F811 -- pytest fixtures imported from the sibling tests are named as test arguments
from __future__ import annotations

from pathlib import Path

import time

from tests.unit.recipes.test_recipe_execution_to_spec import (  # noqa: F401  (fixtures)
    _finished,
    _import,
    _recipe,
    _runs,
    _save,
    _wait,
    engine,
    pages,
)

STEPS = [{"id": "lines", "job": "find-lines", "model": {"kraken": "blla", "kraken_version": "bundled"}},
         {"id": "read", "job": "read-a-line", "model": {"zenodo": "10.5281/zenodo.13788177"}}]


def test_a_run_says_what_it_missed_and_running_again_reads_only_that(client, db, pages, tmp_path, engine, monkeypatch):
    from fichero_server.llm import kraken_runtime
    from fichero_server.models import DocType, Document

    box = Document(name="Box", doc_type=DocType.folder)
    db.save(box)
    for page in pages:
        page.parent_id = box.id
        db.save(page)
    recognize = engine.recognize

    def fail_the_second(image_path, model_path, **kw):
        if Path(image_path).name == "p1.png":
            raise RuntimeError("the page could not be opened")
        return recognize(image_path, model_path, **kw)

    monkeypatch.setattr(kraken_runtime, "recognize_to_geometry", fail_the_second)
    _save(client, _recipe(tmp_path, *STEPS))
    r = client.post("/api/recipes/project/start", json={"folder_id": box.id})
    assert r.status_code == 200, r.text
    first = r.json()["started"]["job_id"]
    _finished(client, first)

    missed = client.get(f"/api/recipes/project/runs/{first}/summary").json()["missed"]
    assert missed["folder_id"] == box.id
    assert missed["offer"] == "Run again on what was missed"
    assert "1 page not done" in missed["words"], missed
    assert engine.read == ["p0.png"]

    monkeypatch.setattr(kraken_runtime, "recognize_to_geometry", recognize)  # the cause is fixed
    r = client.post("/api/recipes/project/start", json={"folder_id": missed["folder_id"]})
    assert r.status_code == 200, r.text
    second = r.json()["started"]["job_id"]
    assert _finished(client, second)["state"] == "done"
    assert engine.read == ["p0.png", "p1.png"]  # the missed page only: p0 is never read twice
    assert client.get(f"/api/recipes/project/runs/{second}/summary").json()["missed"] is None


def test_one_step_runs_again_on_one_folder_as_a_new_pass(client, db, pages, tmp_path, engine, monkeypatch):
    """`source.recipe.step-rerun-on-folder`: a step of a started recipe runs again on one folder alone, Start with that
    folder and the step to redo; the other folder is not read, and the folder's earlier readings are kept."""
    from fichero_server.models import ContentRepresentation, DocType, Document

    folders = []
    for name, page in zip(("A", "B"), pages):
        folder = Document(name=name, doc_type=DocType.folder)
        db.save(folder)
        page.parent_id = folder.id
        db.save(page)
        folders.append(folder)
    _save(client, _recipe(tmp_path, *STEPS))
    assert _finished(client, client.post("/api/recipes/project/start", json={}).json()["started"]["job_id"])[
        "state"] == "done"
    assert sorted(engine.read) == ["p0.png", "p1.png"]
    before = {r.id for r in db.query(ContentRepresentation, document_id=pages[0].id)}

    r = client.post("/api/recipes/project/start", json={"folder_id": folders[0].id, "redo": ["read"]})
    assert r.status_code == 200, r.text
    again = _finished(client, r.json()["started"]["job_id"])
    assert again["state"] == "done", again
    assert sorted(engine.read) == ["p0.png", "p0.png", "p1.png"], "folder A read again, folder B left as it was"
    after = {r.id for r in db.query(ContentRepresentation, document_id=pages[0].id)}
    assert before < after, "a rerun adds a reading; nothing the first run wrote is replaced"


def test_new_material_runs_the_steps_by_itself_only_when_the_project_runs_automatically(client, db, pages, tmp_path,
                                                                                         engine):
    """`source.recipe.steps-follow-new-material`: after Start, a page added runs the recipe's steps over it alone
    (`source.onboard.just-do-it` pins the run); with "Nothing runs automatically" chosen, an added page runs nothing."""
    _save(client, _recipe(tmp_path, *STEPS))
    _finished(client, client.post("/api/recipes/project/start", json={}).json()["started"]["job_id"])
    engine.read = []
    _import(client, tmp_path, "arrived.png")
    assert _wait(lambda: len(_runs(client)) == 2), "the added page is one more run"
    assert all(_finished(client, j["job_id"])["state"] == "done" for j in _runs(client))
    assert engine.read == ["arrived.png"], "only the new page: the pages already read are not read again"

    setup = client.get("/api/recipes/project").json()
    answers = {**setup["answers"], "automatic": {"runs": False}}
    assert client.put("/api/recipes/project", json={"answers": answers, "recipe": setup["recipe"]}).status_code == 200
    engine.read = []
    _import(client, tmp_path, "by-hand.png")
    time.sleep(1.5)
    assert len(_runs(client)) == 2 and engine.read == [], "runs by hand: the added page waits for Start"


def test_the_engine_fixture_stubs_read_again(engine):
    """#6222: Read Again calls `kraken_runtime.read_given_lines`; the shared fixture answers it, never real Kraken."""
    from fichero_server.llm import kraken_runtime

    assert kraken_runtime.read_given_lines == engine.read_given
