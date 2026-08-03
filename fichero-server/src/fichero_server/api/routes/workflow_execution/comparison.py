"""Compare two workflow runs of the same input (#4341).

One endpoint, one question: where do these two runs disagree? It joins two runs
that have already happened, so the common case — "I ran the ensemble last night
and plain HTR this morning, which lines differ?" — costs nothing extra. Running
a fresh pair is done through the existing execute endpoint twice; this does not
hide a second model spend inside a GET.

The diff itself lives in ``workflows.run_comparison`` and is pure, so the rules
that matter (a failed side is reported failed, never as "no differences") are
testable without HTTP.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from fichero_server.api.main import get_library_database
from fichero_server.db import Database
from fichero_server.models import Artifact, Document
from fichero_server.workflows.activity import get_activity_tracker
from fichero_server.workflows.activity_types import WorkflowRun
from fichero_server.workflows.run_comparison import (
    COST_NOTICE,
    RunComparisonError,
    RunSide,
    compare_runs,
)
from fichero_server.workflows.run_status import normalize_status

from .schemas import workflow_internal_error

logger = logging.getLogger(__name__)
router = APIRouter()


# =============================================================================
# Response schemas
# =============================================================================


class ComparisonSideResponse(BaseModel):
    thread_id: str
    workflow_id: str
    workflow_name: str
    status: str
    error: str | None = None
    duration_ms: int | None = None
    artifact_count: int = 0
    steps_total: int = 0
    steps_failed: int = 0
    steps_not_run: int = 0
    steps_produced_nothing: int = 0
    resolved_document_count: int | None = None


class ComparisonArtifactRefResponse(BaseModel):
    artifact_id: str
    document_id: str
    document_name: str | None = None
    artifact_type: str = ""
    step_name: str | None = None
    provider: str | None = None
    model: str | None = None
    content_chars: int = 0


class TextDifferenceResponse(BaseModel):
    kind: str = Field(description="changed | added | removed")
    left_start_line: int | None = None
    right_start_line: int | None = None
    left_lines: list[str] = Field(default_factory=list)
    right_lines: list[str] = Field(default_factory=list)
    left_line_count: int = 0
    right_line_count: int = 0
    lines_truncated: bool = False


class TextDiffResponse(BaseModel):
    left_chars: int
    right_chars: int
    similarity: float = Field(
        description=(
            "Secondary. The named differences are the answer; a ratio alone "
            "does not say which line to check."
        )
    )
    differences: list[TextDifferenceResponse] = Field(default_factory=list)
    difference_count: int = 0
    differences_truncated: bool = False


class SetDifferenceResponse(BaseModel):
    field_name: str
    only_left: list[str] = Field(default_factory=list)
    only_right: list[str] = Field(default_factory=list)
    shared_count: int = 0
    only_left_count: int = 0
    only_right_count: int = 0
    labels_truncated: bool = False


class ValueDifferenceResponse(BaseModel):
    field_name: str
    left: str | None = None
    right: str | None = None


class ArtifactComparisonResponse(BaseModel):
    document_id: str
    document_name: str | None = None
    artifact_type: str
    left: ComparisonArtifactRefResponse
    right: ComparisonArtifactRefResponse
    identical: bool
    text_diff: TextDiffResponse | None = None
    set_differences: list[SetDifferenceResponse] = Field(default_factory=list)
    value_differences: list[ValueDifferenceResponse] = Field(default_factory=list)


class RunComparisonResponse(BaseModel):
    left: ComparisonSideResponse
    right: ComparisonSideResponse
    comparable: bool = Field(
        description=(
            "False when either run did not complete. Read this BEFORE "
            "`identical`: an empty diff from a broken run means nothing."
        )
    )
    incomparable_reason: str | None = None
    same_input: bool | None = Field(
        default=None,
        description=(
            "Whether both runs resolved to the same documents (#4384). None "
            "means unrecorded, which is not the same claim as True."
        ),
    )
    input_note: str = ""
    identical: bool | None = Field(
        default=None,
        description="None whenever the comparison could not be made.",
    )
    difference_count: int = 0
    compared: list[ArtifactComparisonResponse] = Field(default_factory=list)
    only_left: list[ComparisonArtifactRefResponse] = Field(default_factory=list)
    only_right: list[ComparisonArtifactRefResponse] = Field(default_factory=list)
    cost_notice: str = COST_NOTICE


# =============================================================================
# Helpers
# =============================================================================


async def _load_run(db: Database, thread_id: str) -> WorkflowRun:
    tracker = get_activity_tracker(str(db.path))
    run = await tracker.store.get_workflow_run(thread_id)
    if not run:
        raise HTTPException(
            status_code=404, detail=f"Workflow run not found for thread: {thread_id}"
        )
    return run


def _side(db: Database, run: WorkflowRun) -> tuple[RunSide, list[Any]]:
    """Build one side from stored run data plus #4284's per-step records."""
    # Imported here rather than at module scope: threads.py pulls langgraph via
    # its diagram helpers, and this router is imported at engine startup (#3950).
    from .threads import (  # noqa: PLC0415
        _planned_steps_from_run,
        _run_node_names,
        _run_step_records,
    )

    node_name_map = _run_node_names(run)
    planned_steps = _planned_steps_from_run(run)
    steps = _run_step_records(
        db,
        run.thread_id,
        run=run,
        planned_steps=planned_steps,
        node_name_map=node_name_map,
    )
    artifacts = list(db.query(Artifact, run_id=run.thread_id))
    side = RunSide(
        thread_id=run.thread_id,
        workflow_id=run.workflow_id,
        workflow_name=run.workflow_name,
        # Legacy synonyms normalize; an unrecorded status stays literal so it
        # cannot be mistaken for 'completed'.
        status=normalize_status(run.status) or "running",
        steps=steps,
        artifacts=artifacts,
        error=run.error,
        resolved_scope=run.resolved_scope,
        duration_ms=run.duration_ms,
    )
    return side, artifacts


