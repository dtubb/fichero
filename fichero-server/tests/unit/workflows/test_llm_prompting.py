"""Coverage for the pure prompt-building / output-parsing helpers in
``fichero_server.workflows.tools.llm_prompting`` (previously untested). No LLM/network:
these are string transforms used by ``process_text``.

Includes a regression for a fixed data-corruption bug: an empty value used to
fuzzy-match (and get replaced by) the first reference value.
"""

from __future__ import annotations

import pytest

from fichero_server.workflows.tools.llm_prompting import (
    apply_reference_matching,
    build_context_section,
    build_output_constraint,
    build_reference_section,
    build_thinking_preamble,
    match_to_reference,
    parse_output,
)


# ===========================================================================
# build_output_constraint
# ===========================================================================


def test_output_constraint_boolean_and_number():
    assert "yes or no" in build_output_constraint("boolean")
    assert "single number" in build_output_constraint("number")


def test_output_constraint_choice():
    out = build_output_constraint("choice", {"choices": ["A", "B"]})
    assert '"A", "B"' in out
    # No choices -> empty string.
    assert build_output_constraint("choice", {}) == ""


def test_output_constraint_words_and_list_defaults():
    assert "50 words" in build_output_constraint("words")
    assert "20 words" in build_output_constraint("words", {"max_words": 20})
    assert "up to 10 items" in build_output_constraint("list")


def test_output_constraint_json_and_unknown():
    assert "valid JSON only" in build_output_constraint("json")
    assert "matching: {x}" in build_output_constraint("json", {"schema": "{x}"})
    assert build_output_constraint("text") == ""  # no constraint


# ===========================================================================
# parse_output
# ===========================================================================


@pytest.mark.parametrize(
    "text,expected",
    [("yes", True), ("Yes", True), ("true", True), ("1", True),
     ("no", False), ("false", False), ("0", False)],
)
def test_parse_boolean(text, expected):
    assert parse_output(text, "boolean") is expected


def test_parse_boolean_unparseable_returns_text():
    assert parse_output("maybe", "boolean") == "maybe"


def test_parse_number():
    assert parse_output("$1,234.50", "number") == 1234.5
    assert parse_output("50%", "number") == 50
    assert parse_output("-3", "number") == -3
    assert parse_output("not a number", "number") == "not a number"


def test_parse_list_strips_and_drops_empties():
    assert parse_output("a, b ,, c", "list") == ["a", "b", "c"]
    assert parse_output("x|y|z", "list", {"separator": "|"}) == ["x", "y", "z"]


def test_parse_json_direct_and_embedded():
    assert parse_output('{"a": 1}', "json") == {"a": 1}
    # Embedded in prose -> extracted by first-{ / last-}.
    assert parse_output('here you go: {"a": 1} done', "json") == {"a": 1}
    assert parse_output("[1, 2, 3]", "json") == [1, 2, 3]


def test_parse_json_unparseable_returns_text():
    assert parse_output("not json at all", "json") == "not json at all"


# ===========================================================================
# match_to_reference — incl. the empty-value regression
# ===========================================================================


def test_match_exact_case_insensitive():
    assert match_to_reference("john smith", ["John Smith", "Jane Doe"]) == "John Smith"


def test_match_fuzzy_substring_both_directions():
    assert match_to_reference("Smith", ["John Smith"]) == "John Smith"   # value in ref
    assert match_to_reference("John Smith Jr", ["John Smith"]) == "John Smith"  # ref in value


def test_match_no_match_and_empty_refs():
    assert match_to_reference("Zzz", ["John"]) is None
    assert match_to_reference("x", []) is None


def test_match_fuzzy_disabled():
    assert match_to_reference("Smith", ["John Smith"], fuzzy=False) is None


def test_match_empty_value_does_not_match_first_ref():
    # Regression: '' / whitespace used to fuzzy-match the first reference
    # (because "" is a substring of everything).
    assert match_to_reference("", ["John", "Jane"]) is None
    assert match_to_reference("   ", ["John", "Jane"]) is None


