"""Slice 6 (#4924) -- the pure half of first-edit conversion.

Pins the BEHAVIOURS, not the code:

* `source.store.conversion-changes-nothing-seen` -- the master test, in its
  pure form: reads in, rows out, reads back, equal but for `id`, `pass_id`
  and `provisional`.
* `source.store.conversion-ids-repeatable` -- name-based ids, so a lazy
  conversion and an eager one agree, and redo lands on the same row.
* `source.store.converted-boxes-keep-their-maker` -- a machine's box is
  never stored as a person's, and a hand-drawn box keeps its drawer.
* `source.one-store` -- a converted row's words and page still read back.

Nothing here touches a database or a library: `rows_from_reads` is pure, and
that is the point -- the expensive, race-prone half is tested separately.
"""

from __future__ import annotations

import uuid

import pytest

from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryResult
from fichero_server.models import Artifact
from fichero_server.models.knowledge import ProvenanceKind
from fichero_server.models.segments import (
    SEGMENT_CONVERSION_NAMESPACE,
    BoxIndexesNotContiguous,
    converted_pass_id,
    converted_segment_id,
    legacy_pass_id,
    legacy_segment_id,
    pass_read_from_row,
    real_id_for_provisional,
    rows_from_reads,
    segment_read_from_row,
    segments_from_result,
)

DOC_ID = "doc-marshall-1"
ARTIFACT_ID = "artifact-transcription-1"


def machine_block() -> OCRGeometryResult:
    """A machine result with the awkward boxes on purpose: a hand-drawn box
    a person added into it, a box on a second PDF page, a box whose shape the
    anchor cannot hold, and char spans that index into the result's own text."""
    return OCRGeometryResult(
        provider="qwen",
        model="qwen-vl-max",
        text="Primero. Segundo. Tercero. Cuarto.",
        rendition_id=None,
        boxes=[
            OCRGeometryBox(
                text="Primero.",
                bbox=[0.1, 0.1, 0.2, 0.05],
                level="line",
                confidence=0.9,
                char_start=0,
                char_end=8,
                page_index=0,
            ),
            OCRGeometryBox(
                text="Segundo.",
                bbox=[0.1, 0.2, 0.2, 0.05],
                level="line",
                char_start=9,
                char_end=17,
                page_index=0,
            ),
            # A person drew this one into the machine's result.
            OCRGeometryBox(
                text="Tercero.",
                bbox=[0.1, 0.3, 0.2, 0.05],
                level="region",
                page_index=0,
                provider="user",
                source="manual",
            ),
            # Second page of a multi-page PDF.
            OCRGeometryBox(
                text="Cuarto.",
                bbox=[0.1, 0.4, 0.2, 0.05],
                level="line",
                char_start=26,
                char_end=33,
                page_index=1,
            ),
            # Undrawable: a zero-size box the anchor cannot hold as a rect.
            OCRGeometryBox(
                text="",
                bbox=[0.5, 0.5, 0.0, 0.0],
                level="word",
                page_index=1,
            ),
        ],
    )


def reads_for(block: OCRGeometryResult):
    return segments_from_result(
        document_id=DOC_ID,
        artifact_id=ARTIFACT_ID,
        result=block,
        provider=block.provider,
        model=block.model,
        run_id="run-7",
        created_at=None,
        artifact_type="transcription",
    )


class TestTheNamespaceAndTheIds:
    def test_the_conversion_namespace_never_changes(self):
        """Changing it would silently re-identify every converted box in
        every library, so both the value AND its derivation are pinned."""
        assert str(SEGMENT_CONVERSION_NAMESPACE) == "6fd743f7-2111-514c-89f6-dfd308363dd5"
        assert SEGMENT_CONVERSION_NAMESPACE == uuid.uuid5(
            uuid.NAMESPACE_DNS, "segments.conversion.fichero"
        )

    def test_the_same_box_gets_the_same_id_every_time(self):
        """`source.store.conversion-ids-repeatable`: this is what makes a
        lazy conversion and an eager one produce identical rows."""
        assert converted_segment_id(ARTIFACT_ID, 3) == converted_segment_id(ARTIFACT_ID, 3)
        assert converted_pass_id(ARTIFACT_ID) == converted_pass_id(ARTIFACT_ID)

    def test_an_id_is_never_given_to_another_segment(self):
        seen = {converted_segment_id(ARTIFACT_ID, i) for i in range(50)}
        assert len(seen) == 50
        seen.add(converted_pass_id(ARTIFACT_ID))
        assert len(seen) == 51, "a pass and box 0 of the same artifact collided"
        assert converted_segment_id("other-artifact", 0) not in seen

    def test_an_id_is_a_bare_hex_like_every_other_id(self):
        """Ids are compared against `_new_id()` ids all over the app; a
        dashed UUID string would be a different shape."""
        made = converted_segment_id(ARTIFACT_ID, 0)
        assert len(made) == 32 and "-" not in made
        assert int(made, 16) >= 0


