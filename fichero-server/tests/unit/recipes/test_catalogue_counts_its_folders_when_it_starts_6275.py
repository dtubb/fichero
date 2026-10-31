"""The Catalogue step counts its folders when it starts (#6275), after the reading steps before it have finished, not from
the Start plan, which was made before any page had text and said 0 folders. Test: the plan has 0 folders with text, then
reading fills 2 folders; the catalogue step writes 2."""
# ruff: noqa: F811 -- pytest fixtures imported from the sibling tests are named as test arguments
from __future__ import annotations

from tests.unit.recipes.test_catalogue_stage_6087 import asked  # noqa: F401  (fixture)
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


# --- which pages block a folder after a reading step failed ------------------------------------------------------------


def _page_with_a_line(db, parent, name, text="", *, furniture=False, blank=False, doc_type=None):
    from fichero_server.models import DocType, Document
    from fichero_server.models.anchors import SourceAnchor
    from fichero_server.models.knowledge import ProvenanceKind
    from fichero_server.models.segments import Segment, SegmentPass, bbox_and_tile_from_anchor
    from fichero_server.recipes import sorting

    doc = Document(name=name, doc_type=doc_type or DocType.page, parent_id=parent, page_content=text)
    if blank:
        doc.attributes = {sorting.KIND: sorting.BLANK}
    db.save(doc)
    pas = SegmentPass(document_id=doc.id, name="lines", provenance_kind=ProvenanceKind.workflow)
    db.save(pas)
    anchor = SourceAnchor(document_id=doc.id, rect=[0.1, 0.1, 0.6, 0.1])
    x, y, w, h, tile = bbox_and_tile_from_anchor(anchor)
    db.save(Segment(document_id=doc.id, pass_id=pas.id, kind="line", anchor=anchor, bbox_x=x, bbox_y=y, bbox_w=w, bbox_h=h,
                    tile=tile, doc_kind=f"{doc.id}:line", provenance_kind=ProvenanceKind.workflow, is_furniture=furniture))
    return doc.id


def _after_a_failed_read(db, asked):
    from fichero_server.models import DocType, Document
    from fichero_server.recipes import catalogue_step
    from tests.unit.recipes.test_catalogue_stage_6087 import CONFIG

    top = Document(name="Top", doc_type=DocType.folder)
    db.save(top)
    boxes = {}
    for name in ("Box 0", "Box 1"):
        box = Document(name=name, doc_type=DocType.folder, parent_id=top.id)
        db.save(box)
        boxes[name] = box.id
    read = _page_with_a_line(db, boxes["Box 0"], "read", "Letter about wheat")
    blank_verso = _page_with_a_line(db, boxes["Box 0"], "verso", blank=True)
    left_out = _page_with_a_line(db, boxes["Box 0"], "furniture", furniture=True)
    pdf = Document(name="a.pdf", doc_type=DocType.file, parent_id=boxes["Box 0"])
    db.save(pdf)
    cut_page = Document(name="a-p1", doc_type=DocType.page, parent_id=pdf.id, page_content="Page of the pdf")
    db.save(cut_page)
    unread = _page_with_a_line(db, boxes["Box 1"], "unread")
    pages = [read, blank_verso, left_out, cut_page.id, unread]
    return catalogue_step.describe_folders(db, pages, CONFIG, run_id=None, whole_folders_only=True)


def test_a_blank_verso_a_left_out_page_and_a_parent_node_never_block_a_folder(db, asked):
    account = _after_a_failed_read(db, asked)

    assert account["described"] == 1, account  # Box 0 only
    assert [s.split(" (")[0] for s in account["skipped"]] == ["Box 1", "Top"], account["skipped"]
    assert len(asked) == 1 and "Box 0" in asked[0]


def test_a_page_whose_read_failed_blocks_its_folder_though_it_has_some_text(db, asked, monkeypatch):
    from fichero_server.models import DocType, Document
    from fichero_server.recipes import catalogue_step
    from tests.unit.recipes.test_catalogue_stage_6087 import CONFIG

    box = Document(name="Box", doc_type=DocType.folder)
    db.save(box)
    page = _page_with_a_line(db, box.id, "p", "half of it")
    monkeypatch.setattr("fichero_server.recipes.done.failed_reads", lambda db, pages, mark_blank=False: [(page, "failed")])

    account = catalogue_step.describe_folders(db, [page], CONFIG, run_id=None, whole_folders_only=True)

    assert account["described"] == 0 and [s.split(" (")[0] for s in account["skipped"]] == ["Box"]


# --- the step's own inputs ----------------------------------------------------------------------------------------


def _catalogue_pages(db, detail, card, step):
    from fichero_server.recipes import runner

    batch = {"folder": None, "units": [], "last": True}
    return runner._step_pages(db, card, step, batch, runner._tree(db), detail)


def _two_cards(read_state, takes):
    read = {"card": "workflow", "steps": ["read"], "job": "read-a-line", "gives": ["line_readings"], "takes": ["lines"]}
    cat = {"card": "catalogue", "steps": ["cat"], "job": "describe-for-the-catalogue", "gives": ["metadata_values"]}
    if takes is not None:
        cat["takes"] = takes
    steps = [{"steps": ["read"], "card": "workflow", "state": read_state}, {"steps": ["cat"], "card": "catalogue", "state": "waiting"}]
    return {"runs": [read, cat], "steps": steps}, cat, steps[1]


def test_the_readers_are_unfinished_by_any_kind_the_step_takes_and_an_old_run_waits_on_every_step_before(db):
    for state, takes, expected in [("failed", ["line_readings"], True), ("failed", ["x|line_readings"], True),
                                   ("done", ["x|line_readings"], False), ("partial", None, True), ("done", None, False)]:
        detail, card, step = _two_cards(state, takes)
        _documents, scratch, _kinds = _catalogue_pages(db, detail, card, step)
        assert scratch["readers_unfinished"] is expected, (state, takes)


def test_a_folder_trashed_after_the_run_began_leaves_the_catalogue_no_pages_and_no_crash(db):
    detail, card, step = _two_cards("done", ["line_readings"])
    detail["folder_id"] = "a-folder-that-is-gone"

    documents, _scratch, _kinds = _catalogue_pages(db, detail, card, step)

    assert documents == []


def test_a_page_the_run_noted_failed_blocks_its_folder_even_with_no_lines_but_a_blank_one_does_not(db, asked):
    from fichero_server.models import DocType, Document
    from fichero_server.recipes import catalogue_step

    box = Document(name="Box", doc_type=DocType.folder)
    db.save(box)
    read = Document(name="read", doc_type=DocType.page, parent_id=box.id, page_content="a letter")
    lost = Document(name="lost", doc_type=DocType.page, parent_id=box.id)
    db.save(read)
    db.save(lost)
    blank = _page_with_a_line(db, box.id, "verso", blank=True)
    leaves = [read, lost, db.get(Document, blank)]
    ids = [d.id for d in leaves]

    assert [d.name for d in catalogue_step.unread_pages(db, leaves, ids, {lost.id, blank})] == ["lost"]
    assert catalogue_step.unread_pages(db, leaves, ids) == []  # with no note of failure, a page with no lines was not due
