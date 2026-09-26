"""#5072 segment-level probe: a person's correction to a converted page (geometry and reading) versus
the things that come after it -- a vision rerun, an undo/redo. Built on `seeded_converted_page`.

What is pinned here was OBSERVED, not assumed (2026-09-26). Passing tests are the negative results
(the premise HOLDS there); any strict xfail is an open defect, each naming its issue. They are
written as the behaviour the spec wants, so fixing the defect turns the xfail into an XPASS failure
and the marker has to come off -- nothing is fixed by this file.
"""
from __future__ import annotations

import asyncio
import logging

import pytest

import fichero_server.api.routes.document.content_representations  # noqa: F401  (registers the actions)
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.api.routes.document.segment_conversion import live_rows_in_order
from fichero_server.llm import LLMConfig
from fichero_server.media.ocr_geometry import OCRGeometryResult
from fichero_server.models import ActionAudit, Artifact, Document

from .seeded_converted_page import line_box, seed_page

pytestmark = pytest.mark.source_model

CFG = LLMConfig(provider="openai", model="gpt-4o")  # matches the seeded artifact's provider/model


def _rows(db, artifact_id):
    return live_rows_in_order(db, db.get(Artifact, artifact_id).geometry_superseded_by_pass_id)


def _move(client, artifact_id, index, bbox):
    r = client.put(f"/api/artifacts/{artifact_id}/regions", json={"op": "move", "indices": [index], "bbox": bbox})
    assert r.status_code == 200, r.text


def _new_result():
    return OCRGeometryResult(provider="openai", text="brand new", boxes=[line_box(0, 0, "brand new")])


def _rerun_image_path(db, test_package, page):
    from fichero_server.workflows.tools.llm_base import LLMToolConfig, save_file_artifact

    return asyncio.run(save_file_artifact(
        None, "brand new", page.id, str(test_package), CFG, "run-2",
        LLMToolConfig(artifact_type="transcription"), ocr_geometry=_new_result(),
        document=db.get(Document, page.id),
    ))


def _rerun_pdf_page_path(db, test_package, parent):
    from fichero_server.workflows.tools.vision_base import _propagate_to_page_children

    return asyncio.run(_propagate_to_page_children(
        parent.id, ["brand new"], str(test_package), artifact_type="transcription",
        llm_config=CFG, page_geometries=[_new_result()],
    ))


class TestAMovedBoxKeepsItsShape:
    def test_the_polygon_and_baseline_follow_the_move(self, db, client):
        _, _, art = seed_page(db)
        _move(client, art.id, 1, [0.5, 0.5, 0.3, 0.05])
        row = _rows(db, art.id)[1]
        assert row.anchor.rect == [0.5, 0.5, 0.3, 0.05]
        assert min(y for _, y in row.anchor.polygon) == pytest.approx(0.5)
        assert min(y for _, y in row.baseline) >= 0.5

    def test_a_resize_scales_the_shape_and_undo_puts_it_back(self, db, client):
        _, _, art = seed_page(db)
        _move(client, art.id, 0, [0.1, 0.1, 0.6, 0.05])  # converts; box 0 moves nowhere
        was = _rows(db, art.id)[1]
        was_poly, was_base = [list(p) for p in was.anchor.polygon], [list(p) for p in was.baseline]
        _move(client, art.id, 1, [0.2, 0.2, 0.3, 0.10])  # half as wide, twice as tall
        row = _rows(db, art.id)[1]
        xs = [x for x, _ in row.anchor.polygon]
        ys = [y for _, y in row.anchor.polygon]
        assert (min(xs), max(xs)) == (pytest.approx(0.2), pytest.approx(0.5))
        assert (min(ys), max(ys)) == (pytest.approx(0.2), pytest.approx(0.3))
        assert row.baseline[0][0] == pytest.approx(0.2) and row.baseline[1][0] == pytest.approx(0.5)
        first = [a for a in db.all(ActionAudit) if a.action_name == "segment.convert_and_edit"][-1]
        assert client.post(f"/api/actions/audit/{first.id}/undo").status_code == 200
        back = _rows(db, art.id)[1]
        assert back.anchor.polygon == was_poly and back.baseline == was_base

    def test_a_box_with_no_polygon_stays_without_one(self, db, client):
        _, _, art = seed_page(db)
        a = db.get(Artifact, art.id)
        a.ocr_geometry.boxes[1].metadata = {}
        db.save(a)
        _move(client, art.id, 1, [0.5, 0.5, 0.3, 0.05])
        row = _rows(db, art.id)[1]
        assert row.anchor.polygon is None and row.baseline is None

    def test_the_bbox_columns_do_follow_the_rect(self, db, client):
        """The part of #4992 that is fine: reads by area are right."""
        _, _, art = seed_page(db)
        _move(client, art.id, 1, [0.5, 0.5, 0.3, 0.05])
        row = _rows(db, art.id)[1]
        assert (row.bbox_x, row.bbox_y) == (0.5, 0.5)


