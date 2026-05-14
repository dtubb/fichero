"""Unit tests for the workflow quality-gate detector (#1029).

assess_text_quality must catch garbage node output (box glyphs, mostly
[ilegible]) so the builder can stop the run — without false-positiving on
clean text, empty output, or the legitimate no-text sentinels.
"""

from __future__ import annotations

from fichero.workflows.tools.output_quality import assess_text_quality


class TestEmptyAndSentinels:
    def test_empty_is_not_low_quality(self):
        # Emptiness is not this gate's job — handled separately per tool.
        is_low, reason = assess_text_quality("")
        assert is_low is False and reason is None

    def test_whitespace_only_is_not_low_quality(self):
        is_low, reason = assess_text_quality("   \n\t  ")
        assert is_low is False and reason is None

    def test_sin_texto_sentinel_is_valid(self):
        # The transcribe prompt's explicit no-text token — a real result.
        is_low, _ = assess_text_quality("[sin texto]")
        assert is_low is False

    def test_no_text_sentinel_is_valid(self):
        is_low, _ = assess_text_quality("  [no text]  ")
        assert is_low is False


class TestCleanText:
    def test_normal_prose_passes(self):
        text = (
            "The deed records a transfer of land dated 23/7/1999 between "
            "the parties named in the margin. Signed and witnessed."
        )
        is_low, reason = assess_text_quality(text)
        assert is_low is False and reason is None

    def test_one_stray_replacement_char_passes(self):
        # A single bad glyph in a real page is below the ratio threshold.
        text = "A long paragraph of genuine archival text � with one bad char " * 3
        is_low, _ = assess_text_quality(text)
        assert is_low is False

    def test_a_few_ilegible_markers_pass(self):
        # The prompt emits [ilegible] for unreadable spots — a few is normal.
        text = (
            "The witness [ilegible] signed the document on the date shown "
            "above, and the clerk recorded the entry in the register."
        )
        is_low, _ = assess_text_quality(text)
        assert is_low is False


class TestGarbageText:
    def test_box_glyph_output_is_low_quality(self):
        # The #1029 repro — a page that OCR'd to replacement glyphs.
        is_low, reason = assess_text_quality("xvi ⍰⍰,⍰⍰ ⍰⍰,⍰⍰⍰")
        assert is_low is True
        assert reason and "glyph" in reason.lower()

    def test_replacement_char_heavy_output_is_low_quality(self):
        is_low, reason = assess_text_quality("���� ��� ���� ��")
        assert is_low is True
        assert reason is not None

    def test_mostly_ilegible_is_low_quality(self):
        # A transcription that is almost entirely [ilegible] tokens.
        text = "[ilegible] [ilegible] [ilegible] [ilegible] word [ilegible]"
        is_low, reason = assess_text_quality(text)
        assert is_low is True
        assert reason and "ilegible" in reason.lower()

    def test_control_char_heavy_output_is_low_quality(self):
        is_low, _ = assess_text_quality("\x00\x01\x02\x03 \x04\x05 ab")
        assert is_low is True