class TestProvisionalIdsMapToRealOnes:
    def test_a_provisional_segment_id_maps_to_the_id_conversion_gives_it(self):
        provisional = legacy_segment_id(ARTIFACT_ID, 4)
        assert real_id_for_provisional(provisional) == converted_segment_id(ARTIFACT_ID, 4)

    def test_a_provisional_pass_id_maps_to_the_id_conversion_gives_it(self):
        assert real_id_for_provisional(legacy_pass_id(ARTIFACT_ID)) == converted_pass_id(
            ARTIFACT_ID
        )

    def test_every_box_of_a_real_page_round_trips(self):
        """The mapping and the minting must agree for every box, not just
        one -- they are written in two different functions."""
        block = machine_block()
        _, reads = reads_for(block)
        _, rows = rows_from_reads(*reads_for(block))
        for read, row in zip(reads, rows, strict=True):
            assert real_id_for_provisional(read.id) == row.id

    @pytest.mark.parametrize(
        "not_ours",
        [
            "",
            "abc",
            "artifact-1:2",  # no prefix
            "legacy:",  # nothing after the prefix
            "legacy:a:-1",  # negative
            "legacy:a:007",  # not the plain decimal `legacy_segment_id` renders
            "legacy:a: 3",
            "legacy:a:x",
            "legacy:a:1.0",
        ],
    )
    def test_an_id_that_did_not_come_from_us_maps_to_nothing(self, not_ours):
        """Never a guess: an unrecognised id gets `None`, so a caller cannot
        be handed a plausible-looking id for a row that was never minted."""
        assert real_id_for_provisional(not_ours) is None


class TestConversionChangesNothingYouCanSee:
    """`source.store.conversion-changes-nothing-seen`, in its pure form."""

    def test_every_segment_reads_back_the_same_but_for_its_identity(self):
        block = machine_block()
        pass_read, reads = reads_for(block)
        pass_row, rows = rows_from_reads(pass_read, reads)

        after = [
            segment_read_from_row(row, box_index=index, source_block=block)
            for index, row in enumerate(rows)
        ]
        assert len(after) == len(reads)
        for before, now in zip(reads, after, strict=True):
            b = before.model_dump()
            a = now.model_dump()
            # The three the master test allows to differ, plus
            # `source_artifact_id`, which only ever describes the
            # PROVISIONAL store ("this read came out of that blob") and has
            # nothing true to say about a real row.
            for field in ("id", "pass_id", "provisional", "source_artifact_id"):
                b.pop(field)
                a.pop(field)
            # Conversion adds exactly two keys to metadata and changes
            # nothing else in it: the sort key the seam already reads, and
            # the page number, stored so it survives the artifact.
            added = a["metadata"].pop("box_index"), a["metadata"].pop("page_index", None)
            assert added[0] == before.box_index
            assert added[1] == before.page_index
            assert a == b, f"box {before.box_index} changed at conversion"

    def test_every_segment_keeps_its_words(self):
        block = machine_block()
        pass_read, reads = reads_for(block)
        _, rows = rows_from_reads(pass_read, reads)
        after = [
            segment_read_from_row(row, box_index=i, source_block=block)
            for i, row in enumerate(rows)
        ]
        assert [s.text for s in after] == [s.text for s in reads]
        assert after[0].text == "Primero."

    def test_the_passs_own_text_survives(self):
        """`PassRead.text` is the string every box's char span indexes into.
        Losing it would leave every span on the page pointing at nothing --
        silently, because nothing raises."""
        block = machine_block()
        pass_read, reads = reads_for(block)
        pass_row, _ = rows_from_reads(pass_read, reads)
        after = pass_read_from_row(pass_row, artifact_type="transcription", source_block=block)
        assert after.text == block.text == pass_read.text
        assert after.text is not None

    def test_a_char_span_still_points_at_the_same_words(self):
        """The spans are only worth keeping if they still resolve."""
        block = machine_block()
        pass_read, reads = reads_for(block)
        pass_row, rows = rows_from_reads(pass_read, reads)
        text = pass_read_from_row(pass_row, source_block=block).text
        first = segment_read_from_row(rows[0], box_index=0, source_block=block)
        start = first.anchor.char_start
        end = first.anchor.char_end
        assert text[start:end] == "Primero."

    def test_page_index_survives_for_every_box(self):
        block = machine_block()
        pass_read, reads = reads_for(block)
        _, rows = rows_from_reads(pass_read, reads)
        after = [
            segment_read_from_row(row, box_index=i, source_block=block)
            for i, row in enumerate(rows)
        ]
        assert [s.page_index for s in after] == [0, 0, 0, 1, 1]

    def test_page_index_survives_even_when_the_source_artifact_is_gone(self):
        """An artifact is hard-deleted (no soft-delete field). The PDF page
        view filters by `page_index`, so it is STORED, not read back."""
        block = machine_block()
        _, rows = rows_from_reads(*reads_for(block))
        orphaned = segment_read_from_row(rows[3], box_index=3, source_block=None)
        assert orphaned.page_index == 1
        assert orphaned.text is None, "with no block there are no words, and no pretending"

    def test_polygons_and_baselines_are_present_before_and_equal_after(self):
        block = machine_block()
        pass_read, reads = reads_for(block)
        _, rows = rows_from_reads(pass_read, reads)
        for read, row in zip(reads, rows, strict=True):
            assert row.anchor == read.anchor
            assert row.baseline == read.baseline

    def test_an_undrawable_box_is_still_a_row_and_still_holds_its_position(self):
        """The app draws a zero-size placeholder for it; if it vanished,
        every later index would shift by one."""
        block = machine_block()
        pass_read, reads = reads_for(block)
        _, rows = rows_from_reads(pass_read, reads)
        assert len(rows) == len(block.boxes) == 5
        undrawable = rows[4]
        assert undrawable.metadata["box_index"] == 4
        assert undrawable.bbox_w == 0.0 and undrawable.bbox_h == 0.0

    def test_the_pass_is_stamped_with_the_artifacts_time_not_the_conversions(self):
        """The seam sorts passes by `(created_at, id)`. A pass stamped
        `utc_now()` would reorder a page that has two results -- a
        difference a person can see."""
        block = machine_block()
        pass_read, reads = reads_for(block)
        stamped = pass_read.model_copy(update={"created_at": None})
        pass_row, rows = rows_from_reads(stamped, reads)
        # With the artifact's own time, the row carries exactly it.
        from datetime import datetime, timezone

        when = datetime(2019, 3, 2, 9, 30, tzinfo=timezone.utc)
        pass_row, rows = rows_from_reads(
            pass_read.model_copy(update={"created_at": when}), reads
        )
        assert pass_row.created_at == when
        assert all(row.created_at == when for row in rows)


