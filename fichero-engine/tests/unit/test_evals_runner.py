"""Tests for evals/run.py check kinds (#817).

The harness itself is stdlib-only; these verify each check kind grades
correctly without needing an LLM call.
"""

from __future__ import annotations

import sys
from pathlib import Path

# evals/ lives outside src/ — add to path so test can import it.
_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from evals.run import _apply_check, _word_count  # noqa: E402


class TestWordCount:
    def test_simple_words(self):
        assert _word_count("one two three") == 3

    def test_punctuation_ignored(self):
        assert _word_count("hello, world! 42 is a number.") == 6

    def test_empty(self):
        assert _word_count("") == 0


class TestContains:
    def test_pass(self):
        r = _apply_check(
            {"kind": "contains", "value": "Chocó", "rationale": "x"},
            "Mentions Chocó region.",
        )
        assert r.passed

    def test_fail(self):
        r = _apply_check(
            {"kind": "contains", "value": "Bogotá", "rationale": "x"},
            "Mentions Chocó region only.",
        )
        assert not r.passed


class TestNotContains:
    def test_pass(self):
        r = _apply_check(
            {"kind": "not_contains", "value": "tapestry", "rationale": "x"},
            "A clean evidentiary catalogue entry.",
        )
        assert r.passed

    def test_fail(self):
        r = _apply_check(
            {"kind": "not_contains", "value": "tapestry", "rationale": "x"},
            "A vibrant tapestry of mining.",
        )
        assert not r.passed


class TestRegex:
    def test_match_pass(self):
        r = _apply_check(
            {"kind": "regex_match", "value": r"\d{4}", "rationale": "x"},
            "in 1930 the file was opened",
        )
        assert r.passed

    def test_no_match_pass(self):
        r = _apply_check(
            {"kind": "regex_no_match", "value": r"\bTODO\b", "rationale": "x"},
            "Final narrative without placeholders.",
        )
        assert r.passed

    def test_no_match_fail(self):
        r = _apply_check(
            {"kind": "regex_no_match", "value": r"\bTODO\b", "rationale": "x"},
            "Draft with TODO markers.",
        )
        assert not r.passed


class TestWordCountBetween:
    def test_in_range(self):
        r = _apply_check(
            {"kind": "word_count_between", "min": 5, "max": 10, "rationale": "x"},
            "one two three four five six seven",
        )
        assert r.passed

    def test_too_few(self):
        r = _apply_check(
            {"kind": "word_count_between", "min": 5, "max": 10, "rationale": "x"},
            "one two",
        )
        assert not r.passed

    def test_too_many(self):
        r = _apply_check(
            {"kind": "word_count_between", "min": 5, "max": 7, "rationale": "x"},
            "one two three four five six seven eight nine",
        )
        assert not r.passed


class TestStartsWith:
    def test_string_value(self):
        r = _apply_check(
            {"kind": "starts_with", "value": "Demanda", "rationale": "x"},
            "Demanda por heridas.",
        )
        assert r.passed

    def test_list_value_pass(self):
        r = _apply_check(
            {"kind": "starts_with", "value": ["Lawsuit", "Demanda"],
             "rationale": "x"},
            "Demanda por heridas.",
        )
        assert r.passed

    def test_list_value_fail(self):
        r = _apply_check(
            {"kind": "starts_with", "value": ["Lawsuit", "Demanda"],
             "rationale": "x"},
            "In the Chocó region a vibrant tapestry…",
        )
        assert not r.passed

    def test_ignores_leading_whitespace(self):
        r = _apply_check(
            {"kind": "starts_with", "value": "Demanda", "rationale": "x"},
            "   \n\nDemanda por heridas.",
        )
        assert r.passed


class TestRatioToGold:
    def test_close_pass(self):
        r = _apply_check(
            {"kind": "ratio_to_gold", "value": "hello world", "min": 0.3,
             "rationale": "x"},
            "hello cruel world",
        )
        assert r.passed

    def test_distant_fail(self):
        r = _apply_check(
            {"kind": "ratio_to_gold", "value": "hello world", "min": 0.9,
             "rationale": "x"},
            "completely different text here",
        )
        assert not r.passed


class TestUnknownKind:
    def test_unknown_returns_failed_result(self):
        r = _apply_check(
            {"kind": "no_such_check", "rationale": "x"},
            "anything",
        )
        assert not r.passed
        assert "unknown check kind" in r.detail


class TestCriteriaFilesParse:
    """Every shipped criteria file must be valid YAML + name a real
    scenario file."""

    def test_all_criteria_files_load(self):
        import yaml
        criteria_dir = _REPO_ROOT / "evals" / "criteria"
        scenarios_dir = _REPO_ROOT / "evals" / "scenarios"
        for path in criteria_dir.glob("*.yaml"):
            data = yaml.safe_load(path.read_text())
            assert "tool" in data, f"{path}: missing 'tool'"
            assert "scenario" in data, f"{path}: missing 'scenario'"
            assert "checks" in data, f"{path}: missing 'checks'"
            scenario_path = scenarios_dir / f"{data['scenario']}.txt"
            assert scenario_path.exists(), (
                f"{path}: references missing scenario {scenario_path}"
            )
            for check in data["checks"]:
                assert "kind" in check, (
                    f"{path}: every check needs a 'kind' — got {check}"
                )
