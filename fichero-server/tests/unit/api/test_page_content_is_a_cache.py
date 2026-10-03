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
from fichero_server.models.segments import Segment

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
        import time

        seen = []
        monkeypatch.setattr(type(db), "embed", lambda self, doc, *a, **k: seen.append(doc.page_content))
        _correct(db, page, row)
        # The embed is a job on the one local-model lane (#5359): it can queue behind another test's
        # first real embedder load (~13 s measured), so the wait is generous; it returns when seen.
        deadline = time.time() + 60
        while not seen and time.time() < deadline:
            time.sleep(0.05)
        assert seen and seen[-1].startswith(CORRECTED)

    def test_corrections_do_not_wait_for_the_embedder(self, db, client, monkeypatch):
        import threading

        page, art, row = _converted(db, client)
        release = threading.Event()
        started = threading.Event()
        monkeypatch.setattr(type(db), "embed", lambda self, doc, *a, **k: (started.set(), release.wait(10)))
        try:
            _correct(db, page, row)  # would hang for 10 s if the embed ran on the request path
            assert started.wait(60)  # may queue behind another job on the lane; see above
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


class TestUndoingAMoveIsAsCheapAsTheMove:
    """Slice 12's first finding (#4940). A plain move was exempt from the page-text refresh; its
    UNDO -- a `segment.restore_version` -- was not, and on the trial's 20,000-shape page one undo
    re-derived the whole page: ~14 s against the editor's 100 ms. A restore now records whether
    it put back anything that decides the text, and only then refreshes."""

    def _move_one_row(self, db, row):
        live = db.get(Segment, row.id)
        anchor = live.anchor.model_dump(mode="json")
        anchor["rect"][0] = min(0.9, anchor["rect"][0] + 0.01)
        return registry.invoke(db, "segment.update", {
            "segment_id": row.id, "expected_version": live.version, "anchor": anchor}, CTX)

    def test_undoing_a_move_does_not_derive_the_page(self, db, client, monkeypatch):
        import fichero_server.api.routes.document.segment_readings as sr

        page, art, row = _converted(db, client)
        moved = self._move_one_row(db, row)
        calls = []
        monkeypatch.setattr(sr, "document_text", lambda *a, **k: calls.append(1) or (_ for _ in ()).throw(AssertionError("derived for an undo of a move")))
        assert client.post(f"/api/actions/audit/{moved.audit_id}/undo").status_code == 200
        assert calls == []

    def test_undoing_a_furniture_change_still_refreshes(self, db, client):
        """The exemption must not reach a restore that changes which lines count: furniture is
        left out of the derived text, so undoing it puts a line back."""
        page, art, row = _converted(db, client)
        live = db.get(Segment, row.id)
        changed = registry.invoke(db, "segment.update", {
            "segment_id": row.id, "expected_version": live.version, "is_furniture": True}, CTX)
        without = db.get(Document, page.id).page_content
        assert client.post(f"/api/actions/audit/{changed.audit_id}/undo").status_code == 200
        restored = db.get(Document, page.id).page_content
        assert restored != without
        assert restored == client.get(f"/api/segments/document/{page.id}/text").json()["text"]

    def test_a_restore_that_does_not_say_is_refreshed_not_skipped_on_a_guess(self):
        from types import SimpleNamespace

        from fichero_server.actions.page_text_cache import _restore_may_change_text

        assert _restore_may_change_text(SimpleNamespace(after={"segment_id": "s"}), "segment.restore_version")
        assert not _restore_may_change_text(SimpleNamespace(after={"text_relevant": False}), "segment.restore_version")


