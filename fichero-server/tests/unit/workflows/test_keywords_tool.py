"""Coverage for keyword extraction prompt construction."""

from fichero_server.workflows.tools import keywords as tool


def test_keywords_prompt_scopes_and_defaults():
    technical = tool.build_keywords_prompt({"max_keywords": 4, "scope": "technical"})
    fallback = tool.build_keywords_prompt({"scope": "unknown"})
    assert "4 most important keywords" in technical
    assert "technical terminology" in technical
    assert "15 most important keywords" in fallback
    assert "general topics" in fallback
