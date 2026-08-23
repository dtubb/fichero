"""What a re-run redoes, and what it may reuse.

Daniel re-ran a page: Transcribe said "completed in 0ms" and he had no way to
know whether anything happened. Then, running the Detect Regions workflow: "if
we rerun region it should redo it."

Two different intents, and conflating them gives you only bad options —
"reuse everything and report 0ms", or "redo everything including a
transcription nobody asked to redo".

  explicit run   the workflow's TERMINAL deliverable redoes its work;
                 upstream dependencies may still reuse. That is what reuse is
                 FOR — a transcription feeding a regions pass should not be
                 redone to satisfy a regions re-run.
  forced run     Option-held: everything recomputes, no exceptions.
"""

from __future__ import annotations

from fichero_server.workflows.builder import _should_recompute

EXITS = {"exit_node_ids": {"detect", "split"}}


class TestTheTerminalDeliverableRedoesItsWork:
    def test_an_exit_node_recomputes_on_an_ordinary_run(self):
        assert _should_recompute({}, "detect", "detect_regions", EXITS) is True

    def test_an_upstream_dependency_may_still_reuse(self):
        """The whole point of reuse: a transcription feeding a regions pass is
        not redone to satisfy a regions re-run."""
        assert _should_recompute({}, "transcribe", "transcribe", EXITS) is False

    def test_a_workflow_with_no_exits_recorded_forces_nothing(self):
        assert _should_recompute({}, "detect", "detect_regions", {}) is False
        assert _should_recompute({}, "detect", "detect_regions", None) is False


class TestAForcedRunOverridesEverything:
    def test_force_recomputes_an_upstream_node_too(self):
        state = {"force_recompute": True}
        assert _should_recompute(state, "transcribe", "transcribe", EXITS) is True

    def test_force_works_even_with_no_exit_information(self):
        assert _should_recompute({"force_recompute": True}, "n", "transcribe", {}) is True

    def test_force_overrides_the_passthrough_exemption(self):
        """Option-held means everything. A passthrough tool has nothing to
        recompute, but the flag must not be silently ignored either."""
        state = {"force_recompute": True}
        assert _should_recompute(state, "agg", "aggregate", EXITS) is True


class TestAPassthroughExitIsNotTheDeliverable:
    """A fan-in aggregator sitting after the real tool would make "exit" the
    wrong node — the thing the user wanted redone is upstream of it."""

    def test_an_aggregator_exit_does_not_count_as_the_deliverable(self):
        exits = {"exit_node_ids": {"agg"}}
        assert _should_recompute({}, "agg", "aggregate", exits) is False

    def test_a_real_tool_at_the_exit_does(self):
        exits = {"exit_node_ids": {"agg"}}
        assert _should_recompute({}, "agg", "detect_regions", exits) is True


class TestTheTwoFlagsAreDistinct:
    def test_skip_cache_and_force_recompute_are_separate_fields(self):
        """Deliberately not merged: sub-workflows set `skip_cache`
        unconditionally, so widening it to mean "force" would make every child
        run re-OCR its pages — minutes of work nobody asked for."""
        from fichero_server.api.routes.workflow_execution.schemas import (
            ExecuteWorkflowRequest,
        )

        fields = ExecuteWorkflowRequest.model_fields
        assert "skip_cache" in fields
        assert "force_recompute" in fields
        assert fields["force_recompute"].default is False

    def test_skip_cache_alone_does_not_force(self):
        assert _should_recompute({"skip_cache": True}, "transcribe", "transcribe", EXITS) is False
