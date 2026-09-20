"""Source-model slice 4 — matches, forwarding notes, a citable reference (#4922).

`SegmentMatch`, `SegmentForwarding`, `SegmentCarry`, `resolve_segment`, the
merge/split/match/carry actions, and the citable reference resolved through
the EXISTING `/api/locations/resolve`. Each test names the behaviour id it
pins.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from fichero_server.actions.registry import ActionContext, registry
from fichero_server.models import (
    ActionAudit,
    ContentRepresentation,
    ContentRepresentationKind,
    DocType,
    Document,
    FileType,
    Segment,
    SegmentCarry,
    SegmentForwarding,
    SegmentForwardingTooDeep,
    SegmentMatch,
    SegmentPass,
    Status,
    resolve_segment,
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


def _ctx(db, *, actor: str = "system", run_id: str | None = None) -> ActionContext:
    return ActionContext(actor=actor, run_id=run_id, library_path=str(db.path.parent))


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


class TestMatchRecord:
    def test_propose_as_tool_accept_as_person_tool_accept_refused(self, db):
        """source.segment.match-record."""
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        a = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
        b = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])

        tool_ctx = _ctx(db, actor="importer", run_id="run-1")
        result = registry.invoke(
            db, "segment.match_propose",
            {"from_segment_id": a.id, "to_segment_id": b.id}, tool_ctx,
        )
        match_id = result.result["match_id"]
        match = db.get(SegmentMatch, match_id)
        assert match.proposed_by_kind == ProvenanceKind.workflow

        # A tool's accept is refused.
        with pytest.raises(Exception):
            registry.invoke(db, "segment.match_accept", {"match_id": match_id}, tool_ctx)
        assert db.get(SegmentMatch, match_id).state == "proposed"

        # A person's accept succeeds.
        person_ctx = _ctx(db, actor="daniel")
        registry.invoke(db, "segment.match_accept", {"match_id": match_id}, person_ctx)
        accepted = db.get(SegmentMatch, match_id)
        assert accepted.state == "accepted"
        assert accepted.accepted_by == "daniel"

        # Both segments keep their own ids; nothing in either row changed.
        assert db.get(Segment, a.id).id == a.id
        assert db.get(Segment, b.id).id == b.id
        assert db.get(Segment, a.id).anchor.rect == a.anchor.rect
        assert db.get(Segment, b.id).anchor.rect == b.anchor.rect


class TestForwardingNotes:
    def test_merge_split_delete_chain_resolves_in_one_call(self, db):
        """source.segment.forwarding-notes: merge A into B, split B into C
        and D, delete C: resolving A returns D alive and says C was
        deleted, by whom and when, in one call."""
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        seg_a = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.0, 0.0, 0.2, 0.2])
        seg_b = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.3, 0.3, 0.2, 0.2])
        ctx = _ctx(db, actor="daniel")

        registry.invoke(db, "segment.merge", {"segment_ids": [seg_a.id, seg_b.id], "keep_id": seg_b.id}, ctx)

        split_result = registry.invoke(
            db, "segment.split",
            {
                "segment_id": seg_b.id,
                "parts": [
                    {"anchor": {"document_id": doc.id, "rect": [0.3, 0.3, 0.1, 0.1]}},
                    {"anchor": {"document_id": doc.id, "rect": [0.5, 0.5, 0.1, 0.1]}},
                ],
            },
            ctx,
        )
        seg_c = seg_b.id  # "its id stays on one part"
        seg_d = split_result.result["new_segment_ids"][0]

        registry.invoke(
            db, "segment.delete",
            {"segment_ids": [seg_c]}, ctx,
        )
        # segment.delete (slice 3's internal one) does not itself write a
        # forwarding row -- write one directly the way slice 5's real
        # delete will, so resolve_segment sees the deletion in this test.
        db.save(SegmentForwarding(
            document_id=doc.id, old_segment_id=seg_c, kind="deleted",
            new_segment_ids=[], actor="daniel", audit_id="test-audit",
        ))

        resolved = resolve_segment(db, seg_a.id)
        assert resolved.live_segment_ids == [seg_d]
        assert not resolved.ended_in_delete  # D is alive
        deleted_entries = [row for row in resolved.trail if row.old_segment_id == seg_c and row.kind == "deleted"]
        assert len(deleted_entries) == 1
        assert deleted_entries[0].actor == "daniel"
        assert deleted_entries[0].created_at is not None

    def test_hand_made_chain_of_65_raises_too_deep(self, db):
        doc = _make_doc(db)
        ids = [f"seg-{i}" for i in range(66)]
        now_audit = "test-audit"
        for i in range(65):
            db.save(SegmentForwarding(
                document_id=doc.id, old_segment_id=ids[i], kind="merged",
                new_segment_ids=[ids[i + 1]], actor="daniel", audit_id=now_audit,
            ))
        with pytest.raises(SegmentForwardingTooDeep):
            resolve_segment(db, ids[0])

    def test_merge_a_into_b_then_b_into_a_is_a_real_loop_and_is_refused(self, db):
        """A genuine cycle of undone merges IS still refused -- the third
        look's fix (a diamond is not a loop) must not weaken this."""
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        seg_a = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.0, 0.0, 0.1, 0.1])
        seg_b = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.2, 0.2, 0.1, 0.1])
        ctx = _ctx(db, actor="daniel")

        registry.invoke(db, "segment.merge", {"segment_ids": [seg_a.id, seg_b.id], "keep_id": seg_b.id}, ctx)

        with pytest.raises(Exception):
            registry.invoke(
                db, "segment.merge",
                {"segment_ids": [seg_b.id, seg_a.id], "keep_id": seg_a.id}, ctx,
            )

    def test_cross_pass_and_cross_document_merge_is_refused(self, db):
        """A forward across passes or documents is refused
        (SegmentPassMismatch) -- confirmed and pinned by a test, per
        the third-look review's ask."""
        doc_1 = _make_doc(db, "doc1.jpg")
        doc_2 = _make_doc(db, "doc2.jpg")
        pass_1 = _make_pass(db, doc_1.id)
        pass_2 = _make_pass(db, doc_2.id)
        seg_1 = _make_segment(db, document_id=doc_1.id, pass_id=pass_1.id, rect=[0.0, 0.0, 0.1, 0.1])
        seg_2 = _make_segment(db, document_id=doc_2.id, pass_id=pass_2.id, rect=[0.0, 0.0, 0.1, 0.1])
        ctx = _ctx(db, actor="daniel")

        with pytest.raises(Exception):
            registry.invoke(
                db, "segment.merge",
                {"segment_ids": [seg_1.id, seg_2.id], "keep_id": seg_1.id}, ctx,
            )

        # Same document, different passes.
        pass_3 = _make_pass(db, doc_1.id)
        seg_3 = _make_segment(db, document_id=doc_1.id, pass_id=pass_3.id, rect=[0.5, 0.5, 0.1, 0.1])
        with pytest.raises(Exception):
            registry.invoke(
                db, "segment.merge",
                {"segment_ids": [seg_1.id, seg_3.id], "keep_id": seg_1.id}, ctx,
            )

    def _split_then_merge_back(self, db, ctx, *, keep_first: bool):
        """One fresh segment, split in two, then the parts merged back
        together -- in EITHER direction. Returns (original_id, sibling_id)."""
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        original = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.0, 0.0, 0.2, 0.2])

        split_result = registry.invoke(
            db, "segment.split",
            {
                "segment_id": original.id,
                "parts": [
                    {"anchor": {"document_id": doc.id, "rect": [0.0, 0.0, 0.1, 0.1]}},
                    {"anchor": {"document_id": doc.id, "rect": [0.1, 0.1, 0.1, 0.1]}},
                ],
            },
            ctx,
        )
        sibling_id = split_result.result["new_segment_ids"][0]

        keep_id = original.id if keep_first else sibling_id
        registry.invoke(
            db, "segment.merge",
            {"segment_ids": [original.id, sibling_id], "keep_id": keep_id}, ctx,
        )
        return original.id, sibling_id

    def test_split_then_merge_the_parts_back_both_ways_round(self, db):
        """#4922 third look: a diamond made by splitting and later
        rejoining by hand must NOT be refused as a loop, in either
        direction. Under the old (buggy) `forwards_to` this raised."""
        ctx = _ctx(db, actor="daniel")
        # Direction 1: the original id absorbs its own split-off sibling.
        self._split_then_merge_back(db, ctx, keep_first=True)
        # Direction 2: the sibling absorbs the original id.
        self._split_then_merge_back(db, ctx, keep_first=False)

    def test_the_diamond_split_into_two_then_both_merged_into_a_third(self, db):
        """#4922 third look: A split into A and B; A and B later merged
        into (one of) them. Resolving the ORIGINAL id reaches the survivor
        by two paths (the split's sibling list, and the merge's liveness
        note) -- a diamond, not a loop."""
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        original = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.0, 0.0, 0.2, 0.2])
        ctx = _ctx(db, actor="daniel")

        split_result = registry.invoke(
            db, "segment.split",
            {
                "segment_id": original.id,
                "parts": [
                    {"anchor": {"document_id": doc.id, "rect": [0.0, 0.0, 0.1, 0.1]}},
                    {"anchor": {"document_id": doc.id, "rect": [0.1, 0.1, 0.1, 0.1]}},
                ],
            },
            ctx,
        )
        sibling_id = split_result.result["new_segment_ids"][0]

        # Merge both split parts into the sibling (a fresh survivor id, not
        # the original) -- not refused.
        registry.invoke(
            db, "segment.merge",
            {"segment_ids": [original.id, sibling_id], "keep_id": sibling_id}, ctx,
        )

        resolved = resolve_segment(db, original.id)
        assert resolved.live_segment_ids == [sibling_id]

    def test_undo_of_merge_leaves_old_row_beside_a_restored_row(self, db, client):
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        seg_a = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.0, 0.0, 0.1, 0.1])
        seg_b = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.2, 0.2, 0.1, 0.1])
        ctx = _ctx(db, actor="daniel")

        merge_result = registry.invoke(
            db, "segment.merge", {"segment_ids": [seg_a.id, seg_b.id], "keep_id": seg_b.id}, ctx,
        )
        audit_id = merge_result.audit_id

        undo = client.post(f"/api/actions/audit/{audit_id}/undo")
        assert undo.status_code == 200, undo.text

        rows = db.query(SegmentForwarding, old_segment_id=seg_a.id)
        kinds = sorted(r.kind for r in rows)
        assert kinds == ["merged", "restored"]
        assert db.get(Segment, seg_a.id).deleted_at is None


