from fichero_server.workflows.tools.quality import build_quality_prompt


def test_quality_prompt_uses_requested_aspects_and_scale() -> None:
    prompt = build_quality_prompt({"aspects": ["sharpness", "noise"], "scale": "percentage"})

    assert "Evaluate these aspects: sharpness, noise" in prompt
    assert "percentage (0-100)" in prompt
