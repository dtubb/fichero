"""Word-box coverage (2026-08-23, "most pages have say 70%, not 100%").

Two silent-loss mechanisms, both pinned here on the pure halves:
UTF-16 range mapping (NSRange units, not code points) and the interpolated
fallback for ranges Vision cannot map.
"""
from fichero_server.workflows.tools.vision_base import (
    VisionOCRBox,
    _is_duplicate_line,
    _strip_bands,
    _unmatched_reference_bands,
    _interpolated_word_bbox,
    _line_coverage_gaps,
    _rebase_geometry_reading_order,
    _utf16_range,
)


def test_ascii_offsets_are_identical_in_utf16():
    assert _utf16_range("Christmas Day", 10, 13) == (10, 3)


def test_accented_text_shifts_utf16_no_further_than_reality():
    # "Tumáco at" — á is one code point AND one UTF-16 unit; the mapping
    # must not drift for BMP accents…
    assert _utf16_range("Tumáco at", 7, 9) == (7, 2)


def test_non_bmp_characters_widen_the_utf16_offsets():
    # …but a surrogate pair (𝕏 = 2 UTF-16 units) must widen everything
    # after it — the exact drift that made boundingBoxForRange return nil
    # for every word after the character.
    text = "\U0001d54f mark"
    assert _utf16_range(text, 2, 6) == (3, 4)


def test_interpolated_box_slices_the_line_proportionally():
    line = [0.1, 0.5, 0.8, 0.05]
    # chars 5..10 of a 20-char line → x = 0.1 + 0.8*(5/20), w = 0.8*(5/20)
    assert _interpolated_word_bbox(line, 5, 10, 20) == [
        0.1 + 0.8 * 0.25, 0.5, 0.8 * 0.25, 0.05,
    ]


def test_interpolation_survives_a_degenerate_line_length():
    box = _interpolated_word_bbox([0.0, 0.0, 1.0, 0.1], 0, 4, 0)
    assert box[2] >= 0.0


# --- Gap escalation (2026-08-23, "Went to Condoto" had no boxes at all) ---


def _line(text, y, h=0.03, start=None):
    end = None if start is None else start + len(text)
    return VisionOCRBox(text=text, bbox=[0.1, y, 0.8, h], char_start=start, char_end=end)


def test_gap_between_detected_lines_is_found_with_context_padding():
    lines = [_line("SATURDAY, FEBRUARY 11, 1933", 0.10),
             _line("Left at 11 AM for Andagoya", 0.30)]
    gaps = _line_coverage_gaps(lines)
    assert len(gaps) == 1
    top, bottom = gaps[0]
    # The band covers the empty span plus half-a-line of context each side.
    assert top < 0.13 + 1e-9 and bottom > 0.30 - 1e-9


def test_ordinary_line_spacing_produces_no_bands():
    lines = [_line("a", 0.10), _line("b", 0.14), _line("c", 0.18)]
    assert _line_coverage_gaps(lines) == []


def test_page_margins_are_not_gaps():
    # One big empty top margin, tight lines below — internal-only means no band.
    lines = [_line("a", 0.60), _line("b", 0.64)]
    assert _line_coverage_gaps(lines) == []


def test_rebase_restores_reading_order_and_spans():
    # Base pass detected lines 1 and 3; the escalation recovered line 2 with
    # provisional offsets. After rebase: text reads 1-2-3 and every span
    # indexes the REBUILT text.
    l1 = _line("first line", 0.10, start=0)
    l3 = _line("third line", 0.50, start=11)
    l2 = _line("recovered middle", 0.30, start=0)     # provisional
    w2 = VisionOCRBox(text="middle", bbox=[0.4, 0.30, 0.2, 0.03], char_start=10, char_end=16)
    text, lines, words = _rebase_geometry_reading_order([l1, l3, l2], [w2])
    assert text == "first line\nrecovered middle\nthird line"
    assert [line.text for line in lines] == ["first line", "recovered middle", "third line"]
    middle = lines[1]
    assert text[middle.char_start:middle.char_end] == "recovered middle"
    word = words[0]
    assert text[word.char_start:word.char_end] == "middle"


# --- Transcript-anchored bands (2026-08-23, "way down." at ordinary spacing) ---


def test_transcript_names_a_missed_line_between_two_anchors():
    # OCR detected the header and the line two below; the transcript proves
    # a line between them that left NO tall gap.
    detected = [
        _line("FRIDAY, JANUARY 13. 1933", 0.10, start=0),
        _line("Took air plane over to Andagoya", 0.17, start=25),
    ]
    reference = "FRIDAY, JANUARY 13, 1933\nway down. stopped at dredge\nTook air plane over to Andagoya"
    bands = _unmatched_reference_bands(reference, detected)
    assert len(bands) == 1
    top, bottom = bands[0]
    # Band runs from the header's bottom edge to the matched line's top,
    # padded — tight spacing is exactly the point.
    assert top < 0.14 and bottom > 0.16


def test_matched_transcript_produces_no_bands():
    detected = [_line("alpha line here", 0.10), _line("beta line here", 0.14)]
    reference = "alpha line here\nbeta line here"
    assert _unmatched_reference_bands(reference, detected) == []


def test_missed_line_without_both_anchors_stays_unclaimed():
    # The transcript's FIRST line missing (no anchor above) → margins are
    # honest emptiness, never a guessed band.
    detected = [_line("second line matched", 0.30)]
    reference = "first line missed entirely\nsecond line matched"
    assert _unmatched_reference_bands(reference, detected) == []


def test_punctuation_and_case_do_not_fake_a_miss():
    detected = [_line("SATURDAY. JANUARY 14. 1933", 0.10), _line("closing anchor line", 0.30)]
    reference = "Saturday, January 14, 1933\nclosing anchor line"
    assert _unmatched_reference_bands(reference, detected) == []


def test_adjacent_misses_merge_into_one_band():
    detected = [_line("top anchor line", 0.10, start=0), _line("bottom anchor line", 0.40, start=16)]
    reference = (
        "top anchor line\nfirst missed cursive line\nsecond missed cursive line\nbottom anchor line"
    )
    bands = _unmatched_reference_bands(reference, detected)
    assert len(bands) == 1


# --- Strip tiling + dedupe (the smaller-chunks base pass, 2026-08-23) ---


def test_strips_cover_the_page_with_overlap():
    bands = _strip_bands()
    assert bands[0][0] == 0.0 and bands[-1][1] == 1.0
    for (_, bottom), (top, _) in zip(bands, bands[1:]):
        assert top < bottom, "adjacent strips must overlap"


def test_same_line_from_a_strip_is_a_duplicate():
    kept = [_line("Told him we would stop", 0.20)]
    again = _line("TOLD him, we would stop", 0.21)   # case+punct noise, same place
    assert _is_duplicate_line(again, kept)


def test_same_text_far_away_is_not_a_duplicate():
    # Ledger pages repeat phrases ("at Dredge No 4") on different days.
    kept = [_line("at Dredge No 4 all day", 0.15)]
    later = _line("at Dredge No 4 all day", 0.70)
    assert not _is_duplicate_line(later, kept)