class TestCarryAcrossAMatch:
    def test_one_to_one_carry_copies_reading_and_annotation_names_the_match(self, db):
        """source.segment.carry-across-a-match."""
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        rect = [0.1, 0.1, 0.2, 0.1]
        seg_from = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=rect)
        seg_to = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.5, 0.5, 0.2, 0.1])

        reading = ContentRepresentation(
            document_id=doc.id, kind=ContentRepresentationKind.transcription,
            content="hello world", source_anchor=seg_from.anchor,
        )
        db.save(reading)
        annotation = Annotation(document_id=doc.id, kind="highlight", anchor=seg_from.anchor)
        db.save(annotation)

        ctx = _ctx(db, actor="daniel")
        propose = registry.invoke(
            db, "segment.match_propose",
            {"from_segment_id": seg_from.id, "to_segment_id": seg_to.id}, ctx,
        )
        match_id = propose.result["match_id"]
        registry.invoke(db, "segment.match_accept", {"match_id": match_id}, ctx)

        carry_result = registry.invoke(
            db, "segment.carry", {"match_id": match_id, "kinds": ["reading", "annotation"]}, ctx,
        )
        carry_ids = carry_result.result["carry_ids"]
        copy_ids = carry_result.result["copy_ids"]
        assert len(carry_ids) == 2
        assert len(copy_ids) == 2

        # Originals untouched, still on the old segment's anchor.
        assert db.get(ContentRepresentation, reading.id).source_anchor.rect == rect
        assert db.get(Annotation, annotation.id).anchor.rect == rect

        # Copies exist, anchored to the NEW segment, each naming the match.
        carries = [db.get(SegmentCarry, cid) for cid in carry_ids]
        for carry in carries:
            assert carry.match_id == match_id
        reading_copy_id = next(c.copy_id for c in carries if c.carried_kind == "reading")
        annotation_copy_id = next(c.copy_id for c in carries if c.carried_kind == "annotation")
        assert db.get(ContentRepresentation, reading_copy_id).source_anchor.rect == seg_to.anchor.rect
        assert db.get(Annotation, annotation_copy_id).anchor.rect == seg_to.anchor.rect

        # Uncarry removes exactly the copies.
        registry.invoke(db, "segment.uncarry", {"carry_ids": carry_ids}, ctx)
        assert db.get(ContentRepresentation, reading_copy_id) is None
        assert db.get(Annotation, annotation_copy_id) is None
        assert db.get(ContentRepresentation, reading.id) is not None
        assert db.get(Annotation, annotation.id) is not None

    def test_many_to_many_match_carries_no_reading_and_says_why(self, db):
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        seg_from = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.2, 0.1])
        seg_to_1 = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.5, 0.5, 0.1, 0.1])
        seg_to_2 = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.6, 0.6, 0.1, 0.1])

        ctx = _ctx(db, actor="daniel")
        p1 = registry.invoke(
            db, "segment.match_propose",
            {"from_segment_id": seg_from.id, "to_segment_id": seg_to_1.id}, ctx,
        ).result["match_id"]
        p2 = registry.invoke(
            db, "segment.match_propose",
            {"from_segment_id": seg_from.id, "to_segment_id": seg_to_2.id}, ctx,
        ).result["match_id"]
        registry.invoke(db, "segment.match_accept", {"match_id": p1}, ctx)
        registry.invoke(db, "segment.match_accept", {"match_id": p2}, ctx)

        carry_result = registry.invoke(db, "segment.carry", {"match_id": p1, "kinds": ["reading"]}, ctx)
        assert carry_result.result["carry_ids"] == []
        not_carried = carry_result.result["not_carried"]
        assert len(not_carried) == 1
        assert not_carried[0]["kind"] == "reading"
        assert "not-one-to-one" in not_carried[0]["reason"] or "not one-to-one" in not_carried[0]["reason"]


