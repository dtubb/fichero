"""Unit coverage for forced transcript-to-baseline alignment.

Pure logic — builds Kraken-shaped LINE boxes (empty text, ``line_index`` +
``polygon_px`` metadata) and asserts the transcript is hung on them in reading
order, or that alignment is honestly declined when the counts disagree.
"""

from __future__ import annotations

from fichero_server.media.ocr_geometry import (
    OCRGeometryBox,
    OCRGeometryLevel,
    OCRGeometryResult,
)
from fichero_server.media.transcript_alignment import (
    AlignmentStatus,
    BASELINE_COUNT_KEY,
    BOX_CONFIDENCE_KEY,
    BOX_METHOD_KEY,
    CONFIDENCE_KEY,
    GROUND_TRUTH_KEY,
    GROUND_TRUTH_SOURCE,
    STATUS_KEY,
    TRANSCRIPT_LINE_COUNT_KEY,
    UNMATCHED_LINES_KEY,
    align_transcript_to_baselines,
)


def _line_box(line_index: int, top: float) -> OCRGeometryBox:
    """A Kraken-shaped baseline box: empty text, geometry in metadata."""
    return OCRGeometryBox(
        text="",
        bbox=[0.1, top, 0.8, 0.05],
        level=OCRGeometryLevel.LINE,
        provider="kraken",
        model="kraken-blla",
        source="kraken-blla",
        metadata={
            "line_index": line_index,
            "polygon_px": [[10, 10], [90, 10], [90, 20], [10, 20]],
            "baseline_px": [[10, 19], [90, 19]],
            "pixel_frame": {"width": 100.0, "height": 200.0},
        },
    )


def _regions(count: int) -> OCRGeometryResult:
    return OCRGeometryResult(
        provider="kraken",
        model="kraken-blla",
        source="kraken-blla",
        rendition_id="rend-1",
        boxes=[_line_box(i, top=0.1 * i) for i in range(count)],
        metadata={"pixel_frame": {"width": 100.0, "height": 200.0}},
    )


def test_equal_counts_align_by_order():
    transcript = "first line\nsecond line\nthird line"
    result = align_transcript_to_baselines(transcript, _regions(3))

    assert result.metadata[STATUS_KEY] == AlignmentStatus.ALIGNED.value
    assert result.metadata[CONFIDENCE_KEY] == 1.0
    assert result.metadata[GROUND_TRUTH_KEY] == GROUND_TRUTH_SOURCE
    assert result.text == transcript
    assert [box.text for box in result.boxes] == [
        "first line",
        "second line",
        "third line",
    ]
    # Char spans index back into the full transcript.
    for box in result.boxes:
        assert transcript[box.char_start : box.char_end] == box.text
        assert box.confidence == 1.0
        assert box.metadata[BOX_METHOD_KEY] == "forced_order"
        assert box.metadata[BOX_CONFIDENCE_KEY] == 1.0
        # Original geometry is preserved.
        assert "polygon_px" in box.metadata


def test_alignment_respects_line_index_not_list_order():
    # Boxes handed in shuffled order but carrying the true reading order in
    # line_index must still align correctly.
    regions = _regions(3)
    regions = regions.model_copy(
        update={"boxes": [regions.boxes[2], regions.boxes[0], regions.boxes[1]]}
    )
    result = align_transcript_to_baselines("one\ntwo\nthree", regions)
    ordered = sorted(result.boxes, key=lambda b: b.metadata["line_index"])
    assert [b.text for b in ordered] == ["one", "two", "three"]


def test_blank_lines_are_ignored_so_counts_still_match():
    # Trailing/interior blank lines in the cloud transcript should not consume
    # a baseline.
    transcript = "alpha\n\nbeta\n"
    result = align_transcript_to_baselines(transcript, _regions(2))
    assert result.metadata[STATUS_KEY] == AlignmentStatus.ALIGNED.value
    assert [box.text for box in result.boxes] == ["alpha", "beta"]


def test_count_mismatch_declines_rather_than_guesses():
    # 3 transcript lines, 2 baselines: aligning the prefix would risk placing
    # the wrong text; we decline and report both counts.
    transcript = "one\ntwo\nthree"
    result = align_transcript_to_baselines(transcript, _regions(2))
    assert result.metadata[STATUS_KEY] == AlignmentStatus.COUNT_MISMATCH.value
    assert result.metadata[TRANSCRIPT_LINE_COUNT_KEY] == 3
    assert result.metadata[BASELINE_COUNT_KEY] == 2
    assert result.metadata[UNMATCHED_LINES_KEY] == ["one", "two", "three"]
    # No text was invented on the page.
    assert all(box.text == "" for box in result.boxes)


def test_empty_transcript_declines():
    result = align_transcript_to_baselines("   \n  ", _regions(2))
    assert result.metadata[STATUS_KEY] == AlignmentStatus.NO_TRANSCRIPT.value
    assert all(box.text == "" for box in result.boxes)


def test_no_baselines_declines():
    empty = OCRGeometryResult(provider="kraken", model="kraken-blla", boxes=[])
    result = align_transcript_to_baselines("one\ntwo", empty)
    assert result.metadata[STATUS_KEY] == AlignmentStatus.NO_BASELINES.value
