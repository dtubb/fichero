"""Reading at scale off the Mac, from the API (#5398 slice 2): start, follow, re-send and stop.

Thin over `fichero_server.remote_read.job`. Starting, re-sending the failed shards and stopping are
audited actions (`reading.start_at_scale`, `reading.resend_failed`, `reading.cancel_at_scale`), none
undoable: a Job that ran on Hugging Face has run, and what it read lands as passes, each removed like
any pass. Following one reads the job row: shard counts, the failed shards with their reasons, and
what landed.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from fichero_server.actions.registry import ActionContext, ChangeSpec, action, registry
from fichero_server.api.auth import action_context
from fichero_server.api.main import get_library_database, get_library_database_for_write
from fichero_server.db import Database
from fichero_server.models.compute_requests import ReadAtScaleRequest


# The reading subsystem is imported when a request needs it, not at app start (#3950).
def _read_job() -> Any:
    from fichero_server.remote_read import job

    return job


def _refusals() -> tuple[type[Exception], type[Exception]]:
    """(no token, not sendable): the refusals a start answers with 412 and 422."""
    from fichero_server.remote_read.package import NotSendable
    from fichero_server.training.hf_jobs import NoHuggingFaceToken

    return NoHuggingFaceToken, NotSendable

router = APIRouter(prefix="/reading-at-scale")


class ReadingStarted(BaseModel):
    job_id: str
    flavor: str
    price_per_hour_usd: float | None = None


class ReadingJobStatus(BaseModel):
    """A reading run's row: its shards counted, the failed ones with their reasons, what landed."""

    job_id: str
    state: str
    reason: str | None = None
    counts: dict[str, int] = {}
    failed_shards: dict[str, dict[str, Any]] = {}
    package: dict[str, Any] | None = None
    landing: dict[str, int] | None = None
    flavor: str | None = None
    price_per_hour_usd: float | None = None
    step: dict[str, Any] | None = None


class ReadingJobParams(BaseModel):
    job_id: str


def _job_change(job_id: str, emit: str, **after: Any) -> ChangeSpec:
    return ChangeSpec(domains=["job"], target_ids=[job_id], after={"job_id": job_id, **after}, emit_type=emit)


@action("reading.start_at_scale", ReadAtScaleRequest, domains=["job"], undoable=False)
def _action_start(db: Database, params: ReadAtScaleRequest, ctx: ActionContext) -> tuple[dict, ChangeSpec]:
    if not ctx.is_bootstrap:
        # The action layer checked the ids named; a reading run sends every page UNDER them (`pages_to_read`,
        # the same walk the package makes). One the caller may not read refuses the run (fail closed, #5475).
        from fichero_server.remote_read.package import pages_to_read
        from fichero_server.security import authz

        authz.assert_can_read_every(ctx.actor, ctx.library_path, [p.id for p in pages_to_read(db, params.scope_ids)],
                                    bootstrap=False)
    started = _read_job().start(db, params, started_by=ctx.actor or "owner")
    return started, _job_change(started["job_id"], "job.created", kind=_read_job().KIND)


@action("reading.resend_failed", ReadingJobParams, domains=["job"], undoable=False)
def _action_resend(db: Database, params: ReadingJobParams, ctx: ActionContext) -> tuple[dict, ChangeSpec]:
    count = _read_job().resend_failed(db, params.job_id)
    return {"job_id": params.job_id, "resent": count}, _job_change(params.job_id, "job.updated", resent=count)


@action("reading.cancel_at_scale", ReadingJobParams, domains=["job"], undoable=False)
def _action_cancel(db: Database, params: ReadingJobParams, ctx: ActionContext) -> tuple[dict, ChangeSpec]:
    state = _read_job().request_cancel(db, params.job_id)
    return {"job_id": params.job_id, "state": state}, _job_change(params.job_id, "job.updated", state=state)


@router.post("", response_model=ReadingStarted, summary="Read pages on Hugging Face Jobs, many shards as one job")
async def start_reading_at_scale(
    request: ReadAtScaleRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> ReadingStarted:
    """Queue a `read-at-scale` job: the pages in scope (images here, or IIIF canvases by reference) are
    packed with the reader and Fichero's runner, sent to a private bucket of the person's Hugging Face
    account, read in shards (at most `max_in_flight` at once), and each shard's PAGE files land as new
    passes as it finishes. Refused, with nothing queued, without `pages_may_leave` (403), without a
    Hugging Face token (412), or with a reader that cannot run off this Mac (422)."""
    try:
        result = registry.invoke(db, "reading.start_at_scale", request.model_dump(), ctx)
    except _read_job().PagesMayNotLeave as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except _refusals()[0] as exc:
        raise HTTPException(status_code=412, detail=str(exc)) from exc
    except (_refusals()[1], ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ReadingStarted(**result.result)


@router.get("/jobs/{job_id}", response_model=ReadingJobStatus, summary="A reading run's shards and what landed")
async def reading_job_status(job_id: str, db: Database = Depends(get_library_database)) -> ReadingJobStatus:
    try:
        row = _read_job().status(db, job_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ReadingJobStatus(**{k: v for k, v in row.items() if k in ReadingJobStatus.model_fields})


@router.post("/jobs/{job_id}/resend-failed", summary="Send a reading run's failed shards again, and only those")
async def resend_failed_shards(
    job_id: str,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> dict[str, Any]:
    try:
        return registry.invoke(db, "reading.resend_failed", {"job_id": job_id}, ctx).result
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/jobs/{job_id}/cancel", summary="Stop a reading run (cancels its running shards on Hugging Face)")
async def cancel_reading_job(
    job_id: str,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> dict[str, str]:
    try:
        return registry.invoke(db, "reading.cancel_at_scale", {"job_id": job_id}, ctx).result
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
