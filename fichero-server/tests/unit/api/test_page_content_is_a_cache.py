"""#5077: `Document.page_content` is a CACHE of the page's derived text, refreshed by ONE writer
(`actions/page_text_cache.py`, called from `registry.invoke`) whenever a reading changes or a choice
moves. Built on `seeded_converted_page`."""
from __future__ import annotations

import pytest

import fichero_server.api.routes.document.content_representations  # noqa: F401
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.api.routes.document.segment_conversion import live_rows_in_order
from fichero_server.media.transcript_alignment_service import resolve_transcript
from fichero_server.models import ActionAudit, Artifact, ContentRepresentation, Document

from .seeded_converted_page import seed_page

pytestmark = pytest.mark.source_model

CTX = ActionContext(actor="historian", library_path=None, is_bootstrap=True)
CORRECTED = "In the year of Our Lord and Saviour"


def _converted(db, client):
    _, page, art = seed_page(db)
    r = client.put(f"/api/artifacts/{art.id}/regions", json={"op": "move", "indices": [3], "bbox": [0.5, 0.9, 0.1, 0.05]})
    assert r.status_code == 200
    return page, art, live_rows_in_order(db, db.get(Artifact, art.id).geometry_superseded_by_pass_id)[0]


def _correct(db, page, row, content=CORRECTED):
    rid = registry.invoke(db, "representation.create", {
        "document_id": page.id, "segment_id": row.id, "kind": "transcription", "content": content}, CTX).result["id"]
    return registry.invoke(db, "reading.choose", {"segment_id": row.id, "kind": "transcription", "representation_id": rid}, CTX)