class TestAPagesTextIsDerivedInOnePass:
    """Slice 12 (#4940): deriving a 20,000-segment page took ~14.5 s -- one forwarding walk, one
    representation query and one kinds query per LIVE row already in hand. The page's readings are
    now gathered in one batch (~1.8 s). These pin that the batch is the same answer, not a new one."""

    def test_the_batch_gives_exactly_what_each_row_would(self, db, client):
        import fichero_server.api.routes.document.segment_readings as sr
        from fichero_server.models.segments import SegmentPass

        page, art, row = _converted(db, client)
        _correct(db, page, row)  # one stored reading beside the provisional ones
        [pass_row] = [p for p in db.all(SegmentPass) if p.document_id == page.id]
        rows = [r for r in db.all(Segment) if r.pass_id == pass_row.id and r.deleted_at is None]

        batch = sr._readings_for_live_rows(db, rows, page.id, {})
        for r in rows:
            one = sr.readings_of_segment(db, r.id, artifact_memo={})
            assert [(i.id, i.kind, i.content) for i in batch[r.id]] == [(i.id, i.kind, i.content) for i in one], r.id
        assert any(i.provisional for items in batch.values() for i in items), "provisional readings are in the batch"
        assert any(not i.provisional for items in batch.values() for i in items), "and stored ones"

    def test_deriving_a_page_looks_no_row_up_one_at_a_time(self, db, client, monkeypatch):
        import fichero_server.api.routes.document.segment_readings as sr

        page, art, row = _converted(db, client)
        calls = []
        original = db.get
        monkeypatch.setattr(db, "get", lambda model, *a, **k: (calls.append(model.__name__), original(model, *a, **k))[1])
        derived = sr.document_text(db, page.id)
        assert derived.text
        assert calls.count("Segment") == 0, f"{calls.count('Segment')} single-row Segment lookups"


