"""Source-model slice 5 — versions for each segment, and refusing a stale
edit (#4923).

`SegmentVersion`, compare-and-set (`segment.update`), the real versioned
`segment.delete`/`.undelete`, and `segment.restore_version`. Each test
names the behaviour id it pins.
"""

from __future__ import annotations

import json

import pytest
from fastapi import HTTPException

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

    def test_delete_then_undo_leaves_children_a_match_and_a_carry_intact(self, db, client):
        """test-audit F13, 2026-09-20: the test above was vacuous -- the
        annotation it checks is never touched by delete/undo at all (its
        anchor is a rect the join reads, not a reference to the segment's
        id), so it would pass even if delete corrupted every real
        reference. This builds the REAL scenario: a parent with two
        children (`parent_segment_id`), an accepted match, and a carried
        reading -- deletes the PARENT, and confirms every one of these
        still resolves to the same id/state, both right after the delete
        and again after undo."""
        from fichero_server.models import ContentRepresentation, ContentRepresentationKind, SegmentCarry, SegmentMatch

        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        parent = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.0, 0.0, 0.2, 0.2])
        child_1 = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.0, 0.0, 0.1, 0.1])
        child_1.parent_segment_id = parent.id
        db.save(child_1)
        child_2 = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
        child_2.parent_segment_id = parent.id
        db.save(child_2)

        other = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.5, 0.5, 0.1, 0.1])
        ctx = _ctx(db)
        match_id = registry.invoke(
            db, "segment.match_propose",
            {"from_segment_id": parent.id, "to_segment_id": other.id}, ctx,
        ).result["match_id"]
        registry.invoke(db, "segment.match_accept", {"match_id": match_id}, ctx)

        reading = ContentRepresentation(
            document_id=doc.id, kind=ContentRepresentationKind.transcription,
            content="carried text", source_anchor=parent.anchor,
        )
        db.save(reading)
        registry.invoke(
            db, "segment.carry",
            {
                "match_id": match_id, "kinds": ["reading"],
                "expected_versions": {parent.id: parent.version, other.id: other.version},
            },
            ctx,
        )
        carry_ids_before = {c.id for c in db.query(SegmentCarry, match_id=match_id)}
        assert carry_ids_before, "fixture must actually produce a carry"

        def _assert_everything_still_points_at_parent():
            assert db.get(Segment, child_1.id).parent_segment_id == parent.id
            assert db.get(Segment, child_2.id).parent_segment_id == parent.id
            match = db.get(SegmentMatch, match_id)
            assert match.state == "accepted"
            assert {match.from_segment_id, match.to_segment_id} == {parent.id, other.id}
            assert {c.id for c in db.query(SegmentCarry, match_id=match_id)} == carry_ids_before

        delete_result = registry.invoke(
            db, "segment.delete",
            {"segment_ids": [parent.id], "expected_versions": {parent.id: parent.version}}, ctx,
        )
        assert db.get(Segment, parent.id).deleted_at is not None
        _assert_everything_still_points_at_parent()

        undo = client.post(f"/api/actions/audit/{delete_result.audit_id}/undo")
        assert undo.status_code == 200, undo.text
        assert db.get(Segment, parent.id).deleted_at is None
        _assert_everything_still_points_at_parent()

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
        from fastapi import HTTPException

        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        seg = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
        ctx = _ctx(db)
        with pytest.raises(HTTPException) as excinfo:
            registry.invoke(db, "segment.undelete", {"segment_ids": [seg.id]}, ctx)
        assert excinfo.value.status_code == 409
        assert excinfo.value.detail == f"segment {seg.id!r} is not deleted"


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


