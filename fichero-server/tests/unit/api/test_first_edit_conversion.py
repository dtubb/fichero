"""Slice 6 step 5 (#4924) -- a page's FIRST EDIT, end to end.

Through the real `PUT /api/artifacts/{id}/regions`, which is the route the
unchanged app uses. The first edit converts the page's boxes into segment
rows and applies the edit to them, as ONE audited action with ONE undo
step; every edit after it is just the edit.

Behaviours pinned:
* `source.store.ids-on-first-edit`
* `source.store.undo-first-edit-keeps-conversion`
* `source.store.old-app-still-works` -- the positions the app sends keep
  meaning the boxes it was last given.
"""

from __future__ import annotations

import pytest

from fichero_server.actions.registry import ActionContext, registry
from fichero_server.api.routes.document.segment_conversion import live_rows_in_order
from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryResult
from fichero_server.models import ActionAudit, Artifact, DocType, Document, FileType, Status
from fichero_server.models.segments import (
    Segment,
    SegmentPassChoice,
    converted_pass_id,
)

pytestmark = pytest.mark.source_model


def _make_doc(db, name: str = "page.jpg") -> Document:
    doc = Document(
        name=name, doc_type=DocType.file, file_type=FileType.image,
        path=f"/path/{name}", status=Status.completed,
    )
    db.save(doc)
    return doc


def _artifact(db, doc, count: int = 4) -> Artifact:
    artifact = Artifact(
        document_id=doc.id, artifact_type="transcription", provider="qwen",
        ocr_geometry=OCRGeometryResult(
            provider="qwen", text=" ".join(f"w{i}" for i in range(count)),
            boxes=[
                OCRGeometryBox(
                    text=f"w{i}", bbox=[0.1, 0.1 + i * 0.15, 0.2, 0.05], level="line",
                )
                for i in range(count)
            ],
        ),
    )
    db.save(artifact)
    return artifact


def _edit(client, artifact_id: str, payload: dict):
    r = client.put(f"/api/artifacts/{artifact_id}/regions", json=payload)
    assert r.status_code == 200, r.text
    return r.json()


def _ctx() -> ActionContext:
    return ActionContext(actor="historian", library_path=None, is_bootstrap=True)


class TestTheFirstEditConvertsAndEdits:
    def test_one_action_and_one_undo_step(self, db, client):
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        _edit(client, artifact.id, {"op": "move", "indices": [1], "bbox": [0.7, 0.7, 0.1, 0.05]})

        audits = [a for a in db.all(ActionAudit) if a.action_name.startswith(("artifact.", "segment."))]
        assert len(audits) == 1, [a.action_name for a in audits]
        assert audits[0].action_name == "segment.convert_and_edit"

    def test_the_page_is_converted_and_the_edit_landed_on_a_row(self, db, client):
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        _edit(client, artifact.id, {"op": "move", "indices": [1], "bbox": [0.7, 0.7, 0.1, 0.05]})

        assert db.get(Artifact, artifact.id).geometry_superseded_by_pass_id == (
            converted_pass_id(artifact.id)
        )
        rows = live_rows_in_order(db, converted_pass_id(artifact.id))
        assert rows[1].anchor.rect == [0.7, 0.7, 0.1, 0.05]
        assert rows[1].version == 2
        assert all(row.version == 1 for i, row in enumerate(rows) if i != 1)

    def test_converting_is_not_authorship_and_the_edit_names_the_person(
        self, db, client
    ):
        """`source.store.converted-boxes-keep-their-maker`.

        The MACHINE drew these boxes, and converting them does not make
        them anybody else's: every row keeps `workflow`. What the person
        did is recorded where it belongs -- the version row for the box
        they actually touched carries THEIR name, and no other box has a
        version row at all.
        """
        from fichero_server.models.knowledge import ProvenanceKind
        from fichero_server.models.segments import SegmentVersion

        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        _edit(client, artifact.id, {"op": "move", "indices": [1], "bbox": [0.7, 0.7, 0.1, 0.05]})

        rows = live_rows_in_order(db, converted_pass_id(artifact.id))
        assert all(r.provenance_kind is ProvenanceKind.workflow for r in rows)
        assert all(r.created_by == "qwen" for r in rows), "the machine, not the mover"

        touched = db.query(SegmentVersion, segment_id=rows[1].id)
        assert len(touched) == 1
        assert touched[0].actor is not None, "the edit names who made it"
        for untouched in (rows[0], rows[2], rows[3]):
            assert db.query(SegmentVersion, segment_id=untouched.id) == []

    def test_the_working_pass_is_recorded(self, db, client):
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        _edit(client, artifact.id, {"op": "move", "indices": [0], "bbox": [0.7, 0.7, 0.1, 0.05]})

        choices = db.query(SegmentPassChoice, document_id=doc.id)
        assert len(choices) == 1
        assert choices[0].pass_id == converted_pass_id(artifact.id)
        assert choices[0].chosen_by == "daniel" or choices[0].chosen_by is not None
        assert choices[0].superseded_at is None

    def test_a_later_choice_supersedes_rather_than_replacing(self, db, client):
        """Rows are never deleted: what somebody was working on stays
        readable."""
        doc = _make_doc(db)
        first = _artifact(db, doc)
        second = _artifact(db, doc)
        _edit(client, first.id, {"op": "move", "indices": [0], "bbox": [0.7, 0.7, 0.1, 0.05]})
        _edit(client, second.id, {"op": "move", "indices": [0], "bbox": [0.8, 0.8, 0.1, 0.05]})

        choices = db.query(SegmentPassChoice, document_id=doc.id)
        assert len(choices) == 2
        live = [c for c in choices if c.superseded_at is None]
        assert len(live) == 1
        assert live[0].pass_id == converted_pass_id(second.id)

    def test_the_second_edit_converts_nothing(self, db, client):
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        _edit(client, artifact.id, {"op": "move", "indices": [0], "bbox": [0.7, 0.7, 0.1, 0.05]})
        _edit(client, artifact.id, {"op": "move", "indices": [1], "bbox": [0.8, 0.8, 0.1, 0.05]})

        audits = [a for a in db.all(ActionAudit) if a.action_name == "segment.convert_and_edit"]
        assert len(audits) == 2
        assert audits[-1].after["artifact_ids"] == [], "nothing left to convert"
        rows = live_rows_in_order(db, converted_pass_id(artifact.id))
        assert rows[0].anchor.rect == [0.7, 0.7, 0.1, 0.05]
        assert rows[1].anchor.rect == [0.8, 0.8, 0.1, 0.05]