def test_match_skips_empty_reference():
    # An empty reference must not swallow every value.
    assert match_to_reference("John", ["", "Zzz"]) is None


# ===========================================================================
# apply_reference_matching
# ===========================================================================


def test_apply_matches_dict_string_and_list_values():
    result = {"name": "smith", "tags": ["Gold", "unknown"]}
    refs = {"name": ["John Smith"], "tags": ["Gold Mining"]}
    out = apply_reference_matching(result, refs)
    assert out["name"] == "John Smith"          # fuzzy matched
    assert out["tags"][0] == "Gold Mining"      # fuzzy matched
    assert out["tags"][1] == "unknown"          # no match -> kept


def test_apply_passes_through_non_reference_keys():
    out = apply_reference_matching({"other": "x"}, {"name": ["John"]})
    assert out == {"other": "x"}


def test_apply_empty_value_preserved_after_fix():
    # With the fix, an empty field stays empty rather than becoming 'John'.
    out = apply_reference_matching({"name": ""}, {"name": ["John", "Jane"]})
    assert out == {"name": ""}


def test_apply_list_result_matches_against_all_refs():
    out = apply_reference_matching(["gold", "Zzz"], {"a": ["Gold Mining"], "b": ["X"]})
    assert out == ["Gold Mining", "Zzz"]


def test_apply_none_references_returns_unchanged():
    assert apply_reference_matching({"a": 1}, None) == {"a": 1}


# ===========================================================================
# build_reference_section / build_thinking_preamble / build_context_section
# ===========================================================================


def test_reference_section_modes():
    refs = {"names": ["John", "Jane"]}
    assert "only use these exact values" in build_reference_section(refs, "strict")
    assert "prefer these known values" in build_reference_section(refs, "prefer")
    assert "for reference" in build_reference_section(refs, "inform")
    assert build_reference_section(None) == ""
    assert build_reference_section({"names": []}) == ""  # all-empty -> no section


def test_reference_section_truncates_at_twenty():
    section = build_reference_section({"x": [str(i) for i in range(25)]})
    assert "and 5 more" in section


def test_thinking_preamble_levels():
    assert build_thinking_preamble("off") == ""
    assert "step by step" in build_thinking_preamble("medium")
    assert build_thinking_preamble("long")


def test_thinking_preamble_rejects_an_unknown_mode():
    """This test used to assert `build_thinking_preamble("unknown") == ""`.

    That pinned the defect (#4496). Four shipped transcription presets asked
    for `thinking_mode` values outside the enum — `high` and `low` — and each
    silently produced no preamble at all, so the nodes declaring the deepest
    reasoning got none. An unknown mode is a typo in a config, not a request
    for no reasoning, and returning "" made the two indistinguishable.
    """
    with pytest.raises(ValueError, match="unknown"):
        build_thinking_preamble("unknown")


def test_thinking_preamble_delimits_the_reasoning_it_asks_for():
    """The preamble is prepended to prompts that forbid commentary (#4496).

    Asking for undelimited "show your reasoning" in front of "output ONLY the
    transcription" is how 4,518 characters of reasoning ended up stored as a
    transcription. Reasoning must be inside tags a stripper can remove.
    """
    for mode in ("short", "medium", "long"):
        preamble = build_thinking_preamble(mode)
        assert "<think>" in preamble and "</think>" in preamble, mode


def test_context_section_assembles_parts_and_empty():
    out = build_context_section(context="the text", input_metadata={"a": 1},
                                previous_outputs={"transcribe": "T", "skip": ""})
    assert "Document metadata:" in out
    assert "Previous transcribe result:" in out
    assert "skip" not in out  # falsy previous output skipped
    assert "Document text:" in out
    assert build_context_section() == ""  # nothing -> empty
