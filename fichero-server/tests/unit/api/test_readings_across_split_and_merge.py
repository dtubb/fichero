"""Source-model slice 8, part 6 (#4934, #4932) -- what a split and a merge do
to readings, and the lasting reference in the anchor.

Spec: `build-notes-readings-cascade-orders.md`, "Slice 8" -- the section that
opens **"Owed by this slice to the text editor (13b), so it is not
retrofitted"**, plus "Corrected 2026-09-20: ... The lasting segment id lives in
the anchor, `SourceAnchor.segment_id`, one shape for readings, marks, supports
and claims; it is built HERE, under #4932".

Behaviours pinned:
* Split: each part may name the stretch of the reading it takes; with none
  given the reading stays on the kept part and the new parts have none.
* Merge: the kept segment's reading becomes the members' readings joined in
  reading order, as a NEW reading whose maker is the person who merged; the
  members' readings stay on their soft-deleted segments and come back with an
  unmerge.
* Undo of either puts the readings back exactly.
* `source.builds-on-the-anchor` / `source.point.by-id-or-span` -- an anchor may
  NAME its segment, `resolve_anchor` honours that over matching rectangles, and
  a provisional id can never be stored as one.

All through the real actions and the real undo path.
"""

from __future__ import annotations

import pytest

from fichero_server.actions.registry import ActionContext, registry
from fichero_server.api.routes.document.segment_conversion import (
    converted_pass_id,
    live_rows_in_order,
    resolve_anchor,
)
from fichero_server.api.routes.document.segment_readings import readings_of_segment
from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryResult
from fichero_server.models import (
    Artifact,
    ContentRepresentation,
    DocType,
    Document,
    FileType,
    Segment,
    Status,
)
from fichero_server.models.anchors import SourceAnchor
from fichero_server.models.knowledge import ProvenanceKind
from fichero_server.models.segments import AnchorBasis

pytestmark = pytest.mark.source_model

LINES = ["en el nombre", "de dios amen"]
PAGE_TEXT = " ".join(LINES)


def _make_doc(db) -> Document:
    doc = Document(
        name="folio.jpg", doc_type=DocType.file, file_type=FileType.image,
        path="/path/folio.jpg", status=Status.completed,
    )
    db.save(doc)
    return doc


def _artifact(db, doc) -> Artifact:
    boxes = []
    for index, line in enumerate(LINES):
        start = PAGE_TEXT.index(line)
        boxes.append(
            OCRGeometryBox(
                text=line, bbox=[0.1, 0.1 + index * 0.3, 0.6, 0.08], level="line",
                char_start=start, char_end=start + len(line),
            )
        )
    artifact = Artifact(
        document_id=doc.id, artifact_type="transcription", provider="qwen", model="qwen-vl",
        content=PAGE_TEXT,
        ocr_geometry=OCRGeometryResult(provider="qwen", text=PAGE_TEXT, boxes=boxes),
    )
    db.save(artifact)
    return artifact


def _convert(client, artifact_id: str) -> None:
    response = client.put(
        f"/api/artifacts/{artifact_id}/regions",
        json={"op": "move", "indices": [0], "bbox": [0.11, 0.1, 0.6, 0.08]},
    )
    assert response.status_code == 200, response.text


def _person(actor: str = "historian") -> ActionContext:
    return ActionContext(actor=actor, library_path=None, is_bootstrap=True)


def _page(db, client):
    doc = _make_doc(db)
    artifact = _artifact(db, doc)
    _convert(client, artifact.id)
    return doc, artifact, live_rows_in_order(db, converted_pass_id(artifact.id))


def _write_reading(db, segment, content: str, *, kind: str = "transcription"):
    return registry.invoke(
        db,
        "representation.create",
        {
            "document_id": segment.document_id, "segment_id": segment.id,
            "kind": kind, "content": content,
        },
        _person(),
    ).result["id"]


