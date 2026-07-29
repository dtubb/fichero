"""Unit tests for the workflow quality-gate detector (#1029).

assess_text_quality must catch garbage node output (box glyphs, mostly
[ilegible]) so the builder can stop the run — without false-positiving on
clean text, empty output, or the legitimate no-text sentinels.
"""

from __future__ import annotations

from fichero_server.workflows.tools.output_quality import (
    assess_result_quality,
    assess_text_quality,
)

_GARBAGE = "xvi ⍰⍰,⍰⍰ ⍰⍰,⍰⍰⍰"
_CLEAN = "A genuine paragraph of archival text recorded by the clerk."


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
        assert reason and "uncertainty" in reason.lower()

    def test_canonical_ilegible_markers_trip_the_gate(self):
        text = "[ilegible] [ilegible] [ilegible] transcripcion"
        is_low, reason = assess_text_quality(text)
        assert is_low is True
        assert reason and "uncertainty" in reason.lower()

    def test_mostly_uncertain_tokens_is_low_quality(self):
        text = "[UNCERTAIN] [ILLEGIBLE] [UNCERTAIN] [ILLEGIBLE] word [UNCERTAIN]"
        is_low, reason = assess_text_quality(text)
        assert is_low is True
        assert reason and "uncertainty" in reason.lower()

    def test_control_char_heavy_output_is_low_quality(self):
        is_low, _ = assess_text_quality("\x00\x01\x02\x03 \x04\x05 ab")
        assert is_low is True


class TestAssessResultQuality:
    """The all-or-nothing rule: some garbage pages = fine, all = stop."""

    def test_single_garbage_text_stops(self):
        should_stop, reason = assess_result_quality({"text": _GARBAGE})
        assert should_stop is True and reason is not None

    def test_single_clean_text_continues(self):
        should_stop, _ = assess_result_quality({"text": _CLEAN})
        assert should_stop is False

    def test_some_garbage_pages_continue(self):
        # 2 of 5 pages garbage — the document is still mostly usable.
        records = [
            {"doc_id": "1", "text": _CLEAN},
            {"doc_id": "2", "text": _GARBAGE},
            {"doc_id": "3", "text": _CLEAN},
            {"doc_id": "4", "text": _GARBAGE},
            {"doc_id": "5", "text": _CLEAN},
        ]
        should_stop, _ = assess_result_quality({"page_records": records})
        assert should_stop is False

    def test_all_garbage_pages_stop(self):
        records = [{"doc_id": str(i), "text": _GARBAGE} for i in range(5)]
        should_stop, reason = assess_result_quality({"page_records": records})
        assert should_stop is True
        assert reason and "all 5 pages" in reason

    def test_garbage_and_empty_pages_stop(self):
        # Garbage + blank pages, zero usable output — still stops.
        records = [
            {"doc_id": "1", "text": _GARBAGE},
            {"doc_id": "2", "text": "   "},
            {"doc_id": "3", "text": _GARBAGE},
        ]
        should_stop, _ = assess_result_quality({"page_records": records})
        assert should_stop is True

    def test_one_good_page_among_garbage_continues(self):
        records = [{"doc_id": str(i), "text": _GARBAGE} for i in range(9)]
        records.append({"doc_id": "9", "text": _CLEAN})
        should_stop, _ = assess_result_quality({"page_records": records})
        assert should_stop is False

    def test_all_empty_pages_do_not_stop(self):
        # No output at all is not this gate's job.
        records = [{"doc_id": "1", "text": ""}, {"doc_id": "2", "text": "  "}]
        should_stop, _ = assess_result_quality({"page_records": records})
        assert should_stop is False

    def test_page_records_preferred_over_joined_text(self):
        # A node returns both: the joined text reads as garbage-heavy, but
        # per-page granularity shows most pages are fine — continue.
        result = {
            "text": _GARBAGE + "\n\n" + _GARBAGE + "\n\n" + _CLEAN,
            "page_records": [
                {"doc_id": "1", "text": _CLEAN},
                {"doc_id": "2", "text": _CLEAN},
                {"doc_id": "3", "text": _GARBAGE},
            ],
        }
        should_stop, _ = assess_result_quality(result)
        assert should_stop is False

    def test_texts_list_all_garbage_stops(self):
        should_stop, _ = assess_result_quality({"texts": [_GARBAGE, _GARBAGE]})
        assert should_stop is True

    def test_empty_result_does_not_stop(self):
        should_stop, _ = assess_result_quality({})
        assert should_stop is False
