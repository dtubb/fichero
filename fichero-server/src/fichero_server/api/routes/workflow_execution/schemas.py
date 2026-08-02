"""Request/response models and SSE event types for workflow execution."""

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel, Field, model_validator

from fichero_server.workflows.run_status import RunStatus
from fichero_server.workflows.selection import SelectionKind, WorkflowSelection

logger = logging.getLogger(__name__)

# Keys a client might plausibly use to target documents in execute `inputs`,
# none of which any node reads from there. fichero-mcp shipped
# `inputs={"files": [doc_id]}` and every run "completed" green on zero
# documents (#4467). Targets ride in `selection` (or the legacy
# `inputs["selected_doc_ids"]`); anything else is rejected at the boundary
# so a mistargeted run fails loudly instead of succeeding at nothing.
UNREAD_TARGET_INPUT_KEYS = ("files", "documents", "docs", "doc_ids", "document_ids")


class ExecuteWorkflowRequest(BaseModel):
    """Request to execute a workflow."""

    workflow_id: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    thread_id: str | None = None  # Optional - generated if not provided
    checkpoint_ns: str = ""  # Checkpoint namespace for sub-workflows
    interrupt_before: list[str] = Field(
        default_factory=list
    )  # Node IDs to pause before
    interrupt_after: list[str] = Field(default_factory=list)  # Node IDs to pause after
    force_new: bool = (
        False  # If True, ignore provided thread_id and create a fresh execution
    )
    skip_cache: bool = (
        False  # If True, bypass node result cache (still writes new results)
    )
    provider_override: str | None = None  # Optional run-level provider override
    model_override: str | None = None  # Optional run-level model override

    # What the user pointed at (#4397/#4396). Before this there was NO schema
    # for the selection at all — `selected_doc_ids` rode untyped inside
    # `inputs` — which is why a client sending a whole folder for a one-file
    # selection could not be rejected: there was no contract to violate.
    selection: WorkflowSelection | None = None

    @model_validator(mode="after")
    def _derive_selection(self) -> "ExecuteWorkflowRequest":
        """Adapt a legacy `inputs["selected_doc_ids"]` into the typed field.

        ONE adapter, at the boundary, so everything downstream sees only the
        typed selection — not a try-new-then-old chain threaded through each
        use site. It exists solely so the server can start validating and
        recording scope before the client sends the new field, and it is
        removable in a single edit once the client does.

        It cannot launder a bad request into a good one. A flat list of ids is
        described as exactly what it is — `kind=documents`, an explicit set —
        so the legacy path can never *claim* to be a folder run. Only a client
        that sends `selection` explicitly can say `kind=folder`, and that claim
        is validated.
        """
        if self.selection is not None:
            return self
        raw = self.inputs.get("selected_doc_ids") if self.inputs else None
        if isinstance(raw, list) and raw:
            self.selection = WorkflowSelection(
                kind=SelectionKind.documents, ids=[str(i) for i in raw]
            )
        return self

    @model_validator(mode="after")
    def _reject_unread_target_keys(self) -> "ExecuteWorkflowRequest":
        """Fail loudly when doc targets ride under a key nothing reads (#4467).

        Runs after ``_derive_selection``: a request that also carried a real
        selection is fine — only a request whose ONLY targeting is an unread
        key is rejected, because that run would complete having processed
        nothing and report success.
        """
        if self.selection is not None or not self.inputs:
            return self
        stray = [k for k in UNREAD_TARGET_INPUT_KEYS if self.inputs.get(k)]
        if stray:
            raise ValueError(
                f"inputs[{stray!r}] is not read by any workflow node — the run "
                "would complete without processing anything. Pass the target "
                "documents as `selection` (or legacy "
                "`inputs['selected_doc_ids']`). (#4467)"
            )
        return self


class ExecutionStatusResponse(BaseModel):
    """Response with workflow execution status."""

    thread_id: str
    workflow_id: str
    workflow_name: str
    # One vocabulary (#4316): accepted|running|paused|completed|failed|
    # cancelled (+ the soft-delete marker). Exported through OpenAPI so the
    # app can replace its hand-rolled status enums with this generated one.
    status: RunStatus
    checkpoint_id: str | None = None
    current_state: dict[str, Any] | None = None
    error: str | None = None


class ResumeWorkflowRequest(BaseModel):
    """Request to resume a paused workflow."""

    inputs: dict[str, Any] | None = None  # Optional new inputs
    # The human's answer to a workflow that paused on a LangGraph interrupt()
    # (human-in-the-loop, #2529). When set, the run is resumed via
    # Command(resume=answer) so the value is delivered back to the interrupt()
    # call — a plain inputs dict would NOT reach it.
    answer: Any | None = None


class CancelWorkflowRequest(BaseModel):
    """Request to cancel a running workflow."""

    pass  # No parameters needed


class ThreadListResponse(BaseModel):
    """Response with list of execution threads."""

    threads: list[ExecutionStatusResponse]


class ExecuteAcceptedResponse(BaseModel):
    """Response when workflow execution has been accepted (202)."""

    thread_id: str
    workflow_id: str
    workflow_name: str
    status: RunStatus = RunStatus.accepted  # Will transition to "running"
    stream_url: str  # URL to subscribe for SSE events


class SSEEvent(BaseModel):
    """Server-Sent Event for workflow execution updates."""

    # Events: "start", "node_begin", "node_end", "complete", "error", "pause"
    #         "parallel_start", "file_start", "file_complete", "file_error", "parallel_complete"
    event: str
    thread_id: str
    workflow_id: str
    data: dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    # Parallel execution fields
    node_id: str | None = None
    file_path: str | None = None
    file_index: int | None = None
    file_total: int | None = None
    progress: float | None = None  # 0.0 to 1.0
    document_id: str | None = None
    page_id: str | None = None
    display_name: str | None = None
    sequence: int | None = None


def format_sse(event: SSEEvent) -> str:
    """Format an SSE event for streaming."""
    data = event.model_dump_json()
    formatted = f"event: {event.event}\ndata: {data}\n\n"
    logger.debug("[SSE-YIELD] %s: %s", event.event, str(event.data)[:80])
    return formatted


def workflow_internal_error(message: str) -> HTTPException:
    """Shared 500 shape for workflow-execution routes.

    ponytail: keep the client-visible body stable and generic; the route logger
    already has the real exception text.
    """
    return HTTPException(status_code=500, detail=message)
