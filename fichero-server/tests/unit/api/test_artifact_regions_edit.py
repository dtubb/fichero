"""Tests for PUT /api/artifacts/{id}/regions — region curation (2026-08-29).

Regions became first-class objects: a box inside an artifact's
``ocr_geometry.boxes`` can be moved, deleted, added, and combined, each edit
one audited, undoable action.

REWRITTEN for #4924 slice 6 step 5. The ROUTE and its answers are unchanged
-- that is the point, and it is what the app depends on -- but WHERE the
edit lands moved. A page's first edit now converts its boxes into segment
rows and applies the edit to them, as one audited action; the artifact's
``ocr_geometry`` block becomes the record of what the MACHINE produced and
is never written again.

So every assertion below that used to read the stored block now reads one
of two things instead:

* the RESPONSE, which is the app-facing contract and has not changed; or
* the ROWS, which are where the edit actually landed.

And the block is asserted BYTE-EQUAL, which is the new invariant. One
casualty, ruled 2026-09-20: the ``curation_log`` inside the geometry stops
growing at conversion, because the geometry stops being written. Nothing in
the engine or the app ever read it; the history lives in the audit chain and
the segment version rows, which do not travel with an exported artifact.
"""

import pytest

from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryResult
from fichero_server.models import ActionAudit, Artifact, Document, DocType, FileType, Status
from fichero_server.models.segments import Segment


def _rows(db, artifact_id: str, *, live_only: bool = True):
    """The artifact's segment rows, in the one order the app is given them.

    `live_only=False` includes soft-deleted rows, which is how a delete's
    "what was removed" is now answered: the rows are still there.
    """
    from fichero_server.api.routes.document.segment_conversion import live_rows_in_order
    from fichero_server.models.segments import converted_pass_id

    pass_id = converted_pass_id(artifact_id)
    if live_only:
        return live_rows_in_order(db, pass_id)
    return sorted(
        db.query(Segment, pass_id=pass_id),
        key=lambda r: (r.metadata.get("box_index", 0), r.created_at.isoformat()),
    )


def _make_doc(db, name: str = "page.jpg") -> Document:
    doc = Document(
        name=name,
        doc_type=DocType.file,
        file_type=FileType.image,
        path=f"/path/{name}",
        status=Status.completed,
    )
    db.save(doc)
    return doc


def _make_regions_artifact(db, doc_id: str, boxes=None) -> Artifact:
    geometry = OCRGeometryResult(
        text="alpha beta gamma",
        provider="apple_vision",
        boxes=boxes
        if boxes is not None
        else [
            OCRGeometryBox(
                text="alpha", bbox=[0.1, 0.1, 0.2, 0.05], level="region",
                char_start=0, char_end=5,
            ),
            OCRGeometryBox(
                text="beta", bbox=[0.1, 0.3, 0.2, 0.05], level="region",
                char_start=6, char_end=10,
            ),
            OCRGeometryBox(
                text="gamma", bbox=[0.5, 0.5, 0.3, 0.1], level="region",
                char_start=11, char_end=16,
            ),
        ],
    )
    artifact = Artifact(
        document_id=doc_id,
        artifact_type="regions",
        content="alpha beta gamma",
        ocr_geometry=geometry,
    )
    db.save(artifact)
    return artifact


def _edit(client, artifact_id: str, payload: dict):
    return client.put(f"/api/artifacts/{artifact_id}/regions", json=payload)


