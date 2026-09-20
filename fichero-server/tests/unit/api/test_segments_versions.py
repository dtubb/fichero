"""Source-model slice 5 — versions for each segment, and refusing a stale
edit (#4923).

`SegmentVersion`, compare-and-set (`segment.update`), the real versioned
`segment.delete`/`.undelete`, and `segment.restore_version`. Each test
names the behaviour id it pins.
"""

from __future__ import annotations

import json

import pytest

from fichero_server.actions.registry import ActionContext, registry
from fichero_server.models import (
    ActionAudit,
    DocType,
    Document,
    FileType,
    Segment,
    SegmentForwarding,
    SegmentPass,
    SegmentVersion,
    Status,
)
from fichero_server.models.anchors import SourceAnchor
from fichero_server.models.knowledge import Annotation, ProvenanceKind

pytestmark = pytest.mark.source_model


def _make_doc(db, name: str = "page.jpg") -> Document:
    doc = Document(
        name=name, doc_type=DocType.file, file_type=FileType.image,
        path=f"/path/{name}", status=Status.completed,
    )
    db.save(doc)
    return doc


def _ctx(db, *, actor: str = "daniel") -> ActionContext:
    return ActionContext(actor=actor, library_path=str(db.path.parent))


def _make_pass(db, document_id: str) -> SegmentPass:
    pass_row = SegmentPass(document_id=document_id, name="p", provenance_kind=ProvenanceKind.workflow)
    db.save(pass_row)
    return pass_row


def _make_segment(db, *, document_id: str, pass_id: str, rect: list[float], kind: str = "line") -> Segment:
    from fichero_server.models.segments import bbox_and_tile_from_anchor

    anchor = SourceAnchor(document_id=document_id, rect=rect)
    bbox_x, bbox_y, bbox_w, bbox_h, tile = bbox_and_tile_from_anchor(anchor)
    row = Segment(
        document_id=document_id, pass_id=pass_id, kind=kind, anchor=anchor,
        bbox_x=bbox_x, bbox_y=bbox_y, bbox_w=bbox_w, bbox_h=bbox_h, tile=tile,
        doc_kind=f"{document_id}:{kind}", provenance_kind=ProvenanceKind.workflow,
    )
    db.save(row)
    return row


class TestVersionedAlone:
    def test_three_updates_leave_three_versions_and_touch_nothing_else(self, db):
        """source.segment.versioned-alone."""
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        seg = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
        other = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.5, 0.5, 0.1, 0.1])
        other_before = other.model_dump(mode="json")
        ctx = _ctx(db)

        for i, rect in enumerate([[0.11, 0.11, 0.1, 0.1], [0.12, 0.12, 0.1, 0.1], [0.13, 0.13, 0.1, 0.1]]):
            current = db.get(Segment, seg.id)
            registry.invoke(
                db, "segment.update",
                {
                    "segment_id": seg.id, "expected_version": current.version,
                    "anchor": {"document_id": doc.id, "rect": rect},
                }, ctx,
            )

        versions = db.query(SegmentVersion, segment_id=seg.id)
        assert len(versions) == 3
        assert sorted(v.version for v in versions) == [1, 2, 3]
        assert db.get(Segment, seg.id).version == 4

        # Nothing about the OTHER segment moved.
        assert db.get(Segment, other.id).model_dump(mode="json") == other_before
        assert db.query(SegmentVersion, segment_id=other.id) == []

        # restore_version to the first makes a fourth equal to the first.
        current = db.get(Segment, seg.id)
        registry.invoke(
            db, "segment.restore_version",
            {"segment_id": seg.id, "version": 1, "expected_version": current.version}, ctx,
        )
        restored = db.get(Segment, seg.id)
        first_version_row = next(v for v in versions if v.version == 1)
        assert restored.anchor.rect == first_version_row.anchor.rect
        assert restored.version == 5
        assert len(db.query(SegmentVersion, segment_id=seg.id)) == 4