class TestCitableReference:
    def test_reference_resolves_through_locations_resolve(self, db, client):
        """source.segment.citable."""
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        seg = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.2, 0.1])

        r = client.get(f"/api/segments/{seg.id}/reference")
        assert r.status_code == 200, r.text
        reference = r.json()["reference"]
        assert reference.startswith("fichero:segment/")
        assert reference.endswith(f"/{doc.id}/{seg.id}")

        resolved = client.post("/api/locations/resolve", json={"segmentId": reference})
        assert resolved.status_code == 200, resolved.text
        body = resolved.json()
        assert body["resolvedDocumentId"] == doc.id
        assert body["resolvedSegmentId"] == seg.id
        assert body["segmentDeleted"] is False

    def test_reference_after_merge_resolves_to_kept_segment_with_trail(self, db, client):
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        seg_a = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.0, 0.0, 0.1, 0.1])
        seg_b = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.2, 0.2, 0.1, 0.1])
        ctx = _ctx(db, actor="daniel")
        registry.invoke(db, "segment.merge", {"segment_ids": [seg_a.id, seg_b.id], "keep_id": seg_b.id}, ctx)

        resolved = client.post("/api/locations/resolve", json={"segmentId": seg_a.id})
        assert resolved.status_code == 200, resolved.text
        body = resolved.json()
        assert body["resolvedSegmentId"] == seg_b.id
        assert body["resolvedDocumentId"] == doc.id
        assert len(body["segmentForwarding"]) == 1
        assert body["segmentForwarding"][0]["kind"] == "merged"

    def test_reference_after_delete_says_deleted(self, db, client):
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        seg = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.0, 0.0, 0.1, 0.1])
        db.save(SegmentForwarding(
            document_id=doc.id, old_segment_id=seg.id, kind="deleted",
            new_segment_ids=[], actor="daniel", audit_id="test-audit",
        ))

        resolved = client.post("/api/locations/resolve", json={"segmentId": seg.id})
        assert resolved.status_code == 200, resolved.text
        body = resolved.json()
        assert body["segmentDeleted"] is True
        assert body["resolvedDocumentId"] == doc.id


class TestAuditPayloadsCarryNoFreeText:
    def test_no_action_audit_payload_contains_reading_text(self, db):
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        rect = [0.1, 0.1, 0.2, 0.1]
        seg_from = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=rect)
        seg_to = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.5, 0.5, 0.2, 0.1])
        secret_text = "the quick brown fox jumps over the lazy dog TOP SECRET"
        reading = ContentRepresentation(
            document_id=doc.id, kind=ContentRepresentationKind.transcription,
            content=secret_text, source_anchor=seg_from.anchor,
        )
        db.save(reading)

        ctx = _ctx(db, actor="daniel")
        match_id = registry.invoke(
            db, "segment.match_propose",
            {"from_segment_id": seg_from.id, "to_segment_id": seg_to.id}, ctx,
        ).result["match_id"]
        registry.invoke(db, "segment.match_accept", {"match_id": match_id}, ctx)
        registry.invoke(db, "segment.carry", {"match_id": match_id, "kinds": ["reading"]}, ctx)
        registry.invoke(db, "segment.merge", {"segment_ids": [seg_from.id, seg_to.id], "keep_id": seg_to.id}, ctx)

        for audit in db.all(ActionAudit):
            if not audit.action_name.startswith("segment."):
                continue
            payload = json.dumps({"before": audit.before, "after": audit.after, "params": audit.params})
            assert secret_text not in payload, f"{audit.action_name} leaked reading text into its audit payload"


