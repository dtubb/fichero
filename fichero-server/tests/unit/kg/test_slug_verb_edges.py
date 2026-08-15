"""Edge-branch coverage for slug_verb (#1803 dedup-key correctness, #1810).

slug_verb produces the predicate slug used as the SVO dedup key (and the RDF
predicate URI fragment). Existing tests cover normal multi-word verbs; these lock
the edge branches that decide whether claims collapse correctly:
empty -> "assertedAbout" fallback, leading-digit -> "v-" URI-safety prefix,
punctuation -> dash with empty-segment collapse, and the all-punctuation case.
"""

from __future__ import annotations

import pytest

from fichero_server.knowledge._common import slug_verb


@pytest.mark.parametrize("verb", ["", "   ", "\t\n"])
def test_empty_or_blank_verb_falls_back_to_asserted_about(verb: str) -> None:
    assert slug_verb(verb) == "assertedAbout"


def test_clean_verb_is_unchanged() -> None:
    assert slug_verb("founded") == "founded"


def test_punctuation_becomes_dashes_with_empty_segments_collapsed() -> None:
    assert slug_verb("took (coach)!") == "took-coach"
    assert slug_verb("a   b") == "a-b"           # whitespace run -> single dash
    assert slug_verb("served---as") == "served-as"  # repeated dashes collapse


def test_leading_digit_gets_uri_safe_v_prefix() -> None:
    assert slug_verb("123abc") == "v-123abc"
    assert slug_verb("1st place") == "v-1st-place"
    assert slug_verb("1933") == "v-1933"


def test_all_punctuation_collapses_to_bare_v_prefix() -> None:
    # Every char is stripped -> empty slug -> the `if not slug` branch yields "v-".
    assert slug_verb("!!!") == "v-"


def test_case_is_normalized_to_lower() -> None:
    assert slug_verb("FOUNDED") == "founded"
    assert slug_verb("Served As") == "served-as"