class TestDeleteIsUndoable:
    def test_delete_then_undo_restores_the_segment_and_what_pointed_at_it(self, db, client):
        """source.segment.delete-is-undoable."""
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        seg = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
        annotation = Annotation(document_id=doc.id, kind="highlight", anchor=seg.anchor)
        db.save(annotation)
        ctx = _ctx(db)

        delete_result = registry.invoke(
            db, "segment.delete",
            {"segment_ids": [seg.id], "expected_versions": {seg.id: seg.version}}, ctx,
        )
        assert db.get(Segment, seg.id).deleted_at is not None

        undo = client.post(f"/api/actions/audit/{delete_result.audit_id}/undo")
        assert undo.status_code == 200, undo.text

        restored = db.get(Segment, seg.id)
        assert restored.deleted_at is None
        assert restored.id == seg.id  # id unchanged

        # An annotation anchored to it (by rect, today's join) still resolves.
        assert db.get(Annotation, annotation.id).anchor.rect == seg.anchor.rect

        rows = db.query(SegmentForwarding, old_segment_id=seg.id)
        kinds = sorted(r.kind for r in rows)
        assert kinds == ["deleted", "restored"]

    def test_undelete_is_directly_callable(self, db):
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        seg = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
        ctx = _ctx(db)
        registry.invoke(
            db, "segment.delete", {"segment_ids": [seg.id], "expected_versions": {seg.id: seg.version}}, ctx,
        )
        registry.invoke(db, "segment.undelete", {"segment_ids": [seg.id]}, ctx)
        assert db.get(Segment, seg.id).deleted_at is None

    def test_undelete_of_a_live_segment_is_refused(self, db):
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        seg = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
        ctx = _ctx(db)
        with pytest.raises(Exception):
            registry.invoke(db, "segment.undelete", {"segment_ids": [seg.id]}, ctx)


class TestUndoOfAnUndoSucceeds:
    """#4923 second look, fix 1: undoing an undelete (or an update) must
    itself be undoable -- every inverse here reads ONLY `after` (the
    POST-action versions), never `before` (the PRE-action ones), so the
    chain never meets a stale row FOR THAT ONE UNDO. (The generic undo
    route's redo path -- undoing the INVERSE it just ran -- replays the
    ORIGINAL forward action's own RECORDED params verbatim, including its
    original `expected_version`; combined with "a version number is never
    set back" [fix 2], two version bumps have happened by the time that
    replay runs, so the replayed `expected_version` is provably stale by
    then and is correctly REFUSED, not a bug -- see
    `TestRedoReplaysOriginalParamsAndIsCorrectlyRefusedWhenStale` below.)"""

    def test_undoing_a_standalone_undelete_call_succeeds(self, db, client):
        """The concrete bug fix 1 names: `segment.undelete`, called
        directly (not as anyone's inverse), must itself be undoable."""
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        seg = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
        ctx = _ctx(db)
        registry.invoke(
            db, "segment.delete", {"segment_ids": [seg.id], "expected_versions": {seg.id: seg.version}}, ctx,
        )
        undelete_result = registry.invoke(db, "segment.undelete", {"segment_ids": [seg.id]}, ctx)
        assert db.get(Segment, seg.id).deleted_at is None

        undo = client.post(f"/api/actions/audit/{undelete_result.audit_id}/undo")
        assert undo.status_code == 200, undo.text
        assert db.get(Segment, seg.id).deleted_at is not None  # deleted again

    def test_delete_then_undo_succeeds_in_one_hop(self, db, client):
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        seg = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
        ctx = _ctx(db)

        delete_result = registry.invoke(
            db, "segment.delete",
            {"segment_ids": [seg.id], "expected_versions": {seg.id: seg.version}}, ctx,
        )
        undo = client.post(f"/api/actions/audit/{delete_result.audit_id}/undo")
        assert undo.status_code == 200, undo.text
        assert db.get(Segment, seg.id).deleted_at is None