class TestUndoOfAFirstEditKeepsTheConversion:
    """`source.store.undo-first-edit-keeps-conversion`."""

    def _undo(self, db, client):
        audit = [a for a in db.all(ActionAudit) if a.action_name == "segment.convert_and_edit"][-1]
        r = client.post(f"/api/actions/audit/{audit.id}/undo")
        assert r.status_code == 200, r.text
        return r

    def test_the_geometry_goes_back_and_the_rows_stay(self, db, client):
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        was = list(artifact.ocr_geometry.boxes[1].bbox)
        _edit(client, artifact.id, {"op": "move", "indices": [1], "bbox": [0.7, 0.7, 0.1, 0.05]})
        self._undo(db, client)

        rows = live_rows_in_order(db, converted_pass_id(artifact.id))
        assert rows[1].anchor.rect == was, "the move is undone"
        assert rows[1].version == 3, "by a new version, not by erasing one"
        assert len(rows) == 4, "and the conversion is kept"
        assert db.get(Artifact, artifact.id).geometry_superseded_by_pass_id is not None

    def test_the_block_is_byte_equal_through_edit_and_undo(self, db, client):
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        before = db.get(Artifact, artifact.id).ocr_geometry.model_dump(mode="json")
        _edit(client, artifact.id, {"op": "move", "indices": [1], "bbox": [0.7, 0.7, 0.1, 0.05]})
        assert db.get(Artifact, artifact.id).ocr_geometry.model_dump(mode="json") == before
        self._undo(db, client)
        assert db.get(Artifact, artifact.id).ocr_geometry.model_dump(mode="json") == before

    def test_the_page_reads_as_it_did_before_the_edit(self, db, client):
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        before = client.get(f"/api/artifacts/{artifact.id}").json()["ocr_geometry"]["boxes"]
        _edit(client, artifact.id, {"op": "move", "indices": [1], "bbox": [0.7, 0.7, 0.1, 0.05]})
        self._undo(db, client)
        after = client.get(f"/api/artifacts/{artifact.id}").json()["ocr_geometry"]["boxes"]
        assert [b["bbox"] for b in after] == [b["bbox"] for b in before]
        assert [b["text"] for b in after] == [b["text"] for b in before]

    def test_undoing_a_delete_brings_the_boxes_back(self, db, client):
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        _edit(client, artifact.id, {"op": "delete", "indices": [0, 2]})
        assert len(live_rows_in_order(db, converted_pass_id(artifact.id))) == 2
        self._undo(db, client)
        rows = live_rows_in_order(db, converted_pass_id(artifact.id))
        assert len(rows) == 4
        assert [r.metadata["box_index"] for r in rows] == [0, 1, 2, 3]

    def test_undoing_an_add_removes_the_box_and_redo_brings_the_same_one_back(
        self, db, client
    ):
        """The id must be the SAME on the way back -- an id is never given
        to another segment, and redo of an add is an undelete of that row."""
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        _edit(client, artifact.id, {"op": "add", "bbox": [0.5, 0.9, 0.1, 0.05]})
        added = live_rows_in_order(db, converted_pass_id(artifact.id))[-1]

        self._undo(db, client)
        assert len(live_rows_in_order(db, converted_pass_id(artifact.id))) == 4

        undo_audit = [a for a in db.all(ActionAudit) if a.inverse_of is not None][-1]
        r = client.post(f"/api/actions/audit/{undo_audit.id}/undo")
        assert r.status_code == 200, r.text

        rows = live_rows_in_order(db, converted_pass_id(artifact.id))
        assert len(rows) == 5
        assert rows[-1].id == added.id, "redo must bring back the SAME segment"