class TestMove:
    def test_move_updates_bbox_and_persists(self, client, db):
        doc = _make_doc(db)
        a = _make_regions_artifact(db, doc.id)
        block_before = db.get(Artifact, a.id).ocr_geometry.model_dump(mode="json")

        r = _edit(client, a.id, {"op": "move", "indices": [1], "bbox": [0.4, 0.4, 0.2, 0.05]})
        assert r.status_code == 200
        body = r.json()
        assert body["ocr_geometry"]["boxes"][1]["bbox"] == [0.4, 0.4, 0.2, 0.05]
        # Everything else about the box survives the move.
        assert body["ocr_geometry"]["boxes"][1]["text"] == "beta"
        assert body["region_count"] == 3

        # The edit landed on the ROW, and the block is untouched (#4924).
        rows = _rows(db, a.id)
        assert rows[1].anchor.rect == [0.4, 0.4, 0.2, 0.05]
        assert rows[1].version == 2, "a move is a versioned change"
        assert db.get(Artifact, a.id).ocr_geometry.model_dump(mode="json") == block_before

    def test_move_rejects_out_of_bounds_bbox(self, client, db):
        doc = _make_doc(db)
        a = _make_regions_artifact(db, doc.id)
        r = _edit(client, a.id, {"op": "move", "indices": [0], "bbox": [0.9, 0.9, 0.5, 0.5]})
        assert r.status_code == 422
        # And nothing changed — a refused edit must not half-land. Since the
        # whole thing is one transaction, that now means no rows either.
        assert db.get(Artifact, a.id).ocr_geometry.boxes[0].bbox == [0.1, 0.1, 0.2, 0.05]
        assert db.get(Artifact, a.id).geometry_superseded_by_pass_id is None
        assert db.query(Segment, document_id=doc.id) == []

    def test_move_needs_exactly_one_index(self, client, db):
        doc = _make_doc(db)
        a = _make_regions_artifact(db, doc.id)
        r = _edit(client, a.id, {"op": "move", "indices": [0, 1], "bbox": [0.1, 0.1, 0.1, 0.1]})
        assert r.status_code == 422
        r = _edit(client, a.id, {"op": "move", "indices": [0]})
        assert r.status_code == 422


class TestDelete:
    def test_delete_removes_boxes_and_logs_them(self, client, db):
        doc = _make_doc(db)
        a = _make_regions_artifact(db, doc.id)

        r = _edit(client, a.id, {"op": "delete", "indices": [2, 0]})
        assert r.status_code == 200
        body = r.json()
        assert body["region_count"] == 1
        assert [b["text"] for b in body["ocr_geometry"]["boxes"]] == ["beta"]

        # Curation-grade: the removed boxes are SOFT-deleted rows, so what
        # was removed is still there to be undone, and the block still
        # holds all three (#4924).
        rows = _rows(db, a.id, live_only=False)
        assert len(rows) == 3
        assert sum(1 for row in rows if row.deleted_at is not None) == 2
        assert len(db.get(Artifact, a.id).ocr_geometry.boxes) == 3

    def test_delete_index_out_of_range(self, client, db):
        doc = _make_doc(db)
        a = _make_regions_artifact(db, doc.id)
        r = _edit(client, a.id, {"op": "delete", "indices": [3]})
        assert r.status_code == 422

    def test_delete_needs_indices(self, client, db):
        doc = _make_doc(db)
        a = _make_regions_artifact(db, doc.id)
        r = _edit(client, a.id, {"op": "delete", "indices": []})
        assert r.status_code == 422

    def test_delete_writes_audit_with_full_before_snapshot_and_emits(
        self, client, db, monkeypatch
    ):
        doc = _make_doc(db)
        a = _make_regions_artifact(db, doc.id)
        calls: list[tuple] = []
        monkeypatch.setattr(
            "fichero_server.api.change_stream.emit_change",
            lambda *args, **kwargs: calls.append((args, kwargs)),
        )

        r = _edit(client, a.id, {"op": "delete", "indices": [0]})
        assert r.status_code == 200

        # ONE audited action for the conversion AND the edit -- one undo
        # step, which is the whole point (#4924).
        audits = [
            row for row in db.all(ActionAudit)
            if row.action_name == "segment.convert_and_edit"
        ]
        assert len(audits) == 1
        audit = audits[-1]
        assert a.id in audit.target_ids and doc.id in audit.target_ids
        # The edit is recorded as the segment action that carried it, which
        # is what the inverse is worked out from.
        assert audit.after["edit"]["action"] == "segment.delete"
        assert audit.after["segment_count"] == 3
        # Other clients hear about it without a refresh.
        assert calls[-1][1]["type"] == "segment.converted"
        assert calls[-1][1]["artifact_ids"] == [a.id]