class TestRedoReplaysOriginalParamsAndIsCorrectlyRefusedWhenStale:
    """#4923 second look asked for "delete, undo, undo-the-undo" through
    the generic route. Traced precisely: the second call is a REDO (the
    generic route's `inverse_of` path), which replays the FIRST call's own
    RECORDED params verbatim -- including ITS `expected_version`/
    `expected_versions`. Two version bumps happen between the original
    call and the redo attempt (one for the action, one for its undo), and
    "a version number is never set back" [fix 2] means those bumps cannot
    cancel out. So the replayed, now-doubly-stale `expected_version`
    correctly meets `SegmentStale`, refused with a clean 409 -- consistent
    with, not an exception to, "undoing a change that is no longer the
    latest is refused." This is a general property of ANY
    compare-and-set action combined with the generic redo mechanism (no
    other domain in this codebase combines the two), not specific to one
    action here; both delete and update are tested."""

    def test_delete_undo_redo_is_refused_as_stale(self, db, client):
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        seg = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
        ctx = _ctx(db)

        delete_result = registry.invoke(
            db, "segment.delete",
            {"segment_ids": [seg.id], "expected_versions": {seg.id: seg.version}}, ctx,
        )
        undo = client.post(f"/api/actions/audit/{delete_result.audit_id}/undo")
        assert undo.status_code == 200, undo.text

        redo = client.post(f"/api/actions/audit/{undo.json()['audit_id']}/undo")
        assert redo.status_code == 409, redo.text
        assert db.get(Segment, seg.id).deleted_at is None  # unchanged by the refused redo

    def test_update_undo_redo_is_refused_as_stale(self, db, client):
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        seg = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
        from fichero_server.models import ActionAudit

        r = client.request("PUT", f"/api/segments/{seg.id}", json={
            "segment_id": seg.id, "expected_version": 1,
            "anchor": {"document_id": doc.id, "rect": [0.2, 0.2, 0.1, 0.1]},
        })
        assert r.status_code == 200, r.text
        audit = next(a for a in db.all(ActionAudit) if a.action_name == "segment.update")

        undo = client.post(f"/api/actions/audit/{audit.id}/undo")
        assert undo.status_code == 200, undo.text
        assert db.get(Segment, seg.id).anchor.rect == [0.1, 0.1, 0.1, 0.1]

        redo = client.post(f"/api/actions/audit/{undo.json()['audit_id']}/undo")
        assert redo.status_code == 409, redo.text
        # Unchanged by the refused redo -- still the undone (original) state.
        assert db.get(Segment, seg.id).anchor.rect == [0.1, 0.1, 0.1, 0.1]


class TestUndoOfANonLatestChangeIsRefused:
    def test_update_update_undo_the_first_is_refused_as_stale(self, db, client):
        """#4923 second look: undoing a change that is no longer the
        latest is refused, with what changed -- the same compare-and-set
        that protects a live edit also protects an undo."""
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        seg = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
        from fichero_server.models import ActionAudit

        r1 = client.request("PUT", f"/api/segments/{seg.id}", json={
            "segment_id": seg.id, "expected_version": 1,
            "anchor": {"document_id": doc.id, "rect": [0.2, 0.2, 0.1, 0.1]},
        })
        assert r1.status_code == 200, r1.text
        first_audit = next(a for a in db.all(ActionAudit) if a.action_name == "segment.update")

        r2 = client.request("PUT", f"/api/segments/{seg.id}", json={
            "segment_id": seg.id, "expected_version": 2,
            "anchor": {"document_id": doc.id, "rect": [0.3, 0.3, 0.1, 0.1]},
        })
        assert r2.status_code == 200, r2.text

        undo_first = client.post(f"/api/actions/audit/{first_audit.id}/undo")
        assert undo_first.status_code == 409, undo_first.text

        # The row equals the SECOND update, untouched by the refused undo.
        assert db.get(Segment, seg.id).anchor.rect == [0.3, 0.3, 0.1, 0.1]


