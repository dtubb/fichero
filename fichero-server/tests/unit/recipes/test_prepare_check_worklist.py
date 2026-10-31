"""Proposals are stored on the page, listed as Pages to check, and a person's answer replaces the run's row
(`prep.unsure-becomes-a-proposal`, `prep.check.worklist-of-proposals-and-a-sample`, `prep.check.correction-replaces-the-runs-row`,
`prep.check.blank-mark-is-a-correction`, #5382). Fixtures are drawn here; no real page."""
from __future__ import annotations

from PIL import Image

from fichero_server.actions.registry import ActionContext, registry
from fichero_server.media.find_page import PageFound
from fichero_server.models import ActionAudit, DocType, Document, FileType, ImageEditChain
from tests.unit.media.test_turn_straighten_blank import _graph_paper

QUAD = ((0.1, 0.1), (0.9, 0.12), (0.88, 0.9), (0.12, 0.88))


def _page(db, tmp_path, name, image):
    path = tmp_path / name
    image.save(path)
    doc = Document(name=name, doc_type=DocType.file, file_type=FileType.image, path=str(path), metadata={})
    db.save(doc)
    return doc


def _finder(monkeypatch, confidence):
    from fichero_server.media import find_page as module

    found = PageFound(box=(0.1, 0.1, 0.8, 0.8), confidence=confidence, method="contour", quad=QUAD)
    monkeypatch.setattr(module, "find_page", lambda image: found)


def _ctx(tmp_path):
    return ActionContext(actor="person", library_path=str(tmp_path), is_bootstrap=True)


def _undo(db, tmp_path, result, name):
    audit = db.get(ActionAudit, result.audit_id)
    registry.invoke(db, *registry.get(name).invert(audit.before, audit.after, _ctx(tmp_path)), _ctx(tmp_path))


def test_an_unsure_page_box_is_stored_as_a_proposal_and_listed_in_words(db, tmp_path, monkeypatch):
    from fichero_server.recipes.page_crop import crop_pages
    from fichero_server.recipes.prepare_check import worklist

    _finder(monkeypatch, 0.6)
    page = _page(db, tmp_path, "a.png", _graph_paper(ink=True))

    crop_pages(db, [page.id], "run-1", prepare=True)

    proposal = db.get(Document, page.id).metadata["prep_proposals"]["page_box"]
    assert len(proposal["quad"]) == 4 and proposal["confidence"] == 0.6 and "faint" in proposal["words"][0]
    (item,) = worklist(db)
    assert item["id"] == page.id and item["kinds"] == ["page_box"] and not item["sample"]
    assert any("covers 64%" in w for w in item["words"])
    assert "page_box" not in db.get(Document, page.id).metadata, "an unsure box changes nothing: the page keeps its whole frame"


def test_a_later_sure_run_withdraws_the_proposal(db, tmp_path, monkeypatch):
    from fichero_server.recipes.page_crop import crop_pages
    from fichero_server.recipes.prepare_check import worklist

    page = _page(db, tmp_path, "a.png", _graph_paper(ink=True))
    _finder(monkeypatch, 0.6)
    crop_pages(db, [page.id], "run-1", prepare=True)
    _finder(monkeypatch, 0.95)
    crop_pages(db, [page.id], "run-2", prepare=True)
    assert worklist(db) == [] or all(i["sample"] for i in worklist(db))
    assert "page_box" not in db.get(Document, page.id).metadata.get("prep_proposals", {})


def test_squaring_a_proposal_replaces_the_runs_row_leaves_the_list_and_undo_puts_it_back(db, tmp_path, monkeypatch):
    from fichero_server.recipes.page_crop import crop_pages
    from fichero_server.recipes.prepare_check import worklist

    _finder(monkeypatch, 0.6)
    page = _page(db, tmp_path, "a.png", _graph_paper(ink=True))
    crop_pages(db, [page.id], "run-1", prepare=True)
    proposal = db.get(Document, page.id).metadata["prep_proposals"]["page_box"]

    done = registry.invoke(db, "image.square", {"document_id": page.id, "quad": [list(p) for p in QUAD]}, _ctx(tmp_path))

    (chain,) = db.query(ImageEditChain, document_id=page.id)
    (row,) = chain.operations
    assert row["who"] == "person" and row["replaces"]["values"]["quad"] == proposal["quad"], "the run's values stay beside the person's row"
    assert worklist(db) == []
    crop_pages(db, [page.id], "run-2", prepare=True)  # the person's word stands
    assert "page_box" not in db.get(Document, page.id).metadata["prep_proposals"]

    _undo(db, tmp_path, done, "image.square")
    assert db.get(Document, page.id).metadata["prep_proposals"]["page_box"] == proposal
    assert db.query(ImageEditChain, document_id=page.id)[0].operations == []
    assert [i["id"] for i in worklist(db)] == [page.id]