def _real_contents(db, segment_id: str, *, kind: str = "transcription") -> list[str]:
    """The RECORDED readings of one kind that still count on this segment.

    Provisional ones are filtered out on purpose. A split part inherits its
    source box's `metadata["box_index"]` (slice 6, for read order), so the seam
    legitimately offers the machine's whole-line text as a provisional reading
    on BOTH parts -- the machine did say that about the box each part came
    from, and it is labelled provisional and machine-made. What these tests are
    about is the records, so they name them.
    """
    return [
        item.content
        for item in readings_of_segment(db, segment_id)
        if item.kind == kind and not item.retracted and not item.provisional
    ]


class TestSplittingALineWithAReading:
    def test_with_no_span_given_the_reading_stays_on_the_kept_part(self, db, client):
        """Splitting a box is a statement about geometry. Guessing where to cut
        somebody's transcription is not the engine's business."""
        doc, artifact, rows = _page(db, client)
        original = rows[0]
        reading_id = _write_reading(db, original, "en el nombre")

        result = registry.invoke(
            db, "segment.split",
            {
                "segment_id": original.id,
                "expected_version": db.get(Segment, original.id).version,
                "parts": [
                    {"anchor": {"document_id": doc.id, "rect": [0.1, 0.1, 0.3, 0.08]}},
                    {"anchor": {"document_id": doc.id, "rect": [0.4, 0.1, 0.3, 0.08]}},
                ],
            },
            _person(),
        )

        assert result.result["representation_ids"] == []
        kept = db.get(ContentRepresentation, reading_id)
        assert kept.segment_id == original.id
        assert kept.content == "en el nombre"
        new_part = result.result["new_segment_ids"][0]
        assert db.query(ContentRepresentation, segment_id=new_part) == []

    def test_each_part_may_name_the_stretch_it_takes(self, db, client):
        doc, artifact, rows = _page(db, client)
        original = rows[0]
        source_id = _write_reading(db, original, "en el nombre")

        result = registry.invoke(
            db, "segment.split",
            {
                "segment_id": original.id,
                "expected_version": db.get(Segment, original.id).version,
                "parts": [
                    {
                        "anchor": {"document_id": doc.id, "rect": [0.1, 0.1, 0.3, 0.08]},
                        "reading_span": [0, 5],
                    },
                    {
                        "anchor": {"document_id": doc.id, "rect": [0.4, 0.1, 0.3, 0.08]},
                        "reading_span": [6, 12],
                    },
                ],
            },
            _person(),
        )

        assert len(result.result["representation_ids"]) == 2
        new_part = result.result["new_segment_ids"][0]
        assert "en el" in _real_contents(db, original.id)
        assert _real_contents(db, new_part) == ["nombre"]
        # The machine's whole-line text is still offered on the new part, as a
        # PROVISIONAL reading -- labelled, and not what counts.
        provisional = [
            item for item in readings_of_segment(db, new_part) if item.provisional
        ]
        assert [item.content for item in provisional] == ["en el nombre"]
        assert all(item.provenance_kind is ProvenanceKind.workflow for item in provisional)
        # A derived reading names what it came from, and the original is
        # untouched -- the same rule a correction follows.
        derived = [db.get(ContentRepresentation, rid) for rid in result.result["representation_ids"]]
        assert all(row.derived_from_representation_id == source_id for row in derived)
        assert db.get(ContentRepresentation, source_id).content == "en el nombre"

    def test_the_person_who_split_is_the_maker_of_the_parts_readings(self, db, client):
        doc, artifact, rows = _page(db, client)
        original = rows[0]
        _write_reading(db, original, "en el nombre")

        result = registry.invoke(
            db, "segment.split",
            {
                "segment_id": original.id,
                "expected_version": db.get(Segment, original.id).version,
                "parts": [
                    {
                        "anchor": {"document_id": doc.id, "rect": [0.1, 0.1, 0.3, 0.08]},
                        "reading_span": [0, 5],
                    },
                    {
                        "anchor": {"document_id": doc.id, "rect": [0.4, 0.1, 0.3, 0.08]},
                        "reading_span": [6, 12],
                    },
                ],
            },
            ActionContext(actor="runner", run_id="run-1", is_bootstrap=True),
        )

        for rid in result.result["representation_ids"]:
            assert db.get(ContentRepresentation, rid).provenance_kind is ProvenanceKind.workflow

    def test_an_anchor_on_a_derived_reading_names_its_part(self, db, client):
        doc, artifact, rows = _page(db, client)
        original = rows[0]
        _write_reading(db, original, "en el nombre")

        result = registry.invoke(
            db, "segment.split",
            {
                "segment_id": original.id,
                "expected_version": db.get(Segment, original.id).version,
                "parts": [
                    {"anchor": {"document_id": doc.id, "rect": [0.1, 0.1, 0.3, 0.08]}},
                    {
                        "anchor": {"document_id": doc.id, "rect": [0.4, 0.1, 0.3, 0.08]},
                        "reading_span": [6, 12],
                    },
                ],
            },
            _person(),
        )

        new_part = result.result["new_segment_ids"][0]
        derived = db.get(ContentRepresentation, result.result["representation_ids"][0])
        assert derived.segment_id == new_part
        # The LASTING reference, not a rectangle: the part can move and this
        # still points at it.
        assert derived.source_anchor.segment_id == new_part

    def test_a_malformed_span_is_refused_not_clamped(self, db, client):
        doc, artifact, rows = _page(db, client)
        original = rows[0]
        _write_reading(db, original, "en el nombre")

        for bad in ([5, 5], [8, 3], [-1, 4], [3]):
            with pytest.raises(Exception) as excinfo:
                registry.invoke(
                    db, "segment.split",
                    {
                        "segment_id": original.id,
                        "expected_version": db.get(Segment, original.id).version,
                        "parts": [
                            {
                                "anchor": {"document_id": doc.id, "rect": [0.1, 0.1, 0.3, 0.08]},
                                "reading_span": bad,
                            },
                            {"anchor": {"document_id": doc.id, "rect": [0.4, 0.1, 0.3, 0.08]}},
                        ],
                    },
                    _person(),
                )
            assert "reading_span" in str(excinfo.value) or "validation" in str(excinfo.value).lower()

    def test_undoing_the_split_retracts_exactly_what_it_added(self, db, client):
        doc, artifact, rows = _page(db, client)
        original = rows[0]
        source_id = _write_reading(db, original, "en el nombre")

        split = registry.invoke(
            db, "segment.split",
            {
                "segment_id": original.id,
                "expected_version": db.get(Segment, original.id).version,
                "parts": [
                    {
                        "anchor": {"document_id": doc.id, "rect": [0.1, 0.1, 0.3, 0.08]},
                        "reading_span": [0, 5],
                    },
                    {
                        "anchor": {"document_id": doc.id, "rect": [0.4, 0.1, 0.3, 0.08]},
                        "reading_span": [6, 12],
                    },
                ],
            },
            _person(),
        )
        added = split.result["representation_ids"]

        response = client.post(f"/api/actions/audit/{split.audit_id}/undo")
        assert response.status_code == 200, response.text

        for rid in added:
            row = db.get(ContentRepresentation, rid)
            assert row is not None, "a retraction keeps the row"
            assert row.retracted_at is not None
        # And the reading the split did NOT add is exactly as it was.
        #
        # Asserted BY ID, not by comparing a list of contents. Since slice 8b
        # conversion writes its own reading of the same line, so this segment has
        # two recorded readings with IDENTICAL words — a content list cannot tell
        # them apart, and a test that compared one would pass or fail for reasons
        # that have nothing to do with the undo.
        source = db.get(ContentRepresentation, source_id)
        assert source.retracted_at is None
        assert source.content == "en el nombre"
        live = {
            row.id
            for row in db.query(ContentRepresentation, segment_id=original.id)
            if row.retracted_at is None
        }
        assert source_id in live
        assert not (set(added) & live), "a retracted reading is still counting"


