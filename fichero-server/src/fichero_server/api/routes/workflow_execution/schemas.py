"""Request/response models and SSE event types for workflow execution."""

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


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


class ExecutionStatusResponse(BaseModel):
    """Response with workflow execution status."""

    thread_id: str
    workflow_id: str
    workflow_name: str
    status: str  # "running", "paused", "completed", "failed"
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
    status: str = "accepted"  # Will transition to "running"
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
