"""Prompt regressions for transcribe tool instructions."""

from fichero.workflows.tools.transcribe import _build_prompt


def test_transcribe_prompt_explicitly_preserves_diacritics():
    """#1397: accents/diacritics must be preserved exactly."""
    prompt = _build_prompt("es-CO", False)
    lowered = prompt.lower()
    assert "diacrit" in lowered
    assert "do not strip accents" in lowered
