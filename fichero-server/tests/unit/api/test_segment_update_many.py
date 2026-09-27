"""One edit across a selection is ONE action and ONE undo step (#4941).

`segment.update` takes one segment, so before `segment.update_many` a selection-wide
edit — "set these five lines to heading" — was five audited actions and five undo
steps: ⌘Z reverted one line at a time. That is wrong for the person, and grouping the
requests on the client would have made the undo story lie.

What these pin: one audit row for N rows; one undo restores all N; all or nothing
when any row is stale; a row named twice is refused; the cascade's validation still
applies through the bulk path; and undo-of-undo (redo) works on the bulk shape too.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException
from starlette.requests import Request

import fichero_server.api.routes.document.segments  # noqa: F401 — registers the actions
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.api.routes.system.actions_registry import undo_action
from fichero_server.models import ActionAudit, DocType, Document, FileType, Segment, Status
from fichero_server.models.anchors import SourceAnchor
from fichero_server.models.knowledge import ProvenanceKind
from fichero_server.models.segments import SegmentPass, bbox_and_tile_from_anchor


def _ctx(db) -> ActionContext:
    return ActionContext(actor="historian", library_path=str(db.path.parent))


def _page(db, lines: int = 3) -> list[Segment]:
    doc = Document(
        name="folio.jpg", doc_type=DocType.file, file_type=FileType.image,
        path="/path/folio.jpg", status=Status.completed,
    )
    db.save(doc)
    pass_row = SegmentPass(
        document_id=doc.id, name="p", provenance_kind=ProvenanceKind.workflow
    )
    db.save(pass_row)
    rows = []
    for index in range(lines):
        anchor = SourceAnchor(document_id=doc.id, rect=[0.1, 0.1 * index, 0.5, 0.05])
        bbox_x, bbox_y, bbox_w, bbox_h, tile = bbox_and_tile_from_anchor(anchor)
        row = Segment(
            document_id=doc.id, pass_id=pass_row.id, kind="line", anchor=anchor,
            bbox_x=bbox_x, bbox_y=bbox_y, bbox_w=bbox_w, bbox_h=bbox_h, tile=tile,
            doc_kind=f"{doc.id}:line", provenance_kind=ProvenanceKind.workflow,
        )
        db.save(row)
        rows.append(row)
    return rows


def _update_many(db, rows, **attrs):
    return registry.invoke(
        db,
        "segment.update_many",
        {"updates": [
            {"segment_id": row.id, "expected_version": db.get(Segment, row.id).version, **attrs}
            for row in rows
        ]},
        _ctx(db),
    )


def _undo(db, audit_id: str):
    request = Request({
        "type": "http", "headers": [], "client": ("127.0.0.1", 1), "scheme": "https",
        "server": ("testserver", 443), "path": f"/api/actions/audit/{audit_id}/undo",
        "query_string": b"",
    })
    return asyncio.run(undo_action(
        audit_id, request=request, db=db,
        x_fichero_library_path=str(db.path.parent), x_fichero_origin_window=None,
    ))


def _segment_audits(db) -> list[ActionAudit]:
    return [a for a in db.all(ActionAudit) if a.action_name.startswith("segment.")]


class TestOneEditIsOneAction:
    def test_five_lines_are_one_audit_row(self, db):
        rows = _page(db, lines=5)

        _update_many(db, rows, kind="heading")

        audits = _segment_audits(db)
        assert len(audits) == 1, [a.action_name for a in audits]
        assert audits[0].action_name == "segment.update_many"
        assert {db.get(Segment, r.id).kind for r in rows} == {"heading"}

    def test_one_undo_restores_every_line(self, db):
        """The point of the whole action: ⌘Z after a selection-wide edit reverts the
        SELECTION, not one line of it."""
        rows = _page(db, lines=4)
        result = _update_many(db, rows, kind="heading")

        _undo(db, result.audit_id)

        assert {db.get(Segment, r.id).kind for r in rows} == {"line"}

    def test_redo_reapplies_every_line(self, db):
        """Undo of the undo. The bulk inverse is `segment.restore_versions`, whose own
        inverse is the same shape again — so redo works without a redo-specific path."""
        rows = _page(db, lines=3)
        result = _update_many(db, rows, kind="heading")
        undone = _undo(db, result.audit_id)

        _undo(db, undone.audit_id)

        assert {db.get(Segment, r.id).kind for r in rows} == {"heading"}


class TestAllOrNothing:
    def test_one_stale_line_refuses_the_whole_edit(self, db):
        """Half an edit is worse than none, because nothing on screen tells the person
        which half happened. So one line somebody else edited since refuses them all."""
        rows = _page(db, lines=3)
        # Somebody else edits the middle line after it was selected.
        registry.invoke(
            db, "segment.update",
            {"segment_id": rows[1].id, "expected_version": 1, "kind": "word"},
            _ctx(db),
        )

        with pytest.raises(HTTPException) as refused:
            registry.invoke(
                db, "segment.update_many",
                {"updates": [
                    {"segment_id": r.id, "expected_version": 1, "kind": "heading"}
                    for r in rows
                ]},
                _ctx(db),
            )

        assert refused.value.status_code == 409
        assert db.get(Segment, rows[0].id).kind == "line", "the first line was NOT changed"
        assert db.get(Segment, rows[2].id).kind == "line", "nor the last"
        assert db.get(Segment, rows[1].id).kind == "word", "the other person's edit stands"

    def test_a_line_named_twice_is_refused(self, db):
        """It would be snapshotted twice under one audit id, and the second
        compare-and-set would fail against the first's bump — a refusal of the caller's
        own request that reads like somebody else edited the line."""
        rows = _page(db, lines=1)

        with pytest.raises(HTTPException) as refused:
            registry.invoke(
                db, "segment.update_many",
                {"updates": [
                    {"segment_id": rows[0].id, "expected_version": 1, "kind": "a"},
                    {"segment_id": rows[0].id, "expected_version": 1, "kind": "b"},
                ]},
                _ctx(db),
            )

        assert refused.value.status_code == 422
        assert "named twice" in refused.value.detail

    def test_an_empty_edit_is_refused_before_it_reaches_the_action(self, db):
        with pytest.raises(Exception):
            registry.invoke(db, "segment.update_many", {"updates": []}, _ctx(db))


class TestTheSameRulesAsTheSingleRowPath:
    def test_an_unknown_script_is_refused_through_the_bulk_path_too(self, db):
        """The cascade's facts go through the SAME writer `segment.update` uses. A bulk
        path that skipped `assert_known_script` would be a way around it."""
        rows = _page(db, lines=2)

        with pytest.raises(Exception) as refused:
            _update_many(db, rows, script="Zq")

        assert "Zq" in str(refused.value)
        assert all(db.get(Segment, r.id).script is None for r in rows)

    def test_a_language_is_recorded_with_its_provenance(self, db):
        rows = _page(db, lines=2)

        _update_many(db, rows, language="la")

        for row in rows:
            fresh = db.get(Segment, row.id)
            assert fresh.language == "la"
            assert fresh.language_meta, "a fact set in bulk still says who set it"

    def test_undo_restores_the_cascade_facts_too(self, db):
        """`_copy_version_onto_row` is shared with `segment.restore_version` precisely so
        a fact one path restores and the other forgets cannot happen."""
        rows = _page(db, lines=2)
        result = _update_many(db, rows, language="la", direction="rtl")

        _undo(db, result.audit_id)

        for row in rows:
            fresh = db.get(Segment, row.id)
            assert fresh.language is None and fresh.direction is None


class TestTheRoute:
    def test_the_route_answers_the_audit_id_for_the_whole_edit(self, db, client):
        """So the app can offer ⌘Z for the selection without guessing which row to
        invert — the same reason the region-edit route answers one."""
        rows = _page(db, lines=2)

        response = client.patch(
            "/api/segments",
            json={"updates": [
                {"segment_id": r.id, "expected_version": 1, "kind": "heading"} for r in rows
            ]},
        )

        assert response.status_code == 200, response.text
        body = response.json()
        audit = db.get(ActionAudit, body["audit_id"])
        assert audit is not None and audit.action_name == "segment.update_many"
        assert len(body["versions"]) == 2
