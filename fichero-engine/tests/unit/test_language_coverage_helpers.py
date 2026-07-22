"""Unit coverage for the pure helpers in ``fichero.llm.language_coverage``.

The existing ``test_language_coverage.py`` covers a few derived-JSON / heuristic /
unsupported scenarios end-to-end; this file locks the individual pure functions:
code normalization, score banding, the heuristic score formula, synthetic tier
counts, filename sanitisation, and the coverage-payload parsers. No filesystem
or network (payloads are in-memory dicts).
"""

from __future__ import annotations

import pytest

from fichero.llm.language_coverage import (
    LanguageFitModelSpec as Spec,
    LanguageSpec,
    _find_language_in_list,
    _find_language_payload,
    _heuristic_score,
    _int_value,
    _optional_float,
    _optional_int,
    _safe_filename,
    _synthetic_tier_counts,
    _tier_counts,
    language_spec,
    normalize_language_code,
    normalized_model_id,
    score_band,
)


# ===========================================================================
# normalize_language_code / language_spec / normalized_model_id
# ===========================================================================


@pytest.mark.parametrize(
    "raw,expected",
    [("en-US", "en"), ("pt_BR", "pt"), ("  ZH-Hans ", "zh"), ("FR", "fr"), ("", "")],
)
def test_normalize_language_code(raw, expected):
    assert normalize_language_code(raw) == expected


def test_language_spec_known_and_unknown():
    assert language_spec("en-US").name == "English"
    unknown = language_spec("xx")
    assert unknown.code == "xx"
    assert unknown.name == "xx"


def test_language_spec_empty_is_unknown_placeholder():
    spec = language_spec("")
    assert spec.code == ""
    assert spec.name == "unknown"


def test_normalized_model_id_strips_and_lowercases():
    assert normalized_model_id("OpenAI", "GPT 4o") == "openai/gpt4o"
    assert normalized_model_id("  Meta ", " Llama 3 ") == "meta/llama3"


# ===========================================================================
# score_band boundaries
# ===========================================================================


@pytest.mark.parametrize(
    "score,band",
    [(None, "unknown"), (0.90, "excellent"), (0.95, "excellent"),
     (0.89, "good"), (0.75, "good"), (0.74, "limited"), (0.50, "limited"),
     (0.49, "poor"), (0.0, "poor")],
)
def test_score_band(score, band):
    assert score_band(score) == band


# ===========================================================================
# _heuristic_score
# ===========================================================================


def _lang(script):
    return LanguageSpec(code="x", name="X", script=script)


def test_heuristic_latin_base_with_frontier_boost():
    # Latin base 0.86 + 0.04 frontier-model boost.
    assert _heuristic_score(Spec(provider="openai", model="gpt-4o"), _lang("Latin")) == 0.9


def test_heuristic_llama_penalty():
    # Latin 0.86 - 0.03 llama penalty.
    assert _heuristic_score(Spec(provider="meta", model="llama-3"), _lang("Latin")) == 0.83


def test_heuristic_cjk_specialist_boost():
    # Han 0.66 + 0.10 qwen CJK boost.
    assert _heuristic_score(Spec(provider="alibaba", model="qwen2"), _lang("Han")) == 0.76


def test_heuristic_unknown_script_floor():
    assert _heuristic_score(Spec(provider="x", model="y"), _lang(None)) == 0.5


def test_heuristic_score_is_clamped():
    score = _heuristic_score(Spec(provider="openai", model="gpt-5"), _lang("Latin"))
    assert 0.05 <= score <= 0.95


# ===========================================================================
# _synthetic_tier_counts
# ===========================================================================


@pytest.mark.parametrize("score", [0.05, 0.5, 0.9, 0.95])
def test_synthetic_tier_counts_sum_to_total(score):
    counts = _synthetic_tier_counts(score)
    assert counts.total_chars == 100
    assert counts.tier_0_native + counts.tier_1_embedded + counts.tier_2_byte_fallback == 100
    assert counts.tier_1_embedded >= 0  # never negative from int truncation


def test_synthetic_tier_counts_higher_score_more_native():
    assert _synthetic_tier_counts(0.9).tier_0_native > _synthetic_tier_counts(0.3).tier_0_native


# ===========================================================================
# _safe_filename
# ===========================================================================


def test_safe_filename():
    assert _safe_filename("OpenAI/GPT 4o!") == "openai__gpt__4o"
    assert _safe_filename("..model..") == "model"
    assert _safe_filename("gpt-4o") == "gpt-4o"  # allowed chars preserved


# ===========================================================================
# _find_language_payload / _find_language_in_list
# ===========================================================================


def test_find_payload_flat_dict():
    assert _find_language_payload({"en": {"score": 0.9}}, "en") == {"score": 0.9}


def test_find_payload_nested_containers():
    assert _find_language_payload({"coverage": {"es": {"s": 1}}}, "es") == {"s": 1}
    assert _find_language_payload({"languages": {"de": {"s": 2}}}, "de") == {"s": 2}


def test_find_payload_list_via_results_by_code():
    payload = {"results": [{"code": "fr", "score": 0.7}]}
    assert _find_language_payload(payload, "fr") == {"code": "fr", "score": 0.7}


def test_find_payload_miss_and_non_dict():
    assert _find_language_payload({"coverage": {"en": {}}}, "zz") is None
    assert _find_language_payload(["not", "a", "dict"], "en") is None


def test_find_in_list_matches_by_any_code_field_normalized():
    items = [{"language": "en-US", "v": 1}, {"language_code": "pt_BR", "v": 2}]
    assert _find_language_in_list(items, "en") == {"language": "en-US", "v": 1}
    assert _find_language_in_list(items, "pt") == {"language_code": "pt_BR", "v": 2}
    # Non-dict items are skipped; no match -> None.
    assert _find_language_in_list(["x", {"code": "de"}], "zz") is None


# ===========================================================================
# _tier_counts / _optional_float / _optional_int / _int_value
# ===========================================================================


def test_tier_counts_full_and_alt_keys():
    full = _tier_counts({"tier_0_native": 40, "tier_1_embedded": 30, "tier_2_byte_fallback": 30, "total_chars": 100})
    assert full.tier_0_native == 40 and full.total_chars == 100
    # Alt short keys + total derived from the sum when total is absent.
    alt = _tier_counts({"tier0": 10, "tier1": 20})
    assert alt.total_chars == 30


def test_tier_counts_empty_returns_none():
    # An in-contract empty dict (no tier data) -> None.
    assert _tier_counts({}) is None


def test_optional_float_first_valid_and_none():
    assert _optional_float(None, "x", 3) == 3.0
    assert _optional_float("1.5") == 1.5
    assert _optional_float(None, "nope") is None


def test_optional_int_coercion():
    assert _optional_int("5") == 5
    assert _optional_int(1.9) == 1  # truncates
    assert _optional_int("x") is None
    assert _optional_int(None) is None


def test_int_value_keys_and_default():
    raw = {"tier1": "20", "tier_1": 99}
    assert _int_value(raw, "tier_1_embedded", "tier1", default=0) == 20  # first present + parseable
    assert _int_value({}, "missing", default=7) == 7