class TestRedoOfASegmentEditWorks:
    """`source.editor.redo-works` (#4957). #4923 second look originally
    found "delete, undo, undo-the-undo" (redo) refused as stale here and
    read that as correct: the generic route's redo leg replayed the FIRST
    call's own RECORDED params verbatim -- including ITS
    `expected_version`/`expected_versions` -- and two version bumps happen
    between the original call and the redo attempt (one for the action,
    one for its undo), which a verbatim replay could never see coming.
    #4957 corrected the reading: that is not "undoing a change that is no
    longer the latest," it is redo refusing to work AT ALL, even the very
    first time, with no other writer involved. The shared registry's redo
    leg (`actions_registry._refresh_replay_expected_versions`) now works
    the replayed `expected_version`/`expected_versions` out from the
    undo's OWN `after` (the freshest known state) instead of the ancient
    recorded params, so redo succeeds here -- while a GENUINELY stale redo
    (another writer in between) is still correctly refused, see
    `TestRedoStillRefusedWhenAnotherWriterIntervenes` below."""

    def test_delete_undo_redo_succeeds(self, db, client):
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
        assert db.get(Segment, seg.id).deleted_at is None  # restored by the undo

        redo = client.post(f"/api/actions/audit/{undo.json()['audit_id']}/undo")
        assert redo.status_code == 200, redo.text
        assert db.get(Segment, seg.id).deleted_at is not None  # re-deleted by the redo

    def test_update_undo_redo_succeeds(self, db, client):
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
        assert redo.status_code == 200, redo.text
        assert db.get(Segment, seg.id).anchor.rect == [0.2, 0.2, 0.1, 0.1]  # re-applied


