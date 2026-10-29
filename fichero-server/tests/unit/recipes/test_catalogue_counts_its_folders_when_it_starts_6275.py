"""The Catalogue step counts its folders when it starts (#6275), after the reading steps before it have finished, not from
the Start plan, which was made before any page had text and said 0 folders. Test: the plan has 0 folders with text, then
reading fills 2 folders; the catalogue step writes 2."""
# ruff: noqa: F811 -- pytest fixtures imported from the sibling tests are named as test arguments
from __future__ import annotations

from tests.unit.recipes.test_every_stage_resumes_after_a_stop_1134 import (  # noqa: F401  (fixtures)
    CATALOGUE,
    LINES,
    READ,
    _described,
    _finished,
    _folders,
    _recipe,
    _save,
    _start,
    _memory_is_not_the_question,
    engine,
    pages,
    stubs,
)


def test_the_catalogue_step_describes_the_folders_the_reading_filled(client, db, pages, tmp_path, stubs, monkeypatch,
                                                                     with_material):
    import fichero_server.llm as llm
    from fichero_server.models import DocType, Document

    _folders(db, pages)
    texted = [d for d in db.query(Document) if d.doc_type == DocType.page and (d.page_content or "").strip()]
    assert not texted, "the plan is made before any page has text"

    async def describe(material, config=None, system=None, permissive_guardrails=False):
        return "Title: A box.\nScope and content: Letters."

    monkeypatch.setattr(llm, "chat_with_fallback", describe)
    monkeypatch.setattr("fichero_server.recipes.runner.BATCH_PAGE_LIMIT", 1)  # a batch a folder
    _save(client, _recipe(tmp_path, LINES, READ, CATALOGUE))

    run = _finished(client, _start(client))

    assert run["state"] == "done", run
    assert _described(db) == {"Top", "Box 0", "Box 1"}, run



def _catalogue_says(client, job_id) -> dict:
    return next(s for s in client.get(f"/api/recipes/project/runs/{job_id}").json()["steps"] if s["card"] == "catalogue")


def test_a_folder_read_in_full_is_catalogued_though_another_folders_read_failed(client, db, pages, tmp_path, stubs,
                                                                                monkeypatch, with_material):
    """The cap ran out mid-read (B13): the folders whose pages were all read get their catalogue, the others are named."""
    import fichero_server.llm as llm
    from fichero_server.llm import kraken_runtime

    _folders(db, pages)
    real = kraken_runtime.recognize_to_geometry

    def second_dies(image_path, *args, **kwargs):
        if "p1" in str(image_path):  # the second photograph, in Box 1
            raise RuntimeError("cap reached")
        return real(image_path, *args, **kwargs)

    async def describe(material, config=None, system=None, permissive_guardrails=False):
        return "Title: A box.\nScope and content: Letters."

    monkeypatch.setattr(kraken_runtime, "recognize_to_geometry", second_dies)
    monkeypatch.setattr(llm, "chat_with_fallback", describe)
    monkeypatch.setattr("fichero_server.recipes.runner.BATCH_PAGE_LIMIT", 1)  # a batch a folder
    _save(client, _recipe(tmp_path, LINES, READ, CATALOGUE))

    job_id = _start(client)
    _finished(client, job_id)

    assert _described(db) == {"Box 0"}, "the folder read in full is catalogued; Box 1 and Top hold an unread page"
    step = _catalogue_says(client, job_id)
    assert step["state"] == "partial", step
    assert "Box 1" in step["why"] and "Top" in step["why"], step["why"]


def test_a_folder_scoped_run_catalogues_only_that_folder(client, db, pages, tmp_path, stubs, monkeypatch, with_material):
    """#6275: the catalogue step took every page of the project; on a folder's run it must take that folder's alone."""
    import fichero_server.llm as llm
    from fichero_server.models import Document

    top = _folders(db, pages)
    other = db.get(Document, pages[1].id)
    other.page_content = "Already read: a letter about wheat"
    db.save(other)
    boxes = {d.name: d.id for d in db.query(Document) if d.parent_id == top.id}

    async def describe(material, config=None, system=None, permissive_guardrails=False):
        return "Title: A box.\nScope and content: Letters."

    monkeypatch.setattr(llm, "chat_with_fallback", describe)
    _save(client, _recipe(tmp_path, LINES, READ, CATALOGUE))
    r = client.post("/api/recipes/project/start", json={"folder_id": boxes["Box 0"]})
    assert r.status_code == 200, r.text
    run = _finished(client, r.json()["started"]["job_id"])

    assert run["state"] == "done", run
    assert "Box 1" not in _described(db), "the folder's run described a folder outside it"
    assert "Box 0" in _described(db)