class TestStaleIsRefused:
    def test_two_updates_against_version_one_the_second_is_refused(self, db, client):
        """source.edit.stale-is-refused: two writers, both holding version
        1; the first succeeds, the second (stale) is refused with `changed`
        naming the field the first one changed; after re-reading it
        succeeds."""
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        seg = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])

        r1 = client.request("PUT", f"/api/segments/{seg.id}", json={
            "segment_id": seg.id, "expected_version": 1,
            "anchor": {"document_id": doc.id, "rect": [0.2, 0.2, 0.1, 0.1]},
        })
        assert r1.status_code == 200, r1.text

        # Second writer, still holding the OLD version (1) -- refused.
        r2 = client.request("PUT", f"/api/segments/{seg.id}", json={
            "segment_id": seg.id, "expected_version": 1,
            "anchor": {"document_id": doc.id, "rect": [0.3, 0.3, 0.1, 0.1]},
        })
        assert r2.status_code == 409, r2.text
        detail = r2.json()["detail"]
        assert detail["expected_version"] == 1
        assert detail["current_version"] == 2
        assert "anchor" in detail["changed"]

        # The row equals the FIRST update, untouched by the refused second.
        assert db.get(Segment, seg.id).anchor.rect == [0.2, 0.2, 0.1, 0.1]

        # After re-reading (the current version), it succeeds.
        current = db.get(Segment, seg.id)
        r3 = client.request("PUT", f"/api/segments/{seg.id}", json={
            "segment_id": seg.id, "expected_version": current.version,
            "anchor": {"document_id": doc.id, "rect": [0.3, 0.3, 0.1, 0.1]},
        })
        assert r3.status_code == 200, r3.text
        assert db.get(Segment, seg.id).anchor.rect == [0.3, 0.3, 0.1, 0.1]

    def test_updating_a_deleted_segment_is_refused(self, db):
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        seg = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
        ctx = _ctx(db)
        registry.invoke(
            db, "segment.delete", {"segment_ids": [seg.id], "expected_versions": {seg.id: seg.version}}, ctx,
        )
        with pytest.raises(Exception):
            registry.invoke(
                db, "segment.update",
                {"segment_id": seg.id, "expected_version": seg.version + 1,
                 "anchor": {"document_id": doc.id, "rect": [0.2, 0.2, 0.1, 0.1]}},
                ctx,
            )

    def test_restoring_a_version_of_another_segment_is_refused(self, db):
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        seg_a = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
        seg_b = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.5, 0.5, 0.1, 0.1])
        ctx = _ctx(db)
        # Give A a version-1 history row (an update bumps it to 2).
        registry.invoke(
            db, "segment.update",
            {"segment_id": seg_a.id, "expected_version": 1,
             "anchor": {"document_id": doc.id, "rect": [0.15, 0.15, 0.1, 0.1]}}, ctx,
        )
        # B has never been touched -- no version-1 row exists FOR B.
        with pytest.raises(Exception):
            registry.invoke(
                db, "segment.restore_version",
                {"segment_id": seg_b.id, "version": 1, "expected_version": seg_b.version}, ctx,
            )

    def test_changing_document_id_or_pass_id_is_not_accepted_by_the_params_model(self, db, client):
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        seg = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
        r = client.request("PUT", f"/api/segments/{seg.id}", json={
            "segment_id": seg.id, "expected_version": 1, "document_id": "some-other-doc",
        })
        assert r.status_code == 422


class TestStaleDeleteIsRefusedDirectly:
    """test-audit F8, 2026-09-20: a dedicated stale-delete test, not
    dependent on the redo-limitation test that #4957 will rewrite. A
    segment is updated (bumping it to version 2); a `segment.delete` call
    that still holds the OLD version (1) must be refused with the exact
    typed error, leave the row live, write no new `SegmentVersion` row, and
    leave no `deleted` forwarding note. Same shape for a stale
    `segment.restore_version` call."""

    def test_stale_delete_is_refused_row_stays_live_no_version_or_note_written(self, db):
        from fastapi import HTTPException

        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        seg = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
        ctx = _ctx(db)
        registry.invoke(
            db, "segment.update",
            {"segment_id": seg.id, "expected_version": 1,
             "anchor": {"document_id": doc.id, "rect": [0.2, 0.2, 0.1, 0.1]}}, ctx,
        )
        versions_before = len(db.query(SegmentVersion, segment_id=seg.id))
        notes_before = len(db.query(SegmentForwarding, old_segment_id=seg.id))

        with pytest.raises(HTTPException) as excinfo:
            registry.invoke(
                db, "segment.delete",
                {"segment_ids": [seg.id], "expected_versions": {seg.id: 1}}, ctx,
            )
        assert excinfo.value.status_code == 409
        detail = excinfo.value.detail
        assert detail["segment_id"] == seg.id
        assert detail["expected_version"] == 1
        assert detail["current_version"] == 2

        row = db.get(Segment, seg.id)
        assert row.deleted_at is None
        assert row.version == 2
        assert len(db.query(SegmentVersion, segment_id=seg.id)) == versions_before
        assert len(db.query(SegmentForwarding, old_segment_id=seg.id)) == notes_before

    def test_stale_restore_version_is_refused_row_stays_unchanged(self, db):
        from fastapi import HTTPException

        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        seg = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
        ctx = _ctx(db)
        registry.invoke(
            db, "segment.update",
            {"segment_id": seg.id, "expected_version": 1,
             "anchor": {"document_id": doc.id, "rect": [0.2, 0.2, 0.1, 0.1]}}, ctx,
        )
        versions_before = len(db.query(SegmentVersion, segment_id=seg.id))

        with pytest.raises(HTTPException) as excinfo:
            registry.invoke(
                db, "segment.restore_version",
                {"segment_id": seg.id, "version": 1, "expected_version": 1}, ctx,
            )
        assert excinfo.value.status_code == 409
        detail = excinfo.value.detail
        assert detail["expected_version"] == 1
        assert detail["current_version"] == 2

        row = db.get(Segment, seg.id)
        assert row.anchor.rect == [0.2, 0.2, 0.1, 0.1]
        assert row.version == 2
        assert len(db.query(SegmentVersion, segment_id=seg.id)) == versions_before