class TestConvertedBoxesKeepTheirMaker:
    """`source.store.converted-boxes-keep-their-maker`."""

    def test_a_machines_boxes_are_stored_as_the_machines(self):
        block = machine_block()
        pass_read, reads = reads_for(block)
        pass_row, rows = rows_from_reads(pass_read, reads)
        assert pass_row.provenance_kind is ProvenanceKind.workflow
        machine_rows = [rows[i] for i in (0, 1, 3, 4)]
        assert all(r.provenance_kind is ProvenanceKind.workflow for r in machine_rows)
        assert all(r.created_by == "qwen" for r in machine_rows)

    def test_a_hand_drawn_box_inside_a_machine_result_stays_the_persons(self):
        block = machine_block()
        pass_read, reads = reads_for(block)
        _, rows = rows_from_reads(pass_read, reads)
        assert rows[2].provenance_kind is ProvenanceKind.human

    def test_a_hand_drawn_box_names_no_person_rather_than_the_wrong_one(self):
        """The block records THAT a person drew it, never WHICH person.
        Naming the converting actor would credit one historian with
        another's work."""
        block = machine_block()
        _, rows = rows_from_reads(*reads_for(block))
        assert rows[2].created_by is None

    def test_no_converted_row_names_an_actor(self):
        """Nothing in a conversion is the converting person's work. Only the
        edit that triggered it is theirs, on its own segment's version."""
        block = machine_block()
        pass_row, rows = rows_from_reads(*reads_for(block))
        assert pass_row.actor is None
        assert all(row.version == 1 for row in rows)

    def test_a_result_with_no_provider_or_model_is_stored_as_unknown(self):
        block = OCRGeometryResult(
            provider="", boxes=[OCRGeometryBox(text="x", bbox=[0, 0, 0.1, 0.1])]
        )
        pass_read, reads = segments_from_result(
            document_id=DOC_ID, artifact_id=ARTIFACT_ID, result=block,
            provider=None, model=None, run_id=None, created_at=None,
            artifact_type="regions",
        )
        pass_row, rows = rows_from_reads(pass_read, reads)
        assert pass_row.provenance_kind is ProvenanceKind.unknown
        assert rows[0].provenance_kind is ProvenanceKind.unknown
        assert rows[0].created_by is None

    def test_a_users_own_regions_artifact_is_stored_as_a_persons(self):
        block = OCRGeometryResult(
            provider="user", boxes=[OCRGeometryBox(text="", bbox=[0, 0, 0.1, 0.1])]
        )
        pass_read, reads = segments_from_result(
            document_id=DOC_ID, artifact_id=ARTIFACT_ID, result=block,
            provider="user", model=None, run_id=None, created_at=None,
            artifact_type="regions",
        )
        pass_row, rows = rows_from_reads(pass_read, reads)
        assert pass_row.provenance_kind is ProvenanceKind.human
        assert rows[0].created_by is None


