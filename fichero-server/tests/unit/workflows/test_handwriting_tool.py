"""Coverage for handwriting prompt construction."""

from fichero_server.workflows.tools import handwriting as tool


def test_handwriting_prompt_includes_script_guidance_and_diacritic_rule():
    prompt = tool.build_handwriting_prompt(
        {"script": "latin_colonial", "era": "colonial", "language": "es", "handle_diacritics": True}
    )
    assert "latin_colonial" in prompt
    assert "Colonial-era Latin script" in prompt
    assert "Preserve ALL diacritical marks" in prompt
    assert "Output the transcription as plain text" in prompt