class TestUndoRestoresFromOrdinaryData:
    def test_a_blanked_audit_before_still_restores(self, db, client):
        """`before`/`after` on `ActionAudit` are NOT the source of truth --
        undo restores from `SegmentVersion`, ordinary data."""
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        seg = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
        ctx = _ctx(db)

        update_result = registry.invoke(
            db, "segment.update",
            {"segment_id": seg.id, "expected_version": 1,
             "anchor": {"document_id": doc.id, "rect": [0.3, 0.3, 0.1, 0.1]}}, ctx,
        )
        audit = db.get(ActionAudit, update_result.audit_id)
        audit.before = None
        db.save(audit)

        undo = client.post(f"/api/actions/audit/{update_result.audit_id}/undo")
        assert undo.status_code == 200, undo.text
        assert db.get(Segment, seg.id).anchor.rect == [0.1, 0.1, 0.1, 0.1]


class TestCrossPassAndDocumentRefusalOnDelete:
    def test_bulk_delete_across_documents_is_refused(self, db):
        doc_1 = _make_doc(db, "doc1.jpg")
        doc_2 = _make_doc(db, "doc2.jpg")
        pass_1 = _make_pass(db, doc_1.id)
        pass_2 = _make_pass(db, doc_2.id)
        seg_1 = _make_segment(db, document_id=doc_1.id, pass_id=pass_1.id, rect=[0.1, 0.1, 0.1, 0.1])
        seg_2 = _make_segment(db, document_id=doc_2.id, pass_id=pass_2.id, rect=[0.1, 0.1, 0.1, 0.1])
        ctx = _ctx(db)
        with pytest.raises(Exception):
            registry.invoke(
                db, "segment.delete",
                {"segment_ids": [seg_1.id, seg_2.id],
                 "expected_versions": {seg_1.id: 1, seg_2.id: 1}}, ctx,
            )

    def test_bulk_delete_across_passes_same_document_is_refused(self, db):
        doc = _make_doc(db)
        pass_1 = _make_pass(db, doc.id)
        pass_2 = _make_pass(db, doc.id)
        seg_1 = _make_segment(db, document_id=doc.id, pass_id=pass_1.id, rect=[0.1, 0.1, 0.1, 0.1])
        seg_2 = _make_segment(db, document_id=doc.id, pass_id=pass_2.id, rect=[0.5, 0.5, 0.1, 0.1])
        ctx = _ctx(db)
        with pytest.raises(Exception):
            registry.invoke(
                db, "segment.delete",
                {"segment_ids": [seg_1.id, seg_2.id],
                 "expected_versions": {seg_1.id: 1, seg_2.id: 1}}, ctx,
            )


class TestReads:
    def test_versions_route_lists_one_segments_own_history(self, db, client):
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        seg = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
        ctx = _ctx(db)
        registry.invoke(
            db, "segment.update",
            {"segment_id": seg.id, "expected_version": 1,
             "anchor": {"document_id": doc.id, "rect": [0.2, 0.2, 0.1, 0.1]}}, ctx,
        )
        r = client.get(f"/api/segments/{seg.id}/versions")
        assert r.status_code == 200, r.text
        body = r.json()
        assert len(body) == 1
        assert body[0]["version"] == 1
        assert body[0]["segment_id"] == seg.id

    def test_get_segment_resolves_through_forwarding_and_says_so(self, db, client):
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        seg_a = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
        seg_b = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.5, 0.5, 0.1, 0.1])
        ctx = _ctx(db)
        registry.invoke(db, "segment.merge", {"segment_ids": [seg_a.id, seg_b.id], "keep_id": seg_b.id}, ctx)

        live = client.get(f"/api/segments/{seg_b.id}")
        assert live.status_code == 200, live.text
        assert live.json()["resolved_from_forwarding"] is False

        forwarded = client.get(f"/api/segments/{seg_a.id}")
        assert forwarded.status_code == 200, forwarded.text
        body = forwarded.json()
        assert body["resolved_from_forwarding"] is True
        assert body["segment"]["id"] == seg_b.id
        assert len(body["trail"]) == 1


