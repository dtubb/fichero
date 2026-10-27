"""Run again on what was missed (#6170), tested to the spec: `source.recipe.run-again-on-what-was-missed`
(models-chains-and-projects.md), `recipes-run.journey.run-again-on-what-was-missed` (recipes-run.md).

WHY: the Istmina run failed on 112 pages, the app restarted, and nothing said what was missed or offered to run it
again. The run's summary now says what it did not finish and names its scope; the action is plain Start on that scope,
which runs only what is not done, so no page is read twice (`never-rerun-a-model-pass`).
"""
# ruff: noqa: F811 -- pytest fixtures imported from the sibling tests are named as test arguments
from __future__ import annotations

from pathlib import Path

from tests.unit.recipes.test_recipe_execution_to_spec import (  # noqa: F401  (fixtures)
    _finished,
    _recipe,
    _save,
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
