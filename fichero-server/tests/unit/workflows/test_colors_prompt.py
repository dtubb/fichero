from fichero_server.workflows.tools.colors import build_colors_prompt


def test_colors_prompt_defaults_unknown_format_to_hex_instructions() -> None:
    prompt = build_colors_prompt({"color_count": 2, "format": "paint"})

    assert "Extract the 2 most dominant colors" in prompt
    assert 'Use hex codes (e.g., "#FF5733")' in prompt
