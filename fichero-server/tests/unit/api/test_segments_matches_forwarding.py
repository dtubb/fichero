"""Source-model slice 4 — matches, forwarding notes, a citable reference (#4922).

`SegmentMatch`, `SegmentForwarding`, `SegmentCarry`, `resolve_segment`, the
merge/split/match/carry actions, and the citable reference resolved through
the EXISTING `/api/locations/resolve`. Each test names the behaviour id it
pins.
"""

from __future__ import annotations

import inspect
import json
import sys
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
    SegmentVersion,
    Status,
    forwards_to,
    primary_live_segment_id,
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


def _invoke_versioned(db, action_name: str, params: dict, ctx: ActionContext):
    """`registry.invoke`, auto-filling the compare-and-set token(s) #4957
    follow-up 1 added to `segment.merge`/`.unmerge`/`.split`/`.unsplit`/
    `.carry`/`.uncarry` from the CURRENT live `Segment` rows the call
    names -- these tests exercise the action's OWN behaviour, not hand-
    tracked version bookkeeping across a chain of calls. A named id that
    does not resolve to a real `Segment` (a deliberately bogus/legacy id
    in a refusal test) is left out; the action's own checks refuse it for
    the reason under test, same as before this helper existed."""
    params = dict(params)

    def _version(segment_id: str) -> int | None:
        row = db.get(Segment, segment_id)
        return row.version if row is not None else None

    if action_name == "segment.merge":
        versions = {sid: v for sid in params.get("segment_ids", []) if (v := _version(sid)) is not None}
        params.setdefault("expected_versions", versions)
    elif action_name == "segment.unmerge":
        versions = {sid: v for sid in params.get("versions", {}) if (v := _version(sid)) is not None}
        params.setdefault("expected_versions", versions)
    elif action_name == "segment.split":
        v = _version(params.get("segment_id", ""))
        if v is not None:
            params.setdefault("expected_version", v)
    elif action_name == "segment.unsplit":
        v = _version(params.get("segment_id", ""))
        if v is not None:
            params.setdefault("expected_version", v)
        versions = {
            nid: v for nid in params.get("new_segment_ids", []) if (v := _version(nid)) is not None
        }
        params.setdefault("expected_versions", versions)
    elif action_name == "segment.carry":
        match = db.get(SegmentMatch, params.get("match_id", ""))
        if match is not None:
            versions = {
                sid: v for sid in (match.from_segment_id, match.to_segment_id)
                if (v := _version(sid)) is not None
            }
            params.setdefault("expected_versions", versions)
    elif action_name == "segment.uncarry":
        segment_ids: set[str] = set()
        for carry_id in params.get("carry_ids", []):
            carry = db.get(SegmentCarry, carry_id)
            if carry is None:
                continue
            match = db.get(SegmentMatch, carry.match_id)
            if match is not None:
                segment_ids.add(match.from_segment_id)
                segment_ids.add(match.to_segment_id)
        versions = {sid: v for sid in segment_ids if (v := _version(sid)) is not None}
        params.setdefault("expected_versions", versions)
    return registry.invoke(db, action_name, params, ctx)


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
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as excinfo:
            registry.invoke(db, "segment.match_accept", {"match_id": match_id}, tool_ctx)
        assert excinfo.value.status_code == 422
        assert excinfo.value.detail == "only a person can accept a match"
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


