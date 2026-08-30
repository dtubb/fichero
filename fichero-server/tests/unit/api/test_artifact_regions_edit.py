"""Tests for PUT /api/artifacts/{id}/regions — region curation (2026-08-29).

Regions became first-class objects: a box inside an artifact's
``ocr_geometry.boxes`` can be moved, deleted, added, and combined, each edit
one audited, undoable action that also writes a ``curation_log`` entry into
the geometry's own metadata. These tests pin the semantics, the edge cases,
and the side effects (audit row, undo restores the before-snapshot).
"""

import pytest

from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryResult
from fichero_server.models import ActionAudit, Artifact, Document, DocType, FileType, Status


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

        r = _edit(client, a.id, {"op": "move", "indices": [1], "bbox": [0.4, 0.4, 0.2, 0.05]})
        assert r.status_code == 200
        body = r.json()
        assert body["ocr_geometry"]["boxes"][1]["bbox"] == [0.4, 0.4, 0.2, 0.05]
        # Everything else about the box survives the move.
        assert body["ocr_geometry"]["boxes"][1]["text"] == "beta"
        assert body["region_count"] == 3

        stored = db.get(Artifact, a.id)
        assert stored.ocr_geometry.boxes[1].bbox == [0.4, 0.4, 0.2, 0.05]
        log = stored.ocr_geometry.metadata["curation_log"]
        assert log[-1]["op"] == "move"
        assert log[-1]["from_bbox"] == [0.1, 0.3, 0.2, 0.05]

    def test_move_rejects_out_of_bounds_bbox(self, client, db):
        doc = _make_doc(db)
        a = _make_regions_artifact(db, doc.id)
        r = _edit(client, a.id, {"op": "move", "indices": [0], "bbox": [0.9, 0.9, 0.5, 0.5]})
        assert r.status_code == 422
        # And nothing changed — a refused edit must not half-land.
        assert db.get(Artifact, a.id).ocr_geometry.boxes[0].bbox == [0.1, 0.1, 0.2, 0.05]

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

        # Curation-grade: the removed boxes are in the geometry's own log.
        stored = db.get(Artifact, a.id)
        removed = stored.ocr_geometry.metadata["curation_log"][-1]["removed"]
        assert [b["text"] for b in removed] == ["alpha", "gamma"]

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

        audits = [
            row for row in db.all(ActionAudit)
            if row.action_name == "artifact.regions_edit"
        ]
        assert len(audits) == 1
        audit = audits[-1]
        assert audit.target_ids == [a.id]
        # The before-snapshot carries the FULL artifact (all 3 boxes): the
        # invert derives artifact.restore from it, so the edit is never lossy.
        assert len(audit.before["ocr_geometry"]["boxes"]) == 3
        # Other clients hear about the edit without a refresh.
        assert calls[-1][1]["type"] == "artifact.updated"
        assert calls[-1][1]["artifact_ids"] == [a.id]


class TestAdd:
    def test_add_appends_user_box(self, client, db):
        doc = _make_doc(db)
        a = _make_regions_artifact(db, doc.id)

        r = _edit(
            client, a.id,
            {"op": "add", "bbox": [0.2, 0.7, 0.1, 0.1], "text": "drawn"},
        )
        assert r.status_code == 200
        boxes = r.json()["ocr_geometry"]["boxes"]
        assert len(boxes) == 4
        assert boxes[-1]["text"] == "drawn"
        assert boxes[-1]["bbox"] == [0.2, 0.7, 0.1, 0.1]
        assert boxes[-1]["level"] == "region"
        assert boxes[-1]["provider"] == "user"
        assert boxes[-1]["source"] == "manual"

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

    def test_every_edit_appends_to_curation_log(self, client, db):
        doc = _make_doc(db)
        a = _make_regions_artifact(db, doc.id)
        _edit(client, a.id, {"op": "add", "bbox": [0.0, 0.9, 0.1, 0.1]})
        _edit(client, a.id, {"op": "move", "indices": [3], "bbox": [0.1, 0.8, 0.1, 0.1]})
        _edit(client, a.id, {"op": "delete", "indices": [3]})
        log = db.get(Artifact, a.id).ocr_geometry.metadata["curation_log"]
        assert [e["op"] for e in log] == ["add", "move", "delete"]
        assert all("at" in e and "actor" in e for e in log)