def test_accept_leaves_the_page_as_it_is_and_the_list(db, tmp_path, monkeypatch):
    from fichero_server.recipes.page_crop import crop_pages
    from fichero_server.recipes.prepare_check import worklist

    _finder(monkeypatch, 0.6)
    page = _page(db, tmp_path, "a.png", _graph_paper(ink=True))
    crop_pages(db, [page.id], "run-1", prepare=True)

    done = registry.invoke(db, "image.accept_proposal", {"document_id": page.id, "kind": "page_box"}, _ctx(tmp_path))
    assert worklist(db) == []
    _undo(db, tmp_path, done, "image.accept_proposal")
    assert [i["kinds"] for i in worklist(db)] == [["page_box"]]


def test_the_lines_that_do_not_agree_make_a_turn_proposal_a_person_can_answer_with_a_turn(db, tmp_path, monkeypatch):
    from fichero_server.media import turn_by_text as module
    from fichero_server.recipes.page_crop import crop_pages
    from fichero_server.recipes.prepare_check import worklist

    _finder(monkeypatch, 0.95)
    monkeypatch.setattr(module, "turn_by_text", lambda image, **kw: {
        "angle": 0, "lines": 9, "reason": "the lines do not agree which way the page runs"})
    page = _page(db, tmp_path, "a.png", _graph_paper(ink=True))
    crop_pages(db, [page.id], "run-1", prepare=True)
    (item,) = worklist(db)
    assert item["kinds"] == ["turn"] and "do not agree" in item["words"][0]

    registry.invoke(db, "image.rotate", {"document_id": page.id, "angle": 90}, _ctx(tmp_path))
    assert all(i["sample"] for i in worklist(db))  # answered: only the confident page's sample is left (page_region now kept)


def test_a_person_marking_a_page_blank_answers_its_proposal(db, tmp_path):
    from fichero_server.recipes.page_crop import crop_pages
    from fichero_server.recipes.prepare_check import worklist
    from tests.unit.media.test_turn_straighten_blank import _ledger_with_strokes

    page = _page(db, tmp_path, "s.png", _ledger_with_strokes(3))
    crop_pages(db, [page.id], "run-1", prepare=True)
    assert [i["kinds"] for i in worklist(db)] == [["blank"]]
    registry.invoke(db, "image.mark_blank", {"document_id": page.id, "blank": True}, _ctx(tmp_path))
    assert worklist(db) == [], "hidden by the person: it is no unit of work and no proposal"


def test_proposals_come_first_then_one_confident_page_in_twenty(db, tmp_path, monkeypatch):
    from fichero_server.recipes.page_crop import crop_pages
    from fichero_server.recipes.prepare_check import worklist

    image = Image.new("RGB", (60, 80), "white")
    ids = [_page(db, tmp_path, f"p{i:02d}.png", image).id for i in range(41)]
    _finder(monkeypatch, 0.95)
    crop_pages(db, ids, "run-1")
    flagged = db.get(Document, ids[7])
    flagged.metadata = {**flagged.metadata, "prep_proposals": {"turn": {"reason": "the lines do not agree which way the page runs"}}}
    db.save(flagged)
    items = worklist(db)
    assert items[0]["id"] == ids[7] and not items[0]["sample"]
    assert [i["sample"] for i in items] == [False, True, True], "41 pages, 40 confident: those at 0 and 20"
    assert "sample" in items[1]["words"][0]


def test_the_route_and_the_count(db, tmp_path, monkeypatch, client):
    from fichero_server.recipes.page_crop import crop_pages

    _finder(monkeypatch, 0.6)
    page = _page(db, tmp_path, "a.png", _graph_paper(ink=True))
    crop_pages(db, [page.id], "run-1", prepare=True)
    got = client.get("/api/recipes/prepare-images/check")
    assert got.status_code == 200, got.text
    body = got.json()
    assert body["count"] == 1 and body["proposed"] == 1 and body["items"][0]["id"] == page.id
