"""Trusted coverage (#6970, `hands.metric.trusted-coverage`). Offline: no engine, no model."""

from __future__ import annotations

import importlib.util
import random
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
_spec = importlib.util.spec_from_file_location("blind_hands_trusted_coverage", REPO_ROOT / "scripts" / "blind_hands" / "trusted_coverage.py")
c = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(c)


def _lines(n_good, n_bad, conf_of):
    """n_good lines with no errors and n_bad lines with 50% errors, 100 reference characters each."""
    rows = [{"edits": 0, "chars": 100, "confidence": conf_of(i, True)} for i in range(n_good)]
    rows += [{"edits": 50, "chars": 100, "confidence": conf_of(i, False)} for i in range(n_bad)]
    return rows


def test_a_confidence_that_ranks_perfectly_gives_the_largest_prefix_at_two_percent():
    rows = _lines(60, 40, lambda i, good: 0.9 if good else 0.1)
    r = c.trusted_coverage(rows)
    # pooled, not per line: two bad lines still leave 100 edits in 6200 characters (1.6%), a third makes 2.4%
    assert r["trusted_coverage"] == 0.62
    assert r["risk_coverage"][-1] == {"coverage": 1.0, "cer": 0.2}


def test_a_random_confidence_gives_nearly_none():
    rng = random.Random(3)
    rows = _lines(60, 40, lambda i, good: rng.random())
    assert c.trusted_coverage(rows)["trusted_coverage"] < 0.1


def test_a_reader_with_no_confidence_has_no_trusted_coverage():
    rows = _lines(5, 5, lambda i, good: None)
    assert c.trusted_coverage(rows)["trusted_coverage"] == "no confidence"
    assert c.trusted_coverage(rows)["risk_coverage"] == []


def test_a_partly_missing_confidence_is_refused():
    import pytest
    rows = _lines(5, 5, lambda i, good: 0.5 if i else None)
    with pytest.raises(ValueError):
        c.trusted_coverage(rows)


def test_no_prefix_under_the_threshold_gives_zero():
    rows = [{"edits": 10, "chars": 100, "confidence": 0.9}]
    assert c.trusted_coverage(rows)["trusted_coverage"] == 0.0