class TestMergingTwoLinesWithReadings:
    def test_the_kept_segments_reading_is_the_members_joined_in_reading_order(
        self, db, client
    ):
        doc, artifact, rows = _page(db, client)
        _write_reading(db, rows[0], "en el nombre")
        _write_reading(db, rows[1], "de dios amen")

        result = registry.invoke(
            db, "segment.merge",
            {
                "segment_ids": [rows[0].id, rows[1].id],
                "keep_id": rows[0].id,
                "expected_versions": {
                    rows[0].id: db.get(Segment, rows[0].id).version,
                    rows[1].id: db.get(Segment, rows[1].id).version,
                },
            },
            _person(),
        )

        assert len(result.result["representation_ids"]) == 1
        joined = db.get(ContentRepresentation, result.result["representation_ids"][0])
        assert joined.content == "en el nombre de dios amen"
        assert joined.segment_id == rows[0].id

    def test_the_maker_is_the_person_who_merged_not_either_reader(self, db, client):
        """Joining two people's transcriptions is a judgement somebody made,
        not something either of them wrote."""
        doc, artifact, rows = _page(db, client)
        _write_reading(db, rows[0], "en el nombre")
        _write_reading(db, rows[1], "de dios amen")

        result = registry.invoke(
            db, "segment.merge",
            {
                "segment_ids": [rows[0].id, rows[1].id],
                "keep_id": rows[0].id,
                "expected_versions": {
                    rows[0].id: db.get(Segment, rows[0].id).version,
                    rows[1].id: db.get(Segment, rows[1].id).version,
                },
            },
            ActionContext(actor="merger", via_mcp=True, is_bootstrap=True),
        )

        joined = db.get(ContentRepresentation, result.result["representation_ids"][0])
        assert joined.provenance_kind is ProvenanceKind.agent

    def test_the_members_readings_stay_on_their_soft_deleted_segments(self, db, client):
        doc, artifact, rows = _page(db, client)
        _write_reading(db, rows[0], "en el nombre")
        absorbed_reading = _write_reading(db, rows[1], "de dios amen")

        registry.invoke(
            db, "segment.merge",
            {
                "segment_ids": [rows[0].id, rows[1].id],
                "keep_id": rows[0].id,
                "expected_versions": {
                    rows[0].id: db.get(Segment, rows[0].id).version,
                    rows[1].id: db.get(Segment, rows[1].id).version,
                },
            },
            _person(),
        )

        assert db.get(Segment, rows[1].id).deleted_at is not None
        still_there = db.get(ContentRepresentation, absorbed_reading)
        assert still_there.segment_id == rows[1].id
        assert still_there.retracted_at is None
        assert still_there.content == "de dios amen"

    def test_undoing_the_merge_retracts_the_join_and_brings_the_members_back(
        self, db, client
    ):
        doc, artifact, rows = _page(db, client)
        _write_reading(db, rows[0], "en el nombre")
        absorbed_reading = _write_reading(db, rows[1], "de dios amen")

        merge = registry.invoke(
            db, "segment.merge",
            {
                "segment_ids": [rows[0].id, rows[1].id],
                "keep_id": rows[0].id,
                "expected_versions": {
                    rows[0].id: db.get(Segment, rows[0].id).version,
                    rows[1].id: db.get(Segment, rows[1].id).version,
                },
            },
            _person(),
        )
        joined_id = merge.result["representation_ids"][0]

        response = client.post(f"/api/actions/audit/{merge.audit_id}/undo")
        assert response.status_code == 200, response.text

        assert db.get(ContentRepresentation, joined_id).retracted_at is not None
        assert db.get(Segment, rows[1].id).deleted_at is None
        # "Comes back with an unmerge": nothing had to be restored, because the
        # reading never left the segment. Asserted by ID for the same reason as
        # the split's undo — conversion's own reading of this line has the same
        # words as the person's.
        restored = db.get(ContentRepresentation, absorbed_reading)
        assert restored.retracted_at is None
        assert restored.segment_id == rows[1].id
        assert restored.content == "de dios amen"

    def test_a_kind_only_one_member_had_is_not_joined_with_itself(self, db, client):
        doc, artifact, rows = _page(db, client)
        _write_reading(db, rows[0], "en el nombre")
        _write_reading(db, rows[1], "de dios amen")
        _write_reading(db, rows[0], "in the name", kind="translation")

        result = registry.invoke(
            db, "segment.merge",
            {
                "segment_ids": [rows[0].id, rows[1].id],
                "keep_id": rows[0].id,
                "expected_versions": {
                    rows[0].id: db.get(Segment, rows[0].id).version,
                    rows[1].id: db.get(Segment, rows[1].id).version,
                },
            },
            _person(),
        )

        joined = [db.get(ContentRepresentation, rid) for rid in result.result["representation_ids"]]
        assert [row.kind for row in joined] == ["transcription"]
        assert _real_contents(db, rows[0].id, kind="translation") == ["in the name"]