class TestTheAppsPositionsKeepMeaningWhatItWasGiven:
    """`source.store.old-app-still-works` -- the review's own probe."""

    def test_move_delete_then_move_index_three(self, db, client):
        doc = _make_doc(db)
        artifact = _artifact(db, doc, count=6)

        _edit(client, artifact.id, {"op": "move", "indices": [0], "bbox": [0.6, 0.1, 0.1, 0.05]})
        _edit(client, artifact.id, {"op": "delete", "indices": [1]})
        # The app now sees five boxes: w0(moved), w2, w3, w4, w5.
        listed = client.get(f"/api/artifacts/{artifact.id}").json()["ocr_geometry"]["boxes"]
        assert [b["text"] for b in listed] == ["w0", "w2", "w3", "w4", "w5"]

        _edit(client, artifact.id, {"op": "move", "indices": [3], "bbox": [0.9, 0.9, 0.05, 0.05]})
        after = client.get(f"/api/artifacts/{artifact.id}").json()["ocr_geometry"]["boxes"]
        moved = [b for b in after if b["bbox"] == [0.9, 0.9, 0.05, 0.05]]
        assert len(moved) == 1
        assert moved[0]["text"] == "w4", "the box moved is the one the list showed fourth"

    def test_an_index_past_the_end_is_a_typed_422(self, db, client):
        doc = _make_doc(db)
        artifact = _artifact(db, doc, count=3)
        _edit(client, artifact.id, {"op": "move", "indices": [0], "bbox": [0.6, 0.1, 0.1, 0.05]})
        r = client.put(
            f"/api/artifacts/{artifact.id}/regions",
            json={"op": "move", "indices": [9], "bbox": [0.1, 0.1, 0.1, 0.1]},
        )
        assert r.status_code == 422
        assert "out of range" in r.text

    def test_a_combined_box_lands_in_the_lowest_members_slot(self, db, client):
        """Today's `keep_at = min(indices)`. If the combined box went to the
        end instead, every position after it would shift and the inspector's
        rows and palette colours would change under the person."""
        doc = _make_doc(db)
        artifact = _artifact(db, doc, count=5)
        _edit(client, artifact.id, {"op": "combine", "indices": [3, 1]})

        boxes = client.get(f"/api/artifacts/{artifact.id}").json()["ocr_geometry"]["boxes"]
        assert [b["text"] for b in boxes] == ["w0", "w1\nw3", "w2", "w4"]
        assert boxes[1]["source"] == "combine"


