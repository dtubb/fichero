from fichero.workflows.tools.language_identification import _split_text, _to_markdown


def test_language_identification_preserves_paragraph_chunks_and_renders_summary() -> None:
    chunks = _split_text("uno\n\ndos\n\ntres", 8)
    markdown = _to_markdown("es", [{"code": "es", "confidence": 0.875, "chunk_count": 2}], "local")

    assert chunks == ["uno\n\ndos", "tres"]
    assert "| es | 0.875 | 2 |" in markdown
