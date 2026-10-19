"""Find Lines read '0% overlap' for a candidate that found lines, because the other candidate (Apple Vision) had failed
and found none (owner, 2026-10-19; `source.onboard.stages.compare-results-per-model`). Overlap is measured against candidates that
found shapes; with none to compare with it says so in words, never 0%."""
from __future__ import annotations

from fichero_server.recipes.samples import _measure

LINE = [0.1, 0.1, 0.5, 0.05]


def _run(boxes):
    return {"boxes": {"p1": boxes}, "items": ["line"] * len(boxes)}


def test_a_candidate_that_found_nothing_is_not_an_overlap_of_zero():
    [kraken, vision] = _measure(None, "find-lines", [_run([LINE, LINE]), _run([])])
    assert kraken["agreement"] is None
    assert "nothing to compare with" in kraken["not_measured"]
    assert vision["agreement"] == 0.0 or vision["agreement"] is None  # it found none: nothing of its own to overlap


def test_two_candidates_that_found_lines_still_overlap():
    [one, two] = _measure(None, "find-lines", [_run([LINE]), _run([LINE])])
    assert one["agreement"] == 1.0 and two["agreement"] == 1.0 and "not_measured" not in one
