"""Word-box coverage (2026-08-23, "most pages have say 70%, not 100%").

Two silent-loss mechanisms, both pinned here on the pure halves:
UTF-16 range mapping (NSRange units, not code points) and the interpolated
fallback for ranges Vision cannot map.
"""
from fichero_server.workflows.tools.vision_base import (
    _interpolated_word_bbox,
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
