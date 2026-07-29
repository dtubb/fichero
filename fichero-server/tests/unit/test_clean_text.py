"""Unit tests for the Clean Up Text workflow tool.

The tool defaults to deterministic programmatic cleanup and supports an
explicit LLM mode for opt-in behavior.

These tests focus on:

  * the prompt builder honours each aspect toggle,
  * meaning-preservation guardrails are always present,
  * the tool is registered with editable model + prompt config.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

# Importing the package registers every tool via @register_tool.
import fichero_server.workflows.tools  # noqa: F401
from fichero_server.workflows.registry import TOOLS, TOOL_DEFS
from fichero_server.workflows.tools.clean_text import (
    CLEAN_TEXT_CONFIG,
    build_clean_text_prompt,
    clean_text,
    _build_prompt,
)
from fichero_server.workflows.tools.text_cleaning import clean_ocr_text
from fichero_server.llm import LLMConfig


# Substrings that uniquely identify each aspect's instruction line.
_OCR_MARKER = "OCR misrecognitions"
_HYPHEN_MARKER = "split across line breaks"
_WHITESPACE_MARKER = "Normalize whitespace"
_ARTIFACT_MARKER = "running"  # "running page headers/footers"
_GUARDRAIL = "Preserve the original meaning"


class TestBuildPrompt:
    def test_all_aspects_on_includes_every_instruction(self):
        prompt = _build_prompt(True, True, True, True)
        assert _OCR_MARKER in prompt
        assert _HYPHEN_MARKER in prompt
        assert _WHITESPACE_MARKER in prompt
        assert "page headers/footers" in prompt

    def test_guardrails_always_present(self):
        # Even with every toggle off, meaning must be preserved and output
        # must be only the cleaned text (no summarize/paraphrase).
        for combo in [
            (True, True, True, True),
            (False, False, False, False),
            (True, False, True, False),
        ]:
            prompt = _build_prompt(*combo)
            assert _GUARDRAIL in prompt
            assert "[ilegible]" in prompt
            assert "[uncertain]" in prompt
            assert "Do NOT summarize" in prompt
            assert "Output ONLY the cleaned text" in prompt

    def test_fix_ocr_toggle_off_drops_ocr_line(self):
        prompt = _build_prompt(False, True, True, True)
        assert _OCR_MARKER not in prompt
        # Other aspects unaffected.
        assert _HYPHEN_MARKER in prompt
        assert _WHITESPACE_MARKER in prompt

    def test_fix_hyphenation_toggle_off_drops_hyphen_line(self):
        prompt = _build_prompt(True, True, False, True)
        assert _HYPHEN_MARKER not in prompt
        assert _OCR_MARKER in prompt

    def test_normalize_whitespace_toggle_off_drops_whitespace_line(self):
        prompt = _build_prompt(True, False, True, True)
        assert _WHITESPACE_MARKER not in prompt

    def test_strip_artifacts_toggle_off_drops_artifact_line(self):
        prompt = _build_prompt(True, True, True, False)
        assert "page headers/footers" not in prompt

    def test_all_off_still_yields_minimal_cleanup(self):
        prompt = _build_prompt(False, False, False, False)
        # No specific aspect lines, but a minimal tidy instruction remains.
        assert "Tidy obvious whitespace issues only." in prompt


class TestBuildCleanTextPromptFromConfig:
    def test_defaults_when_config_empty(self):
        # Empty config → all aspects default ON.
        prompt = build_clean_text_prompt({})
        assert _OCR_MARKER in prompt
        assert _HYPHEN_MARKER in prompt
        assert _WHITESPACE_MARKER in prompt
        assert "page headers/footers" in prompt

    def test_respects_disabled_toggle(self):
        prompt = build_clean_text_prompt({"strip_artifacts": False})
        assert "page headers/footers" not in prompt
        assert _OCR_MARKER in prompt


class TestRegistration:
    def test_tool_registered(self):
        assert "clean_text" in TOOLS
        assert "clean_text" in TOOL_DEFS

    def test_tool_metadata(self):
        tool_def = TOOL_DEFS["clean_text"]
        assert tool_def.display_name == "Clean Up Text"
        assert tool_def.category == "llm"
        assert tool_def.uses_llm is True
        assert tool_def.supports_batch is True
        # Default prompt is shipped so the UI can show/edit it.
        assert tool_def.default_prompt
        assert _GUARDRAIL in tool_def.default_prompt
        # Prompt builder is wired for live preview.
        assert callable(tool_def.prompt_builder)

    def test_model_and_prompt_are_user_editable(self):
        """The config schema must expose model + prompt override (inherited
        from BASE_CONFIG_SCHEMA) plus the aspect toggles — nothing hard-coded.
        """
        schema = TOOL_DEFS["clean_text"].config_schema
        # Model selection.
        assert "provider_name" in schema
        assert "model_name" in schema
        # Full prompt override.
        assert "prompt" in schema
        assert "cleaning_method" in schema
        # Aspect toggles.
        for key in CLEAN_TEXT_CONFIG:
            assert key in schema

    def test_has_required_text_input_port(self):
        tool_def = TOOL_DEFS["clean_text"]
        port_ids = {p.id for p in tool_def.input_ports}
        assert "text" in port_ids
        text_port = next(p for p in tool_def.input_ports if p.id == "text")
        assert text_port.required is True
        # Output exposes a text port for downstream chaining.
        out_ids = {p.id for p in tool_def.output_ports}
        assert "text" in out_ids


class TestRuntimeBehavior:
    def test_programmatic_cleaner_drops_ocr_digit_soup_keeps_real_lines(self):
        raw_text = """
