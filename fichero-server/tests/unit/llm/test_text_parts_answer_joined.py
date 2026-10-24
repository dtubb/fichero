"""A model that answers as a list of text parts (Gemini 3) reads like one that answers a string: the cloud line read died on
`'list' object has no attribute 'strip'` in a live run (e2e 2026-10-24)."""
from fichero_server.llm import _strip_outer_code_fences


def test_text_parts_are_joined_into_one_string():
    assert _strip_outer_code_fences([{"type": "text", "text": "```json\n[\"a\"]"}, {"type": "text", "text": "\n```"}]) == '["a"]'


def test_a_string_is_as_before_and_other_parts_are_left_alone():
    assert _strip_outer_code_fences("plain") == "plain"
    parts = [{"type": "text", "text": "x"}, {"type": "image_url", "image_url": "u"}]
    assert _strip_outer_code_fences(parts) is parts