class TestAdd:
    def test_add_appends_user_box(self, client, db):
        doc = _make_doc(db)
        a = _make_regions_artifact(db, doc.id)

        r = _edit(client, a.id, {"op": "add", "bbox": [0.2, 0.7, 0.1, 0.1]})
        assert r.status_code == 200
        boxes = r.json()["ocr_geometry"]["boxes"]
        assert len(boxes) == 4
        assert boxes[-1]["bbox"] == [0.2, 0.7, 0.1, 0.1]
        assert boxes[-1]["level"] == "region"
        assert boxes[-1]["provider"] == "user"
        assert boxes[-1]["source"] == "manual"
        assert boxes[-1]["text"] == ""

    def test_an_add_carrying_typed_text_is_refused_until_readings_exist(
        self, client, db
    ):
        """RULED (#4924, the stop point). Once a page's boxes are rows,
        there is nowhere lawful to keep typed text: not the block, which is
        the machine's record and is never written again; not the audit
        chain; and not a `metadata["text"]`, which would be a second home
        for words that the readings slice then has to move row by row.

        This refuses nothing a person can do in the app: both `addRegion`
        call sites send the empty default, and the one region text field
        names a child document, not a box. It IS a change for a CLI or MCP
        caller that passed text, which is why it is pinned here.
        """
        doc = _make_doc(db)
        a = _make_regions_artifact(db, doc.id)
        r = _edit(
            client, a.id,
            {"op": "add", "bbox": [0.2, 0.7, 0.1, 0.1], "text": "drawn"},
        )
        assert r.status_code == 422, r.text
        assert "readings" in r.text
        # Refused whole: no rows, no marker, nothing half-landed.
        assert db.get(Artifact, a.id).geometry_superseded_by_pass_id is None
        assert db.query(Segment, document_id=doc.id) == []

    def test_add_bootstraps_missing_geometry(self, client, db):
        doc = _make_doc(db)
        bare = Artifact(document_id=doc.id, artifact_type="regions", content=None)
        db.save(bare)

        r = _edit(client, bare.id, {"op": "add", "bbox": [0.0, 0.0, 0.5, 0.5]})
        assert r.status_code == 200
        body = r.json()
        assert body["region_count"] == 1
        assert body["ocr_geometry"]["provider"] == "user"

    def test_add_requires_bbox(self, client, db):
        doc = _make_doc(db)
        a = _make_regions_artifact(db, doc.id)
        r = _edit(client, a.id, {"op": "add", "text": "no bbox"})
        assert r.status_code == 422

    def test_non_add_on_geometryless_artifact_is_422(self, client, db):
        doc = _make_doc(db)
        bare = Artifact(document_id=doc.id, artifact_type="transcription", content="x")
        db.save(bare)
        r = _edit(client, bare.id, {"op": "delete", "indices": [0]})
        assert r.status_code == 422