33005 00s000Gc00000(0000005a5a 0D6000000000000000002 ...
República de Colombia
INTENDE ICIA NAL. DEL CHOCO
DISTRITO JUDICIAL DE CALI
JUZGADO PRIMERO DEL CIBCEITO
ISTMIN
1930
...
000000000000000000
23908
TTP. HERALDO.
290029090
"""

        cleaned = clean_ocr_text(raw_text)

        # Real content remains.
        assert "República de Colombia" in cleaned
        assert "INTENDENCIA NAL. DEL CHOCÓ" in cleaned
        assert "DISTRITO JUDICIAL DE CALI" in cleaned
        assert "JUZGADO PRIMERO DEL CIRCUITO" in cleaned
        assert "ISTMINA" in cleaned
        assert "1930" in cleaned
        assert "TIP. HERALDO." in cleaned

        # OCR digit/symbol soup and single-number garbage are removed.
        assert "33005 00s000Gc00000" not in cleaned
        assert "000000000000000000" not in cleaned
        assert "23908" not in cleaned
        assert "290029090" not in cleaned

    def test_programmatic_cleaner_preserves_ilegible_markers(self):
        raw_text = (
            "La firma es [ilegible] y la fecha [uncertain].\n"
            "Chocó conserva sus acentos."
        )

        cleaned = clean_ocr_text(raw_text)

        assert "[ilegible]" in cleaned
        assert "[uncertain]" in cleaned
        assert "Chocó" in cleaned

    @pytest.mark.asyncio
    async def test_programmatic_is_default_and_does_not_call_llm(self):
        cfg = LLMConfig(provider="openai", model="gpt-5")
        with patch("fichero_server.workflows.tools.clean_text.process_text", new=AsyncMock()) as mock_process:
            result = await clean_text(
                inputs={"text": "hello hello world", "save_to_db": False},
                state={},
                llm_config=cfg,
            )
        mock_process.assert_not_awaited()
        assert "error" not in result
        assert result["text"] == "hello world"

    @pytest.mark.asyncio
    async def test_explicit_llm_method_calls_process_text(self):
        cfg = LLMConfig(provider="openai", model="gpt-5")
        expected = {"text": "cleaned", "value": "cleaned", "texts": ["cleaned"], "values": ["cleaned"], "results": [], "artifacts": [], "output_files": []}
        with patch("fichero_server.workflows.tools.clean_text.process_text", new=AsyncMock(return_value=expected)) as mock_process:
            result = await clean_text(
                inputs={"text": "raw", "cleaning_method": "llm", "save_to_db": False},
                state={},
                llm_config=cfg,
            )
        mock_process.assert_awaited_once()
        assert result["text"] == "cleaned"
