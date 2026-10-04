"""Training a reader, from the API (#5398): start, follow and stop a `train-a-model` job.

Thin over `fichero_server.training.job`. Starting and stopping are audited actions (`training.start`,
`training.cancel`), so the app, the CLI, MCP and an agent do it the one way; neither can be undone
(a Job that ran has run). Following one reads the job row: its phase, the Job's id on Hugging Face,
the training set's counts, the price per hour, the last log lines, and the reader it landed.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from fichero_server.actions.registry import ActionContext, ChangeSpec, action, registry
from fichero_server.api.main import get_library_database, get_library_database_for_write
from fichero_server.api.auth import action_context
from fichero_server.db import Database
from fichero_server.training import job as training_job
from fichero_server.training.hf_jobs import NoHuggingFaceToken
from fichero_server.training.job import PagesMayNotLeave, TrainKrakenRequest, TrainVisionLoraRequest
from fichero_server.training import reasons_job
from fichero_server.training.kraken_set import EmptyTrainingSet
from fichero_server.training.reasons_job import GatherReasonsRequest

router = APIRouter(prefix="/training")


class TrainingStarted(BaseModel):
    job_id: str
    flavor: str
    timeout: str
    price_per_hour_usd: float | None = None


class TrainingJobStatus(BaseModel):
    """A training job's row, in words and numbers."""

    job_id: str
    state: str
    reason: str | None = None
    phase: str | None = None
    card: str | None = None
    flavor: str | None = None
    far_id: str | None = None
    price_per_hour_usd: float | None = None
    reader_id: str | None = None
    model_id: str | None = None
    training_set: dict[str, Any] | None = None
    last_lines: list[str] = []
    history: list[dict[str, Any]] = []
    request: dict[str, Any] | None = None


class CancelTrainingParams(BaseModel):
    job_id: str


@action("training.start", TrainKrakenRequest, domains=["job"], undoable=False)
def _action_start(db: Database, params: TrainKrakenRequest, ctx: ActionContext) -> tuple[dict, ChangeSpec]:
    started = training_job.start(db, params, started_by=ctx.actor or "owner")
    return started, ChangeSpec(domains=["job"], target_ids=[started["job_id"]],
                               after={"job_id": started["job_id"], "kind": training_job.KIND},
                               emit_type="job.created")


@action("training.start_vision_lora", TrainVisionLoraRequest, domains=["job"], undoable=False)
def _action_start_vision_lora(db: Database, params: TrainVisionLoraRequest, ctx: ActionContext) -> tuple[dict, ChangeSpec]:
    started = training_job.start(db, params, started_by=ctx.actor or "owner")
    return started, ChangeSpec(domains=["job"], target_ids=[started["job_id"]],
                               after={"job_id": started["job_id"], "kind": training_job.KIND, "card": "vision-lora"},
                               emit_type="job.created")


@action("training.cancel", CancelTrainingParams, domains=["job"], undoable=False)
def _action_cancel(db: Database, params: CancelTrainingParams, ctx: ActionContext) -> tuple[dict, ChangeSpec]:
    state = training_job.request_cancel(db, params.job_id)
    return {"job_id": params.job_id, "state": state}, ChangeSpec(
        domains=["job"], target_ids=[params.job_id], after={"job_id": params.job_id, "state": state},
        emit_type="job.updated")