class TestTheAnchorCanNameWhatItPointsAt:
    """`source.builds-on-the-anchor` / `source.point.by-id-or-span` (#4932)."""

    def test_a_named_segment_is_followed_without_matching_a_rectangle(self, db, client):
        doc, artifact, rows = _page(db, client)
        line = rows[1]
        # An anchor with a DELIBERATELY WRONG rectangle. The name wins, which
        # is the whole point: a recorded fact beats a recovered one.
        anchor = SourceAnchor(
            document_id=doc.id, rect=[0.9, 0.9, 0.05, 0.02], segment_id=line.id
        )

        resolved = resolve_anchor(db, anchor)

        assert resolved.basis is AnchorBasis.segment_named
        assert resolved.segment_id == line.id
        assert resolved.anchor.rect == db.get(Segment, line.id).anchor.rect

    def test_a_named_segment_that_moved_is_followed_to_where_it_is_now(self, db, client):
        doc, artifact, rows = _page(db, client)
        line = rows[1]
        anchor = SourceAnchor(document_id=doc.id, segment_id=line.id)

        registry.invoke(
            db, "segment.update",
            {
                "segment_id": line.id,
                "expected_version": db.get(Segment, line.id).version,
                "anchor": {"document_id": doc.id, "rect": [0.5, 0.5, 0.2, 0.05]},
            },
            _person(),
        )

        resolved = resolve_anchor(db, anchor)
        assert resolved.anchor.rect == [0.5, 0.5, 0.2, 0.05]
        assert resolved.basis is AnchorBasis.segment_named

    def test_a_named_segment_that_was_deleted_is_reported_gone(self, db, client):
        doc, artifact, rows = _page(db, client)
        line = rows[1]
        anchor = SourceAnchor(document_id=doc.id, segment_id=line.id)

        registry.invoke(
            db, "segment.delete",
            {
                "segment_ids": [line.id],
                "expected_versions": {line.id: db.get(Segment, line.id).version},
            },
            _person(),
        )

        resolved = resolve_anchor(db, anchor)
        assert resolved.basis is AnchorBasis.segment_deleted
        assert resolved.segment_id == line.id

    def test_a_named_segment_that_is_not_there_is_not_downgraded_to_a_guess(
        self, db, client
    ):
        """The pointer was EXPLICIT. Being unable to follow it is a fact the
        caller must see, not something to paper over with a rectangle match
        that would land on a different line."""
        doc, artifact, rows = _page(db, client)
        anchor = SourceAnchor(
            document_id=doc.id,
            rect=list(rows[0].anchor.rect),
            segment_id="no-such-segment",
        )

        resolved = resolve_anchor(db, anchor)

        assert resolved.basis is AnchorBasis.stored
        assert resolved.segment_id is None

    def test_an_anchor_with_no_name_still_recovers_by_rectangle(self, db, client):
        """Every anchor written before this slice has no name, and must keep
        resolving exactly as it did."""
        doc, artifact, rows = _page(db, client)
        anchor = SourceAnchor(document_id=doc.id, rect=list(rows[1].anchor.rect))

        resolved = resolve_anchor(db, anchor)

        assert resolved.basis is AnchorBasis.segment
        assert resolved.segment_id == rows[1].id

    def test_all_four_carriers_gain_the_lasting_id_with_no_new_column(self):
        """`source.point.anchor-names-its-segment`: "One shape for all four, no
        new column on any of them; an old record reads as having none."

        This is the load-bearing half of that behaviour and the reason the field
        went on `SourceAnchor` rather than on each record. A reading, a mark, a
        claim and a supporting source all carry the SAME anchor type, so one
        field gave all four the lasting id — and if anyone ever "helpfully" gives
        one of them its own `segment_id` column, this test is what notices.
        """
        from fichero_server.models.knowledge import (
            Annotation,
            KnowledgeClaim,
            SourceSupport,
        )

        carriers = {
            ContentRepresentation: "source_anchor",
            Annotation: "anchor",
            KnowledgeClaim: "source_anchor",
            SourceSupport: "source_anchor",
        }
        for model, field in carriers.items():
            annotation = str(model.model_fields[field].annotation)
            assert "SourceAnchor" in annotation, f"{model.__name__} lost the shared anchor"

        # "No new column on any of them" is about POINTING. Two of the four have
        # a segment-id column for a DIFFERENT and documented reason, and running
        # a blanket version of this assertion is what surfaced the distinction:
        #
        # * `ContentRepresentation.segment_id` is OWNERSHIP — "the segment it
        #   reads", required by slice 8's own field table, indexed, and queried
        #   once per line by `document_text`. A reading of a LINE may still carry
        #   an anchor pointing at a WORD inside it, so the two are not redundant:
        #   the column says which segment this is a reading OF, the anchor says
        #   what its span points AT.
        # * `KnowledgeClaim.source_segment_id` predates this model and names an
        #   entry in a segmentation artifact. `source.statement.
        #   old-segment-field-left-alone` says it keeps its meaning and must
        #   NEVER be given a segment record's id — so its existence is mandated,
        #   not an oversight.
        #
        # The two that had none must still have none: that is where a second
        # answer to "which segment" would actually be created.
        for model in (Annotation, SourceSupport):
            assert not [n for n in model.model_fields if "segment_id" in n], (
                f"{model.__name__} grew its own segment id — it should take the "
                "lasting id from the shared anchor, which is the whole point of "
                "putting it there"
            )

        # And an anchor written before this slice reads as having none, rather
        # than being given one.
        old_anchor = SourceAnchor(document_id="doc-1", rect=[0.1, 0.1, 0.2, 0.05])
        assert old_anchor.segment_id is None
        assert old_anchor.representation_id is None

    def test_a_provisional_id_can_never_be_stored_as_a_lasting_reference(self):
        for field, value in (
            ("segment_id", "legacy:art-1:3"),
            ("representation_id", "legacy-reading:art-1"),
        ):
            with pytest.raises(ValueError) as excinfo:
                SourceAnchor(document_id="doc-1", **{field: value})
            assert "provisional" in str(excinfo.value)

    def test_a_stretch_names_the_exact_reading_it_was_measured_on(self, db, client):
        doc, artifact, rows = _page(db, client)
        line = rows[0]
        reading_id = _write_reading(db, line, "en el nombre")

        pointer = SourceAnchor(
            document_id=doc.id,
            segment_id=line.id,
            representation_id=reading_id,
            char_start=6,
            char_end=12,
        )

        assert pointer.representation_id == reading_id
        text = db.get(ContentRepresentation, reading_id).content
        assert text[pointer.char_start : pointer.char_end] == "nombre"