class TestRedoStillRefusedWhenAnotherWriterIntervenes:
    """The compare-and-set must still catch a GENUINELY stale redo: a
    third writer touches the row between the undo and the redo attempt."""

    def test_update_redo_refused_after_another_writer_edits_in_between(self, db, client):
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

        # Another writer edits the segment after the undo, independently
        # of the undo/redo chain, bumping the version again.
        current_version = db.get(Segment, seg.id).version
        other_writer = client.request("PUT", f"/api/segments/{seg.id}", json={
            "segment_id": seg.id, "expected_version": current_version,
            "anchor": {"document_id": doc.id, "rect": [0.5, 0.5, 0.1, 0.1]},
        })
        assert other_writer.status_code == 200, other_writer.text

        redo = client.post(f"/api/actions/audit/{undo.json()['audit_id']}/undo")
        assert redo.status_code == 409, redo.text
        # Unchanged by the refused redo -- still the other writer's edit.
        assert db.get(Segment, seg.id).anchor.rect == [0.5, 0.5, 0.1, 0.1]


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

    def test_two_threads_racing_the_same_expected_version_exactly_one_wins(self, db, client):
        """test-audit F16, 2026-09-20: proves the version check and the
        write happen inside the SAME transaction, not as two separate
        steps a second writer could slip between. Two threads, both
        holding version 1, released together by a barrier; exactly one
        gets 200, the other gets 409 with `current_version` naming the
        winner's new version -- never both succeeding, never both
        failing. Daemon threads, joined with a timeout so a hang here
        cannot hang the suite."""
        import threading

        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        seg = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])

        barrier = threading.Barrier(2)
        results: list = [None, None]

        def _attempt(index: int, rect: list[float]) -> None:
            barrier.wait(timeout=5)
            results[index] = client.request("PUT", f"/api/segments/{seg.id}", json={
                "segment_id": seg.id, "expected_version": 1,
                "anchor": {"document_id": doc.id, "rect": rect},
            })

        threads = [
            threading.Thread(target=_attempt, args=(0, [0.2, 0.2, 0.1, 0.1]), daemon=True),
            threading.Thread(target=_attempt, args=(1, [0.3, 0.3, 0.1, 0.1]), daemon=True),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
            assert not t.is_alive(), "a racing update thread hung"

        statuses = sorted(r.status_code for r in results)
        assert statuses == [200, 409], statuses
        winner = next(r for r in results if r.status_code == 200)
        loser = next(r for r in results if r.status_code == 409)
        assert loser.json()["detail"]["current_version"] == 2

        final = db.get(Segment, seg.id)
        assert final.version == 2
        assert final.anchor.rect == winner.json()["anchor"]["rect"]
        # Exactly one new SegmentVersion row was written by this race --
        # the pre-existing version-1 snapshot from the write itself, not two.
        assert len(db.query(SegmentVersion, segment_id=seg.id, version=1)) == 1

    def test_updating_a_deleted_segment_is_refused(self, db):
        from fichero_server.models.segments import SegmentDeleted

        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        seg = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
        ctx = _ctx(db)
        registry.invoke(
            db, "segment.delete", {"segment_ids": [seg.id], "expected_versions": {seg.id: seg.version}}, ctx,
        )
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as excinfo:
            registry.invoke(
                db, "segment.update",
                {"segment_id": seg.id, "expected_version": seg.version + 1,
                 "anchor": {"document_id": doc.id, "rect": [0.2, 0.2, 0.1, 0.1]}},
                ctx,
            )
        assert excinfo.value.status_code == 409
        assert excinfo.value.detail == str(SegmentDeleted(seg.id))

    def test_restoring_a_nonexistent_version_is_a_404_not_a_cross_segment_hit(self, db):
        """test-audit F9, 2026-09-20: renamed and re-shaped -- the original
        name ('a version of ANOTHER segment') claimed a cross-segment
        protection this scenario never actually exercised: segment B here
        simply has no version-1 row at all, so this only proved "no such
        version exists", a 404. The second test below is the REAL
        cross-segment case: a version-1 row exists, but for segment A, and
        B's restore_version call (scoped by `(segment_id, version)`
        together) must not find it."""
        from fastapi import HTTPException

        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        seg_a = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
        seg_b = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.5, 0.5, 0.1, 0.1])
        ctx = _ctx(db)
        registry.invoke(
            db, "segment.update",
            {"segment_id": seg_a.id, "expected_version": 1,
             "anchor": {"document_id": doc.id, "rect": [0.15, 0.15, 0.1, 0.1]}}, ctx,
        )
        # B has never been touched -- no version-1 row exists FOR B.
        with pytest.raises(HTTPException) as excinfo:
            registry.invoke(
                db, "segment.restore_version",
                {"segment_id": seg_b.id, "version": 1, "expected_version": seg_b.version}, ctx,
            )
        assert excinfo.value.status_code == 404
        assert excinfo.value.detail == f"segment {seg_b.id!r} has no version 1"

    def test_restoring_segment_bs_version_number_against_segment_a_is_refused(self, db):
        """The REAL cross-segment case: A genuinely has a version-1 row.
        Asking to restore B to "version 1" must not silently find A's row
        -- `(segment_id, version)` scoping means this is ALSO a 404, not a
        wrong-segment success."""
        from fastapi import HTTPException

        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        seg_a = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
        seg_b = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.5, 0.5, 0.1, 0.1])
        ctx = _ctx(db)
        registry.invoke(
            db, "segment.update",
            {"segment_id": seg_a.id, "expected_version": 1,
             "anchor": {"document_id": doc.id, "rect": [0.15, 0.15, 0.1, 0.1]}}, ctx,
        )
        assert db.query(SegmentVersion, segment_id=seg_a.id, version=1), "A must genuinely have version 1"

        with pytest.raises(HTTPException) as excinfo:
            registry.invoke(
                db, "segment.restore_version",
                {"segment_id": seg_b.id, "version": 1, "expected_version": seg_b.version}, ctx,
            )
        assert excinfo.value.status_code == 404
        assert excinfo.value.detail == f"segment {seg_b.id!r} has no version 1"
        # Confirm B was genuinely untouched -- not silently restored from A's row.
        assert db.get(Segment, seg_b.id).anchor.rect == [0.5, 0.5, 0.1, 0.1]

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
        from fastapi import HTTPException

        doc_1 = _make_doc(db, "doc1.jpg")
        doc_2 = _make_doc(db, "doc2.jpg")
        pass_1 = _make_pass(db, doc_1.id)
        pass_2 = _make_pass(db, doc_2.id)
        seg_1 = _make_segment(db, document_id=doc_1.id, pass_id=pass_1.id, rect=[0.1, 0.1, 0.1, 0.1])
        seg_2 = _make_segment(db, document_id=doc_2.id, pass_id=pass_2.id, rect=[0.1, 0.1, 0.1, 0.1])
        ctx = _ctx(db)
        with pytest.raises(HTTPException) as excinfo:
            registry.invoke(
                db, "segment.delete",
                {"segment_ids": [seg_1.id, seg_2.id],
                 "expected_versions": {seg_1.id: 1, seg_2.id: 1}}, ctx,
            )
        assert excinfo.value.status_code == 409
        assert excinfo.value.detail == "segments are not all in the same pass and document"

    def test_bulk_delete_across_passes_same_document_is_refused(self, db):
        from fastapi import HTTPException

        doc = _make_doc(db)
        pass_1 = _make_pass(db, doc.id)
        pass_2 = _make_pass(db, doc.id)
        seg_1 = _make_segment(db, document_id=doc.id, pass_id=pass_1.id, rect=[0.1, 0.1, 0.1, 0.1])
        seg_2 = _make_segment(db, document_id=doc.id, pass_id=pass_2.id, rect=[0.5, 0.5, 0.1, 0.1])
        ctx = _ctx(db)
        with pytest.raises(HTTPException) as excinfo:
            registry.invoke(
                db, "segment.delete",
                {"segment_ids": [seg_1.id, seg_2.id],
                 "expected_versions": {seg_1.id: 1, seg_2.id: 1}}, ctx,
            )
        assert excinfo.value.status_code == 409
        assert excinfo.value.detail == "segments are not all in the same pass and document"


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
        # `{items, count}`, not a bare array (#1075's rule for every list
        # endpoint; `test_no_new_bare_array_get_endpoint` enforces it).
        assert body["count"] == 1
        assert len(body["items"]) == 1
        assert body["items"][0]["version"] == 1
        assert body["items"][0]["segment_id"] == seg.id

    def test_get_segment_resolves_through_forwarding_and_says_so(self, db, client):
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        seg_a = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
        seg_b = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.5, 0.5, 0.1, 0.1])
        ctx = _ctx(db)
        registry.invoke(
            db, "segment.merge",
            {
                "segment_ids": [seg_a.id, seg_b.id], "keep_id": seg_b.id,
                "expected_versions": {seg_a.id: seg_a.version, seg_b.id: seg_b.version},
            },
            ctx,
        )

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
        from pydantic import ValidationError

        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        seg = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
        other = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.5, 0.5, 0.1, 0.1])
        ctx = _ctx(db)
        too_long = "x" * 201
        # `params_model.model_validate` (inside `registry.invoke`, before
        # the action even runs) rejects this -- a pydantic `ValidationError`,
        # never an `HTTPException` (this path never reaches `_as_http_error`).
        with pytest.raises(ValidationError) as excinfo:
            registry.invoke(db, action_name, build_params(seg, other, too_long), ctx)
        assert excinfo.value.errors()[0]["loc"] == (field,)

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


