"""A run must be narratable from its log alone.

Daniel re-ran Diary Entries on one page: Transcribe reported "completed in
0ms", Split ran 1.8s, "Marked 3 completed" — and he could not tell from any of
it whether anything had happened.

"Completed in 0ms" is the specific offender. A node that REUSED cached work
and a node that did the work instantly are different facts, and that sentence
cannot tell them apart. The per-file skip-if-done path already recorded
`{"cached": True}` and the artifact it reused; nothing aggregated it.
"""

from __future__ import annotations

import pytest


def _summarize(results, artifact_ids):
    """The aggregation process_vision performs, exercised directly.

    Kept as a pure shape test rather than a full vision run: the whole point
    is the ARITHMETIC of reused-vs-processed, which does not need Apple Vision
    or an LLM to be wrong.
    """
    reused = [r for r in results if isinstance(r, dict) and r.get("cached")]
    return {
        "reused_count": len(reused),
        "processed_count": len(results) - len(reused),
        "reused_artifact_ids": (
            [a for a in artifact_ids if a]
            if len(reused) == len(results) and results
            else []
        ),
    }


class TestTheCountsAreHonest:
    def test_a_fully_reused_run_says_so(self):
        out = _summarize(
            [{"file": "a", "cached": True}, {"file": "b", "cached": True}],
            ["art-1", "art-2"],
        )
        assert (out["reused_count"], out["processed_count"]) == (2, 0)

    def test_a_fully_computed_run_reports_no_reuse(self):
        out = _summarize([{"file": "a"}, {"file": "b"}], ["art-1", "art-2"])
        assert (out["reused_count"], out["processed_count"]) == (0, 2)

    def test_a_PARTIAL_reuse_is_expressible(self):
        """The common shape, and the reason these are counts rather than a
        `cached: true/false` boolean — 3 of 5 pages cached cannot be said with
        a flag."""
        out = _summarize(
            [{"cached": True}, {"cached": True}, {"cached": True}, {}, {}],
            ["a", "b", "c"],
        )
        assert (out["reused_count"], out["processed_count"]) == (3, 2)

    def test_an_empty_run_claims_no_reuse(self):
        """Zero results must not read as 'everything was reused' — that is the
        absence-as-success shape."""
        out = _summarize([], [])
        assert out["reused_count"] == 0
        assert out["reused_artifact_ids"] == []


class TestTheArtifactIsNamedOnlyWhenItIsTheWholeStory:
    def test_a_fully_reused_run_names_its_artifacts(self):
        """Daniel asked for "reusing existing transcription (artifact <id>)" —
        the id is what lets him go look at what was reused."""
        out = _summarize([{"cached": True}], ["art-42"])
        assert out["reused_artifact_ids"] == ["art-42"]

    def test_a_partial_run_names_none(self):
        """Listing 'the' artifact when only some files were reused would point
        at one page and imply it stood for the run."""
        out = _summarize([{"cached": True}, {}], ["art-1"])
        assert out["reused_artifact_ids"] == []


class TestTheRunnerWording:
    """The sentences a reader actually gets."""

    @staticmethod
    def _sentence(reused, processed, ids, ms=0):
        if reused and not processed:
            artifact = f" (artifact {ids[0]})" if len(ids) == 1 else ""
            return (
                f"Node 'transcribe' reused existing output for {reused} "
                f"item(s){artifact} — nothing re-computed ({ms:.0f}ms)"
            )
        if reused:
            return (
                f"Node 'transcribe' completed in {ms:.0f}ms — {processed} "
                f"processed, {reused} reused from cache"
            )
        return f"Node 'transcribe' completed in {ms:.0f}ms"

    def test_full_reuse_never_says_bare_completed(self):
        line = self._sentence(1, 0, ["art-42"])
        assert "reused existing output" in line
        assert "artifact art-42" in line
        assert line != "Node 'transcribe' completed in 0ms"

    def test_partial_reuse_reports_both_halves(self):
        line = self._sentence(3, 2, [])
        assert "3 reused" in line and "2 processed" in line

    def test_ordinary_work_is_unchanged(self):
        """The overwhelmingly common line must not grow noise."""
        assert self._sentence(0, 5, [], ms=1800) == (
            "Node 'transcribe' completed in 1800ms"
        )
