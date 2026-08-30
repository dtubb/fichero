"""The reviewed transcription placed on measured word boxes.

The page has accurate words with no positions and accurate positions labelled
with inaccurate words. These tests pin the two things that make the merge
usable rather than merely present: a word placed on a real measured box says
so, and a page whose measured skeleton cannot be trusted is REFUSED instead of
being given a confident wrong overlay.
"""

from __future__ import annotations

import pytest

from fichero_server.media.geometry_merge import (
    DERIVED,
    MEASURED,
    merge_reviewed_text_onto_geometry,
)
from fichero_server.media.ocr_geometry import (
    OCRGeometryBox,
    OCRGeometryLevel,
    OCRGeometryResult,
)


def _word(text: str, x: float, y: float, w: float = 0.08, h: float = 0.03):
    return OCRGeometryBox(
        text=text, bbox=[x, y, w, h], level=OCRGeometryLevel.WORD
    )


def _vision(*rows: list[OCRGeometryBox]) -> OCRGeometryResult:
    boxes: list[OCRGeometryBox] = []
    for row in rows:
        boxes.extend(row)
    return OCRGeometryResult(
        text="\n".join(" ".join(b.text for b in row) for row in rows),
        provider="apple",
        boxes=boxes,
    )


def test_correct_words_land_on_the_measured_boxes_that_read_them_wrong():
    """The point of the whole exercise.

    Vision read `mstruia` where the hand says `instruia`. The reviewed word
    must end up on Vision's box for it — same rectangle, correct text — and be
    labelled `measured`, because it IS.
    """
    measured = _vision(
        [_word("Don", 0.10, 0.10), _word("Pedro", 0.20, 0.10)],
        [_word("mstruia", 0.10, 0.20), _word("Popayan", 0.22, 0.20)],
    )
    outcome = merge_reviewed_text_onto_geometry(
        "Don Pedro\ninstruía Popayán", measured
    )

    assert not outcome.refused, outcome.reason
    assert outcome.result is not None
    by_text = {b.text: b for b in outcome.result.boxes}

    assert by_text["Popayán"].bbox == pytest.approx([0.22, 0.20, 0.08, 0.03])
    assert by_text["Popayán"].metadata["provenance"] == MEASURED
    # Accent-and-case folding is what lets a correct word match its own bad
    # reading; without it every accented word would fall through to derived.
    assert by_text["Don"].metadata["provenance"] == MEASURED
    assert outcome.measured_words >= 3


def test_char_spans_index_the_REVIEWED_text_not_the_ocr():
    """A box is only clickable if its span points into the text on screen."""
    reviewed = "Don Pedro\ninstruía Popayán"
    outcome = merge_reviewed_text_onto_geometry(
        reviewed,
        _vision(
            [_word("Don", 0.10, 0.10), _word("Pedro", 0.20, 0.10)],
            [_word("mstruia", 0.10, 0.20), _word("Popayan", 0.22, 0.20)],
        ),
    )
    assert outcome.result is not None
    assert outcome.result.text == reviewed
    for box in outcome.result.boxes:
        assert reviewed[box.char_start : box.char_end] == box.text


def test_a_word_vision_never_read_is_derived_inside_its_line():
    """An unmatched word gets a position, and admits it was interpolated."""
    outcome = merge_reviewed_text_onto_geometry(
        "Don Pedro\ninstruía escribano Popayán",
        _vision(
            [_word("Don", 0.10, 0.10), _word("Pedro", 0.20, 0.10)],
            [_word("mstruia", 0.10, 0.20), _word("Popayan", 0.30, 0.20)],
        ),
    )
    assert outcome.result is not None
    escribano = next(b for b in outcome.result.boxes if b.text == "escribano")
    assert escribano.metadata["provenance"] == DERIVED
    # Placed, not zero-width: a derived box the reader cannot see is the same
    # as no box at all.
    assert escribano.bbox[2] > 0.0
    assert outcome.derived_words >= 1


def test_a_page_whose_line_structure_disagrees_is_refused():
    """Vision merged two columns; the skeleton is wrong.

    Everything derived from a wrong skeleton inherits the error and looks
    authoritative, so the merge must decline and say why rather than emit it.
    """
    measured = _vision([_word("todo", 0.1, 0.1)])
    outcome = merge_reviewed_text_onto_geometry(
        "\n".join(f"linea numero {n} del documento" for n in range(12)), measured
    )
    assert outcome.refused
    assert "line counts disagree" in outcome.reason
    assert outcome.result is None


def test_unrelated_text_is_refused_rather_than_scattered():
    """Nothing aligns, so nothing is claimed."""
    measured = _vision(
        [_word("alpha", 0.1, 0.1)],
        [_word("bravo", 0.1, 0.2)],
        [_word("charlie", 0.1, 0.3)],
    )
    outcome = merge_reviewed_text_onto_geometry(
        "zzzz\nyyyy\nxxxx", measured
    )
    assert outcome.refused
    assert "failed alignment" in outcome.reason


def test_word_only_geometry_recovers_its_lines():
    """Producers that emit no line boxes still get a merge.

    Grouping words by vertical band is what recovers the skeleton; without it
    an Apple Vision word-only result would refuse every page.
    """
    measured = OCRGeometryResult(
        provider="apple",
        text="Don Pedro\nmstruia Popayan",
        boxes=[
            _word("Don", 0.10, 0.100),
            _word("Pedro", 0.20, 0.101),
            _word("mstruia", 0.10, 0.200),
            _word("Popayan", 0.22, 0.201),
        ],
    )
    outcome = merge_reviewed_text_onto_geometry(
        "Don Pedro\ninstruía Popayán", measured
    )
    assert not outcome.refused, outcome.reason
    assert outcome.lines_matched == 2