class TestTheTextIsDerivedFromTheLinesThatCarryIt:
    """Slice 12 (#4940): a 20,000-shape page's text took ~3.3 s, 2.9 s of it loading every word and
    character only to skip them for having no reading. The default order now loads only the rows
    that CAN carry text (~80-100 ms warm). These pin that it is the same answer as deriving from the
    whole pass after every kind of text-changing action, and that it never quietly goes back to
    loading the whole pass."""

    _PAGE = b"""<PcGts xmlns="http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15">
      <Page imageFilename="p.jpg" imageWidth="1000" imageHeight="1000">
        <TextRegion id="r"><Coords points="10,10 990,10 990,500 10,500"/>
          <TextLine id="l1"><Coords points="10,10 990,10 990,60 10,60"/>
            <Word id="w1"><Coords points="10,10 100,10 100,60 10,60"/></Word>
            <Word id="w2"><Coords points="110,10 200,10 200,60 110,60"/></Word>
            <TextEquiv><Unicode>first line</Unicode></TextEquiv></TextLine>
          <TextLine id="l2"><Coords points="10,70 990,70 990,120 10,120"/>
            <Word id="w3"><Coords points="10,70 100,70 100,120 10,120"/></Word>
            <TextEquiv><Unicode>second line</Unicode></TextEquiv></TextLine>
          <TextLine id="l3"><Coords points="10,130 990,130 990,180 10,180"/>
            <TextEquiv><Unicode>third line</Unicode></TextEquiv></TextLine>
        </TextRegion></Page></PcGts>"""

    def _imported_page(self, db, tmp_path):
        import fichero_server.api.routes.document.format_import  # noqa: F401
        from fichero_server.models import DocType, FileType, Status
        from fichero_server.models.segments import SegmentPass

        doc = Document(name="p.jpg", doc_type=DocType.file, file_type=FileType.image,
                       path="/p/p.jpg", status=Status.completed)
        db.save(doc)
        path = tmp_path / "p.page.xml"
        path.write_bytes(self._PAGE)
        registry.invoke(db, "format.import", {"document_id": doc.id, "path": str(path)}, CTX)
        [pass_row] = [p for p in db.all(SegmentPass) if p.document_id == doc.id]
        registry.invoke(db, "pass.choose_working", {"document_id": doc.id, "pass_id": pass_row.id}, CTX)
        rows = {r.metadata.get("foreign", {}).get("ref") or r.id: r for r in db.all(Segment) if r.pass_id == pass_row.id}
        lines = sorted((r for r in db.all(Segment) if r.pass_id == pass_row.id and r.kind == "line"),
                       key=lambda r: r.bbox_y)
        return doc, lines, rows

    def _both(self, db, document_id, monkeypatch):
        import fichero_server.api.routes.document.segment_readings as sr

        fast = sr.document_text(db, document_id)
        with monkeypatch.context() as m:
            m.setattr(sr, "_text_bearing_rows", lambda db_, doc_, pass_id, **_kw: db_.query(Segment, pass_id=pass_id))
            full = sr.document_text(db, document_id)
        return fast, full

    def _assert_same(self, fast, full):
        assert fast.text == full.text
        assert [(s.segment_id, s.start, s.end) for s in fast.spans] == [(s.segment_id, s.start, s.end) for s in full.spans]

    def test_furniture_delete_merge_and_split_all_derive_the_same_text(self, db, tmp_path, monkeypatch):
        doc, lines, _ = self._imported_page(db, tmp_path)
        l1, l2, l3 = lines
        self._assert_same(*self._both(db, doc.id, monkeypatch))

        v = lambda row: db.get(Segment, row.id).version  # noqa: E731
        registry.invoke(db, "segment.update", {"segment_id": l3.id, "expected_version": v(l3), "is_furniture": True}, CTX)
        fast, full = self._both(db, doc.id, monkeypatch)
        self._assert_same(fast, full)
        assert "third line" not in fast.text

        registry.invoke(db, "segment.delete", {"segment_ids": [l2.id], "expected_versions": {l2.id: v(l2)}}, CTX)
        fast, full = self._both(db, doc.id, monkeypatch)
        self._assert_same(fast, full)
        assert "second line" not in fast.text

        registry.invoke(db, "segment.update", {"segment_id": l3.id, "expected_version": v(l3), "is_furniture": False}, CTX)
        registry.invoke(db, "segment.merge", {
            "segment_ids": [l3.id, l1.id], "keep_id": l1.id,
            "expected_versions": {l3.id: v(l3), l1.id: v(l1)}}, CTX)
        self._assert_same(*self._both(db, doc.id, monkeypatch))

        registry.invoke(db, "segment.split", {
            "segment_id": l1.id, "expected_version": v(l1),
            "parts": [{"anchor": {"document_id": doc.id, "rect": [0.01, 0.01, 0.4, 0.05]}},
                      {"anchor": {"document_id": doc.id, "rect": [0.5, 0.01, 0.4, 0.05]}}]}, CTX)
        self._assert_same(*self._both(db, doc.id, monkeypatch))

    def test_a_converted_page_with_provisional_readings_derives_the_same_text(self, db, client, monkeypatch):
        """The other way a row carries text: a box in the artifact it was converted from, found
        by one SQL scan of `metadata.box_index`, not by loading the pass."""
        page, art, row = _converted(db, client)
        fast, full = self._both(db, page.id, monkeypatch)
        self._assert_same(fast, full)
        assert fast.text

    def test_it_never_loads_the_whole_pass(self, db, tmp_path, monkeypatch):
        """Fails if the default order ever falls back to `db.query(Segment, pass_id=...)`."""
        import fichero_server.api.routes.document.segment_readings as sr

        doc, lines, rows = self._imported_page(db, tmp_path)
        original = db.query

        def refuse_whole_pass(model, **filters):
            assert not (model is Segment and "pass_id" in filters and len(filters) == 1), (
                "the default-order derivation loaded every row of the pass"
            )
            return original(model, **filters)

        monkeypatch.setattr(db, "query", refuse_whole_pass)
        derived = sr.document_text(db, doc.id)
        assert "first line" in derived.text

    @pytest.mark.parametrize("named_order", [False, True])
    def test_each_reading_is_loaded_once_per_derivation(self, db, tmp_path, monkeypatch, named_order):
        """On the real Cherokee page (3,910 words) ~83% of deriving the text was hydrating rows,
        11,745 calls, because every reading was loaded TWICE: once for its segment id
        (`_text_bearing_rows`) and again for its content (`_readings_for_live_rows`). Counted
        here as hydrated readings; if either reader goes back to loading them itself, the count
        doubles and this fails. The text is pinned equal to deriving from the whole pass by
        `test_furniture_delete_merge_and_split_all_derive_the_same_text`."""
        import fichero_server.api.routes.document.segment_readings as sr

        doc, lines, rows = self._imported_page(db, tmp_path)
        stored = list(db.query(ContentRepresentation, document_id=doc.id))
        assert len(stored) == 3
        order = None
        if named_order:
            import fichero_server.api.routes.document.reading_orders  # noqa: F401  (registers the action)

            made = registry.invoke(
                db, "reading_order.create",
                {"document_id": doc.id, "pass_id": lines[0].pass_id, "seed_from_pass": True}, CTX,
            )
            order = made.result["order_id"]

        hydrated: list[str] = []
        original = db._hydrate_row

        def counting(model, columns, row):
            if model is ContentRepresentation:
                hydrated.append(model.__name__)
            return original(model, columns, row)

        monkeypatch.setattr(db, "_hydrate_row", counting)
        derived = sr.document_text(db, doc.id, order=order)
        assert "first line" in derived.text
        assert len(hydrated) == len(stored), f"{len(hydrated)} readings hydrated for {len(stored)} stored"
