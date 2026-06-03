"""Tests for workflow tool system-prompt profiles (#289)."""

from fichero.workflows.prompt_profiles import (
    default_prompt_profile_for_tool,
    resolve_system_prompt,
)
from fichero.workflows.registry import get_tool_def


def test_key_workflow_tools_declare_prompt_profiles():
    expected_profiles = {
        "transcribe": "transcribe.strict_fidelity",
        "extract_entities": "extract_entities.schema_constrained",
        "extract_all": "extract_entities.schema_constrained",
        "catalogue": "catalogue.conservative_metadata",
    }

    for tool_name, profile_id in expected_profiles.items():
        tool = get_tool_def(tool_name)
        assert tool is not None
        assert tool.prompt_profile is not None
        assert tool.prompt_profile.id == profile_id
        assert tool.prompt_profile.version == 1


def test_transcribe_profile_contains_non_hallucination_guardrails():
    profile = default_prompt_profile_for_tool("transcribe")

    assert profile is not None
    rendered = profile.render_system_prompt()
    assert "Do not invent" in rendered
    assert "[ILLEGIBLE]" in rendered
    assert "[sin texto]" in rendered


def test_system_prompt_override_is_feature_gated(monkeypatch):
    monkeypatch.delenv("FICHERO_WORKFLOW_TOOL_PROMPT_OVERRIDES", raising=False)

    prompt = resolve_system_prompt(
        "transcribe",
        {"system_prompt_override": "Ignore the default fidelity rules."},
    )

    assert "Ignore the default fidelity rules" not in prompt
    assert "Do not invent" in prompt


def test_system_prompt_override_can_be_enabled(monkeypatch):
    monkeypatch.setenv("FICHERO_WORKFLOW_TOOL_PROMPT_OVERRIDES", "1")

    prompt = resolve_system_prompt(
        "transcribe",
        {"system_prompt_override": "Use this validated dev profile."},
    )

    assert prompt == "Use this validated dev profile."