class TestAuditIdResolvesToARealAuditRow:
    """#4955 addendum, VERIFIED on disk by the spec author: every slice 4/5
    segment action mints its OWN `uuid.uuid4()` for `SegmentVersion.
    audit_id`/`SegmentForwarding.audit_id` BEFORE the generic `ActionAudit`
    row exists (the registry only builds it AFTER `execute()` returns), and
    `ActionRegistry.invoke` used to give that `ActionAudit` a SEPARATE
    default id -- the two ids never met, so every version/forwarding row's
    `audit_id` was an orphan pointing at nothing. Fixed via
    `ChangeSpec.audit_id`: the action hands its own minted id back out, and
    `invoke` uses it as `ActionAudit.id`. One case per action that writes a
    version or forwarding row."""

    def test_update_writes_a_version_whose_audit_id_resolves(self, db):
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        seg = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
        ctx = _ctx(db)

        result = registry.invoke(
            db, "segment.update", {"segment_id": seg.id, "expected_version": 1, "kind_raw": "x"}, ctx,
        )
        version_row = db.query(SegmentVersion, segment_id=seg.id)[0]
        audit = db.get(ActionAudit, version_row.audit_id)
        assert audit is not None, f"orphan audit_id {version_row.audit_id!r}"
        assert audit.id == result.audit_id
        assert audit.action_name == "segment.update"

    def test_restore_version_writes_a_version_whose_audit_id_resolves(self, db):
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        seg = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
        ctx = _ctx(db)
        registry.invoke(db, "segment.update", {"segment_id": seg.id, "expected_version": 1, "kind_raw": "x"}, ctx)

        result = registry.invoke(
            db, "segment.restore_version",
            {"segment_id": seg.id, "version": 1, "expected_version": 2}, ctx,
        )
        newest = max(db.query(SegmentVersion, segment_id=seg.id), key=lambda v: v.version)
        audit = db.get(ActionAudit, newest.audit_id)
        assert audit is not None, f"orphan audit_id {newest.audit_id!r}"
        assert audit.id == result.audit_id
        assert audit.action_name == "segment.restore_version"

    def test_delete_writes_a_version_and_forwarding_whose_audit_ids_resolve(self, db):
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        seg = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
        ctx = _ctx(db)

        result = registry.invoke(
            db, "segment.delete", {"segment_ids": [seg.id], "expected_versions": {seg.id: 1}}, ctx,
        )
        version_row = db.query(SegmentVersion, segment_id=seg.id)[0]
        forwarding_row = db.query(SegmentForwarding, old_segment_id=seg.id)[0]
        for row in (version_row, forwarding_row):
            audit = db.get(ActionAudit, row.audit_id)
            assert audit is not None, f"orphan audit_id {row.audit_id!r}"
            assert audit.id == result.audit_id
            assert audit.action_name == "segment.delete"

    def test_undelete_writes_a_version_and_forwarding_whose_audit_ids_resolve(self, db):
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        seg = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
        ctx = _ctx(db)
        registry.invoke(db, "segment.delete", {"segment_ids": [seg.id], "expected_versions": {seg.id: 1}}, ctx)

        result = registry.invoke(db, "segment.undelete", {"segment_ids": [seg.id]}, ctx)
        newest = max(db.query(SegmentVersion, segment_id=seg.id), key=lambda v: v.version)
        newest_forwarding = max(
            db.query(SegmentForwarding, old_segment_id=seg.id), key=lambda f: f.sequence
        )
        for row in (newest, newest_forwarding):
            audit = db.get(ActionAudit, row.audit_id)
            assert audit is not None, f"orphan audit_id {row.audit_id!r}"
            assert audit.id == result.audit_id
            assert audit.action_name == "segment.undelete"

    def test_merge_writes_forwarding_rows_whose_audit_id_resolves(self, db):
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        seg_a = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.0, 0.0, 0.1, 0.1])
        seg_b = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.3, 0.3, 0.1, 0.1])
        ctx = _ctx(db)

        result = registry.invoke(
            db, "segment.merge",
            {
                "segment_ids": [seg_a.id, seg_b.id], "keep_id": seg_b.id,
                "expected_versions": {seg_a.id: seg_a.version, seg_b.id: seg_b.version},
            },
            ctx,
        )
        forwarding_row = db.query(SegmentForwarding, old_segment_id=seg_a.id)[0]
        audit = db.get(ActionAudit, forwarding_row.audit_id)
        assert audit is not None, f"orphan audit_id {forwarding_row.audit_id!r}"
        assert audit.id == result.audit_id
        assert audit.action_name == "segment.merge"

    def test_unmerge_writes_a_forwarding_row_whose_audit_id_resolves(self, db):
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        seg_a = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.0, 0.0, 0.1, 0.1])
        seg_b = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.3, 0.3, 0.1, 0.1])
        ctx = _ctx(db)
        registry.invoke(
            db, "segment.merge",
            {
                "segment_ids": [seg_a.id, seg_b.id], "keep_id": seg_b.id,
                "expected_versions": {seg_a.id: seg_a.version, seg_b.id: seg_b.version},
            },
            ctx,
        )
        pre_merge_version = db.query(SegmentVersion, segment_id=seg_a.id)[0].version
        current_a_version = db.get(Segment, seg_a.id).version

        result = registry.invoke(
            db, "segment.unmerge",
            {
                "versions": {seg_a.id: pre_merge_version},
                "expected_versions": {seg_a.id: current_a_version},
            },
            ctx,
        )
        newest_forwarding = max(
            db.query(SegmentForwarding, old_segment_id=seg_a.id), key=lambda f: f.sequence
        )
        audit = db.get(ActionAudit, newest_forwarding.audit_id)
        assert audit is not None, f"orphan audit_id {newest_forwarding.audit_id!r}"
        assert audit.id == result.audit_id
        assert audit.action_name == "segment.unmerge"

    def test_split_writes_a_forwarding_row_whose_audit_id_resolves(self, db):
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        seg = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.2, 0.2])
        ctx = _ctx(db)

        result = registry.invoke(
            db, "segment.split",
            {
                "segment_id": seg.id, "expected_version": seg.version,
                "parts": [
                    {"anchor": {"document_id": doc.id, "rect": [0.1, 0.1, 0.1, 0.1]}},
                    {"anchor": {"document_id": doc.id, "rect": [0.2, 0.2, 0.1, 0.1]}},
                ],
            },
            ctx,
        )
        forwarding_row = db.query(SegmentForwarding, old_segment_id=seg.id)[0]
        audit = db.get(ActionAudit, forwarding_row.audit_id)
        assert audit is not None, f"orphan audit_id {forwarding_row.audit_id!r}"
        assert audit.id == result.audit_id
        assert audit.action_name == "segment.split"

    def test_unsplit_writes_a_forwarding_row_whose_audit_id_resolves(self, db):
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        seg = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.2, 0.2])
        ctx = _ctx(db)
        pre_split_version = seg.version
        split_result = registry.invoke(
            db, "segment.split",
            {
                "segment_id": seg.id, "expected_version": seg.version,
                "parts": [
                    {"anchor": {"document_id": doc.id, "rect": [0.1, 0.1, 0.1, 0.1]}},
                    {"anchor": {"document_id": doc.id, "rect": [0.2, 0.2, 0.1, 0.1]}},
                ],
            },
            ctx,
        )
        new_ids = split_result.result["new_segment_ids"]
        current_kept_version = db.get(Segment, seg.id).version

        result = registry.invoke(
            db, "segment.unsplit",
            {
                "segment_id": seg.id, "version": pre_split_version,
                "expected_version": current_kept_version,
                "new_segment_ids": new_ids,
                "expected_versions": {nid: db.get(Segment, nid).version for nid in new_ids},
            },
            ctx,
        )
        newest_forwarding = max(
            db.query(SegmentForwarding, old_segment_id=seg.id), key=lambda f: f.sequence
        )
        audit = db.get(ActionAudit, newest_forwarding.audit_id)
        assert audit is not None, f"orphan audit_id {newest_forwarding.audit_id!r}"
        assert audit.id == result.audit_id
        assert audit.action_name == "segment.unsplit"


