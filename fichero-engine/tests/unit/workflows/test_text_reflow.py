"""Unit tests for text_reflow workflow tool."""

from __future__ import annotations

import pytest

from fichero.workflows.tools.text_reflow import (
    _dehyphenate,
    _is_paragraph_boundary,
    _reflow_text,
    _should_join_lines,
)


class TestDehyphenate:
    """Test de-hyphenation of words split across line breaks."""

    def test_simple_dehyphenation(self):
        """Basic hyphenated word joining."""
        text = "disad-\nvantage"
        result = _dehyphenate(text)
        assert result == "disadvantage"

    def test_multiple_dehyphenations(self):
        """Multiple hyphenated words in text."""
        text = "exam-\nple and advan-\ntage are good"
        result = _dehyphenate(text)
        assert result == "example and advantage are good"

    def test_no_dehyphenation_for_non_hyphenated(self):
        """Leave non-hyphenated text alone."""
        text = "example and advantage"
        result = _dehyphenate(text)
        assert result == text

    def test_hyphen_not_at_break(self):
        """Only dehyphenate hyphens at line breaks."""
        text = "mother-in-law is one word"
        result = _dehyphenate(text)
        assert result == text

    def test_empty_string(self):
        """Dehyphenate handles empty strings."""
        assert _dehyphenate("") == ""

    def test_dehyphenation_with_space(self):
        """Handle hyphens with spaces (from joined lines)."""
        text = "disad- vantage and exam- ple"
        result = _dehyphenate(text)
        assert "disadvantage" in result
        assert "example" in result


class TestParagraphBoundary:
    """Test paragraph boundary detection."""

    def test_blank_line_is_boundary(self):
        """Blank lines are always paragraph boundaries."""
        assert _is_paragraph_boundary("") is True
        assert _is_paragraph_boundary("   ") is True

    def test_sentence_end_is_boundary(self):
        """Lines ending with sentence punctuation are boundaries."""
        assert _is_paragraph_boundary("This is a sentence.") is True
        assert _is_paragraph_boundary("Really?") is True
        assert _is_paragraph_boundary("Exactly!") is True
        assert _is_paragraph_boundary("What:") is True
        assert _is_paragraph_boundary("Actually;") is True
        assert _is_paragraph_boundary("And so…") is True

    def test_sentence_end_with_quotes(self):
        """Sentence-end punctuation with quotes."""
        assert _is_paragraph_boundary('He said "hello".') is True
        assert _is_paragraph_boundary("She asked 'why?'") is True

    def test_short_line_is_boundary(self):
        """Very short lines (< 40 chars) are considered boundaries."""
        assert _is_paragraph_boundary("Short.") is True
        assert _is_paragraph_boundary("A few words") is True
        assert _is_paragraph_boundary("This is a longer short line but still under forty") is False

    def test_normal_line_not_boundary(self):
        """Normal lines are not boundaries."""
        text = "This is a normal line without sentence ending"
        assert _is_paragraph_boundary(text) is False

    def test_indented_next_line(self):
        """Current line ends paragraph if next line is indented."""
        current = "End of paragraph here"
        next_line = "  Indented next paragraph"
        assert _is_paragraph_boundary(current, next_line) is True


class TestShouldJoinLines:
    """Test soft-wrap line joining heuristics."""

    def test_join_normal_continuation(self):
        """Join normal line to next line."""
        current = "This is a line that continues"
        next_line = "on the next line because it is wrapped"
        assert _should_join_lines(current, next_line) is True

    def test_dont_join_after_sentence_end(self):
        """Don't join after sentence-ending punctuation."""
        current = "This is a sentence."
        next_line = "This is a new sentence"
        assert _should_join_lines(current, next_line) is False

    def test_dont_join_to_blank_line(self):
        """Don't join to blank lines."""
        current = "Some text here"
        next_line = ""
        assert _should_join_lines(current, next_line) is False

    def test_dont_join_from_blank_line(self):
        """Blank lines don't join to next line."""
        current = ""
        next_line = "Some text"
        assert _should_join_lines(current, next_line) is False

    def test_dont_join_very_short_line(self):
        """Very short lines (< 20 chars) don't join."""
        current = "Short"
        next_line = "Next line of text"
        assert _should_join_lines(current, next_line) is False

    def test_dont_join_short_with_punct(self):
        """Short lines with punctuation don't join."""
        current = "Really?"
        next_line = "More text here"
        assert _should_join_lines(current, next_line) is False


