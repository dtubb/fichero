"""The older recognition revision run as a second DETECTOR.

Revision 3 reads the page best; revision 1 localizes text revision 3 never
reports (measured 2026-09-03 on six Marshall diary pages — dense small print
went 0.54 → 0.77 text-ink coverage through the full ladder, no page worse).
The pass is only safe because it is additive: it may widen coverage, never
move a box the first pass measured. These tests pin that.
"""

from __future__ import annotations

import pytest

from fichero_server.workflows.tools.vision_base import (
    _VISION_SECOND_DETECTOR_REVISION,
    _fold_unseen_lines,
    _supported_text_revisions,
    VisionOCRBox,
    VisionOCRResult,
)


def _line(text: str, y: float, *, x: float = 0.1, w: float = 0.5, h: float = 0.03,
          char_start: int = 0):
    return VisionOCRBox(
        text=text, bbox=[x, y, w, h], confidence=0.9,
        char_start=char_start, char_end=char_start + len(text),
    )


def _page(*lines: VisionOCRBox) -> VisionOCRResult:
    return VisionOCRResult(
        text="\n".join(b.text for b in lines),
        line_boxes=list(lines),
        word_boxes=[],
    )


def test_a_line_the_page_already_holds_is_dropped_not_duplicated():
    base = _page(_line("Telegram Olva", 0.10), _line("Sick today", 0.20))
    merged, recovered = _fold_unseen_lines(base, _page(_line("Telegram Olva", 0.10)))

    assert recovered == 0
    # Unchanged, not rebuilt: a no-op pass must not reshuffle a good page.
    assert merged is base


def test_a_line_only_the_second_detector_saw_is_added_with_its_words():
    """The gain the whole pass exists for."""
    extra_line = _line("29 30 31", 0.50, char_start=0)
    extra = VisionOCRResult(
        text="29 30 31",
        line_boxes=[extra_line],
        word_boxes=[
            VisionOCRBox(text="29", bbox=[0.10, 0.50, 0.05, 0.03],
                         confidence=0.8, char_start=0, char_end=2),
            VisionOCRBox(text="30", bbox=[0.20, 0.50, 0.05, 0.03],
                         confidence=0.8, char_start=3, char_end=5),
        ],
    )
    base = _page(_line("JANUARY", 0.10))
    merged, recovered = _fold_unseen_lines(base, extra)

    assert recovered == 1
    assert "29 30 31" in merged.text
    assert {b.text for b in merged.word_boxes} == {"29", "30"}


def test_boxes_the_first_pass_measured_are_never_moved():
    """Additive means additive: the second opinion cannot rewrite geometry."""
    kept = _line("Sick today", 0.20)
    before = list(kept.bbox)
    base = _page(kept)
    merged, _ = _fold_unseen_lines(base, _page(_line("Pay day", 0.60)))

    survivor = next(b for b in merged.line_boxes if b.text == "Sick today")
    assert survivor.bbox == before


def test_words_outside_a_folded_line_span_do_not_ride_along():
    """A word is carried by the line that owns its char span, and only that
    line — otherwise a rejected duplicate line donates its words anyway."""
    extra = VisionOCRResult(
        text="alpha\nbravo",
        line_boxes=[_line("alpha", 0.50, char_start=0),
                    _line("bravo", 0.60, char_start=6)],
        word_boxes=[
            VisionOCRBox(text="alpha", bbox=[0.1, 0.50, 0.1, 0.03],
                         confidence=0.8, char_start=0, char_end=5),
            VisionOCRBox(text="bravo", bbox=[0.1, 0.60, 0.1, 0.03],
                         confidence=0.8, char_start=6, char_end=11),
        ],
    )
    base = _page(_line("bravo", 0.60, char_start=0))
    merged, recovered = _fold_unseen_lines(base, extra)

    assert recovered == 1
    assert {b.text for b in merged.word_boxes} == {"alpha"}