class TestAuditPayloadsCarryNoText:
    def test_update_and_restore_version_audit_payloads_carry_no_reading_text(self, db):
        """`segment.update`/`.restore_version` take no free-text field at
        all (their params are ids, versions and geometry only) -- a
        reading's content anchored to the same segment must never show up
        in their audit payloads regardless."""
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        seg = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
        secret = "TOP SECRET reading text nobody should see in an audit row"
        from fichero_server.models import ContentRepresentation, ContentRepresentationKind

        db.save(ContentRepresentation(
            document_id=doc.id, kind=ContentRepresentationKind.transcription,
            content=secret, source_anchor=seg.anchor,
        ))
        ctx = _ctx(db)

        registry.invoke(
            db, "segment.update",
            {"segment_id": seg.id, "expected_version": 1,
             "anchor": {"document_id": doc.id, "rect": [0.2, 0.2, 0.1, 0.1]}}, ctx,
        )
        current = db.get(Segment, seg.id)
        registry.invoke(
            db, "segment.restore_version",
            {"segment_id": seg.id, "version": 1, "expected_version": current.version}, ctx,
        )

        for audit in db.all(ActionAudit):
            if audit.action_name not in ("segment.update", "segment.restore_version"):
                continue
            payload = json.dumps({"before": audit.before, "after": audit.after, "params": audit.params})
            assert secret not in payload, f"{audit.action_name} leaked text into its audit payload"

    def test_deletes_reason_is_a_short_operator_note_not_a_leak(self, db):
        """`reason` is an explicit, short, operator-supplied field on
        `segment.delete` (slice 4's own carve-out: "no free text LONGER
        THAN note and reason") -- it legitimately appears in the audit;
        this is not the text-leak the rule forbids."""
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        seg = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
        ctx = _ctx(db)
        result = registry.invoke(
            db, "segment.delete",
            {"segment_ids": [seg.id], "expected_versions": {seg.id: seg.version}, "reason": "duplicate line"},
            ctx,
        )
        audit = db.get(ActionAudit, result.audit_id)
        assert audit.params["reason"] == "duplicate line"


class TestNotesAreCapped:
    """#4923 second look, fix 3: `reason`/`note` are recorded inside the
    tamper-evident audit chain, where nothing can ever be purged -- capped
    at 200 characters on every params model that has one, one parametrized
    test over all of them."""

    @pytest.mark.parametrize("action_name,build_params,field", [
        (
            "segment.delete",
            lambda seg, other, value: {
                "segment_ids": [seg.id], "expected_versions": {seg.id: seg.version}, "reason": value,
            },
            "reason",
        ),
        (
            "segment.match_propose",
            lambda seg, other, value: {
                "from_segment_id": seg.id, "to_segment_id": other.id, "note": value,
            },
            "note",
        ),
    ])
    def test_a_note_over_200_characters_is_refused(self, db, action_name, build_params, field):
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        seg = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
        other = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.5, 0.5, 0.1, 0.1])
        ctx = _ctx(db)
        too_long = "x" * 201
        with pytest.raises(Exception):
            registry.invoke(db, action_name, build_params(seg, other, too_long), ctx)

    @pytest.mark.parametrize("action_name,build_params,field", [
        (
            "segment.delete",
            lambda seg, other, value: {
                "segment_ids": [seg.id], "expected_versions": {seg.id: seg.version}, "reason": value,
            },
            "reason",
        ),
        (
            "segment.match_propose",
            lambda seg, other, value: {
                "from_segment_id": seg.id, "to_segment_id": other.id, "note": value,
            },
            "note",
        ),
    ])
    def test_a_note_at_exactly_200_characters_is_accepted(self, db, action_name, build_params, field):
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        seg = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
        other = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.5, 0.5, 0.1, 0.1])
        ctx = _ctx(db)
        exactly_200 = "x" * 200
        result = registry.invoke(db, action_name, build_params(seg, other, exactly_200), ctx)
        assert result.ok