class TestRowsFromReadsRefusesWhatItCannotStoreHonestly:
    def test_box_indexes_with_a_gap_refuse_the_whole_pass(self):
        block = machine_block()
        pass_read, reads = reads_for(block)
        holed = [r for i, r in enumerate(reads) if i != 2]
        with pytest.raises(BoxIndexesNotContiguous):
            rows_from_reads(pass_read, holed)

    def test_box_indexes_out_of_order_refuse_the_whole_pass(self):
        pass_read, reads = reads_for(machine_block())
        with pytest.raises(BoxIndexesNotContiguous):
            rows_from_reads(pass_read, list(reversed(reads)))

    def test_a_pass_that_names_no_artifact_refuses(self):
        pass_read, reads = reads_for(machine_block())
        with pytest.raises(ValueError, match="source artifact"):
            rows_from_reads(pass_read.model_copy(update={"source_artifact_id": None}), reads)

    def test_a_result_with_no_boxes_makes_an_empty_pass_not_an_error(self):
        block = OCRGeometryResult(provider="user", boxes=[])
        pass_row, rows = rows_from_reads(*segments_from_result(
            document_id=DOC_ID, artifact_id=ARTIFACT_ID, result=block,
            provider="user", model=None, run_id=None, created_at=None,
            artifact_type="regions",
        ))
        assert rows == []
        assert pass_row.id == converted_pass_id(ARTIFACT_ID)


class TestAConvertedRowReadsBackSafely:
    @pytest.mark.parametrize("bad", [True, False, "3", 3.0, None, -1, 99])
    def test_a_box_index_that_cannot_name_a_box_reads_as_no_text(self, bad):
        """`metadata` has been through a JSON column. `True` is an `int` in
        Python, so a stray `true` would otherwise index box 1."""
        block = machine_block()
        _, rows = rows_from_reads(*reads_for(block))
        row = rows[0].model_copy(update={"metadata": {"box_index": bad}})
        assert segment_read_from_row(row, box_index=0, source_block=block).text is None

    def test_reading_without_a_block_gives_no_text_but_still_the_page(self):
        """The two are not symmetrical, on purpose. `text` lives in the
        block, so with no block there are no words and no pretending.
        `page_index` is STORED on the row, so it survives -- which is what
        lets the PDF page view keep filtering after the artifact is gone."""
        _, rows = rows_from_reads(*reads_for(machine_block()))
        read = segment_read_from_row(rows[0], box_index=0)
        assert read.text is None
        assert read.page_index == 0

    def test_a_segment_that_was_never_converted_answers_exactly_as_before(self):
        """The guard that this change is additive: a row created by
        `segment.create` carries neither key, so every existing caller of
        `segment_read_from_row` gets the answer it got yesterday."""
        _, rows = rows_from_reads(*reads_for(machine_block()))
        plain = rows[0].model_copy(update={"metadata": {}})
        read = segment_read_from_row(plain, box_index=0, source_block=machine_block())
        assert read.text is None and read.page_index is None

    def test_a_pass_read_without_a_block_keeps_the_old_answer(self):
        pass_row, _ = rows_from_reads(*reads_for(machine_block()))
        assert pass_read_from_row(pass_row).text is None


class TestTheMarkerField:
    def test_an_artifact_starts_unconverted(self):
        artifact = Artifact(document_id=DOC_ID, artifact_type="transcription")
        assert artifact.geometry_superseded_by_pass_id is None

    def test_the_marker_is_the_only_thing_conversion_changes_on_an_artifact(self):
        """The block is kept untouched for good: it is the record of what the
        machine produced, and still the home of each box's words."""
        block = machine_block()
        artifact = Artifact(
            document_id=DOC_ID, artifact_type="transcription", ocr_geometry=block
        )
        before = artifact.model_dump(mode="json")
        artifact.geometry_superseded_by_pass_id = converted_pass_id(artifact.id)
        after = artifact.model_dump(mode="json")
        assert before.pop("geometry_superseded_by_pass_id") is None
        assert after.pop("geometry_superseded_by_pass_id") is not None
        assert before == after