class TestCarryNeverCopiesAStatement:
    def test_claim_evidence_is_refused_not_carried(self, db):
        """#4922 review: a claim is knowledge, never a page mark -- carry
        must never create a second claim row. Statements are carried in
        the statements step (slice 8)."""
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        seg_from = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.2, 0.1])
        seg_to = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.5, 0.5, 0.2, 0.1])
        ctx = _ctx(db, actor="daniel")
        match_id = registry.invoke(
            db, "segment.match_propose",
            {"from_segment_id": seg_from.id, "to_segment_id": seg_to.id}, ctx,
        ).result["match_id"]
        registry.invoke(db, "segment.match_accept", {"match_id": match_id}, ctx)

        from fichero_server.models import KnowledgeClaim

        claims_before = len(db.all(KnowledgeClaim))
        with pytest.raises(Exception):
            registry.invoke(db, "segment.carry", {"match_id": match_id, "kinds": ["claim_evidence"]}, ctx)
        assert len(db.all(KnowledgeClaim)) == claims_before

    def test_carried_reading_keeps_its_character_span(self, db):
        """#4922 review: a carried copy's anchor is the new segment's own,
        but the ORIGINAL's character span survives (a wholesale anchor
        replacement would otherwise drop it)."""
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        rect = [0.1, 0.1, 0.2, 0.1]
        seg_from = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=rect)
        seg_to = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.5, 0.5, 0.2, 0.1])
        anchor_with_span = seg_from.anchor.model_copy(update={"char_start": 3, "char_end": 9})
        reading = ContentRepresentation(
            document_id=doc.id, kind=ContentRepresentationKind.transcription,
            content="hello world", source_anchor=anchor_with_span,
        )
        db.save(reading)

        ctx = _ctx(db, actor="daniel")
        match_id = registry.invoke(
            db, "segment.match_propose",
            {"from_segment_id": seg_from.id, "to_segment_id": seg_to.id}, ctx,
        ).result["match_id"]
        registry.invoke(db, "segment.match_accept", {"match_id": match_id}, ctx)
        carry_result = registry.invoke(db, "segment.carry", {"match_id": match_id, "kinds": ["reading"]}, ctx)
        copy_id = carry_result.result["copy_ids"][0]

        copy = db.get(ContentRepresentation, copy_id)
        assert copy.source_anchor.rect == seg_to.anchor.rect  # the NEW place
        assert copy.source_anchor.char_start == 3  # the ORIGINAL's span, kept
        assert copy.source_anchor.char_end == 9

    def test_carry_across_an_unaccepted_match_is_refused(self, db):
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        seg_from = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.2, 0.1])
        seg_to = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.5, 0.5, 0.2, 0.1])
        ctx = _ctx(db, actor="daniel")
        match_id = registry.invoke(
            db, "segment.match_propose",
            {"from_segment_id": seg_from.id, "to_segment_id": seg_to.id}, ctx,
        ).result["match_id"]
        # Never accepted.
        with pytest.raises(Exception):
            registry.invoke(db, "segment.carry", {"match_id": match_id, "kinds": ["reading"]}, ctx)

    def test_uncarry_removes_exactly_the_copies_never_an_original(self, db):
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        rect = [0.1, 0.1, 0.2, 0.1]
        seg_from = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=rect)
        seg_to = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.5, 0.5, 0.2, 0.1])
        reading = ContentRepresentation(
            document_id=doc.id, kind=ContentRepresentationKind.transcription,
            content="hello", source_anchor=seg_from.anchor,
        )
        db.save(reading)
        ctx = _ctx(db, actor="daniel")
        match_id = registry.invoke(
            db, "segment.match_propose",
            {"from_segment_id": seg_from.id, "to_segment_id": seg_to.id}, ctx,
        ).result["match_id"]
        registry.invoke(db, "segment.match_accept", {"match_id": match_id}, ctx)
        carry_result = registry.invoke(db, "segment.carry", {"match_id": match_id, "kinds": ["reading"]}, ctx)
        copy_id = carry_result.result["copy_ids"][0]
        carry_id = carry_result.result["carry_ids"][0]

        registry.invoke(db, "segment.uncarry", {"carry_ids": [carry_id]}, ctx)
        assert db.get(ContentRepresentation, copy_id) is None
        assert db.get(ContentRepresentation, reading.id) is not None
        assert db.get(SegmentCarry, carry_id) is None


