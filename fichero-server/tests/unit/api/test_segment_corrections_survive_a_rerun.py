"""#5072 segment-level probe: a person's correction to a converted page (geometry and reading) versus
the things that come after it -- a vision rerun, an undo/redo. Built on `seeded_converted_page`.

What is pinned here was OBSERVED, not assumed (2026-09-26). Passing tests are the negative results
(the premise HOLDS there); the strict xfails are the defects, each naming its issue. They are
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
    @pytest.mark.xfail(strict=True, reason="#4992: anchor_for replaces rect only; polygon and baseline stay where the line was")
    def test_the_polygon_and_baseline_follow_the_move(self, db, client):
        _, _, art = seed_page(db)
        _move(client, art.id, 1, [0.5, 0.5, 0.3, 0.05])
        row = _rows(db, art.id)[1]
        assert row.anchor.rect == [0.5, 0.5, 0.3, 0.05]
        assert min(y for _, y in row.anchor.polygon) == pytest.approx(0.5)
        assert min(y for _, y in row.baseline) >= 0.5

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

    @pytest.mark.xfail(strict=True, reason="#4993 (as observed, worse than filed): the in-place branch's refusal is swallowed by the per-page except; the run reports nothing failed and the new result is dropped")
    def test_a_pdf_page_rerun_is_not_silently_dropped(self, db, client, test_package):
        parent, page, art = seed_page(db)
        _move(client, art.id, 1, [0.5, 0.5, 0.3, 0.05])
        ids = _rerun_pdf_page_path(db, test_package, parent)
        assert ids, "the run saved nothing and said nothing"
        assert len(db.query(Artifact, document_id=page.id)) == 2

    def test_a_pdf_page_rerun_does_not_raise_it_logs_and_returns_no_artifact(self, db, client, test_package, caplog):
        """What actually happens today, so the change is visible when it comes."""
        parent, page, art = seed_page(db)
        _move(client, art.id, 1, [0.5, 0.5, 0.3, 0.05])
        with caplog.at_level(logging.WARNING):
            ids = _rerun_pdf_page_path(db, test_package, parent)
        assert ids == []
        assert any("was converted to segments" in r.getMessage() for r in caplog.records)
        assert len(db.query(Artifact, document_id=page.id)) == 1
        assert _rows(db, art.id)[1].anchor.rect == [0.5, 0.5, 0.3, 0.05]

    @pytest.mark.xfail(strict=True, reason="#5081: the page-child path writes Document.page_content BEFORE the artifact save the refusal then blocks, so the page text becomes the rerun's while the artifact and rows keep the old one")
    def test_a_refused_pdf_page_rerun_leaves_the_page_text_alone(self, db, client, test_package):
        parent, page, art = seed_page(db)
        was = db.get(Document, page.id).page_content
        _move(client, art.id, 1, [0.5, 0.5, 0.3, 0.05])
        _rerun_pdf_page_path(db, test_package, parent)
        assert db.get(Document, page.id).page_content == was


class TestRedoOfAFirstEdit:
    @pytest.mark.xfail(strict=True, reason="#4991: redo replays the recorded POSITION, so after a delete above it the redo moves a different box")
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