class TestAReadingChangeRefreshesTheCache:
    def test_a_correction_reaches_page_content(self, db, client):
        page, art, row = _converted(db, client)
        _correct(db, page, row)
        text = db.get(Document, page.id).page_content
        assert text.startswith(CORRECTED) and text.endswith("sailed from Cadiz")

    def test_the_cache_is_the_derived_text_byte_for_byte(self, db, client):
        page, art, row = _converted(db, client)
        _correct(db, page, row)
        derived = client.get(f"/api/segments/document/{page.id}/text").json()["text"]
        assert db.get(Document, page.id).page_content == derived

    def test_undo_puts_the_cache_back(self, db, client):
        page, art, row = _converted(db, client)
        before = db.get(Document, page.id).page_content
        result = _correct(db, page, row)
        assert db.get(Document, page.id).page_content != before
        assert client.post(f"/api/actions/audit/{result.audit_id}/undo").status_code == 200
        first = [a for a in db.all(ActionAudit) if a.action_name == "representation.create"][-1]
        assert client.post(f"/api/actions/audit/{first.id}/undo").status_code == 200
        assert db.get(Document, page.id).page_content.startswith("In the year of our Lord ")

    def test_search_is_re_embedded_with_the_corrected_text(self, db, client, monkeypatch):
        page, art, row = _converted(db, client)
        import threading, time

        seen = []
        monkeypatch.setattr(type(db), "embed", lambda self, doc, *a, **k: seen.append(doc.page_content))
        _correct(db, page, row)
        deadline = time.time() + 10
        while not seen and time.time() < deadline:
            time.sleep(0.05)  # the embed runs on a background thread
        assert seen and seen[-1].startswith(CORRECTED)

    def test_corrections_do_not_wait_for_the_embedder(self, db, client, monkeypatch):
        import threading

        page, art, row = _converted(db, client)
        release = threading.Event()
        started = threading.Event()
        monkeypatch.setattr(type(db), "embed", lambda self, doc, *a, **k: (started.set(), release.wait(10)))
        try:
            _correct(db, page, row)  # would hang for 10 s if the embed ran on the request path
            assert started.wait(5)
        finally:
            release.set()

    def test_a_page_a_person_edited_directly_is_left_alone(self, db, client):
        page, art, row = _converted(db, client)
        doc = db.get(Document, page.id)
        doc.page_content = "my own words"
        doc.metadata = {**(doc.metadata or {}), "page_content_user_edited_at": "2026-09-26T00:00:00Z"}
        db.save(doc)
        _correct(db, page, row)
        assert db.get(Document, page.id).page_content == "my own words"

    def test_a_refresh_that_cannot_run_fails_the_action_and_the_reading_is_not_written(self, db, client, monkeypatch):
        from fichero_server.actions import page_text_cache

        page, art, row = _converted(db, client)
        monkeypatch.setattr(page_text_cache, "refresh_in_transaction", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
        with pytest.raises(RuntimeError):
            registry.invoke(db, "representation.create", {
                "document_id": page.id, "segment_id": row.id, "kind": "transcription", "content": CORRECTED}, CTX)
        assert [r for r in db.query(ContentRepresentation, segment_id=row.id) if r.content == CORRECTED] == []

    def test_a_geometry_only_edit_does_not_touch_the_cache(self, db, client):
        page, art, row = _converted(db, client)
        doc = db.get(Document, page.id)
        doc.page_content = "left as it was"
        db.save(doc)
        assert client.put(f"/api/artifacts/{art.id}/regions", json={"op": "move", "indices": [1], "bbox": [0.5, 0.5, 0.3, 0.05]}).status_code == 200
        assert db.get(Document, page.id).page_content == "left as it was"


class TestAMembershipChangeRefreshesTheCache:
    """Delete, undelete, merge and combine change which lines the derived text has (#5077)."""

    def _cache(self, db, page):
        return db.get(Document, page.id).page_content

    def test_deleting_a_box_removes_its_line(self, db, client):
        page, art, row = _converted(db, client)
        r = client.put(f"/api/artifacts/{art.id}/regions", json={"op": "delete", "indices": [3]})
        assert r.status_code == 200
        derived = client.get(f"/api/segments/document/{page.id}/text").json()["text"]
        assert self._cache(db, page) == derived
        assert "Cadiz" not in derived, "the box is gone and so is its line"

    def test_undoing_the_delete_brings_the_line_back(self, db, client):
        page, art, row = _converted(db, client)
        client.put(f"/api/artifacts/{art.id}/regions", json={"op": "delete", "indices": [3]})
        last = [a for a in db.all(ActionAudit) if a.action_name == "segment.convert_and_edit"][-1]
        assert client.post(f"/api/actions/audit/{last.id}/undo").status_code == 200
        assert "Cadiz" in self._cache(db, page)
        assert self._cache(db, page) == client.get(f"/api/segments/document/{page.id}/text").json()["text"]

    def test_combining_two_boxes_keeps_the_cache_equal_to_the_derived_text(self, db, client):
        page, art, row = _converted(db, client)
        assert client.put(f"/api/artifacts/{art.id}/regions", json={"op": "combine", "indices": [1, 2]}).status_code == 200
        assert self._cache(db, page) == client.get(f"/api/segments/document/{page.id}/text").json()["text"]

    def test_a_plain_move_does_not_run_the_refresh(self, db, client, monkeypatch):
        from fichero_server.actions import page_text_cache

        page, art, row = _converted(db, client)
        calls = []
        import fichero_server.api.routes.document.segment_readings as sr
        monkeypatch.setattr(sr, "document_text", lambda *a, **k: calls.append(1) or (_ for _ in ()).throw(AssertionError("derived for a move")))
        assert client.put(f"/api/artifacts/{art.id}/regions", json={"op": "move", "indices": [1], "bbox": [0.5, 0.5, 0.3, 0.05]}).status_code == 200
        assert calls == []


class TestTheAlignerIsExempt:
    def test_a_curated_page_aligns_against_the_machines_text_not_the_cache(self, db, client):
        page, art, row = _converted(db, client)
        _correct(db, page, row)
        assert db.get(Document, page.id).page_content.startswith(CORRECTED)
        assert resolve_transcript(db, page.id) == db.get(Artifact, art.id).content

    def test_an_unedited_page_still_prefers_its_page_content(self, db):
        _, page, art = seed_page(db)
        assert resolve_transcript(db, page.id) == db.get(Document, page.id).page_content


class TestAChangeOnAPassNobodyReadsDoesNotDerive:
    """The import that spent 38 of its 44 seconds re-reading a page whose text had not changed
    (#5085 neighbour): readings written on a pass that is not the working pass cannot change the
    derived text. Skipped by WHICH PASS, not by action name, so every future caller with the same
    property is covered."""

    def _second_pass_with_a_segment(self, db, page):
        from fichero_server.models.anchors import SourceAnchor

        new_pass = registry.invoke(db, "segment.pass_create", {"document_id": page.id, "name": "imported", "run_id": "run-x"}, CTX).result
        pass_id = new_pass.get("pass_id") or new_pass.get("id")
        seg = registry.invoke(db, "segment.create", {
            "document_id": page.id, "pass_id": pass_id, "kind": "line",
            "anchor": SourceAnchor(document_id=page.id, rect=[0.1, 0.9, 0.5, 0.05]).model_dump(mode="json")}, CTX).result
        return pass_id, seg["segment_ids"][0]

    def test_a_reading_on_a_non_working_pass_does_not_read_the_page(self, db, client, monkeypatch):
        import fichero_server.api.routes.document.segment_readings as sr

        page, art, row = _converted(db, client)
        before = db.get(Document, page.id).page_content
        pass_id, seg_id = self._second_pass_with_a_segment(db, page)
        monkeypatch.setattr(sr, "document_text", lambda *a, **k: (_ for _ in ()).throw(AssertionError("derived a page nobody reads")))
        registry.invoke(db, "representation.create", {"document_id": page.id, "segment_id": seg_id,
                        "kind": "transcription", "content": "imported words"}, CTX)
        assert db.get(Document, page.id).page_content == before

    def test_choosing_that_pass_as_the_working_pass_does_refresh(self, db, client):
        page, art, row = _converted(db, client)
        pass_id, seg_id = self._second_pass_with_a_segment(db, page)
        registry.invoke(db, "representation.create", {"document_id": page.id, "segment_id": seg_id,
                        "kind": "transcription", "content": "imported words"}, CTX)
        assert "imported words" not in db.get(Document, page.id).page_content
        registry.invoke(db, "pass.choose_working", {"document_id": page.id, "pass_id": pass_id}, CTX)
        assert db.get(Document, page.id).page_content == "imported words"