class TestUndoOfACombinePutsThePageBack:
    """FIX FIRST from the step 5 review.

    A combine is `segment.merge` PLUS a reshape of the kept segment to the
    union. `segment.unmerge` undoes only the merge -- it restores the
    ABSORBED segments and never touches the kept row, because merge never
    touched it either. So undoing a combine with the merge's inverse alone
    brought the swallowed boxes back UNDERNEATH a kept box still shaped as
    the union and still reading all three boxes' words. The page was not
    what it was, and nothing raised.
    """

    def _seam(self, client, doc_id: str):
        r = client.get(f"/api/segments/document/{doc_id}")
        assert r.status_code == 200, r.text
        return r.json()

    def _undo_latest(self, db, client):
        audit = [
            a for a in db.all(ActionAudit)
            if a.action_name == "segment.convert_and_edit"
        ][-1]
        r = client.post(f"/api/actions/audit/{audit.id}/undo")
        assert r.status_code == 200, r.text
        return audit

    def test_undo_then_redo_of_a_combine_round_trips_through_the_seam(self, db, client):
        doc = _make_doc(db)
        artifact = _artifact(db, doc, count=6)
        # Convert first, so the combine is not also the conversion and the
        # seam's "before" is a converted page -- the comparison is then
        # about the COMBINE alone.
        _edit(client, artifact.id, {"op": "move", "indices": [0], "bbox": [0.1, 0.1, 0.2, 0.05]})

        before = self._seam(client, doc.id)
        block_before = db.get(Artifact, artifact.id).ocr_geometry.model_dump(mode="json")

        _edit(client, artifact.id, {"op": "combine", "indices": [2, 3, 4]})
        combined = self._seam(client, doc.id)
        assert len(combined["segments"]) == len(before["segments"]) - 2
        assert any(s["text"] == "w2\nw3\nw4" for s in combined["segments"])

        self._undo_latest(db, client)
        after_undo = self._seam(client, doc.id)

        # FIELD FOR FIELD, including each box's words -- ids and all, since
        # a combine mints nothing and undoing it must restore the same rows.
        assert after_undo["segments"] == before["segments"]
        assert after_undo["passes"] == before["passes"]

        undo_audit = [a for a in db.all(ActionAudit) if a.inverse_of is not None][-1]
        assert undo_audit.action_name == "segment.uncombine"
        r = client.post(f"/api/actions/audit/{undo_audit.id}/undo")
        assert r.status_code == 200, r.text
        after_redo = self._seam(client, doc.id)
        assert [s["text"] for s in after_redo["segments"]] == [
            s["text"] for s in combined["segments"]
        ]

        assert db.get(Artifact, artifact.id).ocr_geometry.model_dump(mode="json") == (
            block_before
        ), "the machine's own record is untouched throughout"

    def test_the_kept_box_stops_reading_the_words_it_swallowed(self, db, client):
        """The sharpest symptom: `member_box_indexes` is written straight
        onto the row and is NOT part of `SegmentVersion`, so restoring a
        version alone would leave the kept box still reading all three
        boxes' words."""
        doc = _make_doc(db)
        artifact = _artifact(db, doc, count=5)
        _edit(client, artifact.id, {"op": "combine", "indices": [1, 2]})
        kept = live_rows_in_order(db, converted_pass_id(artifact.id))[1]
        assert kept.metadata["member_box_indexes"] == [1, 2]

        self._undo_latest(db, client)

        kept_after = db.get(Segment, kept.id)
        assert "member_box_indexes" not in kept_after.metadata
        boxes = client.get(f"/api/artifacts/{artifact.id}").json()["ocr_geometry"]["boxes"]
        assert [b["text"] for b in boxes] == ["w0", "w1", "w2", "w3", "w4"]

    def test_the_kept_box_goes_back_to_its_own_shape_and_kind(self, db, client):
        doc = _make_doc(db)
        artifact = _artifact(db, doc, count=5)
        was = list(artifact.ocr_geometry.boxes[1].bbox)
        _edit(client, artifact.id, {"op": "combine", "indices": [1, 2]})
        kept = live_rows_in_order(db, converted_pass_id(artifact.id))[1]
        assert kept.anchor.rect != was, "the combine did widen it"

        self._undo_latest(db, client)
        kept_after = db.get(Segment, kept.id)
        assert kept_after.anchor.rect == was
        assert kept_after.kind == "line", "and its own kind, not the union's"

    def test_undoing_one_of_two_combines_leaves_the_other(self, db, client):
        """`member_box_indexes_added` is EXACTLY this combine's members, so
        combining twice and undoing once removes only the second's."""
        doc = _make_doc(db)
        artifact = _artifact(db, doc, count=6)
        _edit(client, artifact.id, {"op": "combine", "indices": [0, 1]})
        _edit(client, artifact.id, {"op": "combine", "indices": [2, 3]})

        self._undo_latest(db, client)
        boxes = client.get(f"/api/artifacts/{artifact.id}").json()["ocr_geometry"]["boxes"]
        texts = [b["text"] for b in boxes]
        # Exactly one box short of six: the first combine still holds two
        # boxes together, the second is fully undone.
        assert sorted(texts) == sorted(["w0\nw1", "w2", "w3", "w4", "w5"]), texts