class TestMatchAcceptProvenanceRealActorShapes:
    """test-audit F15, 2026-09-20: `MatchNeedsAPerson` ("only a person
    accepts a match") is enforced by `_provenance_kind_from_ctx(ctx) ==
    ProvenanceKind.human`. That function used to check only `run_id` and
    `actor`, so a call arriving through the MCP tool surface -- REAL shape:
    `ActionContext(actor=<the authenticated user's own name>, via_mcp=True)`,
    no `run_id` (`api/routes/mcp/tools.py`) -- fell through to `human`,
    exactly like a literal UI click by that same person, letting an
    autonomous MCP-driven accept through a gate meant for a person. The
    established rule for this SAME distinction already exists for claims
    and annotations (#4868/#4869): `ProvenanceKind.agent if ctx.via_mcp
    else ProvenanceKind.human`. `_provenance_kind_from_ctx` now applies
    that ONE rule too, so an MCP-shaped accept is refused the same way a
    tool/workflow accept already was."""

    def test_an_mcp_shaped_context_with_a_real_users_own_name_is_refused(self, db):
        """The MCP surface's REAL shape (api/routes/mcp/tools.py): the
        actor is the caller's own authenticated username -- not "system",
        not empty -- and `via_mcp=True`, no `run_id`. Before the fix this
        actor shape satisfied `_provenance_kind_from_ctx`'s old `human`
        branch (a real actor, no run) exactly like a genuine person's
        click; it must not."""
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        a = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
        b = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
        person_ctx = _ctx(db, actor="daniel")
        result = registry.invoke(
            db, "segment.match_propose",
            {"from_segment_id": a.id, "to_segment_id": b.id}, person_ctx,
        )
        match_id = result.result["match_id"]

        from fichero_server.actions.registry import ActionContext as _ActionContext

        mcp_ctx = _ActionContext(actor="daniel", library_path=str(db.path.parent), via_mcp=True)
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as excinfo:
            registry.invoke(db, "segment.match_accept", {"match_id": match_id}, mcp_ctx)
        assert excinfo.value.status_code == 422
        assert excinfo.value.detail == "only a person can accept a match"
        assert db.get(SegmentMatch, match_id).state == "proposed"

        # The SAME actor, through the ordinary (non-MCP) surface, succeeds --
        # proving the refusal above is about the SURFACE, not the name.
        registry.invoke(db, "segment.match_accept", {"match_id": match_id}, person_ctx)
        assert db.get(SegmentMatch, match_id).state == "accepted"

    def test_a_chat_dispatched_context_with_a_real_users_own_name_still_accepts(self, db):
        """The chat surface's REAL shape (`actions/chat_tools.py`'s
        `dispatch_tool_call`): actor is the real user, `via_mcp` is never
        set there (stays `False`), `run_id` is whatever the surrounding
        chat turn's `ActionContext.run_id` was -- `None` for an ordinary
        interactive turn. This is DELIBERATELY still `human` here: chat
        isn't flagged `via_mcp` by the established claims/annotations rule
        either (#4868/#4869 only branches on `via_mcp`), so extending that
        to chat would be a SECOND, invented rule, not the one asked for."""
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        a = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
        b = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
        person_ctx = _ctx(db, actor="daniel")
        result = registry.invoke(
            db, "segment.match_propose",
            {"from_segment_id": a.id, "to_segment_id": b.id}, person_ctx,
        )
        match_id = result.result["match_id"]

        from fichero_server.actions.registry import ActionContext as _ActionContext

        chat_ctx = _ActionContext(actor="daniel", run_id=None, library_path=str(db.path.parent))
        registry.invoke(db, "segment.match_accept", {"match_id": match_id}, chat_ctx)
        assert db.get(SegmentMatch, match_id).state == "accepted"


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

        _invoke_versioned(db, "segment.merge", {"segment_ids": [seg_a.id, seg_b.id], "keep_id": seg_b.id}, ctx)

        split_result = _invoke_versioned(
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

        # segment.delete is now the real, versioned one (slice 5, #4923) --
        # it writes its own `deleted` forwarding row.
        c_version = db.get(Segment, seg_c).version
        registry.invoke(
            db, "segment.delete",
            {"segment_ids": [seg_c], "expected_versions": {seg_c: c_version}}, ctx,
        )

        resolved = resolve_segment(db, seg_a.id)
        assert resolved.live_segment_ids == [seg_d]
        assert not resolved.ended_in_delete  # D is alive
        deleted_entries = [row for row in resolved.trail if row.old_segment_id == seg_c and row.kind == "deleted"]
        assert len(deleted_entries) == 1
        assert deleted_entries[0].actor == "daniel"
        assert deleted_entries[0].created_at is not None

    def test_primary_live_id_after_a_split_is_the_requested_id_itself(self, db):
        """test-audit F2, 2026-09-20: after a split, `_forwarding_walk`
        processes the REQUESTED id at depth 1 of its breadth-first walk --
        before any sibling can be discovered at depth >= 2 -- so whenever
        the requested id is itself still live, it is unconditionally
        `live_segment_ids[0]` by construction (the split's own new parts
        are only reachable one hop later). `primary_live_segment_id`'s
        "prefer the requested id" branch and its "else element zero"
        branch can therefore never disagree for any input reachable
        through today's actions -- this pins that invariant explicitly
        rather than leaving it untested."""
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        seg = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.2, 0.2])
        ctx = _ctx(db, actor="daniel")

        _invoke_versioned(
            db, "segment.split",
            {
                "segment_id": seg.id,
                "parts": [
                    {"anchor": {"document_id": doc.id, "rect": [0.1, 0.1, 0.1, 0.1]}},
                    {"anchor": {"document_id": doc.id, "rect": [0.2, 0.2, 0.1, 0.1]}},
                ],
            },
            ctx,
        )

        resolved = resolve_segment(db, seg.id)
        assert seg.id in resolved.live_segment_ids
        assert len(resolved.live_segment_ids) > 1, "fixture must exercise the multi-id case"
        assert resolved.live_segment_ids[0] == seg.id
        assert primary_live_segment_id(resolved) == seg.id

    def test_primary_live_id_is_the_first_part_listed_when_the_split_was_made(self, db):
        """test-audit F2, 2026-09-20: when the REQUESTED id is not itself
        live (merged away), `primary_live_segment_id` falls back to "the
        first part listed when the split was made" -- pinned here by
        actually making the requested id's own trail pass through a split
        with a stated, non-alphabetical/non-random part order."""
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        seg_a = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.0, 0.0, 0.1, 0.1])
        seg_b = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.3, 0.3, 0.1, 0.1])
        ctx = _ctx(db, actor="daniel")

        _invoke_versioned(db, "segment.merge", {"segment_ids": [seg_a.id, seg_b.id], "keep_id": seg_b.id}, ctx)
        split_result = _invoke_versioned(
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
        seg_c = seg_b.id  # "its id stays on one part" -- listed FIRST
        seg_d = split_result.result["new_segment_ids"][0]  # listed SECOND

        resolved = resolve_segment(db, seg_a.id)
        assert seg_a.id not in resolved.live_segment_ids  # A was merged away
        assert resolved.live_segment_ids == [seg_c, seg_d]
        assert primary_live_segment_id(resolved) == seg_c

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

    def test_a_chain_of_exactly_64_hops_resolves_cleanly(self, db):
        """test-audit F4, 2026-09-20: the sibling of the 65-raises test,
        AT the cap boundary -- `_forwarding_walk`'s `depth` counts NODES
        visited (checked BEFORE each node is processed), so a chain needs
        `edges + 1` depth-units to reach its terminal, live id: 63 `merged`
        edges (64 ids total) reaches depth exactly 64 -- the cap -- and
        resolves; one more edge (64 edges / 65 ids, needing depth 65)
        raises, proven directly below so the boundary itself is pinned,
        not just a comfortably-over-it case."""
        doc = _make_doc(db)
        ids = [f"seg-{i}" for i in range(64)]
        audit_id = "test-audit-64"
        for i in range(63):
            db.save(SegmentForwarding(
                document_id=doc.id, old_segment_id=ids[i], kind="merged",
                new_segment_ids=[ids[i + 1]], actor="daniel", audit_id=audit_id,
            ))
        resolved = resolve_segment(db, ids[0])
        assert resolved.live_segment_ids == [ids[63]]
        assert not resolved.ended_in_delete

    def test_one_more_hop_past_the_boundary_raises(self, db):
        """The exact tight boundary for the raise: 64 edges (65 ids) --
        one more than the resolving case above -- is already too many."""
        doc = _make_doc(db)
        ids = [f"seg-{i}" for i in range(65)]
        audit_id = "test-audit-64-plus-one"
        for i in range(64):
            db.save(SegmentForwarding(
                document_id=doc.id, old_segment_id=ids[i], kind="merged",
                new_segment_ids=[ids[i + 1]], actor="daniel", audit_id=audit_id,
            ))
        with pytest.raises(SegmentForwardingTooDeep):
            resolve_segment(db, ids[0])

    def test_merge_a_into_b_then_b_into_a_is_a_real_loop_and_is_refused(self, db):
        """A genuine cycle of undone merges IS still refused -- the third
        look's fix (a diamond is not a loop) must not weaken this.

        test-audit F4, 2026-09-20: this is now REFUSED BY THE LIVENESS
        CHECK, not by `forwards_to` -- once A is merged into B, A is not
        live, so `_action_merge`'s own liveness loop (which runs BEFORE
        `forwards_to` is ever called) refuses this exact case first. The
        production code says so itself (the comment above `forwards_to`'s
        call site: "with every participant now confirmed live, above,
        this can only ever be true for keep_id == absorbed_id"). This
        test still pins the OBSERVABLE behaviour (refused), but
        `TestForwardsToSafetyNet` below tests the cycle-detection logic
        directly, since no route can reach the state that would exercise
        it."""
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        seg_a = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.0, 0.0, 0.1, 0.1])
        seg_b = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.2, 0.2, 0.1, 0.1])
        ctx = _ctx(db, actor="daniel")

        _invoke_versioned(db, "segment.merge", {"segment_ids": [seg_a.id, seg_b.id], "keep_id": seg_b.id}, ctx)

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as excinfo:
            _invoke_versioned(
                db, "segment.merge",
                {"segment_ids": [seg_b.id, seg_a.id], "keep_id": seg_a.id}, ctx,
            )
        assert excinfo.value.status_code == 409
        assert "is not live" in excinfo.value.detail

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
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as excinfo:
            _invoke_versioned(
                db, "segment.merge",
                {"segment_ids": [seg_1.id, seg_2.id], "keep_id": seg_1.id}, ctx,
            )
        assert excinfo.value.status_code == 409
        assert excinfo.value.detail == "segments being merged are not all in the same pass and document"

        # Same document, different passes.
        pass_3 = _make_pass(db, doc_1.id)
        seg_3 = _make_segment(db, document_id=doc_1.id, pass_id=pass_3.id, rect=[0.5, 0.5, 0.1, 0.1])
        with pytest.raises(HTTPException) as excinfo2:
            _invoke_versioned(
                db, "segment.merge",
                {"segment_ids": [seg_1.id, seg_3.id], "keep_id": seg_1.id}, ctx,
            )
        assert excinfo2.value.status_code == 409
        assert excinfo2.value.detail == "segments being merged are not all in the same pass and document"

    def _split_then_merge_back(self, db, ctx, *, keep_first: bool):
        """One fresh segment, split in two, then the parts merged back
        together -- in EITHER direction. Returns (original_id, sibling_id)."""
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        original = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.0, 0.0, 0.2, 0.2])

        split_result = _invoke_versioned(
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
        _invoke_versioned(
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

        split_result = _invoke_versioned(
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
        _invoke_versioned(
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

        merge_result = _invoke_versioned(
            db, "segment.merge", {"segment_ids": [seg_a.id, seg_b.id], "keep_id": seg_b.id}, ctx,
        )
        audit_id = merge_result.audit_id

        undo = client.post(f"/api/actions/audit/{audit_id}/undo")
        assert undo.status_code == 200, undo.text

        rows = db.query(SegmentForwarding, old_segment_id=seg_a.id)
        kinds = sorted(r.kind for r in rows)
        assert kinds == ["merged", "restored"]
        assert db.get(Segment, seg_a.id).deleted_at is None

    def test_unmerge_restores_from_the_snapshot_even_with_a_blanked_audit_before(self, db, client):
        """#4923 second look: unmerge restores from the `SegmentVersion`
        snapshot `segment.merge` itself wrote -- never from the audit
        record's own `before` -- proven the same way `segment.update`'s
        undo is: blank `before` and it still restores."""
        from fichero_server.models import ActionAudit

        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        seg_a = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.0, 0.0, 0.1, 0.1])
        seg_b = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.2, 0.2, 0.1, 0.1])
        ctx = _ctx(db, actor="daniel")

        merge_result = _invoke_versioned(
            db, "segment.merge", {"segment_ids": [seg_a.id, seg_b.id], "keep_id": seg_b.id}, ctx,
        )
        audit = db.get(ActionAudit, merge_result.audit_id)
        audit.before = None
        db.save(audit)

        undo = client.post(f"/api/actions/audit/{merge_result.audit_id}/undo")
        assert undo.status_code == 200, undo.text
        restored = db.get(Segment, seg_a.id)
        assert restored.deleted_at is None
        assert restored.anchor.rect == [0.0, 0.0, 0.1, 0.1]

    def test_unsplit_restores_from_the_snapshot_even_with_a_blanked_audit_before(self, db, client):
        from fichero_server.models import ActionAudit

        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        original = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.0, 0.0, 0.2, 0.2])
        original_rect = list(original.anchor.rect)
        ctx = _ctx(db, actor="daniel")

        split_result = _invoke_versioned(
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
        audit = db.get(ActionAudit, split_result.audit_id)
        audit.before = None
        db.save(audit)

        undo = client.post(f"/api/actions/audit/{split_result.audit_id}/undo")
        assert undo.status_code == 200, undo.text
        restored = db.get(Segment, original.id)
        assert restored.anchor.rect == original_rect

    def test_split_then_unsplit_the_version_is_higher_than_before_the_split(self, db, client):
        """#4923 second look: a version number is never set back -- after
        split then unsplit, the segment sits at a NEW, higher version, not
        the one it had before the split."""
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        original = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.0, 0.0, 0.2, 0.2])
        version_before_split = original.version
        ctx = _ctx(db, actor="daniel")

        split_result = _invoke_versioned(
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
        undo = client.post(f"/api/actions/audit/{split_result.audit_id}/undo")
        assert undo.status_code == 200, undo.text

        assert db.get(Segment, original.id).version > version_before_split


class TestForwardsToSafetyNet:
    """test-audit F4, 2026-09-20: `forwards_to` is the SAFETY NET behind
    `_action_merge`'s liveness gate (its own docstring and the call site's
    comment both say the liveness check now refuses every cycle-closing
    merge first). No route can build the state needed to reach
    `forwards_to`'s cycle branch through the merge action any more, so
    these tests call it directly, with hand-built `SegmentForwarding` rows
    -- a genuine unit test of the safety net, not of anything a caller can
    trigger today."""

    def test_a_direct_undone_merge_edge_closes_a_cycle(self, db):
        """One hand-built `merged` row X->Y is enough: does adding the
        edge Y->X (absorbing Y into X) close a cycle? Yes -- X already
        forwards to Y."""
        doc = _make_doc(db)
        db.save(SegmentForwarding(
            document_id=doc.id, old_segment_id="seg-x", kind="merged",
            new_segment_ids=["seg-y"], actor="daniel", audit_id="a1",
        ))
        assert forwards_to(db, "seg-x", "seg-y") is True

    def test_a_multi_hop_undone_merge_chain_still_closes_a_cycle(self, db):
        doc = _make_doc(db)
        db.save(SegmentForwarding(
            document_id=doc.id, old_segment_id="seg-x", kind="merged",
            new_segment_ids=["seg-y"], actor="daniel", audit_id="a1",
        ))
        db.save(SegmentForwarding(
            document_id=doc.id, old_segment_id="seg-y", kind="merged",
            new_segment_ids=["seg-z"], actor="daniel", audit_id="a2",
        ))
        assert forwards_to(db, "seg-x", "seg-z") is True
        assert forwards_to(db, "seg-x", "seg-w") is False

    def test_unrelated_ids_do_not_close_a_cycle(self, db):
        doc = _make_doc(db)
        db.save(SegmentForwarding(
            document_id=doc.id, old_segment_id="seg-x", kind="merged",
            new_segment_ids=["seg-y"], actor="daniel", audit_id="a1",
        ))
        assert forwards_to(db, "seg-x", "seg-nowhere") is False

    def test_the_same_id_trivially_closes_a_cycle(self, db):
        assert forwards_to(db, "seg-x", "seg-x") is True

    def test_a_restored_merge_no_longer_forwards(self, db):
        """An UNDONE merge (a later `restored` row) means the id is live
        again -- `_merged_chain_target` returns `None` for it, so a fresh
        merge attempt reusing that id closes no cycle."""
        doc = _make_doc(db)
        db.save(SegmentForwarding(
            document_id=doc.id, old_segment_id="seg-x", kind="merged",
            new_segment_ids=["seg-y"], actor="daniel", audit_id="a1",
            sequence=db.next_forwarding_sequence(),
        ))
        db.save(SegmentForwarding(
            document_id=doc.id, old_segment_id="seg-x", kind="restored",
            new_segment_ids=[], actor="daniel", audit_id="a2",
            sequence=db.next_forwarding_sequence(),
        ))
        assert forwards_to(db, "seg-x", "seg-y") is False


class TestEveryEmitTypeCarriesItsIdLists:
    """test-audit F7, 2026-09-20: `segments.py` emits 9 DISTINCT
    `emit_type`s (grep: pass.created, pass.deleted, segment.created,
    .deleted, .restored, .updated, .matched, .merged, .split); only 3 were
    checked by any test (proven by mutation M2d: dropping `segment_ids=`
    from merge's `ChangeSpec` passed every test). One representative
    action per emit_type, captured through the REAL `emit_change` call
    (not just the action's own return), asserting `segment_ids`/
    `pass_ids`/`document_ids` are non-empty and name the right rows."""

    @pytest.fixture
    def captured(self, monkeypatch):
        calls: list[dict] = []

        def spy(*args, **kwargs):
            calls.append(kwargs)

        monkeypatch.setattr("fichero_server.api.change_stream.emit_change", spy)
        return calls

    def test_pass_created(self, db, captured):
        doc = _make_doc(db)
        ctx = _ctx(db, actor="daniel")
        registry.invoke(db, "segment.pass_create", {"document_id": doc.id, "name": "p"}, ctx)
        call = captured[-1]
        assert call["type"] == "pass.created"
        assert call["document_ids"] == [doc.id]
        assert call["pass_ids"], "pass_ids must not be empty"

    def test_pass_deleted(self, db, captured):
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        ctx = _ctx(db, actor="daniel")
        registry.invoke(db, "segment.pass_delete", {"pass_id": pass_row.id}, ctx)
        call = captured[-1]
        assert call["type"] == "pass.deleted"
        assert call["pass_ids"] == [pass_row.id]
        assert call["document_ids"] == [doc.id]

    def test_segment_created(self, db, captured):
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        ctx = _ctx(db, actor="daniel")
        registry.invoke(
            db, "segment.create",
            {"document_id": doc.id, "pass_id": pass_row.id, "kind": "word",
             "anchor": {"document_id": doc.id, "rect": [0.1, 0.1, 0.1, 0.1]}}, ctx,
        )
        call = captured[-1]
        assert call["type"] == "segment.created"
        assert call["pass_ids"] == [pass_row.id]
        assert call["document_ids"] == [doc.id]
        assert call["segment_ids"], "segment_ids must not be empty"

    def test_segment_deleted(self, db, captured):
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        seg = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
        ctx = _ctx(db, actor="daniel")
        registry.invoke(
            db, "segment.delete",
            {"segment_ids": [seg.id], "expected_versions": {seg.id: seg.version}}, ctx,
        )
        call = captured[-1]
        assert call["type"] == "segment.deleted"
        assert call["segment_ids"] == [seg.id]
        assert call["document_ids"] == [doc.id]

    def test_segment_restored(self, db, captured):
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        seg = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
        ctx = _ctx(db, actor="daniel")
        registry.invoke(
            db, "segment.delete",
            {"segment_ids": [seg.id], "expected_versions": {seg.id: seg.version}}, ctx,
        )
        registry.invoke(db, "segment.undelete", {"segment_ids": [seg.id]}, ctx)
        call = captured[-1]
        assert call["type"] == "segment.restored"
        assert call["segment_ids"] == [seg.id]

    def test_segment_updated(self, db, captured):
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        seg = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
        ctx = _ctx(db, actor="daniel")
        registry.invoke(
            db, "segment.update",
            {"segment_id": seg.id, "expected_version": seg.version,
             "anchor": {"document_id": doc.id, "rect": [0.2, 0.2, 0.1, 0.1]}}, ctx,
        )
        call = captured[-1]
        assert call["type"] == "segment.updated"
        assert call["segment_ids"] == [seg.id]

    def test_segment_matched(self, db, captured):
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        a = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
        b = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
        ctx = _ctx(db, actor="daniel")
        registry.invoke(
            db, "segment.match_propose",
            {"from_segment_id": a.id, "to_segment_id": b.id}, ctx,
        )
        call = captured[-1]
        assert call["type"] == "segment.matched"
        assert set(call["segment_ids"]) == {a.id, b.id}
        assert call["document_ids"] == [doc.id]

    def test_segment_merged(self, db, captured):
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        a = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
        b = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
        ctx = _ctx(db, actor="daniel")
        _invoke_versioned(db, "segment.merge", {"segment_ids": [a.id, b.id], "keep_id": b.id}, ctx)
        call = captured[-1]
        assert call["type"] == "segment.merged"
        assert set(call["segment_ids"]) == {a.id, b.id}, (
            "M2d: dropping segment_ids from merge's event survived every "
            "existing test before this one"
        )

    def test_segment_split(self, db, captured):
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        seg = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.2, 0.2])
        ctx = _ctx(db, actor="daniel")
        _invoke_versioned(
            db, "segment.split",
            {"segment_id": seg.id, "parts": [
                {"anchor": {"document_id": doc.id, "rect": [0.1, 0.1, 0.1, 0.1]}},
                {"anchor": {"document_id": doc.id, "rect": [0.2, 0.2, 0.1, 0.1]}},
            ]}, ctx,
        )
        call = captured[-1]
        assert call["type"] == "segment.split"
        assert seg.id in call["segment_ids"]
        assert len(call["segment_ids"]) == 2

    def test_every_distinct_emit_type_in_the_file_has_a_test_above(self):
        """Fails loudly if a new `emit_type=` string is added to
        `segments.py` without a matching test here -- the registry-driven
        guarantee F7 asked for, at the emit_type granularity (the unit
        `emit_change` actually broadcasts on)."""
        import re

        src = inspect.getsource(sys.modules["fichero_server.api.routes.document.segments"])
        found = set(re.findall(r'emit_type="([a-z_.]+)"', src))
        tested = {
            "pass.created", "pass.deleted", "segment.created", "segment.deleted",
            "segment.restored", "segment.updated", "segment.matched",
            "segment.merged", "segment.split",
        }
        assert found == tested, f"untested emit_type(s): {found - tested}; stale test(s): {tested - found}"


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

        carry_result = _invoke_versioned(
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
        _invoke_versioned(db, "segment.uncarry", {"carry_ids": carry_ids}, ctx)
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

        carry_result = _invoke_versioned(db, "segment.carry", {"match_id": p1, "kinds": ["reading"]}, ctx)
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
        _invoke_versioned(db, "segment.merge", {"segment_ids": [seg_a.id, seg_b.id], "keep_id": seg_b.id}, ctx)

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
        _invoke_versioned(db, "segment.carry", {"match_id": match_id, "kinds": ["reading"]}, ctx)
        _invoke_versioned(db, "segment.merge", {"segment_ids": [seg_from.id, seg_to.id], "keep_id": seg_to.id}, ctx)

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
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as excinfo:
            _invoke_versioned(db, "segment.carry", {"match_id": match_id, "kinds": ["claim_evidence"]}, ctx)
        assert excinfo.value.status_code == 422
        assert "claim_evidence" in excinfo.value.detail and "statements step" in excinfo.value.detail
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
        carry_result = _invoke_versioned(db, "segment.carry", {"match_id": match_id, "kinds": ["reading"]}, ctx)
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
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as excinfo:
            _invoke_versioned(db, "segment.carry", {"match_id": match_id, "kinds": ["reading"]}, ctx)
        assert excinfo.value.status_code == 422
        assert excinfo.value.detail == f"match {match_id!r} is not accepted (state: 'proposed')"

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
        carry_result = _invoke_versioned(db, "segment.carry", {"match_id": match_id, "kinds": ["reading"]}, ctx)
        copy_id = carry_result.result["copy_ids"][0]
        carry_id = carry_result.result["carry_ids"][0]

        _invoke_versioned(db, "segment.uncarry", {"carry_ids": [carry_id]}, ctx)
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
        split_result = _invoke_versioned(
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
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as excinfo:
            _invoke_versioned(
                db, "segment.merge",
                {"segment_ids": [a.id, b.id], "keep_id": "not-a-real-id"}, ctx,
            )
        assert excinfo.value.status_code == 422
        assert excinfo.value.detail == "keep_id 'not-a-real-id' is not among segment_ids"

    def test_split_with_fewer_than_two_parts_is_refused(self, db):
        from fastapi import HTTPException

        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        original = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.0, 0.0, 0.2, 0.2])
        ctx = _ctx(db, actor="daniel")
        with pytest.raises(HTTPException) as excinfo:
            _invoke_versioned(
                db, "segment.split",
                {"segment_id": original.id, "parts": [{"anchor": {"document_id": doc.id, "rect": [0.0, 0.0, 0.1, 0.1]}}]},
                ctx,
            )
        assert excinfo.value.status_code == 422
        assert excinfo.value.detail == "split needs two or more parts"

    def test_split_with_a_part_outside_the_image_is_refused(self, db):
        """The part's anchor is rejected by `SourceAnchor`'s own pydantic
        validation, inside `registry.invoke`'s `params_model.model_validate`
        -- BEFORE the action runs, so this is a `ValidationError`, never an
        `HTTPException` (there is nothing yet to route through `_as_http_error`)."""
        from pydantic import ValidationError

        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        original = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.0, 0.0, 0.2, 0.2])
        ctx = _ctx(db, actor="daniel")
        with pytest.raises(ValidationError):
            _invoke_versioned(
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
        (
            "segment.merge",
            lambda a, b: {
                "segment_ids": ["legacy:x", b.id], "keep_id": b.id,
                # #4957 follow-up 1: now a required field on the params
                # model -- irrelevant to what this test checks (the
                # provisional-id refusal runs first), but its ABSENCE
                # would fail pydantic validation before ever reaching
                # `_action_merge`'s own checks.
                "expected_versions": {"legacy:x": 1, b.id: b.version},
            },
        ),
        (
            "segment.split",
            lambda a, b: {
                "segment_id": "legacy:x", "expected_version": 1,
                "parts": [
                    {"anchor": {"document_id": "d", "rect": [0, 0, 0.1, 0.1]}},
                    {"anchor": {"document_id": "d", "rect": [0.5, 0.5, 0.1, 0.1]}},
                ],
            },
        ),
    ])
    def test_a_legacy_id_is_refused_on_each_action(self, db, action_name, build_params):
        """test-audit F9, 2026-09-20: asserts the SPECIFIC reason -- a 422
        whose detail names the id as provisional -- not just "some
        exception happened", which `split`'s bogus `document_id: "d"`
        anchor could otherwise mask (it would fail placement validation
        for an unrelated reason regardless of the provisional check).
        Confirmed empirically all three land on the provisional check
        FIRST (`_assert_not_provisional_http` runs before any anchor
        validation in every one of these actions)."""
        from fastapi import HTTPException

        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        a = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
        b = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.3, 0.3, 0.1, 0.1])
        ctx = _ctx(db, actor="daniel")
        with pytest.raises(HTTPException) as excinfo:
            registry.invoke(db, action_name, build_params(a, b), ctx)
        assert excinfo.value.status_code == 422
        assert "legacy:x" in excinfo.value.detail and "provisional" in excinfo.value.detail

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
        _invoke_versioned(db, "segment.merge", {"segment_ids": [seg.id, keep.id], "keep_id": keep.id}, ctx)
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
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as excinfo:
            _invoke_versioned(
                db, "segment.merge",
                {"segment_ids": [live.id, not_live.id], "keep_id": live.id}, ctx,
            )
        assert excinfo.value.status_code == 409
        assert "is not live" in excinfo.value.detail and reason in excinfo.value.detail

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
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as excinfo:
            _invoke_versioned(
                db, "segment.merge",
                {"segment_ids": [live.id, not_live.id], "keep_id": not_live.id}, ctx,
            )
        assert excinfo.value.status_code == 409
        assert "is not live" in excinfo.value.detail and reason in excinfo.value.detail

    @pytest.mark.parametrize("reason", ["deleted", "merged"])
    def test_split_refuses_a_not_live_segment(self, db, reason):
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        ctx = _ctx(db, actor="daniel")
        not_live = (
            self._deleted_segment(db, doc, pass_row) if reason == "deleted"
            else self._merged_away_segment(db, doc, pass_row, ctx)
        )
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as excinfo:
            _invoke_versioned(
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
        assert excinfo.value.status_code == 409
        assert "is not live" in excinfo.value.detail and reason in excinfo.value.detail

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
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as excinfo:
            _invoke_versioned(db, "segment.carry", {"match_id": match_id, "kinds": ["annotation"]}, ctx)
        assert excinfo.value.status_code == 409
        assert "is not live" in excinfo.value.detail and reason in excinfo.value.detail


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

        split_result = _invoke_versioned(
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
        carry_ids = _invoke_versioned(
            db, "segment.carry", {"match_id": match_xy, "kinds": ["reading"]}, ctx,
        ).result["carry_ids"]
        _invoke_versioned(db, "segment.uncarry", {"carry_ids": carry_ids}, ctx)

        match_to_reject = registry.invoke(
            db, "segment.match_propose", {"from_segment_id": seg_a.id, "to_segment_id": seg_x.id}, ctx,
        ).result["match_id"]
        registry.invoke(db, "segment.match_reject", {"match_id": match_to_reject}, ctx)

        match_to_withdraw = registry.invoke(
            db, "segment.match_propose", {"from_segment_id": seg_b.id, "to_segment_id": seg_y.id}, ctx,
        ).result["match_id"]
        registry.invoke(db, "segment.match_withdraw", {"match_id": match_to_withdraw}, ctx)

        # merge, then snapshot the forwarding table.
        merge_result = _invoke_versioned(
            db, "segment.merge", {"segment_ids": [seg_a.id, seg_b.id], "keep_id": seg_b.id}, ctx,
        )
        forwarding_after_merge = {r.id: r.model_dump(mode="json") for r in db.all(SegmentForwarding)}
        assert len(forwarding_after_merge) >= 1

        # split.
        _invoke_versioned(
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

        # #4923 second look: slice 5's own actions too -- update, delete,
        # undelete, restore_version -- in the SAME scenario.
        registry.invoke(
            db, "segment.update",
            {"segment_id": seg_x.id, "expected_version": db.get(Segment, seg_x.id).version,
             "anchor": {"document_id": doc.id, "rect": [0.41, 0.41, 0.1, 0.1]}}, ctx,
        )
        current_x = db.get(Segment, seg_x.id)
        registry.invoke(
            db, "segment.delete",
            {"segment_ids": [seg_x.id], "expected_versions": {seg_x.id: current_x.version}}, ctx,
        )
        registry.invoke(db, "segment.undelete", {"segment_ids": [seg_x.id]}, ctx)
        current_x = db.get(Segment, seg_x.id)
        registry.invoke(
            db, "segment.restore_version",
            {"segment_id": seg_x.id, "version": 1, "expected_version": current_x.version}, ctx,
        )

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

        # (d) #4923 second look: (segment_id, version) is unique in
        # segmentversions after this whole sequence of actions.
        pairs = [(v.segment_id, v.version) for v in db.all(SegmentVersion)]
        assert len(pairs) == len(set(pairs)), f"duplicate (segment_id, version) pairs: {pairs}"

        # (e) #4923 second look: no Segment.version ever decreased. X went
        # through update, delete, undelete, restore_version above -- its
        # own version-row numbers must be exactly 1..N, no gap, no repeat,
        # never a number lower than one already seen.
        x_version_rows = sorted(
            (v.version for v in db.query(SegmentVersion, segment_id=seg_x.id)),
        )
        assert x_version_rows == sorted(set(x_version_rows)), "a version number repeated for seg_x"
        assert x_version_rows == list(range(1, len(x_version_rows) + 1)), (
            f"seg_x's version history has a gap or a regression: {x_version_rows}"
        )


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
            _invoke_versioned(
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
            "POST", "/api/segments/merge",
            # #4957 follow-up 1: now a required field -- irrelevant to
            # what this test checks (the provisional-id refusal runs
            # first), but its ABSENCE would 422 for the wrong reason.
            {"segment_ids": ["legacy:x", "real"], "keep_id": "real",
             "expected_versions": {"legacy:x": 1, "real": 1}},
        )),
        ("keep_id", lambda doc_id, pass_id: (
            "POST", "/api/segments/merge",
            {"segment_ids": ["real", "real2"], "keep_id": "legacy:x",
             "expected_versions": {"real": 1, "real2": 1, "legacy:x": 1}},
        )),
    ],
    ("POST", "/segments/split"): [
        ("segment_id", lambda doc_id, pass_id: (
            "POST", "/api/segments/split",
            # #4957 follow-up 1: now a required field -- see the merge
            # entries above for why it is included here regardless.
            {"segment_id": "legacy:x", "expected_version": 1, "parts": [
                {"anchor": {"document_id": doc_id, "rect": [0.0, 0.0, 0.1, 0.1]}},
                {"anchor": {"document_id": doc_id, "rect": [0.5, 0.5, 0.1, 0.1]}},
            ]},
        )),
    ],
    ("POST", "/segments/carry"): [],  # match_id is never provisional-shaped
    ("GET", "/segments/{segment_id}/reference"): [
        ("segment_id (path)", lambda doc_id, pass_id: ("GET", "/api/segments/legacy:x/reference", None)),
    ],
    ("PUT", "/segments/{segment_id}"): [
        ("segment_id", lambda doc_id, pass_id: (
            "PUT", "/api/segments/legacy:x",
            {"segment_id": "legacy:x", "expected_version": 1},
        )),
        ("parent_segment_id", lambda doc_id, pass_id: (
            "PUT", "/api/segments/real",
            {"segment_id": "real", "expected_version": 1, "parent_segment_id": "legacy:x"},
        )),
    ],
    ("POST", "/segments/delete"): [
        ("segment_ids[]", lambda doc_id, pass_id: (
            "POST", "/api/segments/delete",
            {"segment_ids": ["legacy:x"], "expected_versions": {"legacy:x": 1}},
        )),
    ],
    ("POST", "/segments/undelete"): [
        ("segment_ids[]", lambda doc_id, pass_id: (
            "POST", "/api/segments/undelete", {"segment_ids": ["legacy:x"]},
        )),
    ],
    ("POST", "/segments/{segment_id}/restore-version"): [
        ("segment_id (path)", lambda doc_id, pass_id: (
            "POST", "/api/segments/legacy:x/restore-version",
            {"version": 1, "expected_version": 1},
        )),
    ],
    ("GET", "/segments/{segment_id}/versions"): [
        ("segment_id (path)", lambda doc_id, pass_id: ("GET", "/api/segments/legacy:x/versions", None)),
    ],
    ("GET", "/segments/{segment_id}"): [
        ("segment_id (path)", lambda doc_id, pass_id: ("GET", "/api/segments/legacy:x", None)),
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
    url = url.replace("real2", b.id).replace("real", a.id)
    if json_body is not None:
        json_body = json.loads(
            json.dumps(json_body).replace('"real2"', f'"{b.id}"').replace('"real"', f'"{a.id}"')
        )
    r = client.request(method, url, json=json_body)
    assert r.status_code == 422, f"{route_key} field {field_name!r}: expected 422, got {r.status_code}: {r.text}"
    assert "provisional" in r.text, f"{route_key} field {field_name!r}: 422 detail did not name 'provisional'"


class TestRedoOfAMintingActionComesBackUnderTheSameId:
    """#4957 addendum, per the spec author's review
    (agent-work/source-model/reviews/redo-4957-review.md): a redo row has
    `inverse_of` set exactly like a genuine undo row, so a SECOND undo (lap
    2, undoing a REDONE action) used to replay the FIRST undo's now-stale
    params -- for split, silent corruption (the redo's own new parts stay
    live, duplicated, on top of the restored kept line); for carry, stray
    copies; for create/pass_create/match_propose, the redo's own new row
    was stranded (its own undo/redo permanently refused). Fixed by
    `ActionRegistration.redo_via_own_invert`, opted in on the segment
    actions that mint a new id/row (`source.editor.redo-works`). Mounted
    through the real undo ROUTE (`client.post(.../undo)`); asserted on
    ROWS, not just status codes."""

    def test_split_do_undo_redo_undo_leaves_exactly_one_live_line_and_no_stray_parts(
        self, db, client,
    ):
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        seg = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.2, 0.2])
        ctx = _ctx(db, actor="daniel")

        do = _invoke_versioned(
            db, "segment.split",
            {
                "segment_id": seg.id,
                "parts": [
                    {"anchor": {"document_id": doc.id, "rect": [0.1, 0.1, 0.1, 0.1]}},
                    {"anchor": {"document_id": doc.id, "rect": [0.2, 0.2, 0.1, 0.1]}},
                ],
            },
            ctx,
        )
        first_new_id = do.result["new_segment_ids"][0]

        undo = client.post(f"/api/actions/audit/{do.audit_id}/undo")
        assert undo.status_code == 200, undo.text

        redo = client.post(f"/api/actions/audit/{undo.json()['audit_id']}/undo")
        assert redo.status_code == 200, redo.text
        second_new_id = redo.json()["result"]["new_segment_ids"][0]
        assert second_new_id != first_new_id  # redo mints its OWN new parts

        undo_again = client.post(f"/api/actions/audit/{redo.json()['audit_id']}/undo")
        assert undo_again.status_code == 200, undo_again.text

        # Exactly the kept line is live; BOTH the first split's part (long
        # gone) and the second (redo's own, this undo's real target) are
        # gone -- nothing stray survives the round trip. `_action_unsplit`
        # HARD-deletes the new parts it retires (not a soft delete).
        live = [s for s in db.query(Segment, document_id=doc.id) if s.deleted_at is None]
        assert [s.id for s in live] == [seg.id]
        assert db.get(Segment, first_new_id) is None
        assert db.get(Segment, second_new_id) is None

    def test_carry_do_undo_redo_undo_leaves_zero_copies(self, db, client):
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        seg_from = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.2, 0.1])
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

        do = _invoke_versioned(db, "segment.carry", {"match_id": match_id, "kinds": ["reading"]}, ctx)

        undo = client.post(f"/api/actions/audit/{do.audit_id}/undo")
        assert undo.status_code == 200, undo.text

        redo = client.post(f"/api/actions/audit/{undo.json()['audit_id']}/undo")
        assert redo.status_code == 200, redo.text

        undo_again = client.post(f"/api/actions/audit/{redo.json()['audit_id']}/undo")
        assert undo_again.status_code == 200, undo_again.text
        assert db.query(SegmentCarry, match_id=match_id) == []
        remaining = db.query(ContentRepresentation, document_id=doc.id)
        assert len(remaining) == 1
        assert remaining[0].id == reading.id  # only the original -- no stray copy

    def test_create_do_undo_redo_undo_comes_back_under_the_same_id(self, db, client):
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        ctx = _ctx(db, actor="daniel")

        do = registry.invoke(
            db, "segment.create",
            {
                "document_id": doc.id, "pass_id": pass_row.id, "kind": "word",
                "anchor": {"document_id": doc.id, "rect": [0.1, 0.1, 0.1, 0.1]},
            },
            ctx,
        )
        segment_id = do.result["segment_ids"][0]

        undo = client.post(f"/api/actions/audit/{do.audit_id}/undo")
        assert undo.status_code == 200, undo.text
        assert db.get(Segment, segment_id).deleted_at is not None

        redo = client.post(f"/api/actions/audit/{undo.json()['audit_id']}/undo")
        assert redo.status_code == 200, redo.text
        # Own-invert redoes via undelete of the SAME id -- ids never move.
        assert db.get(Segment, segment_id).deleted_at is None
        assert len(db.query(Segment, document_id=doc.id)) == 1

        undo_again = client.post(f"/api/actions/audit/{redo.json()['audit_id']}/undo")
        assert undo_again.status_code == 200, undo_again.text
        assert db.get(Segment, segment_id).deleted_at is not None
        assert len(db.query(Segment, document_id=doc.id)) == 1  # still one row, never a second

    def test_pass_create_do_undo_redo_undo_comes_back_under_the_same_id(self, db, client):
        from fichero_server.models import SegmentPass

        doc = _make_doc(db)
        ctx = _ctx(db, actor="daniel")

        do = registry.invoke(db, "segment.pass_create", {"document_id": doc.id, "name": "p"}, ctx)
        pass_id = do.result["id"]

        undo = client.post(f"/api/actions/audit/{do.audit_id}/undo")
        assert undo.status_code == 200, undo.text
        assert db.get(SegmentPass, pass_id).deleted_at is not None

        redo = client.post(f"/api/actions/audit/{undo.json()['audit_id']}/undo")
        assert redo.status_code == 200, redo.text
        assert db.get(SegmentPass, pass_id).deleted_at is None
        assert len(db.query(SegmentPass, document_id=doc.id)) == 1

        undo_again = client.post(f"/api/actions/audit/{redo.json()['audit_id']}/undo")
        assert undo_again.status_code == 200, undo_again.text
        assert db.get(SegmentPass, pass_id).deleted_at is not None
        assert len(db.query(SegmentPass, document_id=doc.id)) == 1  # still one row

    def test_match_propose_do_undo_redo_undo_leaves_zero_stray_matches(self, db, client):
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        seg_from = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.1, 0.1, 0.1, 0.1])
        seg_to = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.5, 0.5, 0.1, 0.1])
        ctx = _ctx(db, actor="daniel")

        do = registry.invoke(
            db, "segment.match_propose",
            {"from_segment_id": seg_from.id, "to_segment_id": seg_to.id}, ctx,
        )
        first_match_id = do.result["match_id"]

        undo = client.post(f"/api/actions/audit/{do.audit_id}/undo")
        assert undo.status_code == 200, undo.text

        redo = client.post(f"/api/actions/audit/{undo.json()['audit_id']}/undo")
        assert redo.status_code == 200, redo.text
        second_match_id = redo.json()["result"]["match_id"]
        assert second_match_id != first_match_id  # redo made its own, fresh match

        undo_again = client.post(f"/api/actions/audit/{redo.json()['audit_id']}/undo")
        assert undo_again.status_code == 200, undo_again.text
        assert db.get(SegmentMatch, first_match_id) is None
        assert db.get(SegmentMatch, second_match_id) is None  # not stranded

    def test_merge_redo_is_refused_after_an_intervening_edit(self, db, client):
        """#4957 follow-up 1, superseding an earlier version of this test
        that predates the token: BEFORE the token, this exact redo
        silently re-merged away a segment someone had just reshaped (the
        review's own finding) -- "safe" in that no SegmentVersion snapshot
        was lost, but not what the behaviour promises ("a redo is refused
        when something else changed the segment since") and the person
        pressing Redo was never told. Now this first redo attempt (a plain
        REPLAY of the original merge, refreshed from the UNDO's own
        `after` -- captured BEFORE the intervening edit) is correctly
        refused as stale, so the edit survives because the merge never
        re-ran, not because a snapshot happened to catch it."""
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        seg_a = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.0, 0.0, 0.1, 0.1])
        seg_b = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.3, 0.3, 0.1, 0.1])
        ctx = _ctx(db, actor="daniel")

        do = _invoke_versioned(
            db, "segment.merge", {"segment_ids": [seg_a.id, seg_b.id], "keep_id": seg_b.id}, ctx,
        )
        undo = client.post(f"/api/actions/audit/{do.audit_id}/undo")
        assert undo.status_code == 200, undo.text
        assert db.get(Segment, seg_a.id).deleted_at is None  # restored, live again

        # Another writer edits A in between the undo and the redo.
        a_version = db.get(Segment, seg_a.id).version
        other_writer = client.request("PUT", f"/api/segments/{seg_a.id}", json={
            "segment_id": seg_a.id, "expected_version": a_version,
            "kind_raw": "someone-else-edited-this",
        })
        assert other_writer.status_code == 200, other_writer.text

        redo = client.post(f"/api/actions/audit/{undo.json()['audit_id']}/undo")
        assert redo.status_code == 409, redo.text
        # Unchanged by the refused redo: A is still live, still carrying
        # the other writer's edit, never merged away.
        restored = db.get(Segment, seg_a.id)
        assert restored.deleted_at is None
        assert restored.kind_raw == "someone-else-edited-this"

    def test_merge_undo_restores_the_edited_content_not_the_original(self, db, client):
        """#4957 review 3, item 8: restores a property the rewritten test
        above no longer pins -- `_action_merge` snapshots the absorbed
        segment AS IT IS NOW, not as it was when first created. Edit A,
        THEN merge it away, THEN undo: A must come back with the EDITED
        content, never the pre-edit original."""
        doc = _make_doc(db)
        pass_row = _make_pass(db, doc.id)
        seg_a = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.0, 0.0, 0.1, 0.1])
        seg_b = _make_segment(db, document_id=doc.id, pass_id=pass_row.id, rect=[0.3, 0.3, 0.1, 0.1])
        ctx = _ctx(db, actor="daniel")

        edit = client.request("PUT", f"/api/segments/{seg_a.id}", json={
            "segment_id": seg_a.id, "expected_version": 1, "kind_raw": "edited-before-merge",
        })
        assert edit.status_code == 200, edit.text

        do = _invoke_versioned(
            db, "segment.merge", {"segment_ids": [seg_a.id, seg_b.id], "keep_id": seg_b.id}, ctx,
        )
        assert db.get(Segment, seg_a.id).deleted_at is not None

        undo = client.post(f"/api/actions/audit/{do.audit_id}/undo")
        assert undo.status_code == 200, undo.text

        restored = db.get(Segment, seg_a.id)
        assert restored.deleted_at is None
        assert restored.kind_raw == "edited-before-merge"  # the EDIT, not the original
