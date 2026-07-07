"""Tests for UTF-16 ↔ code-point offset conversion (#3262).

The Swift frontend sends char_start/char_end as UTF-16 offsets (NSString
uses UTF-16). Python str[i:j] slices by code point. Characters outside the
BMP (emoji, rare CJK, some math) are 2 UTF-16 code units but 1 Python
code point, so every offset past such a character is shifted by +1 per
non-BMP char — silently wrong provenance.

These tests verify the conversion helper.
"""

from fichero.utf16_offsets import utf16_offset_to_codepoint, utf16_range_to_codepoint_range


class TestUtf16OffsetConversion:
    def test_bmp_only_offsets_unchanged(self):
        """ASCII and BMP text: UTF-16 offsets == code-point offsets."""
        text = "hello world"
        assert utf16_offset_to_codepoint(text, 0) == 0
        assert utf16_offset_to_codepoint(text, 6) == 6
        assert utf16_range_to_codepoint_range(text, 0, 5) == (0, 5)

    def test_emoji_before_highlighted_span(self):
        """'🎉abc' — 🎉 is 2 UTF-16 units, so 'abc' starts at UTF-16 offset 2."""
        text = "🎉abc"
        assert utf16_offset_to_codepoint(text, 2) == 1
        assert utf16_range_to_codepoint_range(text, 2, 5) == (1, 4)

    def test_emoji_in_middle(self):
        """'ab🎉cd' — 🎉 at code point 2, UTF-16 offset 2."""
        text = "ab🎉cd"
        assert utf16_range_to_codepoint_range(text, 2, 4) == (2, 3)
        assert utf16_range_to_codepoint_range(text, 0, 2) == (0, 2)
        assert utf16_range_to_codepoint_range(text, 4, 6) == (3, 5)

    def test_multiple_emoji(self):
        """Each emoji is 2 UTF-16 units."""
        text = "🎉🎉x"
        assert utf16_range_to_codepoint_range(text, 0, 4) == (0, 2)
        assert utf16_range_to_codepoint_range(text, 4, 5) == (2, 3)

    def test_offset_past_end_clamps(self):
        """Offset beyond string length clamps to len(text)."""
        assert utf16_offset_to_codepoint("hello", 100) == 5

    def test_offset_inside_surrogate_pair_snaps_to_start(self):
        """UTF-16 offset 1 lands inside 🎉's surrogate pair; snap to code point 0."""
        assert utf16_offset_to_codepoint("🎉ab", 1) == 0

    def test_empty_range_returns_zero(self):
        """start >= end after conversion → (0, 0)."""
        assert utf16_range_to_codepoint_range("hello", 3, 3) == (0, 0)

    def test_real_transcription_with_emoji(self):
        """Simulated page content: 'El niño 👦 jugó' — annotate 'jugó'."""
        text = "El niño 👦 jugó"
        # 'j' is at: E(0) l(1) ' '(2) n(3) i(4) ñ(5) o(6) ' '(7) 👦(8) ' '(9) j(10)
        # UTF-16: E(0) l(1) ' '(2) n(3) i(4) ñ(5) o(6) ' '(7) 👦(8,9) ' '(10) j(11)
        # 'jugó' starts at code point 10, UTF-16 offset 11
        cp_start = utf16_offset_to_codepoint(text, 11)
        cp_end = utf16_offset_to_codepoint(text, 15)  # 'jugó' is 4 UTF-16 units
        assert cp_start == 10
        assert text[cp_start:cp_end] == "jugó"