class TestARerunOnAnEditedPage:
    def test_the_image_path_saves_a_new_artifact_and_leaves_the_edited_rows_alone(self, db, client, test_package):
        """Negative result: the path every producer but one takes already does what the spec wants."""
        _, page, art = seed_page(db)
        _move(client, art.id, 1, [0.5, 0.5, 0.3, 0.05])
        new_id = _rerun_image_path(db, test_package, page)
        assert new_id and new_id != art.id
        assert _rows(db, art.id)[1].anchor.rect == [0.5, 0.5, 0.3, 0.05], "the person's move survives"
        text = client.get(f"/api/segments/document/{page.id}/text").json()["text"]
        assert text.startswith("In the year of our Lord"), "the page still reads from the edited pass"

    def test_a_corrected_reading_survives_a_rerun_in_the_derived_text(self, db, client, test_package):
        _, page, art = seed_page(db)
        _move(client, art.id, 1, [0.5, 0.5, 0.3, 0.05])
        seg = _rows(db, art.id)[2]
        ctx = ActionContext(actor="historian", library_path=None, is_bootstrap=True)
        rid = registry.invoke(db, "representation.create", {
            "document_id": page.id, "segment_id": seg.id, "kind": "transcription",
            "content": "and fifty-three, the ship"}, ctx).result["id"]
        registry.invoke(db, "reading.choose", {"segment_id": seg.id, "kind": "transcription",
                                               "representation_id": rid}, ctx)
        _rerun_image_path(db, test_package, page)
        text = client.get(f"/api/segments/document/{page.id}/text").json()["text"]
        assert "fifty-three" in text

    def test_a_pdf_page_rerun_is_not_silently_dropped(self, db, client, test_package):
        parent, page, art = seed_page(db)
        _move(client, art.id, 1, [0.5, 0.5, 0.3, 0.05])
        ids = _rerun_pdf_page_path(db, test_package, parent)
        assert ids, "the run saved nothing and said nothing"
        assert len(db.query(Artifact, document_id=page.id)) == 2

    def test_a_pdf_page_rerun_saves_a_new_artifact_and_says_nothing_failed(self, db, client, test_package, caplog):
        """#4993: the outlier path now behaves like the image path."""
        parent, page, art = seed_page(db)
        _move(client, art.id, 1, [0.5, 0.5, 0.3, 0.05])
        with caplog.at_level(logging.WARNING):
            ids = _rerun_pdf_page_path(db, test_package, parent)
        assert len(ids) == 1 and ids[0] != art.id
        assert not any("Failed to save per-page" in r.getMessage() for r in caplog.records)
        assert len(db.query(Artifact, document_id=page.id)) == 2
        assert _rows(db, art.id)[1].anchor.rect == [0.5, 0.5, 0.3, 0.05]

    def test_a_typed_conversion_refusal_is_not_swallowed(self, db, client, test_package, monkeypatch):
        """Were the in-place guard ever reached, the run must see the refusal, not `[]`/`None`."""
        from fichero_server.api.routes.document import segment_conversion as sc

        parent, page, art = seed_page(db)
        _move(client, art.id, 1, [0.5, 0.5, 0.3, 0.05])
        monkeypatch.setattr(sc, "is_converted", lambda a: False)
        monkeypatch.setattr(sc, "assert_geometry_writable", lambda a: (_ for _ in ()).throw(sc.GeometryFrozenByConversion(a.id, "p")))
        with pytest.raises(sc.GeometryFrozenByConversion):
            _rerun_pdf_page_path(db, test_package, parent)

    def test_a_refused_pdf_page_rerun_leaves_the_page_text_alone(self, db, client, test_package):
        parent, page, art = seed_page(db)
        was = db.get(Document, page.id).page_content
        _move(client, art.id, 1, [0.5, 0.5, 0.3, 0.05])
        _rerun_pdf_page_path(db, test_package, parent)
        assert db.get(Document, page.id).page_content == was


