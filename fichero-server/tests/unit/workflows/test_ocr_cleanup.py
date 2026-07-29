"""Unit tests for the OCR cleanup workflow tool."""

from __future__ import annotations

import pytest

from fichero_server.workflows.tools.ocr_cleanup import (
    _dehyphenate,
    _rejoin_columns,
    _strip_stamps,
    ocr_cleanup,
)


class TestDehyphenate:
    def test_joins_hyphenated_split(self):
        assert _dehyphenate("exam-\nple") == "example"

    def test_preserves_intentional_hyphens(self):
        # Hyphens not followed by a newline are untouched
        text = "well-known fact"
        assert _dehyphenate(text) == text

    def test_multiple_splits(self):
        text = "doc-\nument and re-\nport"
        assert _dehyphenate(text) == "document and report"

    def test_no_change_when_clean(self):
        text = "No hyphens here.\nJust plain text."
        assert _dehyphenate(text) == text


class TestStripStamps:
    def test_strips_library_of_congress(self):
        text = "Some content.\nLIBRARY OF CONGRESS\nMore content."
        result = _strip_stamps(text)
        assert "LIBRARY OF CONGRESS" not in result
        assert "Some content." in result
        assert "More content." in result

    def test_strips_returned_stamp(self):
        text = "Page text.\nRETURNED\nNext page."
        result = _strip_stamps(text)
        assert "RETURNED" not in result

    def test_strips_date_stamp(self):
        text = "Text.\nSEP 12 1987\nMore text."
        result = _strip_stamps(text)
        assert "SEP 12 1987" not in result

    def test_collapses_blank_lines(self):
        text = "A\n\n\n\n\nB"
        result = _strip_stamps(text)
        assert "\n\n\n" not in result

    def test_no_change_when_clean(self):
        text = "Regular text without stamps.\nAnother line."
        assert _strip_stamps(text) == text


class TestRejoinColumns:
    def test_joins_short_line(self):
        # A short line not ending in punctuation should join with the next
        short = "The quick brown"
        next_line = "fox jumps over"
        text = f"{short}\n{next_line}"
        result = _rejoin_columns(text, min_line_length=60)
        assert "The quick brown fox jumps over" in result

    def test_preserves_sentence_end_lines(self):
        # Line ending in period should NOT be joined
        text = "End of sentence.\nNext sentence starts here."
        result = _rejoin_columns(text, min_line_length=60)
        assert "End of sentence." in result
        assert "Next sentence starts here." in result
        # They should remain on separate lines
        assert "End of sentence.\nNext sentence starts here." in result

    def test_preserves_blank_paragraph_separators(self):
        text = "First paragraph.\n\nSecond paragraph."
        result = _rejoin_columns(text, min_line_length=60)
        assert "\n\n" in result

    def test_long_lines_not_joined(self):
        long_line = "A" * 70
        next_line = "B" * 30
        text = f"{long_line}\n{next_line}"
        result = _rejoin_columns(text, min_line_length=60)
        assert long_line in result
        assert next_line in result


@pytest.mark.asyncio
async def test_ocr_cleanup_all_steps():
    """Integration: all three steps applied end-to-end."""
    raw = (
        "Some text with a hy-\nphenated word.\n"
        "LIBRARY OF CONGRESS\n"
        "Short col\n"
        "umn text here.\n"
    )
    result = await ocr_cleanup(
        inputs={
            "text": raw,
            "_config": {
                "dehyphenate": True,
                "rejoin_columns": True,
                "strip_stamps": True,
                "min_line_length": 60,
            },
        },
        state={},
        llm_config=None,
    )
    cleaned = result["text"]
    assert "LIBRARY OF CONGRESS" not in cleaned
    assert "hyphenated" in cleaned


@pytest.mark.asyncio
async def test_ocr_cleanup_empty_text():
    result = await ocr_cleanup(
        inputs={"text": "", "_config": {}},
        state={},
        llm_config=None,
    )
    assert result["text"] == ""


@pytest.mark.asyncio
async def test_ocr_cleanup_individual_flags():
    """Verify individual flags can be disabled."""
    text = "exam-\nple word"
    result = await ocr_cleanup(
        inputs={"text": text, "_config": {"dehyphenate": False, "rejoin_columns": False, "strip_stamps": False}},
        state={},
        llm_config=None,
    )
    # With all flags off, text should be unchanged (modulo strip)
    assert "exam-" in result["text"]