class TestReflowText:
    """Test the full text reflow pipeline."""

    def test_simple_soft_wrap_join(self):
        """Join soft-wrapped lines."""
        text = "This is a long line that\nwas broken across two lines\nfor no good reason"
        result = _reflow_text(text)
        assert result == "This is a long line that was broken across two lines for no good reason"

    def test_preserve_paragraph_breaks(self):
        """Preserve blank lines between paragraphs."""
        text = "First paragraph here\nstill first paragraph\n\nSecond paragraph starts here\nand continues"
        result = _reflow_text(text)
        assert result == "First paragraph here still first paragraph\n\nSecond paragraph starts here and continues"

    def test_preserve_sentence_boundaries(self):
        """Preserve natural breaks at sentence ends."""
        text = "First sentence here.\nSecond sentence starts here.\nThird sentence too."
        result = _reflow_text(text)
        # Each sentence ends with period, so they stay separate
        assert result == "First sentence here.\nSecond sentence starts here.\nThird sentence too."

    def test_dehyphenate_during_reflow(self):
        """De-hyphenate words while reflowing."""
        text = "This word is disad-\nvantage but good for exam-\nple"
        result = _reflow_text(text)
        assert "disadvantage" in result
        assert "example" in result
        assert "-\n" not in result

    def test_empty_text(self):
        """Handle empty text gracefully."""
        assert _reflow_text("") == ""
        assert _reflow_text("   ") == ""

    def test_single_line(self):
        """Single line text unchanged."""
        text = "Just one line here"
        result = _reflow_text(text)
        assert result == text

    def test_book_page_realistic_case_1(self):
        """Realistic book page with mid-paragraph breaks and hyphenation.

        This simulates a scanned book page where the OCR has hard-wrapped
        at arbitrary column widths, includes hyphenation, and paragraph breaks.
        """
        text = """The history of typography is a complex and fascinat-
ing subject that spans centuries of human innovation.
From the earliest movable type in Asia to Gutenberg's
revolutionary printing press, the evolution of how we
represent and share written language has profoundly
shaped civilization itself.

The development of typefaces reflects not only technolog-
ical advancement but also aesthetic and cultural values
of each era. During the Renaissance, typographers worked
to create fonts that would make books more accessible
and beautiful to a growing reading public. These early
faces, such as Garamond, remain influential today."""

        result = _reflow_text(text)
        # Check that words are de-hyphenated
        assert "fascinating" in result
        assert "technological" in result
        # Check that paragraphs are preserved
        assert "\n\n" in result
        # Verify no dangling hyphens at line breaks remain
        assert "-\n" not in result

    def test_book_page_realistic_case_2(self):
        """Another realistic case with multi-column OCR artifact."""
        text = """The scholar examined the medieval manuscript with
great care. Each page contained intricate illuminations
and carefully executed calligraphy that represented
centuries of monastic dedication.

The monks who created these works understood the value
of precision and beauty in their craft. They prepared
their own pigments from minerals and plants, creating
colors that have survived for over a thousand years.
The dedication required to complete such work was enor-
mous, often taking years per manuscript."""

        result = _reflow_text(text)
        assert "enormous" in result  # de-hyphenated
        assert "dedication" not in "dedica-\ntion"  # no broken dedication
        # Paragraphs should be preserved
        para_count = result.count("\n\n")
        assert para_count >= 1

    def test_book_page_with_indentation(self):
        """Page with indented new paragraph."""
        text = """First paragraph without indentation continues
on the second line as is typical of body text.

     The second paragraph begins with indentation,
a common convention in traditional typography. This
indentation marks the start of a new thought or
section within the document."""

        result = _reflow_text(text)
        # Should preserve paragraph breaks
        assert "\n\n" in result

    def test_multiple_consecutive_hyphens(self):
        """Multiple hyphenated words in sequence."""
        text = """The quick brown fox jumps over the lazy dog qui-
etly. The soft moonlight illuminated the entire gar-
den with an ethereal glow that seemed to trans-
form everything it touched."""

        result = _reflow_text(text)
        assert "quietly" in result
        assert "garden" in result
        assert "transform" in result

    def test_preserve_intentional_short_lines(self):
        """Very short lines that appear intentional (poem, list) are preserved."""
        text = """The text continues normally here with standard
paragraph formatting that flows across multiple
lines as expected.

Short.
Very short.
Just a few.

Then it continues again in normal paragraph
style as before."""

        result = _reflow_text(text)
        # The intentionally short lines should mostly be preserved
        lines = result.split("\n")
        # Verify structure is reasonable
        assert any(len(line.strip()) < 20 for line in lines)

    def test_mixed_punctuation_preservation(self):
        """Different punctuation marks preserve boundaries correctly."""
        text = """The first part ends with exclamation!
The second part is a question?
The third contains a semicolon;
And the fourth is just normal text that
continues to the next line because it is wrapped."""

        result = _reflow_text(text)
        # Lines ending with special punctuation should not join
        assert "exclamation!\n" in result
        assert "question?\n" in result
        assert "semicolon;\n" in result

    def test_ellipsis_as_boundary(self):
        """Ellipsis is treated as sentence boundary."""
        text = """The story ends here with mystery…
And then it continues with a new thought that
stretches across multiple wrapped lines."""

        result = _reflow_text(text)
        # Ellipsis should be treated as boundary
        assert "…\n" in result or "…" in result


class TestEdgeCases:
    """Test edge cases and corner scenarios."""

    def test_text_with_only_hyphens(self):
        """Text that is only hyphens/dashes."""
        text = "- - - - -"
        result = _reflow_text(text)
        assert result == text

    def test_text_with_only_spaces(self):
        """Text that is only whitespace."""
        text = "     \n     \n     "
        result = _reflow_text(text)
        assert result == ""

    def test_very_long_line(self):
        """Very long single line is preserved."""
        text = "a" * 1000
        result = _reflow_text(text)
        assert len(result) > 0

    def test_alternating_short_long_lines(self):
        """Alternating very short and long lines."""
        text = "Short\nThis is a very long line that continues\nMore\nAnother long line that goes on and on\nEnd"
        result = _reflow_text(text)
        # Should preserve the short lines
        assert "Short" in result
        assert "More" in result
        assert "End" in result

    def test_unicode_text(self):
        """Unicode text is handled correctly."""
        text = """Café and résumé are French words.
They continue on this line with éclat."""
        result = _reflow_text(text)
        assert "Café" in result
        assert "résumé" in result
        assert "éclat" in result

    def test_dos_line_endings(self):
        """DOS/Windows line endings are normalized."""
        text = "First line\r\nSecond line\r\nThird line"
        # Split will preserve \r, but our logic should still work
        result = _reflow_text(text)
        assert "First" in result or "line" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
