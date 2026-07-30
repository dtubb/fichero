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
