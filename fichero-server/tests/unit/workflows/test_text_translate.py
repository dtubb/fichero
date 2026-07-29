"""Unit tests for the Translate + Translate Review workflow tools (#926).

Both tools are LLM-driven (covered by process_text integration paths), so
these tests focus on the deterministic, user-editable surface:

  * the prompt builders honour the target/source language + toggles,
  * fidelity / output guardrails are always present,
  * the tools are registered with editable model + prompt config,
  * the target language is config-driven, never a hard-coded literal
    (feedback_user_editable_not_hardcoded).
"""

from __future__ import annotations

# Importing the package registers every tool via @register_tool.
import fichero_server.workflows.tools  # noqa: F401
from fichero_server.workflows.registry import TOOLS, TOOL_DEFS
from fichero_server.workflows.tools.text_translate import (
    DEFAULT_TARGET_LANGUAGE,
    TEXT_TRANSLATE_CONFIG,
    build_text_translate_prompt,
    _build_prompt as _build_translate_prompt,
)
from fichero_server.workflows.tools.text_translate_review import (
    TEXT_TRANSLATE_REVIEW_CONFIG,
    build_text_translate_review_prompt,
    _build_prompt as _build_review_prompt,
)


# Substrings that identify the fidelity guardrails.
_TRANSLATE_GUARDRAIL = "do NOT summarize"
_PRESERVE_NAMES_MARKER = "proper names"
_REVIEW_GUARDRAIL = "Output ONLY the corrected"


class TestBuildTranslatePrompt:
    def test_target_language_appears_in_prompt(self):
        prompt = _build_translate_prompt("French", "auto", True)
        assert "into French" in prompt
        # The default English must NOT leak when another target is chosen.
        assert "into English" not in prompt

    def test_default_target_is_english_but_overridable(self):
        # Empty/whitespace target falls back to the default, not a crash.
        prompt = _build_translate_prompt("", "auto", True)
        assert f"into {DEFAULT_TARGET_LANGUAGE}" in prompt

    def test_source_language_named_when_not_auto(self):
        prompt = _build_translate_prompt("English", "Spanish", True)
        assert "from Spanish" in prompt

    def test_source_auto_omits_from_clause(self):
        prompt = _build_translate_prompt("English", "auto", True)
        assert "from auto" not in prompt
        assert "from " not in prompt.split("into English")[0]

    def test_guardrails_always_present(self):
        for combo in [("English", "auto", True), ("German", "es", False)]:
            prompt = _build_translate_prompt(*combo)
            assert _TRANSLATE_GUARDRAIL in prompt
            assert "Output ONLY" in prompt

    def test_preserve_names_toggle(self):
        on = _build_translate_prompt("English", "auto", True)
        off = _build_translate_prompt("English", "auto", False)
        assert _PRESERVE_NAMES_MARKER in on
        assert _PRESERVE_NAMES_MARKER not in off


class TestBuildTranslatePromptFromConfig:
    def test_defaults_when_config_empty(self):
        prompt = build_text_translate_prompt({})
        assert f"into {DEFAULT_TARGET_LANGUAGE}" in prompt
        assert _PRESERVE_NAMES_MARKER in prompt  # preserve_names defaults True

    def test_respects_config_target(self):
        prompt = build_text_translate_prompt({"target_language": "Portuguese"})
        assert "into Portuguese" in prompt

    def test_respects_disabled_preserve_names(self):
        prompt = build_text_translate_prompt({"preserve_names": False})
        assert _PRESERVE_NAMES_MARKER not in prompt


class TestBuildReviewPrompt:
    def test_target_language_appears(self):
        prompt = _build_review_prompt("French", "auto")
        assert "French" in prompt
        assert _REVIEW_GUARDRAIL in prompt

    def test_compares_against_source_context(self):
        prompt = _build_review_prompt("English", "auto")
        # The review must instruct the model to read the source from Context.
        assert "Context" in prompt
        assert "draft" in prompt.lower()

    def test_source_language_named_when_not_auto(self):
        prompt = _build_review_prompt("English", "Spanish")
        assert "Spanish" in prompt

    def test_review_from_config(self):
        prompt = build_text_translate_review_prompt({"target_language": "Italian"})
        assert "Italian" in prompt


class TestTranslateRegistration:
    def test_tool_registered(self):
        assert "text_translate" in TOOLS
        assert "text_translate" in TOOL_DEFS

    def test_tool_metadata(self):
        tool_def = TOOL_DEFS["text_translate"]
        assert tool_def.display_name == "Translate Text"
        assert tool_def.category == "llm"
        assert tool_def.uses_llm is True
        assert tool_def.supports_batch is True
        assert tool_def.default_prompt
        assert _TRANSLATE_GUARDRAIL in tool_def.default_prompt
        assert callable(tool_def.prompt_builder)

    def test_language_and_model_are_user_editable(self):
        """Config must expose model + prompt override (from BASE_CONFIG_SCHEMA)
        plus the language fields — nothing hard-coded."""
        schema = TOOL_DEFS["text_translate"].config_schema
        assert "provider_name" in schema
        assert "model_name" in schema
        assert "prompt" in schema
        for key in TEXT_TRANSLATE_CONFIG:
            assert key in schema
        # Target language ships an editable default, not a literal.
        assert schema["target_language"]["default"] == DEFAULT_TARGET_LANGUAGE

    def test_has_required_text_ports(self):
        tool_def = TOOL_DEFS["text_translate"]
        in_ids = {p.id for p in tool_def.input_ports}
        assert "text" in in_ids
        text_port = next(p for p in tool_def.input_ports if p.id == "text")
        assert text_port.required is True
        out_ids = {p.id for p in tool_def.output_ports}
        assert "text" in out_ids


class TestReviewRegistration:
    def test_tool_registered(self):
        assert "text_translate_review" in TOOLS
        assert "text_translate_review" in TOOL_DEFS

    def test_tool_metadata(self):
        tool_def = TOOL_DEFS["text_translate_review"]
        assert tool_def.display_name == "Translate Review"
        assert tool_def.category == "llm"
        assert tool_def.uses_llm is True
        assert tool_def.default_prompt
        assert _REVIEW_GUARDRAIL in tool_def.default_prompt
        assert callable(tool_def.prompt_builder)

    def test_language_and_model_are_user_editable(self):
        schema = TOOL_DEFS["text_translate_review"].config_schema
        assert "provider_name" in schema
        assert "model_name" in schema
        assert "prompt" in schema
        for key in TEXT_TRANSLATE_REVIEW_CONFIG:
            assert key in schema

    def test_text_input_is_the_draft(self):
        tool_def = TOOL_DEFS["text_translate_review"]
        in_ids = {p.id for p in tool_def.input_ports}
        assert "text" in in_ids  # the draft translation
        assert "context" in in_ids  # the original source
        text_port = next(p for p in tool_def.input_ports if p.id == "text")
        assert text_port.required is True
