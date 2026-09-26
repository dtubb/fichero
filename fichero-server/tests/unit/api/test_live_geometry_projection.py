"""Slice 6 (#4924) -- `source.store.old-app-still-works`.

The app does not read segments yet (app stage 2, #4954, is held): every one
of its region readers addresses a box by its POSITION in the artifact's box
list, and the engine keeps that true through a conversion by serving an
ordered projection of the rows.

These tests write the rows BY HAND. That is deliberate: the projection has
to be right before anything converts a page, and a test that went through
the conversion action could not tell a projection bug from a conversion bug.

Also pins the half the notes did not have: `region_count` and
`geometry_rendition_id` ride on list responses where the geometry itself
does not, and a curated page must not keep reporting its old count.
"""

from __future__ import annotations

import pytest

from fichero_server.api.routes.document.segment_conversion import (
    ConversionMarkerDangling,
    geometry_from_rows,
    is_converted,
    live_box_count,
    live_geometry,
    live_rows_in_order,
)
from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryResult
from fichero_server.models import Artifact, DocType, Document, FileType, Status
from fichero_server.models.knowledge import ProvenanceKind
from fichero_server.models.segments import (
    Segment,
    SegmentPass,
    rows_from_reads,
    segments_from_result,
)

pytestmark = pytest.mark.source_model


def _make_doc(db, name: str = "page.jpg") -> Document:
    doc = Document(
        name=name, doc_type=DocType.file, file_type=FileType.image,
        path=f"/path/{name}", status=Status.completed,
    )
    db.save(doc)
    return doc


def _block(count: int = 4, rendition_id: str | None = None) -> OCRGeometryResult:
    return OCRGeometryResult(
        provider="qwen",
        model="qwen-vl-max",
        text="uno dos tres cuatro",
        rendition_id=rendition_id,
        boxes=[
            OCRGeometryBox(
                text=f"w{i}",
                bbox=[0.1, 0.1 + i * 0.1, 0.2, 0.05],
                level="line",
                page_index=0,
            )
            for i in range(count)
        ],
        metadata={"curation_log": [{"op": "move"}]},
    )


def _artifact(db, doc, block: OCRGeometryResult | None = None) -> Artifact:
    artifact = Artifact(
        document_id=doc.id,
        artifact_type="transcription",
        provider="qwen",
        model="qwen-vl-max",
        ocr_geometry=block if block is not None else _block(),
    )
    db.save(artifact)
    return artifact


def _convert_by_hand(db, doc, artifact) -> SegmentPass:
    """Write the rows and set the marker, WITHOUT the conversion action."""
    pass_row, rows = rows_from_reads(*segments_from_result(
        document_id=doc.id,
        artifact_id=artifact.id,
        result=artifact.ocr_geometry,
        provider=artifact.provider,
        model=artifact.model,
        run_id=artifact.run_id,
        created_at=artifact.created_at,
        artifact_type=artifact.artifact_type,
    ))
    db.save(pass_row)
    for row in rows:
        db.save(row)
    artifact.geometry_superseded_by_pass_id = pass_row.id
    db.save(artifact)
    return pass_row


class TestWhichStoreAnArtifactReadsFrom:
    def test_an_artifact_is_unconverted_until_its_marker_is_set(self, db):
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        assert is_converted(artifact) is False
        assert live_geometry(db, artifact) is artifact.ocr_geometry

    def test_a_pass_that_merely_names_the_artifact_does_not_convert_it(self, db):
        """Any caller can make such a pass by hand through
        `POST /api/segments/passes`, so it cannot be what "converted" means."""
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        db.save(SegmentPass(
            document_id=doc.id, name="by hand",
            provenance_kind=ProvenanceKind.human, source_artifact_id=artifact.id,
        ))
        assert is_converted(artifact) is False
        assert live_geometry(db, artifact) == artifact.ocr_geometry

    def test_a_marker_with_no_pass_behind_it_raises(self, db):
        """NEVER a fall back to the frozen block: that would silently undo a
        person's edits on screen and look fine doing it."""
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        artifact.geometry_superseded_by_pass_id = "no-such-pass"
        db.save(artifact)
        with pytest.raises(ConversionMarkerDangling):
            live_geometry(db, artifact)

    def test_a_marker_naming_a_deleted_pass_raises(self, db):
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        pass_row = _convert_by_hand(db, doc, artifact)
        from fichero_server.core.timeutil import utc_now

        pass_row.deleted_at = utc_now()
        db.save(pass_row)
        with pytest.raises(ConversionMarkerDangling):
            live_geometry(db, artifact)


