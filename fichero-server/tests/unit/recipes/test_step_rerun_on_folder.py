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
    _png,
    _recipe,
    _run_status,
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


def test_changed_material_runs_the_steps_again_by_itself(client, db, pages, tmp_path, engine):
    """`source.recipe.steps-follow-new-material`, changed material: after Start, a file imported again with its content
    changed arrives as material of its own and the recipe's steps run over it alone, by themselves; the earlier page and
    its reading are kept (a rerun is a new pass, never an overwrite)."""
    from PIL import Image

    from fichero_server.models import ContentRepresentation, Document

    _save(client, _recipe(tmp_path, *STEPS))
    _finished(client, client.post("/api/recipes/project/start", json={}).json()["started"]["job_id"])
    path = _import(client, tmp_path, "changed.png")
    assert _wait(lambda: len(_runs(client)) == 2)
    assert all(_finished(client, j["job_id"])["state"] == "done" for j in _runs(client))
    first = next(d for d in db.query(Document) if d.name == "changed.png")
    kept = {r.id for r in db.query(ContentRepresentation, document_id=first.id)}
    assert kept, "the first page was read"

    engine.read = []
    image = Image.open(path).convert("RGB")
    image.putpixel((1, 1), (0, 0, 0))  # the original is replaced by a changed one
    image.save(str(path), format="PNG")
    assert client.post("/api/ingest/files", json={"paths": [str(path)]}).status_code == 200
    assert _wait(lambda: len(_runs(client)) == 3), "the changed file is one more run, by itself"
    assert all(_finished(client, j["job_id"])["state"] == "done" for j in _runs(client))
    assert engine.read == ["changed.png"], "only the changed page"
    assert {r.id for r in db.query(ContentRepresentation, document_id=first.id)} == kept, "the earlier reading is kept"


def test_a_run_on_imported_pages_offers_running_again_on_those_pages_alone(client, db, pages, tmp_path, engine,
                                                                           monkeypatch):
    """#6170: a run the import started covers its new pages alone, so what it missed is those pages, offered back as
    Start on them (`documents`), never as Start on the whole project (which would also read a page nobody started)."""
    from fichero_server.llm import kraken_runtime
    from fichero_server.models import DocType, Document, FileType
    from tests.unit.recipes.test_recipe_execution_to_spec import _png

    recognize = engine.recognize

    def fail_late(image_path, model_path, **kw):
        if Path(image_path).name == "late.png":
            raise RuntimeError("the page could not be opened")
        return recognize(image_path, model_path, **kw)

    _save(client, _recipe(tmp_path, *STEPS))
    _finished(client, client.post("/api/recipes/project/start", json={}).json()["started"]["job_id"])
    db.save(Document(name="waiting.png", doc_type=DocType.file, file_type=FileType.image,
                     path=str(_png(tmp_path / "waiting.png"))))  # a page no run was started on
    monkeypatch.setattr(kraken_runtime, "recognize_to_geometry", fail_late)
    engine.read = []
    _import(client, tmp_path, "late.png")
    assert _wait(lambda: len(_runs(client)) == 2)
    imported = next(r["job_id"] for r in _runs(client) if r["started_by"] == "import")
    _finished(client, imported)
    late = next(d for d in db.query(Document) if d.name == "late.png")
    missed = client.get(f"/api/recipes/project/runs/{imported}/summary").json()["missed"]
    assert missed and missed["folder_id"] is None and missed["documents"] == [late.id], missed

    monkeypatch.setattr(kraken_runtime, "recognize_to_geometry", recognize)  # the cause is fixed
    r = client.post("/api/recipes/project/start", json={"documents": missed["documents"]})
    assert r.status_code == 200, r.text
    assert _finished(client, r.json()["started"]["job_id"])["state"] == "done"
    assert engine.read == ["late.png"], "the missed page alone: the page nobody started waits"


def test_start_on_pages_refuses_a_folder_too_and_pages_not_in_the_project(client, db, pages, tmp_path):
    """#6170: Start takes a folder or some pages, never both; and the pages must be the project's own."""
    _save(client, _recipe(tmp_path, *STEPS))
    page = pages[0].id
    r = client.post("/api/recipes/project/start", json={"documents": [page], "folder_id": "anything"})
    assert r.status_code == 422 and "not both" in r.text, r.text
    r = client.post("/api/recipes/project/start", json={"documents": [page, "not-a-page"]})
    assert r.status_code == 422 and "not in the project" in r.text, r.text
    assert not _runs(client), "a refused Start queues no run"