class TestCombine:
    def test_combine_unions_bbox_and_concatenates_in_reading_order(self, client, db):
        doc = _make_doc(db)
        a = _make_regions_artifact(db, doc.id)

        # Indices given in REVERSE reading order on purpose — the result must
        # still read alpha before beta (char spans decide, not click order).
        r = _edit(client, a.id, {"op": "combine", "indices": [1, 0]})
        assert r.status_code == 200
        boxes = r.json()["ocr_geometry"]["boxes"]
        assert len(boxes) == 2
        merged = boxes[0]  # lands at the smallest combined index
        assert merged["text"] == "alpha\nbeta"
        # Union of [0.1,0.1,0.2,0.05] and [0.1,0.3,0.2,0.05].
        assert merged["bbox"] == pytest.approx([0.1, 0.1, 0.2, 0.25])
        assert merged["char_start"] == 0
        assert merged["char_end"] == 10
        assert merged["source"] == "combine"
        # The untouched box survives, after the merged one.
        assert boxes[1]["text"] == "gamma"

    def test_combine_without_char_spans_uses_top_then_left(self, client, db):
        doc = _make_doc(db)
        a = _make_regions_artifact(
            db, doc.id,
            boxes=[
                OCRGeometryBox(text="below", bbox=[0.1, 0.6, 0.2, 0.1], level="region"),
                OCRGeometryBox(text="above", bbox=[0.1, 0.1, 0.2, 0.1], level="region"),
            ],
        )
        r = _edit(client, a.id, {"op": "combine", "indices": [0, 1]})
        assert r.status_code == 200
        merged = r.json()["ocr_geometry"]["boxes"][0]
        assert merged["text"] == "above\nbelow"
        assert merged["char_start"] is None

    def test_combine_mixed_levels_becomes_region(self, client, db):
        doc = _make_doc(db)
        a = _make_regions_artifact(
            db, doc.id,
            boxes=[
                OCRGeometryBox(text="w", bbox=[0.1, 0.1, 0.1, 0.1], level="word"),
                OCRGeometryBox(text="l", bbox=[0.3, 0.3, 0.1, 0.1], level="line"),
            ],
        )
        r = _edit(client, a.id, {"op": "combine", "indices": [0, 1]})
        assert r.status_code == 200
        assert r.json()["ocr_geometry"]["boxes"][0]["level"] == "region"

    def test_combine_needs_two_indices(self, client, db):
        doc = _make_doc(db)
        a = _make_regions_artifact(db, doc.id)
        r = _edit(client, a.id, {"op": "combine", "indices": [0]})
        assert r.status_code == 422

    def test_duplicate_indices_are_deduped(self, client, db):
        doc = _make_doc(db)
        a = _make_regions_artifact(db, doc.id)
        r = _edit(client, a.id, {"op": "combine", "indices": [0, 0, 1]})
        assert r.status_code == 200
        assert len(r.json()["ocr_geometry"]["boxes"]) == 2


class TestContract:
    def test_unknown_artifact_is_404(self, client):
        r = _edit(client, "nope", {"op": "delete", "indices": [0]})
        assert r.status_code == 404

    def test_unknown_op_is_422(self, client, db):
        doc = _make_doc(db)
        a = _make_regions_artifact(db, doc.id)
        r = _edit(client, a.id, {"op": "explode", "indices": [0]})
        assert r.status_code == 422

    def test_the_curation_log_stops_at_the_first_edit(self, client, db):
        """RULED 2026-09-20, and the one visible casualty of freezing the
        block: the `curation_log` inside the geometry stops growing,
        because the geometry stops being written.

        Nothing in the engine or the app ever read it. The history moves to
        the audit chain and the segment version rows, which is where undo
        already reads from -- but unlike the log it does NOT travel with an
        exported artifact, and the route's docstring no longer promises
        that it does.
        """
        doc = _make_doc(db)
        a = _make_regions_artifact(db, doc.id)
        for payload in (
            {"op": "add", "bbox": [0.0, 0.9, 0.1, 0.1]},
            {"op": "move", "indices": [3], "bbox": [0.1, 0.8, 0.1, 0.1]},
            {"op": "delete", "indices": [3]},
        ):
            assert _edit(client, a.id, payload).status_code == 200

        # The block never gained a log, because it was never written.
        block = db.get(Artifact, a.id).ocr_geometry
        assert "curation_log" not in block.metadata
        assert len(block.boxes) == 3, "and the machine's own boxes are all still there"

        # The history is in the chain instead: one audited action per edit.
        edits = [
            row.after["edit"]["action"] for row in db.all(ActionAudit)
            if row.action_name == "segment.convert_and_edit" and row.after.get("edit")
        ]
        assert edits == ["segment.create", "segment.update", "segment.delete"]

        # And in the version rows, which is what undo reads.
        rows = _rows(db, a.id, live_only=False)
        assert any(row.version > 1 for row in rows)