class TestTheProjectionLooksLikeTheBlockItReplaced:
    def test_a_converted_page_projects_the_same_boxes_in_the_same_order(self, db):
        doc = _make_doc(db)
        block = _block(count=4)
        artifact = _artifact(db, doc, block)
        _convert_by_hand(db, doc, artifact)

        projected = live_geometry(db, artifact)
        assert [b.bbox for b in projected.boxes] == [b.bbox for b in block.boxes]
        assert [b.text for b in projected.boxes] == ["w0", "w1", "w2", "w3"]
        assert [b.level for b in projected.boxes] == [b.level for b in block.boxes]

    def test_everything_about_the_result_rather_than_one_box_is_kept(self, db):
        """The result's own text is what every box's char span indexes into;
        the rendition says WHICH picture the boxes were measured on; the
        curation log is the history that travels with the artifact."""
        doc = _make_doc(db)
        block = _block(count=3, rendition_id="rend-crop-1")
        artifact = _artifact(db, doc, block)
        _convert_by_hand(db, doc, artifact)

        projected = live_geometry(db, artifact)
        assert projected.text == block.text
        assert projected.rendition_id == "rend-crop-1"
        assert projected.provider == block.provider
        assert projected.model == block.model
        assert projected.metadata == block.metadata

    def test_the_stored_block_is_never_touched_by_reading_the_projection(self, db):
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        before = artifact.ocr_geometry.model_dump(mode="json")
        _convert_by_hand(db, doc, artifact)
        live_geometry(db, artifact)
        reread = db.get(Artifact, artifact.id)
        assert reread.ocr_geometry.model_dump(mode="json") == before


class TestAnEditMovesWhatEveryReaderSees:
    def test_moving_a_row_moves_the_box_the_app_is_given(self, db):
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        pass_row = _convert_by_hand(db, doc, artifact)

        rows = live_rows_in_order(db, pass_row.id)
        moved = rows[1]
        moved.anchor = moved.anchor.model_copy(update={"rect": [0.6, 0.6, 0.1, 0.1]})
        db.save(moved)

        projected = live_geometry(db, artifact)
        assert projected.boxes[1].bbox == [0.6, 0.6, 0.1, 0.1]
        assert projected.boxes[1].text == "w1", "a move must not cost a box its words"
        # And the others did not move.
        assert projected.boxes[0].bbox == artifact.ocr_geometry.boxes[0].bbox

    def test_deleting_a_row_shifts_the_positions_after_it_exactly_as_today(self, db):
        """The old app addresses a box by position; after a delete its
        positions shift, and the projection must shift with them."""
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        pass_row = _convert_by_hand(db, doc, artifact)
        from fichero_server.core.timeutil import utc_now

        rows = live_rows_in_order(db, pass_row.id)
        rows[1].deleted_at = utc_now()
        db.save(rows[1])

        projected = live_geometry(db, artifact)
        assert [b.text for b in projected.boxes] == ["w0", "w2", "w3"]
        assert live_box_count(db, artifact) == 3

    def test_a_row_added_after_conversion_lands_at_the_end_as_an_add_does(self, db):
        """`_edit_regions_impl`'s ADD appends. A row with no stored
        `box_index` sorts after every converted one, which is the same
        place -- so the app's positions do not move under it."""
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        pass_row = _convert_by_hand(db, doc, artifact)

        from fichero_server.models.segments import bbox_and_tile_from_anchor
        from fichero_server.models.anchors import SourceAnchor

        anchor = SourceAnchor(document_id=doc.id, rect=[0.8, 0.8, 0.1, 0.1])
        x, y, w, h, tile = bbox_and_tile_from_anchor(anchor)
        db.save(Segment(
            document_id=doc.id, pass_id=pass_row.id, kind="region", anchor=anchor,
            bbox_x=x, bbox_y=y, bbox_w=w, bbox_h=h, tile=tile,
            doc_kind=f"{doc.id}:region", provenance_kind=ProvenanceKind.human,
            created_by="someone",
        ))

        projected = live_geometry(db, artifact)
        assert len(projected.boxes) == 5
        assert projected.boxes[4].bbox == [0.8, 0.8, 0.1, 0.1]
        assert [b.text for b in projected.boxes[:4]] == ["w0", "w1", "w2", "w3"]

    def test_a_box_drawn_after_conversion_is_honestly_a_persons(self, db):
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        pass_row = _convert_by_hand(db, doc, artifact)
        from fichero_server.models.anchors import SourceAnchor
        from fichero_server.models.segments import bbox_and_tile_from_anchor

        anchor = SourceAnchor(document_id=doc.id, rect=[0.8, 0.8, 0.1, 0.1])
        x, y, w, h, tile = bbox_and_tile_from_anchor(anchor)
        db.save(Segment(
            document_id=doc.id, pass_id=pass_row.id, kind="region", anchor=anchor,
            bbox_x=x, bbox_y=y, bbox_w=w, bbox_h=h, tile=tile,
            doc_kind=f"{doc.id}:region", provenance_kind=ProvenanceKind.human,
        ))
        drawn = live_geometry(db, artifact).boxes[4]
        assert drawn.provider == "user" and drawn.source == "manual"
        assert drawn.text == ""