class TestUnsplitRefusesAPartTouchedMeanwhile:
    """#4957 follow-up 1: "an inverse must never hard-delete something a
    later step touched" -- `unsplit` used to `db.delete` every part it was
    given unconditionally, even one someone else had since edited. Now it
    is refused, with a typed reason, and NOTHING is deleted (not even the
    other, untouched parts) -- the whole action rolls back."""

    def test_unsplit_refuses_when_a_part_was_edited_meanwhile_nothing_deleted(self, db):
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        seg = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.2, 0.2])
        ctx = _ctx(db)
        pre_split_version = seg.version

        split_result = registry.invoke(
            db, "segment.split",
            {
                "segment_id": seg.id, "expected_version": pre_split_version,
                "parts": [
                    {"anchor": {"document_id": doc.id, "rect": [0.1, 0.1, 0.1, 0.1]}},
                    {"anchor": {"document_id": doc.id, "rect": [0.2, 0.2, 0.1, 0.1]}},
                ],
            },
            ctx,
        )
        new_ids = split_result.result["new_segment_ids"]
        part_id = new_ids[0]
        stale_expected_versions = {nid: db.get(Segment, nid).version for nid in new_ids}

        # Someone else edits the part in between the split and the unsplit.
        part_before_edit = db.get(Segment, part_id).version
        edited = registry.invoke(
            db, "segment.update",
            {"segment_id": part_id, "expected_version": part_before_edit, "kind_raw": "someone-else-edited-this"},
            ctx,
        )
        assert edited.ok

        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db, "segment.unsplit",
                {
                    "segment_id": seg.id, "version": pre_split_version,
                    "expected_version": db.get(Segment, seg.id).version,
                    "new_segment_ids": new_ids,
                    "expected_versions": stale_expected_versions,
                },
                ctx,
            )
        assert exc.value.status_code == 409

        # NOTHING was deleted -- not the touched part, not the untouched one.
        for nid in new_ids:
            row = db.get(Segment, nid)
            assert row is not None, f"{nid} was deleted despite the refusal"
            assert row.deleted_at is None
        assert db.get(Segment, part_id).kind_raw == "someone-else-edited-this"
        # The kept segment was never restored either -- refused BEFORE any write.
        assert db.get(Segment, seg.id).anchor.rect == [0.1, 0.1, 0.1, 0.1]