def test_the_revision_we_ship_is_one_this_machine_offers():
    """A constant naming a revision the OS does not have would silently turn
    the pass off, and nothing else would say so."""
    revisions = _supported_text_revisions()
    if not revisions:
        pytest.skip("Vision text recognition unavailable on this machine")
    assert _VISION_SECOND_DETECTOR_REVISION in revisions
    assert all(isinstance(r, int) for r in revisions)


def test_an_os_that_cannot_enumerate_revisions_disables_the_pass():
    """Empty set, not an exception: an unreadable OS answer must degrade to
    'do not use a revision I cannot confirm exists'."""
    _supported_text_revisions.cache_clear()
    import sys

    class _Broken:
        class VNRecognizeTextRequest:
            @staticmethod
            def supportedRevisions():
                raise RuntimeError("no such selector")

    real = sys.modules.get("Vision")
    sys.modules["Vision"] = _Broken
    try:
        assert _supported_text_revisions() == frozenset()
    finally:
        if real is not None:
            sys.modules["Vision"] = real
        else:
            del sys.modules["Vision"]
        _supported_text_revisions.cache_clear()


def test_a_word_whose_span_two_lines_claim_goes_to_the_one_it_sits_on():
    """Escalated lines carry their CROP's offsets, so spans collide.

    A line recovered from a crop starts at char 0 exactly like the page's
    first line. Taking the first span match sent those words to whichever line
    came earlier in the list, and rebasing then moved their spans relative to
    the wrong line — measured 2026-09-03 on a Marshall page: three word boxes
    at opposite ends of the page all claiming `char_start` 0, and across six
    pages only 29–72% of word spans read back as their own word. With position
    breaking the tie: 84–99%.
    """
    from fichero_server.workflows.tools.vision_base import _owning_line

    top = _line("first line", 0.05, char_start=0)
    recovered = _line("later line", 0.70, char_start=0)
    word = VisionOCRBox(
        text="later", bbox=[0.1, 0.705, 0.08, 0.02],
        confidence=0.9, char_start=0, char_end=5,
    )
    assert _owning_line(word, [top, recovered]) is recovered
    assert _owning_line(word, [recovered, top]) is recovered


def test_an_unambiguous_span_still_wins_without_consulting_geometry():
    """Position is a tie-break, not the rule: a word derived from its line's
    own rect must not be re-homed to a nearer line."""
    from fichero_server.workflows.tools.vision_base import _owning_line

    a = _line("alpha", 0.10, char_start=0)
    b = _line("bravo", 0.11, char_start=6)
    word = VisionOCRBox(
        text="alpha", bbox=[0.1, 0.111, 0.08, 0.02],
        confidence=None, char_start=0, char_end=5,
    )
    assert _owning_line(word, [a, b]) is a


def test_a_band_reading_the_same_line_differently_is_not_a_new_line():
    """The transcription-doubling bug, pinned.

    `_is_duplicate_line` compares TEXT, so a strip that re-reads a line and
    disagrees by one character looked like a discovery, and both readings
    landed in the page text. Measured 2026-09-03: the paleography gold page
    intermittently scored 0.88 character error against a 0.40 baseline. Area,
    not text, is the question a whole-page second pass has to answer.
    """
    from fichero_server.workflows.tools.vision_base import _overlaps_existing_area

    already = _line("y con esta ocasion", 0.30)
    reread = _line("y con esta ocafion", 0.302)   # one character apart
    assert _overlaps_existing_area(reread, [already], 0.30)


def test_a_line_where_the_page_read_nothing_still_gets_through():
    """The guard must not close the door the escalations exist to open."""
    from fichero_server.workflows.tools.vision_base import _overlaps_existing_area

    already = _line("y con esta ocasion", 0.30)
    discovered = _line("Mr & Mrs WW Avery returned", 0.62)
    assert not _overlaps_existing_area(discovered, [already], 0.30)


def test_a_degenerate_rect_is_treated_as_already_covered():
    """A zero-area candidate carries no evidence; it must not be admitted on
    the technicality that nothing overlaps it."""
    from fichero_server.workflows.tools.vision_base import _overlaps_existing_area

    flat = _line("", 0.5, w=0.0, h=0.0)
    assert _overlaps_existing_area(flat, [], 0.30)
