"""A correction applied to the folder's other pages (`prep.check.apply-correction-to-the-folder`, #5382, #6192).

WHY: a notebook photographed the same way is cropped or turned the same way on every page; fixing one page and copying the
fix, after seeing three pages with it, is faster than fixing 300. Fixtures are drawn here; no real page.
"""
from __future__ import annotations

import base64
import io

from PIL import Image

import fichero_server.api.routes.ingest.image_editing  # noqa: F401  (registers the image.* actions)
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.media.blank_page import mark_blank
from fichero_server.models import ActionAudit, DocType, Document, FileType, ImageEditChain

QUAD = [[0.1, 0.1], [0.9, 0.12], [0.88, 0.9], [0.12, 0.88]]


def _folder(db, pages=5):
    folder = Document(name="Box 1", doc_type=DocType.folder)
    db.save(folder)
    docs = []
    for i in range(pages):
        path = db.path.parent / "files" / f"p{i}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (200 + i, 120), (230, 225, 210)).save(path)
        doc = Document(name=f"p{i}.png", parent_id=folder.id, path=str(path), file_type=FileType.image, metadata={})
        db.save(doc)
        docs.append(doc)
    return folder, docs


def _ops(db, doc_id):
    rows = list(db.query(ImageEditChain, document_id=doc_id))
    return rows[0].operations if rows else []


def _ctx(tmp_path):
    return ActionContext(actor="person", library_path=str(tmp_path), is_bootstrap=True)


def _params(folder, docs, op=None):
    return {"folder_id": folder.id, "source_document_id": docs[0].id, "operation": op or {"op": "square", "quad": QUAD}}


def test_the_preview_shows_first_middle_and_last_and_writes_no_row(db, tmp_path, client):
    folder, docs = _folder(db, 7)
    got = client.post("/api/images/batch-prepare/preview", json=_params(folder, docs))
    assert got.status_code == 200, got.text
    body = got.json()
    assert [p["document_id"] for p in body["previews"]] == [docs[1].id, docs[4].id, docs[6].id], "first, middle, last of the pages left"
    assert body["pages"] == 6
    assert Image.open(io.BytesIO(base64.b64decode(body["previews"][0]["image_base64"]))).width > 0
    assert all(_ops(db, d.id) == [] for d in docs), "a preview writes no row"
    assert all(a.action_name != "image.batch_prepare" for a in db.query(ActionAudit))


def test_the_batch_copies_the_correction_to_every_other_page_with_one_batch_id(db, tmp_path):
    folder, docs = _folder(db)
    result = registry.invoke(db, "image.batch_prepare", _params(folder, docs), _ctx(tmp_path))

    assert set(result.result["applied"]) == {d.id for d in docs[1:]}
    rows = [_ops(db, d.id) for d in docs[1:]]
    assert all(len(r) == 1 and r[0]["who"] == "person" and r[0]["params"]["quad"] == QUAD for r in rows)
    assert {r[0]["batch_id"] for r in rows} == {result.result["batch_id"]}
    assert result.audit_id == result.result["batch_id"]
    assert _ops(db, docs[0].id) == [], "the page the correction came from already has it"


def test_pages_hidden_as_blank_or_already_done_by_a_person_are_left_out_and_said(db, tmp_path):
    folder, docs = _folder(db)
    mark_blank(db, docs[1].id, True, who="run r1")
    registry.invoke(db, "image.square", {"document_id": docs[2].id, "quad": QUAD}, _ctx(tmp_path))
    result = registry.invoke(db, "image.batch_prepare", _params(folder, docs), _ctx(tmp_path))
    assert set(result.result["applied"]) == {docs[3].id, docs[4].id}
    why = {s["id"]: s["why"] for s in result.result["skipped"]}
    assert "blank" in why[docs[1].id] and "person" in why[docs[2].id]


def test_the_whole_batch_undoes_as_one(db, tmp_path):
    folder, docs = _folder(db)
    result = registry.invoke(db, "image.batch_prepare", _params(folder, docs), _ctx(tmp_path))
    audit = db.get(ActionAudit, result.audit_id)
    assert audit is not None
    ctx = _ctx(tmp_path)
    registry.invoke(db, *registry.get("image.batch_prepare").invert(audit.before, audit.after, ctx), ctx)
    assert all(_ops(db, d.id) == [] for d in docs)


def test_one_page_leaves_the_batch_and_the_others_keep_it(db, tmp_path):
    folder, docs = _folder(db)
    result = registry.invoke(db, "image.batch_prepare", _params(folder, docs), _ctx(tmp_path))
    done = registry.invoke(db, "image.undo_batch_page",
                           {"document_id": docs[2].id, "batch_id": result.result["batch_id"]}, _ctx(tmp_path))
    assert _ops(db, docs[2].id) == []
    assert all(len(_ops(db, d.id)) == 1 for d in (docs[1], docs[3], docs[4]))
    audit = db.get(ActionAudit, done.audit_id)  # and that page's undo puts its row back
    ctx = _ctx(tmp_path)
    registry.invoke(db, *registry.get("image.undo_batch_page").invert(audit.before, audit.after, ctx), ctx)
    assert len(_ops(db, docs[2].id)) == 1


def test_a_turn_is_copied_as_degrees_and_a_square_needs_its_four_corners(db, tmp_path, client):
    folder, docs = _folder(db, 3)
    registry.invoke(db, "image.batch_prepare", _params(folder, docs, {"op": "rotate", "angle": 90}), _ctx(tmp_path))
    assert _ops(db, docs[1].id)[0]["params"] == {"angle": 90.0, "expand": True}
    bad = client.post("/api/images/batch-prepare/preview", json=_params(folder, docs, {"op": "square"}))
    assert bad.status_code == 422