class TestMissingActionCoverage:
    """Behaviours the third-look review named as untested: eleven actions,
    seven routes, and eleven tests was too few."""

    def test_segment_unsplit(self, db, client):
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        original = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.0, 0.0, 0.2, 0.2])
        original_rect = list(original.anchor.rect)
        ctx = _ctx(db, actor="daniel")
        split_result = registry.invoke(
            db, "segment.split",
            {
                "segment_id": original.id,
                "parts": [
                    {"anchor": {"document_id": doc.id, "rect": [0.0, 0.0, 0.1, 0.1]}},
                    {"anchor": {"document_id": doc.id, "rect": [0.1, 0.1, 0.1, 0.1]}},
                ],
            },
            ctx,
        )
        new_id = split_result.result["new_segment_ids"][0]

        undo = client.post(f"/api/actions/audit/{split_result.audit_id}/undo")
        assert undo.status_code == 200, undo.text

        assert db.get(Segment, new_id) is None  # hard-deleted, existed only for this action
        restored = db.get(Segment, original.id)
        assert restored.anchor.rect == original_rect
        assert restored.deleted_at is None
        rows = db.query(SegmentForwarding, old_segment_id=original.id)
        assert any(r.kind == "restored" for r in rows)

    def test_match_withdraw(self, db):
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        a = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
        b = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.3, 0.3, 0.1, 0.1])
        ctx = _ctx(db, actor="daniel")
        match_id = registry.invoke(
            db, "segment.match_propose", {"from_segment_id": a.id, "to_segment_id": b.id}, ctx,
        ).result["match_id"]
        registry.invoke(db, "segment.match_withdraw", {"match_id": match_id}, ctx)
        assert db.get(SegmentMatch, match_id) is None

    def test_match_reject(self, db):
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        a = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
        b = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.3, 0.3, 0.1, 0.1])
        ctx = _ctx(db, actor="daniel")
        match_id = registry.invoke(
            db, "segment.match_propose", {"from_segment_id": a.id, "to_segment_id": b.id}, ctx,
        ).result["match_id"]
        registry.invoke(db, "segment.match_reject", {"match_id": match_id}, ctx)
        assert db.get(SegmentMatch, match_id).state == "rejected"

    def test_match_set_state(self, db):
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        a = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
        b = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.3, 0.3, 0.1, 0.1])
        ctx = _ctx(db, actor="daniel")
        match_id = registry.invoke(
            db, "segment.match_propose", {"from_segment_id": a.id, "to_segment_id": b.id}, ctx,
        ).result["match_id"]
        registry.invoke(db, "segment.match_accept", {"match_id": match_id}, ctx)
        registry.invoke(db, "segment.match_set_state", {"match_id": match_id, "state": "proposed"}, ctx)
        reverted = db.get(SegmentMatch, match_id)
        assert reverted.state == "proposed"
        assert reverted.accepted_by is None


class TestMoreRefusals:
    def test_keep_id_not_among_segment_ids_is_refused(self, db):
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        a = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
        b = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.3, 0.3, 0.1, 0.1])
        ctx = _ctx(db, actor="daniel")
        with pytest.raises(Exception):
            registry.invoke(
                db, "segment.merge",
                {"segment_ids": [a.id, b.id], "keep_id": "not-a-real-id"}, ctx,
            )

    def test_split_with_fewer_than_two_parts_is_refused(self, db):
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        original = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.0, 0.0, 0.2, 0.2])
        ctx = _ctx(db, actor="daniel")
        with pytest.raises(Exception):
            registry.invoke(
                db, "segment.split",
                {"segment_id": original.id, "parts": [{"anchor": {"document_id": doc.id, "rect": [0.0, 0.0, 0.1, 0.1]}}]},
                ctx,
            )

    def test_split_with_a_part_outside_the_image_is_refused(self, db):
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        original = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.0, 0.0, 0.2, 0.2])
        ctx = _ctx(db, actor="daniel")
        with pytest.raises(Exception):
            registry.invoke(
                db, "segment.split",
                {
                    "segment_id": original.id,
                    "parts": [
                        {"anchor": {"document_id": doc.id, "rect": [0.0, 0.0, 0.1, 0.1]}},
                        {"anchor": {"document_id": doc.id, "rect": [0.9, 0.9, 0.5, 0.5]}},
                    ],
                },
                ctx,
            )

    @pytest.mark.parametrize("action_name,build_params", [
        ("segment.match_propose", lambda a, b: {"from_segment_id": "legacy:x", "to_segment_id": b.id}),
        ("segment.merge", lambda a, b: {"segment_ids": ["legacy:x", b.id], "keep_id": b.id}),
        ("segment.split", lambda a, b: {"segment_id": "legacy:x", "parts": [
            {"anchor": {"document_id": "d", "rect": [0, 0, 0.1, 0.1]}},
            {"anchor": {"document_id": "d", "rect": [0.5, 0.5, 0.1, 0.1]}},
        ]}),
    ])
    def test_a_legacy_id_is_refused_on_each_action(self, db, action_name, build_params):
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        a = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
        b = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.3, 0.3, 0.1, 0.1])
        ctx = _ctx(db, actor="daniel")
        with pytest.raises(Exception):
            registry.invoke(db, action_name, build_params(a, b), ctx)

    def test_a_legacy_id_is_refused_on_segment_reference_route(self, db, client):
        r = client.get("/api/segments/legacy:some-artifact:0/reference")
        assert r.status_code == 422


