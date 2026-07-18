from fichero.workflows.tools.describe import build_describe_prompt


def test_describe_prompt_uses_focus_with_fallback_detail_level() -> None:
    prompt = build_describe_prompt({"detail_level": "unknown", "focus": "marginalia"})

    assert "Provide a detailed visual description" in prompt
    assert "Focus particularly on: marginalia" in prompt
