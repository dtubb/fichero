"""Phase E unit tests for the multi-output catalogue tool (#805).

Covers:
- _format_claims_as_context renders entity dict to inline LLM context
- _split_text_into_chunks splits on page boundaries when possible
- _generate_timeline / _generate_keywords build correct prompts + handle errors
- Multi-artifact save: 3 distinct artifact types
- Idempotent rerun: prior catalogue.* artifacts deleted before save

No live LLM or DB required — chat() is mocked, DB ops are mocked.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from fichero.workflows.tools.catalogue import (
    _format_claims_as_context,
    _generate_keywords,
    _generate_timeline,
    _split_text_into_chunks,
)


class TestFormatClaimsAsContext:
    def test_empty_data_returns_empty_string(self):
        assert _format_claims_as_context(None) == ""
        assert _format_claims_as_context({}) == ""

    def test_people_section_renders_names(self):
        data = {
            "people": [
                {"name": "Don Matheo", "context": "lender"},
                {"name": "Federico Leighton", "context": "engineer"},
            ]
        }
        out = _format_claims_as_context(data)
        assert "People found:" in out
        assert "Don Matheo" in out
        assert "Federico Leighton" in out

    def test_skips_empty_sections(self):
        data = {"people": [], "places": [{"name": "Cali"}]}
        out = _format_claims_as_context(data)
        assert "People found" not in out
        assert "Places found:" in out
        assert "Cali" in out

    def test_dates_use_normalized_form(self):
        data = {
            "dates": [
                {"date_normalized": "1922-08-24", "date": "twenty-fourth of August"},
                {"date_normalized": "", "date": "1925"},
            ]
        }
        out = _format_claims_as_context(data)
        assert "1922-08-24" in out
        assert "1925" in out

    def test_keywords_render_as_semicolon_list(self):
        data = {"keywords": ["mining", "lawsuit", "Chocó"]}
        out = _format_claims_as_context(data)
        assert "Keywords:" in out
        assert "mining; lawsuit; Chocó" in out


class TestSplitTextIntoChunks:
    def test_short_text_one_chunk(self):
        chunks = _split_text_into_chunks("hello", 100)
        assert chunks == ["hello"]

    def test_splits_on_page_boundary(self):
        text = "page one" + "\n\n---\n\n" + "page two" + "\n\n---\n\n" + "page three"
        chunks = _split_text_into_chunks(text, 20)
        assert len(chunks) >= 2
        # Each chunk respects the budget (with small slack for separator)
        for c in chunks:
            assert len(c) <= 30

    def test_falls_back_to_paragraph_split_when_page_too_large(self):
        long_page = "para1\n\n" + "X" * 50 + "\n\npara3"
        chunks = _split_text_into_chunks(long_page, 30)
        # Should split somehow rather than return one giant chunk
        assert all(len(c) <= 60 for c in chunks)

    def test_extreme_long_text_falls_back_to_char_slice(self):
        text = "X" * 1000
        chunks = _split_text_into_chunks(text, 100)
        assert len(chunks) == 10
        assert all(len(c) == 100 for c in chunks)


class TestGenerateTimeline:
    """Timeline is now rendered programmatically from the date claims —
    no LLM call. Small models hallucinate or misorder dates; sorting
    YYYY-MM-DD strings is deterministic and free."""

    def test_empty_data_returns_empty(self):
        assert _generate_timeline(None) == ""
        assert _generate_timeline({}) == ""
        assert _generate_timeline({"dates": []}) == ""

    def test_renders_sorted_markdown_bullets(self):
        data = {"dates": [
            {"date_normalized": "1931-08-03", "context": "appeal filed"},
            {"date_normalized": "1930-05-12", "context": "deed signed"},
        ]}
        result = _generate_timeline(data)
        # Earliest first, bold date, em-dash, context.
        assert result == (
            "* **1930-05-12** — deed signed\n"
            "* **1931-08-03** — appeal filed"
        )

    def test_uses_legacy_spanish_keys_as_fallback(self):
        data = {"fechas": [
            {"fecha_normalizada": "1925-02-28", "contexto": "Dispatch"},
        ]}
        result = _generate_timeline(data)
        assert result == "* **1925-02-28** — Dispatch"

    def test_skips_undated_entries(self):
        data = {"dates": [
            {"context": "no date here"},
            {"date_normalized": "1922-08-24", "context": "dredge sank"},
        ]}
        result = _generate_timeline(data)
        assert result == "* **1922-08-24** — dredge sank"

    def test_dedupes_identical_pairs(self):
        data = {"dates": [
            {"date_normalized": "1930-05-12", "context": "X"},
            {"date_normalized": "1930-05-12", "context": "X"},
        ]}
        assert _generate_timeline(data) == "* **1930-05-12** — X"

    def test_no_context_renders_just_date(self):
        data = {"dates": [{"date_normalized": "1930-05-12", "context": ""}]}
        assert _generate_timeline(data) == "* **1930-05-12**"


class TestGenerateKeywords:
    @pytest.mark.asyncio
    async def test_empty_input_returns_empty(self):
        cfg = MagicMock()
        result = await _generate_keywords("", "English", cfg, "")
        assert result == ""

    @pytest.mark.asyncio
    async def test_prompt_asks_for_subject_keywords(self):
        cfg = MagicMock()
        with patch(
            "fichero.workflows.tools.catalogue.chat_with_fallback",
            new=AsyncMock(return_value="mining; lawsuit; Chocó"),
        ) as mock_chat:
            result = await _generate_keywords("source text", "Spanish", cfg)
            instructions = mock_chat.call_args.kwargs["system"]
            assert "keyword" in instructions.lower()
            assert "Spanish" in instructions
            assert result == "mining; lawsuit; Chocó"

    @pytest.mark.asyncio
    async def test_chat_failure_returns_empty(self):
        cfg = MagicMock()
        with patch(
            "fichero.workflows.tools.catalogue.chat_with_fallback",
            new=AsyncMock(side_effect=RuntimeError("oom")),
        ):
            result = await _generate_keywords("text", "English", cfg)
            assert result == ""