class TestRedoOfAFirstEdit:
    def test_redo_moves_the_box_that_was_moved_not_whatever_sits_there_now(self, db, client):
        _, _, art = seed_page(db)
        _move(client, art.id, 1, [0.5, 0.5, 0.3, 0.05])
        first = [a for a in db.all(ActionAudit) if a.action_name == "segment.convert_and_edit"][-1]
        assert client.post(f"/api/actions/audit/{first.id}/undo").status_code == 200
        moved_id = _rows(db, art.id)[1].id
        assert client.put(f"/api/artifacts/{art.id}/regions", json={"op": "delete", "indices": [0]}).status_code == 200
        undo_audit = [a for a in db.all(ActionAudit) if a.inverse_of == first.id][-1]
        assert client.post(f"/api/actions/audit/{undo_audit.id}/undo").status_code == 200
        by_id = {r.id: r for r in _rows(db, art.id)}
        assert by_id[moved_id].anchor.rect == [0.5, 0.5, 0.3, 0.05]

    def test_redo_of_a_delete_deletes_the_same_box_after_another_delete_above_it(self, db, client):
        _, _, art = seed_page(db)
        assert client.put(f"/api/artifacts/{art.id}/regions", json={"op": "delete", "indices": [2]}).status_code == 200
        first = [a for a in db.all(ActionAudit) if a.action_name == "segment.convert_and_edit"][-1]
        assert client.post(f"/api/actions/audit/{first.id}/undo").status_code == 200
        victim = _rows(db, art.id)[2].id
        assert client.put(f"/api/artifacts/{art.id}/regions", json={"op": "delete", "indices": [0]}).status_code == 200
        undo_audit = [a for a in db.all(ActionAudit) if a.inverse_of == first.id][-1]
        assert client.post(f"/api/actions/audit/{undo_audit.id}/undo").status_code == 200
        assert victim not in {r.id for r in _rows(db, art.id)}
        assert len(_rows(db, art.id)) == 2, "box 0 (deleted meanwhile) and the redone victim are both gone"

    def test_redo_refuses_when_its_box_is_gone_instead_of_editing_another(self, db, client):
        _, _, art = seed_page(db)
        _move(client, art.id, 1, [0.5, 0.5, 0.3, 0.05])
        first = [a for a in db.all(ActionAudit) if a.action_name == "segment.convert_and_edit"][-1]
        assert client.post(f"/api/actions/audit/{first.id}/undo").status_code == 200
        assert client.put(f"/api/artifacts/{art.id}/regions", json={"op": "delete", "indices": [1]}).status_code == 200
        before = [(r.id, r.anchor.rect) for r in _rows(db, art.id)]
        undo_audit = [a for a in db.all(ActionAudit) if a.inverse_of == first.id][-1]
        r = client.post(f"/api/actions/audit/{undo_audit.id}/undo")
        assert r.status_code == 409, r.text
        assert [(x.id, x.anchor.rect) for x in _rows(db, art.id)] == before