@router.post("/kraken", response_model=TrainingStarted, summary="Train a Kraken reader on Hugging Face Jobs")
async def start_kraken_training(
    request: TrainKrakenRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> TrainingStarted:
    """Queue a `train-a-model` job: the pages in scope whose lines the teacher read go to a private
    bucket of the person's Hugging Face account, Fichero's trainer fine-tunes the base reader there,
    and the trained reader comes home as a reader card. Refused (and nothing queued) without the
    person's yes for the pages to leave, without a Hugging Face token, or with a base reader that is
    not installed."""
    try:
        result = registry.invoke(db, "training.start", request.model_dump(), ctx)
    except PagesMayNotLeave as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except NoHuggingFaceToken as exc:
        raise HTTPException(status_code=412, detail=str(exc)) from exc
    except (EmptyTrainingSet, ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return TrainingStarted(**result.result)


@router.post("/vision-lora", response_model=TrainingStarted,
             summary="Train a vision model with LoRA on Hugging Face Jobs, landed here as MLX")
async def start_vision_lora_training(
    request: TrainVisionLoraRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> TrainingStarted:
    """Queue a `train-a-model` job on the vision-model card: the same training set as the Kraken
    card, cut into line pictures with the line reader's own instruction and the teacher's answers; a
    LoRA on the bf16 base (Qwen2.5-VL 7B by default) on the cheapest GPU that fits; the merged model
    converted to 4-bit MLX on this Mac and landed as `fichero-trained/<name>`, the adapter kept beside
    it. The same refusals as the Kraken card."""
    try:
        result = registry.invoke(db, "training.start_vision_lora", request.model_dump(), ctx)
    except PagesMayNotLeave as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except NoHuggingFaceToken as exc:
        raise HTTPException(status_code=412, detail=str(exc)) from exc
    except (EmptyTrainingSet, ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return TrainingStarted(**result.result)


@router.get("/jobs/{job_id}", response_model=TrainingJobStatus, summary="A training job's phase and outcome")
async def training_job_status(job_id: str, db: Database = Depends(get_library_database)) -> TrainingJobStatus:
    try:
        row = training_job.status(db, job_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return TrainingJobStatus(**{k: v for k, v in row.items() if k in TrainingJobStatus.model_fields})


@router.post("/jobs/{job_id}/cancel", summary="Stop a training job (cancels its Job on Hugging Face)")
async def cancel_training_job(
    job_id: str,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> dict[str, str]:
    try:
        return registry.invoke(db, "training.cancel", {"job_id": job_id}, ctx).result
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


class ReasonsJobParams(BaseModel):
    job_id: str


@action("training.gather_reasons", GatherReasonsRequest, domains=["job"], undoable=False)
def _action_gather_reasons(db: Database, params: GatherReasonsRequest, ctx: ActionContext) -> tuple[dict, ChangeSpec]:
    started = reasons_job.start(db, params, started_by=ctx.actor or "owner")
    return started, ChangeSpec(domains=["job"], target_ids=[started["job_id"]],
                               after={"job_id": started["job_id"], "kind": reasons_job.KIND}, emit_type="job.created")


@action("training.cancel_reasons", ReasonsJobParams, domains=["job"], undoable=False)
def _action_cancel_reasons(db: Database, params: ReasonsJobParams, ctx: ActionContext) -> tuple[dict, ChangeSpec]:
    state = reasons_job.request_cancel(db, params.job_id)
    return {"job_id": params.job_id, "state": state}, ChangeSpec(
        domains=["job"], target_ids=[params.job_id], after={"job_id": params.job_id, "state": state},
        emit_type="job.updated")


@router.post("/reasons", summary="Ask a palaeographer for its reasons (or review) on each checked line")
async def start_gathering_reasons(
    request: GatherReasonsRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> dict[str, str]:
    """Queue a `gather-reasons` job (#4642): the teacher (a reasoning vision model) reads every line of
    the checked pass in scope, held-out pages left out, and gives the letterforms, abbreviations and
    uncertain readings behind each reading (`read`), or reviews the `draft` pass's reading of each line
    (`review`). Each call is an episode in the ledger; the vision card's `why`, `thinking` and `review`
    arms are made from them. A hosted teacher goes through the egress gate like any model call."""
    try:
        return registry.invoke(db, "training.gather_reasons", request.model_dump(), ctx).result
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/reasons/{job_id}", summary="A reasons job's counts in words and numbers")
async def reasons_job_status(job_id: str, db: Database = Depends(get_library_database)) -> dict[str, Any]:
    try:
        return reasons_job.status(db, job_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/reasons/{job_id}/cancel", summary="Stop a reasons job (no further lines are asked about)")
async def cancel_reasons_job(
    job_id: str,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> dict[str, str]:
    try:
        return registry.invoke(db, "training.cancel_reasons", {"job_id": job_id}, ctx).result
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