class TestSegmentNotLive:
    """#4922 second look: merge, split and carry accept only LIVE
    participants -- otherwise a soft-deleted or already-merged-away
    segment could be "merged", writing a note newer than the one that
    actually explains its state, and a delete would quietly become a
    merge."""

    def _deleted_segment(self, db, doc, pass_row):
        seg = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.7, 0.7, 0.1, 0.1])
        db.save(SegmentForwarding(
            document_id=doc.id, old_segment_id=seg.id, kind="deleted",
            new_segment_ids=[], actor="daniel", audit_id="test-audit",
            sequence=db.next_forwarding_sequence(),
        ))
        return seg

    def _merged_away_segment(self, db, doc, pass_row, ctx):
        seg = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.8, 0.8, 0.1, 0.1])
        keep = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.85, 0.85, 0.1, 0.1])
        registry.invoke(db, "segment.merge", {"segment_ids": [seg.id, keep.id], "keep_id": keep.id}, ctx)
        return seg

    @pytest.mark.parametrize("reason", ["deleted", "merged"])
    def test_merge_refuses_a_not_live_participant(self, db, reason):
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        ctx = _ctx(db, actor="daniel")
        live = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
        not_live = (
            self._deleted_segment(db, doc, pass_row) if reason == "deleted"
            else self._merged_away_segment(db, doc, pass_row, ctx)
        )
        with pytest.raises(Exception):
            registry.invoke(
                db, "segment.merge",
                {"segment_ids": [live.id, not_live.id], "keep_id": live.id}, ctx,
            )

    @pytest.mark.parametrize("reason", ["deleted", "merged"])
    def test_merge_refuses_a_not_live_keep_id(self, db, reason):
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        ctx = _ctx(db, actor="daniel")
        live = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
        not_live = (
            self._deleted_segment(db, doc, pass_row) if reason == "deleted"
            else self._merged_away_segment(db, doc, pass_row, ctx)
        )
        with pytest.raises(Exception):
            registry.invoke(
                db, "segment.merge",
                {"segment_ids": [live.id, not_live.id], "keep_id": not_live.id}, ctx,
            )

    @pytest.mark.parametrize("reason", ["deleted", "merged"])
    def test_split_refuses_a_not_live_segment(self, db, reason):
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        ctx = _ctx(db, actor="daniel")
        not_live = (
            self._deleted_segment(db, doc, pass_row) if reason == "deleted"
            else self._merged_away_segment(db, doc, pass_row, ctx)
        )
        with pytest.raises(Exception):
            registry.invoke(
                db, "segment.split",
                {
                    "segment_id": not_live.id,
                    "parts": [
                        {"anchor": {"document_id": doc.id, "rect": [0.0, 0.0, 0.1, 0.1]}},
                        {"anchor": {"document_id": doc.id, "rect": [0.5, 0.5, 0.1, 0.1]}},
                    ],
                },
                ctx,
            )

    @pytest.mark.parametrize("reason", ["deleted", "merged"])
    @pytest.mark.parametrize("end", ["from", "to"])
    def test_carry_refuses_a_not_live_end(self, db, reason, end):
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        ctx = _ctx(db, actor="daniel")
        live = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
        not_live = (
            self._deleted_segment(db, doc, pass_row) if reason == "deleted"
            else self._merged_away_segment(db, doc, pass_row, ctx)
        )
        from_id, to_id = (not_live.id, live.id) if end == "from" else (live.id, not_live.id)

        # match_propose/accept themselves don't check liveness (a match can
        # legitimately be proposed before either side changes); the refusal
        # is at carry time, against the CURRENT state of both ends.
        match_id = registry.invoke(
            db, "segment.match_propose", {"from_segment_id": from_id, "to_segment_id": to_id}, ctx,
        ).result["match_id"]
        registry.invoke(db, "segment.match_accept", {"match_id": match_id}, ctx)
        with pytest.raises(Exception):
            registry.invoke(db, "segment.carry", {"match_id": match_id, "kinds": ["annotation"]}, ctx)


class TestSegmentReferenceRouteAlone:
    def test_reference_route_404s_for_an_unknown_segment(self, db, client):
        r = client.get("/api/segments/does-not-exist/reference")
        assert r.status_code == 404


class TestCitableStringValidation:
    def test_reference_from_another_library_is_refused(self, db, client):
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        seg = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
        bogus_reference = f"fichero:segment/not-this-library-uuid/{doc.id}/{seg.id}"
        r = client.post("/api/locations/resolve", json={"segmentId": bogus_reference})
        assert r.status_code == 422

    def test_document_id_and_segment_id_disagreeing_is_refused(self, db, client):
        doc_1 = _make_doc(db, "doc1.jpg")
        doc_2 = _make_doc(db, "doc2.jpg")
        pass_1 = _make_pass(db, doc_1.id)
        seg = _make_segment(db, document_id=doc_1.id, pass_id=pass_1.id, rect=[0.1, 0.1, 0.1, 0.1])
        r = client.post("/api/locations/resolve", json={"documentId": doc_2.id, "segmentId": seg.id})
        assert r.status_code == 422


class TestSplitReturnsAllLiveParts:
    def test_reference_made_before_a_split_resolves_to_both_parts(self, db, client):
        """#4922 third look: a reference to a line later cut in two must
        not quietly open one half."""
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        original = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.0, 0.0, 0.2, 0.2])
        ctx = _ctx(db, actor="daniel")

        split_result = registry.invoke(
            db, "segment.split",
            {
                "segment_id": original.id,
                "parts": [
                    {"anchor": {"document_id": doc.id, "rect": [0.0, 0.0, 0.1, 0.1]}},
                    {"anchor": {"document_id": doc.id, "rect": [0.1, 0.1, 0.1, 0.1]}},
                ],
            },
            ctx,
        )
        new_id = split_result.result["new_segment_ids"][0]

        resolved = client.post("/api/locations/resolve", json={"segmentId": original.id})
        assert resolved.status_code == 200, resolved.text
        body = resolved.json()
        assert set(body["liveSegmentIds"]) == {original.id, new_id}
        # The part that kept the id is the primary.
        assert body["resolvedSegmentId"] == original.id


