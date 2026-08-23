"""Option-held run: recompute everything, ignore every cache.

Daniel re-ran a page and Transcribe reported "completed in 0ms". There WAS a
`skip_cache` flag on the run request — but it bypasses the LangGraph
node-result cache, not the ARTIFACT cache in vision_base. Two different caches,
and the one a user would reach for did not reach the one that short-circuited.

`force_ocr` is the existing per-tool primitive for exactly this: it bypasses
the text-already-present check, the PDF text-layer shortcut AND the artifact
cache. It was only reachable as node config, so it could not be asked for at
run level.
"""

from __future__ import annotations

from fichero_server.workflows.resolver import resolve_inputs


class TestAForcedRunReachesTheTools:
    def test_force_ocr_is_set_when_the_run_is_forced(self):
        resolved = resolve_inputs({}, {"force_recompute": True})
        assert resolved["force_ocr"] is True

    def test_an_ordinary_run_is_untouched(self):
        """The common path must not silently start forcing OCR — that would
        turn every run into minutes of recomputation."""
        assert "force_ocr" not in resolve_inputs({}, {"force_recompute": False})
        assert "force_ocr" not in resolve_inputs({}, {})


class TestExplicitNodeConfigWins:
    def test_a_node_set_to_false_stays_false(self):
        """A run-level convenience must not overrule a choice someone made
        about a specific node."""
        resolved = resolve_inputs({"force_ocr": False}, {"force_recompute": True})
        assert resolved["force_ocr"] is False

    def test_a_node_set_to_true_stays_true(self):
        resolved = resolve_inputs({"force_ocr": True}, {"force_recompute": False})
        assert resolved["force_ocr"] is True


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
        assert "force_ocr" not in resolve_inputs({}, {"skip_cache": True})