class TestRestoreRefusesADeadPassOrParent:
    """#4957 follow-up 2: `undelete`, `unmerge` and `unsplit` refuse to
    bring a segment back into a pass or under a parent that is no longer
    live -- otherwise an undo/redo could restore it into a place the read
    seam or the reader treats as gone (a soft-deleted pass is skipped
    entirely by `list_document_segments`)."""

    def test_undelete_refuses_into_a_deleted_pass(self, db, client):
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        seg = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
        ctx = _ctx(db)

        registry.invoke(
            db, "segment.delete", {"segment_ids": [seg.id], "expected_versions": {seg.id: 1}}, ctx,
        )
        # The pass is deleted AFTER the segment, while it is still soft-deleted.
        delete_pass_response = client.delete(f"/api/segments/passes/{pass_row.id}")
        assert delete_pass_response.status_code == 200, delete_pass_response.text
        assert db.get(SegmentPass, pass_row.id).deleted_at is not None

        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db, "segment.undelete",
                {"segment_ids": [seg.id]}, ctx,
            )
        assert exc.value.status_code == 409
        assert db.get(Segment, seg.id).deleted_at is not None  # still deleted, unchanged

    def test_undelete_refuses_under_a_deleted_parent(self, db):
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        parent = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.0, 0.0, 0.3, 0.3])
        child = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
        child.parent_segment_id = parent.id
        db.save(child)
        ctx = _ctx(db)

        registry.invoke(
            db, "segment.delete", {"segment_ids": [child.id], "expected_versions": {child.id: 1}}, ctx,
        )
        # The parent is deleted AFTER the child, while the child is still
        # soft-deleted -- merge is the real way a segment becomes not-live
        # without a pass delete; a plain delete on the parent segment is
        # simplest to set up here and exercises the SAME liveness check.
        registry.invoke(
            db, "segment.delete", {"segment_ids": [parent.id], "expected_versions": {parent.id: 1}}, ctx,
        )

        with pytest.raises(HTTPException) as exc:
            registry.invoke(db, "segment.undelete", {"segment_ids": [child.id]}, ctx)
        assert exc.value.status_code == 409
        assert db.get(Segment, child.id).deleted_at is not None

    def test_unmerge_refuses_into_a_deleted_pass(self, db, client):
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        keep = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.5, 0.5, 0.1, 0.1])
        absorbed = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
        ctx = _ctx(db)

        registry.invoke(
            db, "segment.merge",
            {
                "segment_ids": [keep.id, absorbed.id], "keep_id": keep.id,
                "expected_versions": {keep.id: 1, absorbed.id: 1},
            },
            ctx,
        )
        pre_merge_version = db.query(SegmentVersion, segment_id=absorbed.id)[0].version
        absorbed_current_version = db.get(Segment, absorbed.id).version

        delete_pass_response = client.delete(f"/api/segments/passes/{pass_row.id}")
        assert delete_pass_response.status_code == 200, delete_pass_response.text

        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db, "segment.unmerge",
                {
                    "versions": {absorbed.id: pre_merge_version},
                    "expected_versions": {absorbed.id: absorbed_current_version},
                },
                ctx,
            )
        assert exc.value.status_code == 409
        assert db.get(Segment, absorbed.id).deleted_at is not None  # still merged away

    def test_unsplit_refuses_into_a_deleted_pass(self, db, client):
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        seg = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.2, 0.2])
        ctx = _ctx(db)
        pre_split_version = seg.version

        split_result = registry.invoke(
            db, "segment.split",
            {
                "segment_id": seg.id, "expected_version": pre_split_version,
                "parts": [
                    {"anchor": {"document_id": doc.id, "rect": [0.1, 0.1, 0.1, 0.1]}},
                    {"anchor": {"document_id": doc.id, "rect": [0.2, 0.2, 0.1, 0.1]}},
                ],
            },
            ctx,
        )
        new_ids = split_result.result["new_segment_ids"]
        current_kept_version = db.get(Segment, seg.id).version

        delete_pass_response = client.delete(f"/api/segments/passes/{pass_row.id}")
        assert delete_pass_response.status_code == 200, delete_pass_response.text

        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db, "segment.unsplit",
                {
                    "segment_id": seg.id, "version": pre_split_version,
                    "expected_version": current_kept_version,
                    "new_segment_ids": new_ids,
                    "expected_versions": {nid: db.get(Segment, nid).version for nid in new_ids},
                },
                ctx,
            )
        assert exc.value.status_code == 409
        # Nothing deleted -- refused before the hard-delete of the parts.
        for nid in new_ids:
            assert db.get(Segment, nid) is not None