def _document_names(db: Database, *artifact_lists: list[Any]) -> dict[str, str]:
    wanted = {
        doc_id
        for artifacts in artifact_lists
        for artifact in artifacts
        for doc_id in (artifact.document_id, artifact.source_document_id)
        if doc_id
    }
    if not wanted:
        return {}
    return {doc.id: doc.name for doc in db.query(Document) if doc.id in wanted}


# =============================================================================
# Endpoint
# =============================================================================


@router.get("/comparisons", response_model=RunComparisonResponse)
async def compare_workflow_runs(
    left: str = Query(description="Thread id of the first run"),
    right: str = Query(description="Thread id of the second run"),
    db: Database = Depends(get_library_database),
) -> RunComparisonResponse:
    """Diff what two runs produced from the same input.

    Pairs each side's artifacts on (document, artifact type) and reports where
    they disagree: line-level differences for transcriptions, and for
    extraction which entities or claims each side found that the other missed.

    Costs nothing extra — both runs already happened. Producing a fresh pair
    means executing the same input twice, i.e. roughly double the model spend
    of a single run; that is stated in `cost_notice` so a client can say it
    plainly at the point a user triggers one.

    If either run failed, was cancelled, or is still going, the response comes
    back with `comparable=false`, a reason naming which side, and
    `identical=null` — an empty diff from a broken run must never read the same
    as an empty diff from two runs that agreed.
    """
    try:
        left_run = await _load_run(db, left)
        right_run = await _load_run(db, right)

        left_side, left_artifacts = _side(db, left_run)
        right_side, right_artifacts = _side(db, right_run)

        try:
            comparison = compare_runs(
                left_side,
                right_side,
                document_names=_document_names(db, left_artifacts, right_artifacts),
            )
        except RunComparisonError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        return RunComparisonResponse(**asdict(comparison))

    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to compare runs %s and %s", left, right)
        raise workflow_internal_error("Failed to compare workflow runs")
