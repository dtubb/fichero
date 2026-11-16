"""A blank page is hidden, skipped by every later step, and a person can unhide it (`prep.blank-pages-hidden-in-the-item-view`,
`prep.blank-pages-marked`, `prep.check.blank-mark-is-a-correction`, #5382, #1791).

WHY: the left page of Sergio's notebooks is often empty graph paper; reading it costs time and invents text. It is kept,
not deleted, so a person can see why a page is missing and bring it back with one click.
"""
from __future__ import annotations

from PIL import Image

from fichero_server.models import DocType, Document, FileType, ImageEditChain
from tests.unit.media.test_turn_straighten_blank import _graph_paper


def _page(db, tmp_path, name, image):
    path = tmp_path / name
    image.save(path)
    doc = Document(name=name, doc_type=DocType.page, file_type=FileType.image, path=str(path), metadata={})
    db.save(doc)
    return doc, path


def test_a_blank_page_is_hidden_kept_and_left_out_of_what_a_recipe_runs(db, tmp_path):
    from fichero_server.recipes.page_crop import crop_pages

    blank, blank_path = _page(db, tmp_path, "blank.png", _graph_paper(ink=False))
    written, _ = _page(db, tmp_path, "written.png", _graph_paper(ink=True))
    before = blank_path.read_bytes()

    account = crop_pages(db, [blank.id, written.id], "run-1", prepare=True)

    assert account["blank"] == 1
    hidden = db.get(Document, blank.id)
    assert hidden is not None and hidden.exclude_from_processing is True and hidden.metadata["blank"]["blank"] is True
    assert not db.get(Document, written.id).exclude_from_processing
    assert set(db.unit_of_work_ids()) == {written.id}, "no later step is given the blank page"
    (chain,) = db.query(ImageEditChain, document_id=blank.id)
    assert [(o["op"], o["params"], o["who"]) for o in chain.operations] == [("mark_blank", {"blank": True}, "run run-1")]
    assert blank_path.read_bytes() == before, "the page is kept, never changed"


def test_unhide_is_a_correction_that_a_rerun_does_not_undo(db, tmp_path):
    from fichero_server.media.blank_page import unhide
    from fichero_server.recipes.page_crop import crop_pages

    blank, _ = _page(db, tmp_path, "blank.png", _graph_paper(ink=False))
    crop_pages(db, [blank.id], "run-1", prepare=True)
    assert db.unit_of_work_ids() == []

    assert unhide(db, blank.id) == blank.id

    assert db.unit_of_work_ids() == [blank.id], "back among the pages, to be queued through the steps it skipped"
    (chain,) = db.query(ImageEditChain, document_id=blank.id)
    assert [(o["params"], o["who"]) for o in chain.operations] == [({"blank": True}, "run run-1"), ({"blank": False}, "person")]
    crop_pages(db, [blank.id], "run-2", prepare=True)  # the person's word stands
    assert db.unit_of_work_ids() == [blank.id]


def test_the_edit_chain_accepts_the_blank_row():
    from fichero_server.api.routes.ingest.image_editing import _validate_operations
    from fichero_server.media.image_ops import apply_operation

    ops = _validate_operations([{"op": "mark_blank", "params": {"blank": True}, "who": "person"}])
    image = Image.new("RGB", (10, 10), "white")
    assert apply_operation(image, ops[0]) is image  # it changes no pixel


def test_a_page_excluded_for_another_reason_is_still_a_unit_of_work(db, tmp_path):
    """Review finding: pages excluded before blank marking existed (a person's curation, the B12 libraries) stay among what
    a run counts, samples and runs; only a page hidden as blank leaves, and so does a blank-hidden page cut from a photograph."""
    from fichero_server.media.blank_page import mark_blank
    from fichero_server.recipes.done import pages_for

    curated, _ = _page(db, tmp_path, "curated.png", _graph_paper(ink=True))
    curated.exclude_from_processing = True  # no blank mark: a person's own curation
    db.save(curated)
    blank, _ = _page(db, tmp_path, "blank.png", _graph_paper(ink=False))
    mark_blank(db, blank.id, True, who="run run-1")
    plain, _ = _page(db, tmp_path, "plain.png", _graph_paper(ink=True))
    cut = Document(name="cut.png", doc_type=DocType.chunk, file_type=FileType.image, path=str(tmp_path / "plain.png"),
                   metadata={"split_source_id": plain.id}, exclude_from_processing=True)
    db.save(cut)
    mark_blank(db, cut.id, True, who="run run-1")

    assert set(db.unit_of_work_ids()) == {curated.id, plain.id}
    assert set(pages_for(db, {}, None)) == {curated.id, plain.id}, "a blank-hidden cut page is not added back"
    mark_blank(db, blank.id, False, who="person")
    assert blank.id in db.unit_of_work_ids()


def test_a_runs_hide_is_an_audited_action_and_undo_shows_the_page_again(db, tmp_path):
    """Review finding: the run's own hide went around the action layer, so it had no audit row and no Undo."""
    from fichero_server.actions.registry import ActionContext, registry
    from fichero_server.models import ActionAudit
    from fichero_server.recipes.page_crop import crop_pages

    blank, _ = _page(db, tmp_path, "blank.png", _graph_paper(ink=False))
    crop_pages(db, [blank.id], "run-7", prepare=True)
    assert db.get(Document, blank.id).exclude_from_processing is True

    audits = [a for a in db.query(ActionAudit) if a.action_name == "image.mark_blank"]
    assert len(audits) == 1 and audits[0].run_id == "run-7"
    reg = registry.get("image.mark_blank")
    assert reg.undoable
    ctx = ActionContext(actor="person", library_path=str(tmp_path), is_bootstrap=True)
    registry.invoke(db, *reg.invert(audits[0].before, audits[0].after, ctx), ctx)

    shown = db.get(Document, blank.id)
    assert shown.exclude_from_processing is False and "blank" not in (shown.metadata or {})
    assert db.query(ImageEditChain, document_id=blank.id)[0].operations == []


def test_a_persons_answer_clears_the_blank_proposal_and_undo_brings_it_back(db, tmp_path):
    """Review finding: a `blank` proposal was stored and nothing showed it. The app lists pages whose metadata holds one;
    hiding or keeping it is a person's word, which removes it from the list, and Undo puts it back."""
    from fichero_server.actions.registry import ActionContext, registry
    from fichero_server.models import ActionAudit
    from fichero_server.recipes.page_crop import crop_pages
    from tests.unit.media.test_turn_straighten_blank import _ledger_with_strokes

    page, _ = _page(db, tmp_path, "strokes.png", _ledger_with_strokes(3))
    crop_pages(db, [page.id], "run-1", prepare=True)
    proposal = db.get(Document, page.id).metadata["prep_proposals"]["blank"]
    assert "kept, not hidden" in proposal["reason"] and not db.get(Document, page.id).exclude_from_processing

    ctx = ActionContext(actor="person", library_path=str(tmp_path), is_bootstrap=True)
    kept = registry.invoke(db, "image.mark_blank", {"document_id": page.id, "blank": False}, ctx)
    assert "blank" not in db.get(Document, page.id).metadata["prep_proposals"]
    crop_pages(db, [page.id], "run-2", prepare=True)  # the person's word stands: no new proposal
    assert "blank" not in db.get(Document, page.id).metadata["prep_proposals"]

    audit = db.get(ActionAudit, kept.audit_id)
    reg = registry.get("image.mark_blank")
    registry.invoke(db, *reg.invert(audit.before, audit.after, ctx), ctx)
    assert db.get(Document, page.id).metadata["prep_proposals"]["blank"] == proposal
