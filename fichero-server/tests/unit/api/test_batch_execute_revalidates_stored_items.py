"""A STORED batch item is validated before it runs (#4500 / #4467).

#4500 added selection validation to `CreateBatchRequest`. That closed the
create door and left the execute door open: `/execute` and `/retry` read items
already PERSISTED in the batch store and hand them straight to
`build_initial_state`. So a batch created before that validation existed — or
written by any other path — still ran unchecked, resolving zero documents while
reporting every item complete.

That is #4467's shape at batch scale, and worse: a batch's whole appeal is that
you do not watch it, so "20 runs completed" over nothing looks like success
until someone opens the library.

The fix re-runs the SAME validator at the execute boundary, so this is a second
CALL SITE for one rule rather than a second rule.
"""

from __future__ import annotations

import pytest

from fichero_server.execution.batch import _validate_batch_item_inputs


class TestAStoredItemIsCheckedBeforeItRuns:
    def test_an_unread_target_key_is_refused(self):
        """The #4467 payload. `files` is read by nothing, so this run would
        process zero documents and report success."""
        with pytest.raises(ValueError) as caught:
            _validate_batch_item_inputs({"files": ["doc-9"]}, "wf-1")
        assert "#4467" in str(caught.value)

    @pytest.mark.parametrize("key", ["documents", "docs", "doc_ids", "document_ids"])
    def test_every_plausible_wrong_key_is_refused(self, key):
        with pytest.raises(ValueError):
            _validate_batch_item_inputs({key: ["doc-9"]}, "wf-1")

    def test_a_real_selection_is_allowed_and_resolves_to_those_documents(self):
        """The fix must refuse the broken shape, not everything.

        Asserts what the accepted inputs MEAN, not merely that nothing raised:
        a test whose only claim is "no exception" cannot tell a working
        validator from one that was deleted.
        """
        from fichero_server.api.routes.workflow_execution.schemas import (
            ExecuteWorkflowRequest,
        )

        inputs = {"selected_doc_ids": ["doc-9"]}
        _validate_batch_item_inputs(inputs, "wf-1")
        resolved = ExecuteWorkflowRequest(workflow_id="wf-1", inputs=inputs)
        assert resolved.selection is not None
        assert resolved.selection.ids == ["doc-9"]

    def test_inputs_with_no_targeting_at_all_are_allowed(self):
        """A workflow whose source node needs no explicit selection is legal;
        refusing it would trade a silent no-op for a broken feature."""
        from fichero_server.api.routes.workflow_execution.schemas import (
            ExecuteWorkflowRequest,
        )

        for inputs in ({"prompt": "hello"}, {}):
            _validate_batch_item_inputs(inputs, "wf-1")
            assert (
                ExecuteWorkflowRequest(workflow_id="wf-1", inputs=inputs).selection
                is None
            ), "no targeting should mean no selection, not a fabricated one"

    def test_it_RAISES_rather_than_returning_a_flag(self):
        """#4467's doctrine: refuse, do not quietly succeed at nothing. A
        caller that has to remember to check a boolean is a caller that will
        forget."""
        with pytest.raises(ValueError):
            _validate_batch_item_inputs({"files": ["doc-9"]}, "wf-1")


class TestItIsTheSameValidatorNotACopy:
    """Two validators for one concept is the defect class behind #4403, #4415
    and #4480. This asserts the batch path defers to the execute boundary
    rather than reimplementing its rules."""

    def test_it_defers_to_ExecuteWorkflowRequest(self):
        import inspect

        import fichero_server.execution.batch as batch_module

        source = inspect.getsource(batch_module._validate_batch_item_inputs)
        assert "ExecuteWorkflowRequest" in source, (
            "the batch validator no longer constructs the real request model; "
            "if it now has its own rules they will drift from the boundary's"
        )

    def test_a_rule_added_to_the_boundary_reaches_batches(self):
        """Demonstrates inheritance rather than asserting it: the unread-key
        rule lives in ExecuteWorkflowRequest and fires here without the batch
        path knowing anything about it."""
        from fichero_server.api.routes.workflow_execution.schemas import (
            UNREAD_TARGET_INPUT_KEYS,
        )

        for key in UNREAD_TARGET_INPUT_KEYS:
            with pytest.raises(ValueError):
                _validate_batch_item_inputs({key: ["doc-9"]}, "wf-1")