class TestInvariants:
    def test_every_slice_4_action_preserves_identity_and_append_only_forwarding(self, db, client):
        """The third-look review's invariant test: run every slice 4
        action, then assert (a) no Segment's id/document_id/pass_id ever
        changed, (b) the forwarding table only GREW and no pre-existing
        row differs byte for byte, (c) after unmerge the old merged note
        is still there AND a restored note was added."""
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        seg_a = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.0, 0.0, 0.1, 0.1])
        seg_b = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.2, 0.2, 0.1, 0.1])
        seg_x = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.4, 0.4, 0.1, 0.1])
        seg_y = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.6, 0.6, 0.1, 0.1])
        ctx = _ctx(db, actor="daniel")

        identity_before = {
            s.id: (s.id, s.document_id, s.pass_id) for s in (seg_a, seg_b, seg_x, seg_y)
        }

        # match: propose, accept, carry, uncarry, reject, withdraw.
        reading = ContentRepresentation(
            document_id=doc.id, kind=ContentRepresentationKind.transcription,
            content="hello", source_anchor=seg_x.anchor,
        )
        db.save(reading)
        match_xy = registry.invoke(
            db, "segment.match_propose", {"from_segment_id": seg_x.id, "to_segment_id": seg_y.id}, ctx,
        ).result["match_id"]
        registry.invoke(db, "segment.match_accept", {"match_id": match_xy}, ctx)
        carry_ids = registry.invoke(
            db, "segment.carry", {"match_id": match_xy, "kinds": ["reading"]}, ctx,
        ).result["carry_ids"]
        registry.invoke(db, "segment.uncarry", {"carry_ids": carry_ids}, ctx)

        match_to_reject = registry.invoke(
            db, "segment.match_propose", {"from_segment_id": seg_a.id, "to_segment_id": seg_x.id}, ctx,
        ).result["match_id"]
        registry.invoke(db, "segment.match_reject", {"match_id": match_to_reject}, ctx)

        match_to_withdraw = registry.invoke(
            db, "segment.match_propose", {"from_segment_id": seg_b.id, "to_segment_id": seg_y.id}, ctx,
        ).result["match_id"]
        registry.invoke(db, "segment.match_withdraw", {"match_id": match_to_withdraw}, ctx)

        # merge, then snapshot the forwarding table.
        merge_result = registry.invoke(
            db, "segment.merge", {"segment_ids": [seg_a.id, seg_b.id], "keep_id": seg_b.id}, ctx,
        )
        forwarding_after_merge = {r.id: r.model_dump(mode="json") for r in db.all(SegmentForwarding)}
        assert len(forwarding_after_merge) >= 1

        # split.
        registry.invoke(
            db, "segment.split",
            {
                "segment_id": seg_b.id,
                "parts": [
                    {"anchor": {"document_id": doc.id, "rect": [0.2, 0.2, 0.05, 0.05]}},
                    {"anchor": {"document_id": doc.id, "rect": [0.25, 0.25, 0.05, 0.05]}},
                ],
            },
            ctx,
        )

        # undo the merge -> segment.unmerge.
        undo = client.post(f"/api/actions/audit/{merge_result.audit_id}/undo")
        assert undo.status_code == 200, undo.text

        # (a) identity never changes.
        for original_id, (id_, document_id, pass_id) in identity_before.items():
            row = db.get(Segment, original_id)
            assert row is not None
            assert (row.id, row.document_id, row.pass_id) == (id_, document_id, pass_id)

        # (b) forwarding table only grew; no pre-existing row mutated.
        forwarding_after_everything = {r.id: r.model_dump(mode="json") for r in db.all(SegmentForwarding)}
        assert len(forwarding_after_everything) > len(forwarding_after_merge)
        for fid, snapshot in forwarding_after_merge.items():
            assert forwarding_after_everything[fid] == snapshot, f"forwarding row {fid} was mutated"

        # (c) after unmerge: the old merged note is there AND a restored note was added.
        rows_for_a = db.query(SegmentForwarding, old_segment_id=seg_a.id)
        kinds = sorted(r.kind for r in rows_for_a)
        assert kinds == ["merged", "restored"]


class TestRollbackOnlyInAnger:
    def test_a_failed_forwarding_write_leaves_nothing_behind(self, db, monkeypatch):
        """#4922 third look: make the SECOND write of a merge fail (the
        forwarding note, after the absorbed segment's soft-delete), and
        assert no absorbed segment is soft-deleted, no note was written,
        and the audit table is unchanged -- the rollback-only transaction
        actually rolls back the whole action, not just its own step."""
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        seg_a = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.0, 0.0, 0.1, 0.1])
        seg_b = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.2, 0.2, 0.1, 0.1])
        ctx = _ctx(db, actor="daniel")

        original_save = db.save

        def failing_save(obj):
            if isinstance(obj, SegmentForwarding):
                raise RuntimeError("simulated failure writing the forwarding note")
            return original_save(obj)

        monkeypatch.setattr(db, "save", failing_save)

        audits_before = len(db.all(ActionAudit))
        forwarding_before = len(db.all(SegmentForwarding))
        with pytest.raises(RuntimeError):
            registry.invoke(
                db, "segment.merge", {"segment_ids": [seg_a.id, seg_b.id], "keep_id": seg_b.id}, ctx,
            )

        assert db.get(Segment, seg_a.id).deleted_at is None
        assert len(db.all(SegmentForwarding)) == forwarding_before
        assert len(db.all(ActionAudit)) == audits_before


# ---------------------------------------------------------------------------
# One parametrized test over EVERY write route in the segments router
# (#4922 second look): built from `router.routes` itself, so a route added
# in a later slice either gets its id fields listed here or FAILS this
# test for being unlisted -- it can never silently ship uncovered.
#
# Scope: a "provisional id" is `LEGACY_ID_PREFIX`-shaped and can only ever
# be a segment/pass id (`source.seam.provisional-ids-refused`). Fields
# like `match_id`/`carry_id` are never provisional-shaped -- a `legacy:`
# string there is simply "not found" (404), not a refused write, so they
# are listed with no id fields to check rather than silently skipped.
# Read-only routes (the GET seam by document id) are listed the same way.
# ---------------------------------------------------------------------------

from fichero_server.api.routes.document import segments as _segments_route_module  # noqa: E402

