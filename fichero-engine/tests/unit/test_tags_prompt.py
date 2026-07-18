from fichero.workflows.tools.tags import build_tags_prompt


def test_tags_prompt_includes_requested_count_and_categories() -> None:
    prompt = build_tags_prompt({"tag_count": 3, "categories": ["flora", "script"]})

    assert "Return 3 relevant keywords/tags" in prompt
    assert "Focus on these categories: flora, script" in prompt
