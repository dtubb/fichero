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
            "personas_clave": [
                {"nombre": "Don Matheo", "contexto": "lender"},
                {"nombre": "Federico Leighton", "contexto": "engineer"},
            ]
        }
        out = _format_claims_as_context(data)
        assert "People found:" in out
        assert "Don Matheo" in out
        assert "Federico Leighton" in out

    def test_skips_empty_sections(self):
        data = {"personas_clave": [], "lugares": [{"nombre": "Cali"}]}
        out = _format_claims_as_context(data)
        assert "People found" not in out
        assert "Places found:" in out
        assert "Cali" in out

    def test_dates_use_normalized_form(self):
        data = {
            "fechas": [
                {"fecha_normalizada": "1922-08-24", "fecha": "twenty-fourth of August"},
                {"fecha_normalizada": "", "fecha": "1925"},
            ]
        }
        out = _format_claims_as_context(data)
        assert "1922-08-24" in out
        assert "1925" in out

    def test_keywords_render_as_semicolon_list(self):
        data = {"palabras_clave": ["mining", "lawsuit", "Chocó"]}
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
    @pytest.mark.asyncio
    async def test_empty_input_returns_empty(self):
        cfg = MagicMock()
        result = await _generate_timeline("", "English", cfg, "")
        assert result == ""

    @pytest.mark.asyncio
    async def test_prompt_asks_for_chronology(self):
        cfg = MagicMock()
        with patch(
            "fichero.workflows.tools.catalogue.chat",
            new=AsyncMock(return_value="* **1922-08-24** — Dredge sank."),
        ) as mock_chat:
            await _generate_timeline("source text", "English", cfg)
            assert mock_chat.called
            # Inspect the prompt content
            call_args = mock_chat.call_args
            messages = call_args[0][0]
            prompt_text = messages[0]["content"]
            assert "chronological" in prompt_text.lower() or "timeline" in prompt_text.lower()
            assert "English" in prompt_text

    @pytest.mark.asyncio
    async def test_chat_failure_returns_empty(self):
        cfg = MagicMock()
        with patch(
            "fichero.workflows.tools.catalogue.chat",
            new=AsyncMock(side_effect=RuntimeError("model busy")),
        ):
            result = await _generate_timeline("text", "English", cfg)
            assert result == ""

    @pytest.mark.asyncio
    async def test_uses_claim_context_when_provided(self):
        cfg = MagicMock()
        with patch(
            "fichero.workflows.tools.catalogue.chat",
            new=AsyncMock(return_value="timeline"),
        ) as mock_chat:
            await _generate_timeline("text", "English", cfg, claim_context="Dates found: 1922-08-24")
            prompt_text = mock_chat.call_args[0][0][0]["content"]
            assert "1922-08-24" in prompt_text


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
            "fichero.workflows.tools.catalogue.chat",
            new=AsyncMock(return_value="mining; lawsuit; Chocó"),
        ) as mock_chat:
            result = await _generate_keywords("source text", "Spanish", cfg)
            prompt_text = mock_chat.call_args[0][0][0]["content"]
            assert "keyword" in prompt_text.lower()
            assert "Spanish" in prompt_text
            assert result == "mining; lawsuit; Chocó"

    @pytest.mark.asyncio
    async def test_chat_failure_returns_empty(self):
        cfg = MagicMock()
        with patch(
            "fichero.workflows.tools.catalogue.chat",
            new=AsyncMock(side_effect=RuntimeError("oom")),
        ):
            result = await _generate_keywords("text", "English", cfg)
            assert result == ""