def test_unchanged_material_imported_again_is_not_read_again(client, db, pages, tmp_path, engine):
    """#6225, never rerun a model pass (#6127): after Start, the same file imported again unchanged is the page it already
    is: no second page, no run queued, the reader not called again."""
    from fichero_server.models import Document

    _save(client, _recipe(tmp_path, *STEPS))
    _finished(client, client.post("/api/recipes/project/start", json={}).json()["started"]["job_id"])
    path = _import(client, tmp_path, "same.png")
    assert _wait(lambda: len(_runs(client)) == 2)
    assert all(_finished(client, j["job_id"])["state"] == "done" for j in _runs(client))

    engine.read = []
    assert client.post("/api/ingest/files", json={"paths": [str(path)]}).status_code == 200
    assert not _wait(lambda: len(_runs(client)) > 2, seconds=3), "an unchanged file queues no run"
    assert engine.read == [], "the reader is not called again"
    assert sum(d.name == "same.png" for d in db.query(Document)) == 1, "the same page, not a second"


def test_a_new_file_copied_in_is_hashed_once(client, tmp_path, monkeypatch):
    """#6225 review: the unchanged-import check hashes the file, and the import reuses that hash (copy and move; a
    link import hashes again, as the folder import does, to catch a file changed while it was read)."""
    from fichero_server.importers import ingest
    from tests.unit.recipes.test_recipe_execution_to_spec import _png

    hashed, real = [], ingest._file_checksum
    monkeypatch.setattr(ingest, "_file_checksum", lambda path, *a, **k: hashed.append(path) or real(path, *a, **k))
    r = client.post("/api/ingest/file", json={"path": str(_png(tmp_path / "once.png")), "mode": "copy"})
    assert r.status_code == 200, r.text
    assert len(hashed) == 1, hashed


def test_a_deliberate_second_page_is_duplicate_or_another_folder(client, db, tmp_path):
    """#6225: copy, link and move dedupe alike (copy is how the file is stored, not a second page asked for); a
    deliberate second page is Duplicate, or the same file imported into another folder."""
    from fichero_server.models import DocType, Document

    path = _png(tmp_path / "same.png")

    def imported(**kw):
        r = client.post("/api/ingest/file", json={"path": str(path), **kw})
        assert r.status_code == 200, r.text
        return r.json()["id"]

    first = imported(mode="copy")
    assert imported(mode="copy") == first, "an unchanged copy import is the page it already is"
    assert imported(mode="link") == first, "link dedupes as copy does"
    r = client.post(f"/api/documents/{first}/duplicate")
    assert r.status_code == 200, r.text
    assert r.json()["id"] != first, "Duplicate after an unchanged re-import is a new page"
    folder = Document(name="Other", doc_type=DocType.folder)
    db.save(folder)
    assert imported(mode="copy", parent_id=folder.id) != first, "another folder is a new page"


def test_the_engine_fixture_stubs_read_again(engine):
    """#6222: Read Again calls `kraken_runtime.read_given_lines`; the shared fixture answers it, never real Kraken."""
    from fichero_server.llm import kraken_runtime

    assert kraken_runtime.read_given_lines == engine.read_given


def test_the_steps_to_run_again_come_with_the_project_not_a_plan(client, pages, tmp_path):
    """`source.recipe.step-rerun-on-folder`: the folder menu lists the started recipe's steps to run again from the
    project's setup (`GET /api/recipes/project`, `redo_steps`), read when the project opens, with no Start plan read
    first; none before the first yes."""
    _save(client, _recipe(tmp_path, *STEPS))
    assert client.get("/api/recipes/project").json()["redo_steps"] == [], "nothing started: nothing to run again"
    assert _finished(client, client.post("/api/recipes/project/start", json={}).json()["started"]["job_id"])[
        "state"] == "done"
    redo = client.get("/api/recipes/project").json()["redo_steps"]
    assert any("read" in s["steps"] for s in redo) and all(s["name"] for s in redo), redo
    # Each one is what Start takes back as `redo`: the folder's rerun of it starts.
    r = client.post("/api/recipes/project/start", json={"folder_id": None, "redo": redo[0]["steps"]})
    assert r.status_code == 200, r.text
    assert _finished(client, r.json()["started"]["job_id"])["state"] == "done"


def test_a_run_on_fewer_pages_than_the_project_says_why(client, db, pages, tmp_path, engine):
    """#6091 (dogfood B12: Start said 95 pages, the run took 58, nothing said why): each stage of the run carries Start's
    own count of what was already done, so the row can say it."""
    from fichero_server.models import DocType, Document, FileType

    _save(client, _recipe(tmp_path, *STEPS))
    _finished(client, client.post("/api/recipes/project/start", json={}).json()["started"]["job_id"])
    db.save(Document(name="p2.png", doc_type=DocType.file, file_type=FileType.image, path=str(_png(tmp_path / "p2.png"))))
    job_id = client.post("/api/recipes/project/start", json={}).json()["started"]["job_id"]
    _finished(client, job_id)
    notes = [s.get("note") for s in _run_status(client, job_id)["steps"]]
    assert "already done on 2 of 3 pages; runs on the other 1" in notes, notes