#: (method, path exactly as declared on the router) -> list of id checks.
#: Each check is `(field_path_description, request_builder)`, where
#: `request_builder(doc_id, pass_id)` returns `(method, url, json_or_None)`
#: with ONE field replaced by a `legacy:` id.
_ROUTE_ID_CHECKS: dict[tuple[str, str], list[tuple[str, Any]]] = {
    ("GET", "/segments/document/{doc_id}"): [],  # read-only seam, no provisional refusal here
    ("POST", "/segments/passes"): [
        ("document_id", lambda doc_id, pass_id: (
            "POST", "/api/segments/passes", {"document_id": "legacy:x", "name": "n"},
        )),
        ("source_artifact_id", lambda doc_id, pass_id: (
            "POST", "/api/segments/passes",
            {"document_id": doc_id, "name": "n", "source_artifact_id": "legacy:x"},
        )),
    ],
    ("DELETE", "/segments/passes/{pass_id}"): [
        ("pass_id (path)", lambda doc_id, pass_id: ("DELETE", "/api/segments/passes/legacy:x", None)),
    ],
    ("POST", "/segments"): [
        ("document_id", lambda doc_id, pass_id: (
            "POST", "/api/segments",
            {"document_id": "legacy:x", "pass_id": pass_id, "kind": "word",
             "anchor": {"document_id": "legacy:x", "rect": [0.1, 0.1, 0.1, 0.1]}},
        )),
        ("pass_id", lambda doc_id, pass_id: (
            "POST", "/api/segments",
            {"document_id": doc_id, "pass_id": "legacy:x", "kind": "word",
             "anchor": {"document_id": doc_id, "rect": [0.1, 0.1, 0.1, 0.1]}},
        )),
        ("parent_segment_id", lambda doc_id, pass_id: (
            "POST", "/api/segments",
            {"document_id": doc_id, "pass_id": pass_id, "kind": "word",
             "anchor": {"document_id": doc_id, "rect": [0.1, 0.1, 0.1, 0.1]},
             "parent_segment_id": "legacy:x"},
        )),
    ],
    ("POST", "/segments/bulk"): [
        ("document_id", lambda doc_id, pass_id: (
            "POST", "/api/segments/bulk",
            {"document_id": "legacy:x", "pass_id": pass_id,
             "segments": [{"kind": "word", "anchor": {"document_id": "legacy:x", "rect": [0.1, 0.1, 0.1, 0.1]}}]},
        )),
        ("pass_id", lambda doc_id, pass_id: (
            "POST", "/api/segments/bulk",
            {"document_id": doc_id, "pass_id": "legacy:x",
             "segments": [{"kind": "word", "anchor": {"document_id": doc_id, "rect": [0.1, 0.1, 0.1, 0.1]}}]},
        )),
    ],
    ("POST", "/segments/matches"): [
        ("from_segment_id", lambda doc_id, pass_id: (
            "POST", "/api/segments/matches", {"from_segment_id": "legacy:x", "to_segment_id": "real"},
        )),
        ("to_segment_id", lambda doc_id, pass_id: (
            "POST", "/api/segments/matches", {"from_segment_id": "real", "to_segment_id": "legacy:x"},
        )),
    ],
    ("POST", "/segments/matches/{match_id}/accept"): [],  # match_id is never provisional-shaped
    ("POST", "/segments/matches/{match_id}/reject"): [],
    ("POST", "/segments/merge"): [
        ("segment_ids[]", lambda doc_id, pass_id: (
            "POST", "/api/segments/merge", {"segment_ids": ["legacy:x", "real"], "keep_id": "real"},
        )),
        ("keep_id", lambda doc_id, pass_id: (
            "POST", "/api/segments/merge", {"segment_ids": ["real", "real2"], "keep_id": "legacy:x"},
        )),
    ],
    ("POST", "/segments/split"): [
        ("segment_id", lambda doc_id, pass_id: (
            "POST", "/api/segments/split",
            {"segment_id": "legacy:x", "parts": [
                {"anchor": {"document_id": doc_id, "rect": [0.0, 0.0, 0.1, 0.1]}},
                {"anchor": {"document_id": doc_id, "rect": [0.5, 0.5, 0.1, 0.1]}},
            ]},
        )),
    ],
    ("POST", "/segments/carry"): [],  # match_id is never provisional-shaped
    ("GET", "/segments/{segment_id}/reference"): [
        ("segment_id (path)", lambda doc_id, pass_id: ("GET", "/api/segments/legacy:x/reference", None)),
    ],
}


def test_router_route_list_matches_the_checked_route_list():
    """Fails closed: a route added to the segments router that is not
    listed in `_ROUTE_ID_CHECKS` above fails HERE, by name -- it cannot
    ship with its provisional-id handling silently unchecked."""
    actual_routes = {
        (method, route.path)
        for route in _segments_route_module.router.routes
        for method in route.methods
    }
    listed_routes = set(_ROUTE_ID_CHECKS.keys())
    missing = actual_routes - listed_routes
    assert not missing, f"route(s) not listed in _ROUTE_ID_CHECKS: {sorted(missing)}"
    stale = listed_routes - actual_routes
    assert not stale, f"_ROUTE_ID_CHECKS lists route(s) that no longer exist: {sorted(stale)}"


@pytest.mark.parametrize(
    "route_key,field_name,build_request",
    [
        (route_key, field_name, build_request)
        for route_key, checks in _ROUTE_ID_CHECKS.items()
        for field_name, build_request in checks
    ],
    ids=[
        f"{method}-{path}-{field_name}"
        for (method, path), checks in _ROUTE_ID_CHECKS.items()
        for field_name, _build_request in checks
    ],
)
def test_a_legacy_id_is_refused_with_422_on_every_write_route_field(
    db, client, route_key, field_name, build_request,
):
    doc = _make_doc(db)
    pass_row = _make_pass(db, doc.id)
    a = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
    b = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.3, 0.3, 0.1, 0.1])

    method, url, json_body = build_request(doc.id, pass_row.id)
    if json_body is not None:
        json_body = json.loads(
            json.dumps(json_body).replace('"real2"', f'"{b.id}"').replace('"real"', f'"{a.id}"')
        )
    r = client.request(method, url, json=json_body)
    assert r.status_code == 422, f"{route_key} field {field_name!r}: expected 422, got {r.status_code}: {r.text}"
    assert "provisional" in r.text, f"{route_key} field {field_name!r}: 422 detail did not name 'provisional'"