class TestTheCountAndTheFrameAreLiveToo:
    def test_the_count_follows_a_delete(self, db):
        """`region_count` rides on LIST responses where the geometry does
        not, so a page whose owner deleted three boxes must not keep
        reporting twenty in the library list."""
        doc = _make_doc(db)
        artifact = _artifact(db, doc, _block(count=6))
        pass_row = _convert_by_hand(db, doc, artifact)
        assert live_box_count(db, artifact) == 6
        from fichero_server.core.timeutil import utc_now

        for row in live_rows_in_order(db, pass_row.id)[:2]:
            row.deleted_at = utc_now()
            db.save(row)
        assert live_box_count(db, artifact) == 4

    def test_counting_an_unconverted_artifact_asks_the_database_nothing(self, db):
        """Every artifact is unconverted until its page's first edit, so the
        common path must not pay for a query."""
        doc = _make_doc(db)
        artifact = _artifact(db, doc, _block(count=6))

        class Exploding:
            def query(self, *a, **k):
                raise AssertionError("an unconverted artifact must not be queried")

            def get(self, *a, **k):
                raise AssertionError("an unconverted artifact must not be queried")

        assert live_box_count(Exploding(), artifact) == 6
        assert live_geometry(Exploding(), artifact) is artifact.ocr_geometry

    def test_an_artifact_with_no_geometry_at_all_still_answers(self, db):
        doc = _make_doc(db)
        bare = Artifact(document_id=doc.id, artifact_type="summary")
        db.save(bare)
        assert live_geometry(db, bare) is None
        assert live_box_count(db, bare) == 0


class TestAwkwardRows:
    def test_an_undrawable_row_still_holds_its_position(self, db):
        """If it vanished, every later box would shift up one -- silently
        moving somebody's regions."""
        doc = _make_doc(db)
        block = OCRGeometryResult(
            provider="qwen",
            boxes=[
                OCRGeometryBox(text="a", bbox=[0.1, 0.1, 0.2, 0.05]),
                OCRGeometryBox(text="", bbox=[0.5, 0.5, 0.0, 0.0]),
                OCRGeometryBox(text="c", bbox=[0.1, 0.3, 0.2, 0.05]),
            ],
        )
        artifact = _artifact(db, doc, block)
        _convert_by_hand(db, doc, artifact)
        projected = live_geometry(db, artifact)
        assert len(projected.boxes) == 3
        assert projected.boxes[1].bbox == [0.0, 0.0, 0.0, 0.0]
        assert [b.text for b in projected.boxes] == ["a", "", "c"]

    def test_a_row_whose_source_box_is_out_of_range_degrades_to_an_empty_box(self, db):
        """Defensive: the row's shape is still right, it just has no words
        to show. Never an exception on a page read.

        Note the second assertion. `metadata["box_index"]` is BOTH the sort
        key and the pointer at the words, so a corrupt one moves the row as
        well as blanking it -- 999 sorts it last. Worth pinning, because it
        says the two uses cannot be separated without a second stored field."""
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        pass_row = _convert_by_hand(db, doc, artifact)
        rows = live_rows_in_order(db, pass_row.id)
        was_second = rows[1]
        was_second.metadata = {"box_index": 999}
        db.save(was_second)

        projected = live_geometry(db, artifact)
        assert len(projected.boxes) == 4
        assert projected.boxes[3].text == "", "no box to read words from"
        assert projected.boxes[3].bbox == was_second.anchor.rect, "shape still right"
        assert [b.text for b in projected.boxes[:3]] == ["w0", "w2", "w3"]

    def test_a_pass_with_no_live_rows_projects_an_empty_box_list(self, db):
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        pass_row = _convert_by_hand(db, doc, artifact)
        from fichero_server.core.timeutil import utc_now

        for row in live_rows_in_order(db, pass_row.id):
            row.deleted_at = utc_now()
            db.save(row)
        projected = live_geometry(db, artifact)
        assert projected.boxes == []
        assert projected.text == artifact.ocr_geometry.text

    def test_geometry_from_rows_needs_no_block_at_all(self, db):
        """An artifact can be hard-deleted out from under its rows."""
        result = geometry_from_rows(None, [])
        assert result.boxes == [] and result.provider == "user"
