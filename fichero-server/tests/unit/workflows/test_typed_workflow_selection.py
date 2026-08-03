"""A run must declare what the user pointed at (#4397 #4396 #4427).

`selected_doc_ids` rode untyped inside `ExecuteWorkflowRequest.inputs`, a
`dict[str, Any]`. There was no schema for the selection AT ALL — not a weak
contract, an absent one. That is why #4396 was possible: a client sent a whole
folder when the user had picked one file, and nothing could reject it, because
there was nothing to violate.

The point is not that the field is typed. It is that it says what the user
POINTED AT rather than a pre-resolved id list. A flat `list[str]` would have
fixed the type and kept the wrong division of labour — the client still
deciding what a folder means, the server still obliged to trust it.

Nothing here skips.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from fichero_server.api.routes.workflow.batch import CreateBatchRequest
from fichero_server.api.routes.workflow_execution.schemas import (
    ExecuteWorkflowRequest,
)
from fichero_server.workflows.selection import SelectionKind, WorkflowSelection


class TestTheShapeIsValidated:
    """The first place in the system that can refuse an incoherent request."""

    def test_a_folder_run_names_exactly_one_folder(self):
        selection = WorkflowSelection(kind=SelectionKind.folder, ids=["caja-3"])
        assert selection.container_id == "caja-3"

    def test_a_folder_run_with_many_ids_is_rejected(self):
        """#4396, made unrepresentable rather than merely fixed.

        A client that has already expanded a folder is describing a different
        run than the user asked for. It can still send those ids — but only
        as `documents`, which is what they honestly are.
        """
        with pytest.raises(ValidationError) as caught:
            WorkflowSelection(
                kind=SelectionKind.folder,
                ids=["caja-3", "doc-1", "doc-2"],
            )
        message = str(caught.value)
        assert "single container" in message
        assert "kind=documents instead" in message, (
            "the error must say what the client SHOULD have sent, or it is a "
            "refusal without a remedy"
        )

    def test_a_collection_run_is_held_to_the_same_rule(self):
        with pytest.raises(ValidationError):
            WorkflowSelection(
                kind=SelectionKind.collection, ids=["col-1", "col-2"]
            )

    def test_an_explicit_document_set_may_hold_many_ids(self):
        selection = WorkflowSelection(
            kind=SelectionKind.documents, ids=["d1", "d2", "d3"]
        )
        assert len(selection.ids) == 3
        assert selection.container_id is None, (
            "an explicit document set is not scoped to a container — claiming "
            "one would invite folder-level output onto an arbitrary member"
        )

    def test_an_empty_selection_is_rejected(self):
        """A missing argument, not a scope."""
        with pytest.raises(ValidationError) as caught:
            WorkflowSelection(kind=SelectionKind.documents, ids=[])
        assert "at least one id" in str(caught.value)

    def test_blank_ids_are_not_a_selection(self):
        with pytest.raises(ValidationError):
            WorkflowSelection(kind=SelectionKind.documents, ids=["", "   "])

    def test_ids_are_cleaned_not_silently_dropped(self):
        selection = WorkflowSelection(
            kind=SelectionKind.documents, ids=[" d1 ", "d2"]
        )
        assert selection.ids == ["d1", "d2"]

    def test_an_unknown_kind_is_rejected(self):
        """The enum is the point: a vocabulary a client can misspell will
        eventually be misspelled, and it should fail at the boundary."""
        with pytest.raises(ValidationError):
            WorkflowSelection(kind="everything", ids=["d1"])


class TestTheRequestCarriesIt:
    def test_an_explicit_selection_is_preserved(self):
        request = ExecuteWorkflowRequest(
            workflow_id="wf-1",
            selection=WorkflowSelection(kind=SelectionKind.folder, ids=["caja-3"]),
        )
        assert request.selection.kind is SelectionKind.folder
        assert request.selection.container_id == "caja-3"

    def test_a_folder_claim_with_many_ids_is_rejected_at_the_request(self):
        """The boundary that #4396 went through. This is the assertion that
        makes the whole field worth having."""
        with pytest.raises(ValidationError):
            ExecuteWorkflowRequest(
                workflow_id="wf-1",
                selection={"kind": "folder", "ids": ["caja-3", "d1", "d2"]},
            )


class TestTheLegacyAdapter:
    """One adapter at the boundary, so everything downstream sees only the
    typed field — not a try-new-then-old chain at each use site."""

    def test_legacy_selected_doc_ids_becomes_a_typed_document_set(self):
        request = ExecuteWorkflowRequest(
            workflow_id="wf-1",
            inputs={"selected_doc_ids": ["d1", "d2"]},
        )
        assert request.selection is not None
        assert request.selection.kind is SelectionKind.documents
        assert request.selection.ids == ["d1", "d2"]

    def test_the_adapter_cannot_launder_a_flat_list_into_a_folder_claim(self):
        """The property that keeps this from being a compatibility shim.

        A legacy request can only ever produce `documents` — the honest
        description of a flat id list. It can never CLAIM to be a folder run,
        so the adapter cannot manufacture the assertion #4396 needed to make.
        """
        request = ExecuteWorkflowRequest(
            workflow_id="wf-1",
            inputs={"selected_doc_ids": ["caja-3"]},
        )
        assert request.selection.kind is SelectionKind.documents
        assert request.selection.container_id is None

    def test_an_explicit_selection_wins_over_the_legacy_key(self):
        request = ExecuteWorkflowRequest(
            workflow_id="wf-1",
            inputs={"selected_doc_ids": ["ignored"]},
            selection=WorkflowSelection(kind=SelectionKind.folder, ids=["caja-3"]),
        )
        assert request.selection.container_id == "caja-3"
        assert request.selection.ids == ["caja-3"]

    def test_a_request_with_no_selection_at_all_is_allowed(self):
        """Workflows with no document input are legitimate (#2244/#2245) and
        must not be forced to invent a scope."""
        request = ExecuteWorkflowRequest(workflow_id="wf-1")
        assert request.selection is None

    def test_an_empty_legacy_list_does_not_fabricate_a_selection(self):
        request = ExecuteWorkflowRequest(
            workflow_id="wf-1", inputs={"selected_doc_ids": []}
        )
        assert request.selection is None, (
            "an empty list is not a selection; inventing one would report a "
            "scope the user never chose"
        )


class TestUnreadTargetKeysAreRejected:
    """#4467: targets under a key nothing reads must fail at the boundary.

    fichero-mcp sent `inputs={"files": [doc_id]}` — a key no node reads from
    execute inputs — and every run completed green with zero documents and
    zero artifacts. A run that succeeds at nothing is the worst failure shape
    this project knows; the request is now rejected where it can still be
    attributed to the caller.
    """

    def test_inputs_files_alone_is_rejected_not_silently_dropped(self):
        with pytest.raises(ValidationError) as caught:
            ExecuteWorkflowRequest(workflow_id="wf-1", inputs={"files": ["doc-1"]})
        message = str(caught.value)
        assert "selection" in message, (
            "the error must say what the client SHOULD have sent"
        )
        assert "#4467" in message

    @pytest.mark.parametrize(
        "key", ["documents", "docs", "doc_ids", "document_ids"]
    )
    def test_every_plausible_wrong_key_is_rejected(self, key):
        with pytest.raises(ValidationError):
            ExecuteWorkflowRequest(workflow_id="wf-1", inputs={key: ["doc-1"]})

    def test_a_real_selection_beside_a_stray_key_is_allowed(self):
        """Only a request whose ONLY targeting is unread is incoherent."""
        request = ExecuteWorkflowRequest(
            workflow_id="wf-1",
            inputs={"files": ["doc-1"], "selected_doc_ids": ["doc-1"]},
        )
        assert request.selection is not None

    def test_empty_stray_values_do_not_reject(self):
        """`{"files": []}` carries no target; refusing it would break callers
        that pass empty scaffolding dicts."""
        request = ExecuteWorkflowRequest(workflow_id="wf-1", inputs={"files": []})
        assert request.selection is None

    def test_non_target_inputs_pass_untouched(self):
        request = ExecuteWorkflowRequest(
            workflow_id="wf-1", inputs={"prompt": "hello", "temperature": 0.2}
        )
        assert request.selection is None


class TestTheBatchPathUsesTheSameBoundary:
    """#4500: batch items reached NEITHER validator.

    `CreateBatchRequest` had no `selection` field at all, and `BatchManager`
    handed `item.inputs` straight to `build_initial_state` without ever
    constructing an `ExecuteWorkflowRequest`. So every rule above — the
    #4396 folder-with-many-ids refusal, #4467's unread target keys — was
    simply absent on the batch path. Every other execute path was guarded;
    this one was a hole with the guarantee written on the outside of it.

    These live beside the direct-execute tests deliberately. One boundary,
    one rule, one place its behaviour is pinned: a batch-shaped copy of these
    assertions could pass while the batch path drifted, which is the shape of
    the original defect.
    """

    def test_a_batch_claiming_a_folder_with_many_ids_is_rejected(self):
        with pytest.raises(ValidationError) as caught:
            CreateBatchRequest(
                workflow_id="wf-1",
                items=[{}],
                selection={"kind": "folder", "ids": ["caja-3", "doc-1", "doc-2"]},
            )
        message = str(caught.value)
        assert "single container" in message
        assert "kind=documents instead" in message

    def test_the_same_claim_is_rejected_on_a_direct_execute(self):
        """The point is not that batch refuses it — it is that both refuse it
        for the same stated reason. Divergent messages mean divergent rules."""
        with pytest.raises(ValidationError) as batch_error:
            CreateBatchRequest(
                workflow_id="wf-1",
                items=[{}],
                selection={"kind": "folder", "ids": ["caja-3", "doc-1"]},
            )
        with pytest.raises(ValidationError) as execute_error:
            ExecuteWorkflowRequest(
                workflow_id="wf-1",
                selection={"kind": "folder", "ids": ["caja-3", "doc-1"]},
            )
        assert "single container" in str(batch_error.value)
        assert "single container" in str(execute_error.value)

    def test_a_batch_item_with_only_an_unread_target_key_is_rejected(self):
        """#4467 on the batch path. Without this the batch runs green over
        nothing, N times."""
        with pytest.raises(ValidationError) as caught:
            CreateBatchRequest(workflow_id="wf-1", items=[{"files": ["doc-1"]}])
        assert "#4467" in str(caught.value)

    def test_the_rejection_names_which_item_was_wrong(self):
        """"A batch was rejected" is not actionable when the caller sent two
        hundred of them."""
        with pytest.raises(ValidationError) as caught:
            CreateBatchRequest(
                workflow_id="wf-1",
                items=[
                    {"selected_doc_ids": ["doc-1"]},
                    {"selected_doc_ids": ["doc-2"]},
                    {"docs": ["doc-3"]},
                ],
            )
        assert "batch item 2" in str(caught.value)

    def test_a_coherent_folder_batch_is_accepted_and_scoped_to_the_folder(self):
        request = CreateBatchRequest(
            workflow_id="wf-1",
            items=[{}],
            selection={"kind": "folder", "ids": ["caja-3"]},
        )
        assert request.selection.container_id == "caja-3"
        # Mirrors the runner: the validated selection is what the run is
        # scoped to, so the item carries it where build_initial_state reads it.
        assert request.items[0]["selected_doc_ids"] == ["caja-3"]

    def test_per_item_targeting_is_not_overwritten_by_the_batch_selection(self):
        """Per-item ids are what the items are FOR. Replacing them with the
        batch's would silently re-scope every item to the same documents —
        trading a missing guard for a scope bug."""
        request = CreateBatchRequest(
            workflow_id="wf-1",
            items=[{"selected_doc_ids": ["doc-1"]}, {"selected_doc_ids": ["doc-2"]}],
            selection={"kind": "documents", "ids": ["doc-1", "doc-2"]},
        )
        assert request.items[0]["selected_doc_ids"] == ["doc-1"]
        assert request.items[1]["selected_doc_ids"] == ["doc-2"]

    def test_a_batch_with_no_selection_at_all_still_works(self):
        """The field is optional: existing callers that pass legacy per-item
        ids keep working, or the fix breaks every batch in the field."""
        request = CreateBatchRequest(
            workflow_id="wf-1", items=[{"selected_doc_ids": ["doc-1"]}]
        )
        assert request.selection is None
        assert request.items[0]["selected_doc_ids"] == ["doc-1"]

    def test_non_target_item_inputs_pass_through_untouched(self):
        request = CreateBatchRequest(
            workflow_id="wf-1", items=[{"prompt": "hello", "temperature": 0.2}]
        )
        assert request.items[0] == {"prompt": "hello", "temperature": 0.2}
