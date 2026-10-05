"""Training a reader, from the API (#5398): start, follow and stop a `train-a-model` job.

Thin over `fichero_server.training.job`. Starting and stopping are audited actions (`training.start`,
`training.cancel`), so the app, the CLI, MCP and an agent do it the one way; neither can be undone
(a Job that ran has run). Following one reads the job row: its phase, the Job's id on Hugging Face,
the training set's counts, the price per hour, the last log lines, and the reader it landed.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from fichero_server.actions.registry import ActionContext, ChangeSpec, action, registry
from fichero_server.api.main import (
    get_library_database,
    get_library_database_for_write,
    optional_library_path,
    readable_documents,
)
from fichero_server.api.auth import action_context
from fichero_server.db import Database
from fichero_server.models.compute_requests import (
    GatherReasonsRequest,
    ReasonsABRequest,
    TrainKrakenHereRequest,
    TrainKrakenRequest,
    TrainVisionLoraRequest,
)


# The training subsystem is imported when a request needs it, not at app start (#3950): the routes and
# their actions are known at start; the work and its exceptions load on first use.
def _training_job() -> Any:
    from fichero_server.training import job

    return job


def _reasons_job() -> Any:
    from fichero_server.training import reasons_job

    return reasons_job


def _no_token() -> type[Exception]:
    from fichero_server.training.hf_jobs import NoHuggingFaceToken

    return NoHuggingFaceToken


def _empty_set() -> type[Exception]:
    from fichero_server.training.kraken_set import EmptyTrainingSet

    return EmptyTrainingSet

router = APIRouter(prefix="/training")


def _every_page_readable(db: Database, scope_ids: list[str], ctx: ActionContext) -> None:
    """A training set or a reasons job reads every page UNDER its scope (`pages_in_scope`); the action
    layer checked only the ids named. Refuse when one of those pages is one this caller may not read."""
    if ctx.is_bootstrap:
        return
    from fichero_server.security import authz
    from fichero_server.training.kraken_set import pages_in_scope

    authz.assert_can_read_every(ctx.actor, ctx.library_path, [p.id for p in pages_in_scope(db, scope_ids)],
                                bootstrap=False)


class TrainingStarted(BaseModel):
    job_id: str
    flavor: str
    timeout: str
    price_per_hour_usd: float | None = None


class TrainingStartedHere(BaseModel):
    job_id: str


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
    measured: dict[str, Any] | None = None


class CancelTrainingParams(BaseModel):
    job_id: str


@action("training.start", TrainKrakenRequest, domains=["job"], undoable=False)
def _action_start(db: Database, params: TrainKrakenRequest, ctx: ActionContext) -> tuple[dict, ChangeSpec]:
    _every_page_readable(db, params.scope_ids, ctx)
    started = _training_job().start(db, params, started_by=ctx.actor or "owner")
    return started, ChangeSpec(domains=["job"], target_ids=[started["job_id"]],
                               after={"job_id": started["job_id"], "kind": _training_job().KIND},
                               emit_type="job.created")


@action("training.start_vision_lora", TrainVisionLoraRequest, domains=["job"], undoable=False)
def _action_start_vision_lora(db: Database, params: TrainVisionLoraRequest, ctx: ActionContext) -> tuple[dict, ChangeSpec]:
    _every_page_readable(db, params.scope_ids, ctx)
    started = _training_job().start(db, params, started_by=ctx.actor or "owner")
    return started, ChangeSpec(domains=["job"], target_ids=[started["job_id"]],
                               after={"job_id": started["job_id"], "kind": _training_job().KIND, "card": "vision-lora"},
                               emit_type="job.created")


@action("training.start_here", TrainKrakenHereRequest, domains=["job"], undoable=False)
def _action_start_here(db: Database, params: TrainKrakenHereRequest, ctx: ActionContext) -> tuple[dict, ChangeSpec]:
    from fichero_server.training import local as local_training  # the engine starts without it (#3950)

    _every_page_readable(db, params.scope_ids, ctx)
    started = local_training.start(db, params, started_by=ctx.actor or "owner")
    return started, ChangeSpec(domains=["job"], target_ids=[started["job_id"]],
                               after={"job_id": started["job_id"], "kind": local_training.KIND},
                               emit_type="job.created")


@action("training.cancel", CancelTrainingParams, domains=["job"], undoable=False)
def _action_cancel(db: Database, params: CancelTrainingParams, ctx: ActionContext) -> tuple[dict, ChangeSpec]:
    state = _training_job().request_cancel(db, params.job_id)
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
    except _training_job().PagesMayNotLeave as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except _no_token() as exc:
        raise HTTPException(status_code=412, detail=str(exc)) from exc
    except (_empty_set(), ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return TrainingStarted(**result.result)


@router.post("/kraken/here", response_model=TrainingStartedHere, summary="Train a Kraken reader on this Mac, gently")
async def start_kraken_training_here(
    request: TrainKrakenHereRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> TrainingStartedHere:
    """Queue a `train-on-this-mac` job: the same training set and settings as the Hugging Face card,
    trained here on the local-model lane. Nothing leaves this Mac. It holds while the Mac is in use,
    hot or on battery, lets memory go and comes back when memory is tight or other work is waiting,
    resumes from its last finished epoch, and records the memory and time it took. Follow and stop it
    with `/training/jobs/{job_id}`. Refused with a base reader that is not installed."""
    try:
        result = registry.invoke(db, "training.start_here", request.model_dump(), ctx)
    except (ValueError, RuntimeError, LookupError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return TrainingStartedHere(**result.result)


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
    except _training_job().PagesMayNotLeave as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except _no_token() as exc:
        raise HTTPException(status_code=412, detail=str(exc)) from exc
    except (_empty_set(), ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return TrainingStarted(**result.result)


@router.get("/jobs/{job_id}", response_model=TrainingJobStatus, summary="A training job's phase and outcome")
async def training_job_status(job_id: str, db: Database = Depends(get_library_database)) -> TrainingJobStatus:
    try:
        row = _training_job().status(db, job_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return TrainingJobStatus(**{k: v for k, v in row.items() if k in TrainingJobStatus.model_fields})


class TrainingSetPreview(BaseModel):
    """What a training set from these pages holds, and what it leaves out and why."""

    teacher: str
    pages: int
    lines: int
    lines_read_by_a_model: int
    lines_checked_by_a_person: int
    lines_left_out: int
    left_out: dict[str, int]
    left_out_lines: list[dict[str, str]]
    lines_with_a_verdict: int
    check_ran: bool
    flags_checked: list[str]
    held_out: list[dict[str, str]]
    missing: list[dict[str, str]]


@router.get("/set", response_model=TrainingSetPreview,
            summary="What a training set from these pages would hold, and the flagged lines it leaves out")
async def preview_training_set(
    request: Request,
    teacher: str = Query(..., description="The model whose line readings are the lessons."),
    scope_ids: list[str] = Query(..., description="Folders or pages whose teacher-read lines are the lessons."),
    held_out_ids: list[str] = Query([], description="Pages kept home as the test."),
    x_fichero_library_path: str | None = Depends(optional_library_path),
    db: Database = Depends(get_library_database),
) -> TrainingSetPreview:
    """Counted exactly as a training job builds its set, nothing written or sent
    (`compute.tune.set-excludes-flagged-lines`): the pages and lines that would teach, the lines left
    out by flag (an empty or `null` reading, a reading whose newest check verdict rejects it) with
    each line's segment, whether the check had run on the set's lines, the held-out pages and the
    pages missing with why."""
    from fichero_server.training.kraken_set import build_training_set, pages_in_scope

    # ACCESS CONTROL (#5180): the read check sees single ids, never a list. The scope is filtered to
    # what this caller may read, then expanded to its pages and filtered again -- a folder they may
    # read can hold a page denied on its own -- and the held-out pages likewise, so a preview never
    # counts or names a page the caller may not read. The owner's scope is unchanged.
    if not getattr(request.state, "bootstrap_auth", False):
        scope_ids = readable_documents(request, x_fichero_library_path, scope_ids)
        scope_ids = readable_documents(request, x_fichero_library_path, [p.id for p in pages_in_scope(db, scope_ids)])
        held_out_ids = readable_documents(request, x_fichero_library_path, held_out_ids)
    made = build_training_set(db, scope_ids=scope_ids, teacher=teacher, held_out_ids=held_out_ids, out_dir=None)
    return TrainingSetPreview(**{k: v for k, v in made.summary().items() if k in TrainingSetPreview.model_fields})


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


class ModelRunsOn(BaseModel):
    """One build of the model and what runs it; `here` when that build is on this engine's disk."""

    build: str
    runs_on: str | None = None
    here: bool


class ModelHeldOutScores(BaseModel):
    """The newest evaluation on the card: CER over the held-out pages under each normalisation policy."""

    measured_at: str | None = None
    job_id: str | None = None
    checked: str | None = None
    pages: int
    cer: dict[str, float | None]


class TrainedModelNode(BaseModel):
    """A model Fichero trained or fine-tuned, as the training node shows it, read from its card (#5439).

    None where the card carries no such fact: `licence` for a Kraken reader (its card names none),
    `base` for a reader trained from nothing, `scores` before any evaluation."""

    id: str
    name: str
    kind: str = Field(description="kraken-reader or vision-lora")
    summary: str | None = None
    base: str | None = None
    teacher: str | None = None
    job_id: str | None = None
    trained_at: str | None = None
    trained_where: str | None = Field(None, description="The card's target: huggingface-jobs or this-mac.")
    training_set: dict[str, Any] | None = None
    scores: ModelHeldOutScores | None = None
    evaluations: int = 0
    size_bytes: int | None = None
    runs_on: list[ModelRunsOn] = []
    licence: str | None = None
    licence_note: str | None = None
    may_publish: bool = Field(description="True only when the card says not_for_release: false.")
    release_note: str | None = None


class TrainedModelNodes(BaseModel):
    models: list[TrainedModelNode]


class TrainedModelInspector(TrainedModelNode):
    """One trained model's Inspector: the node's facts, its whole card and every evaluation, oldest first."""

    card: dict[str, Any]
    evaluation_history: list[dict[str, Any]]


def _model_nodes() -> Any:
    from fichero_server.training import model_nodes

    return model_nodes


@router.get("/models", response_model=TrainedModelNodes,
            summary="The models Fichero trained or fine-tuned, as the training node lists them")
async def list_trained_models(db: Database = Depends(get_library_database)) -> TrainedModelNodes:
    """The models trained in this library's project only (#5483), newest first, each read from its card
    (`source.model.node-in-sidebar`): provenance (base, teacher, training set, job, when, where), the
    newest held-out scores per normalisation policy, size (the weights' bytes on this Mac, null when they
    are not here), where it runs, licence and whether it may be published. A downloaded or imported model
    is not listed: it lives in Settings; so does a reader whose card predates the project being recorded."""
    return TrainedModelNodes(models=[TrainedModelNode(**n) for n in _model_nodes().model_nodes(db)])


@router.get("/model", response_model=TrainedModelInspector, summary="One trained model's Inspector facts")
async def trained_model_inspector(
    model: str = Query(..., description="The model id: kraken-trained-<job> or fichero-trained/<name>."),
    db: Database = Depends(get_library_database),
) -> TrainedModelInspector:
    """`source.model.node-inspector`: the node's facts plus its whole card and every evaluation on it. 404
    for a model Fichero did not train in this library's project (no training card, or another project's)."""
    node = _model_nodes().model_node(db, model)
    if node is None:
        raise HTTPException(status_code=404, detail=f"{model} is not a model trained in this project")
    return TrainedModelInspector(**node)


class ReasonsJobParams(BaseModel):
    job_id: str


@action("training.gather_reasons", GatherReasonsRequest, domains=["job"], undoable=False)
def _action_gather_reasons(db: Database, params: GatherReasonsRequest, ctx: ActionContext) -> tuple[dict, ChangeSpec]:
    _every_page_readable(db, params.scope_ids, ctx)
    started = _reasons_job().start(db, params, started_by=ctx.actor or "owner")
    return started, ChangeSpec(domains=["job"], target_ids=[started["job_id"]],
                               after={"job_id": started["job_id"], "kind": _reasons_job().KIND}, emit_type="job.created")


@action("training.cancel_reasons", ReasonsJobParams, domains=["job"], undoable=False)
def _action_cancel_reasons(db: Database, params: ReasonsJobParams, ctx: ActionContext) -> tuple[dict, ChangeSpec]:
    state = _reasons_job().request_cancel(db, params.job_id)
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
    uncertain readings behind each reading. Each call is an episode in the ledger; the vision card's
    `why` and `thinking` arms are made from them (the `review` arm from the check job's readings card,
    `POST /api/check/runs`). A hosted teacher goes through the egress gate like any model call."""
    try:
        return registry.invoke(db, "training.gather_reasons", request.model_dump(), ctx).result
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/reasons/{job_id}", summary="A reasons job's counts in words and numbers")
async def reasons_job_status(job_id: str, db: Database = Depends(get_library_database)) -> dict[str, Any]:
    try:
        return _reasons_job().status(db, job_id)
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


@action("training.measure_reasons_ab", ReasonsABRequest, domains=["job"], undoable=False)
def _action_measure_ab(db: Database, params: ReasonsABRequest, ctx: ActionContext) -> tuple[dict, ChangeSpec]:
    started = _reasons_job().start_ab(db, params, started_by=ctx.actor or "owner")
    return started, ChangeSpec(domains=["job"], target_ids=[started["job_id"]],
                               after={"job_id": started["job_id"], "kind": _reasons_job().KIND_AB}, emit_type="job.created")


@router.post("/reasons-ab", summary="Measure answer-only against reasoning students on held-out checked pages")
async def start_reasons_ab(
    request: ReasonsABRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> dict[str, str]:
    """Queue a `reasons-ab` job (#4642, `distill.reasoning.ab-decides`): every contender reads the held-out
    checked lines as it was trained (a reasoning student also with its reasoning off); one CER and WER
    each, seconds a line, and for a `why` student whether its errors fall where it said it was unsure. A
    reasoning student is adopted only beyond `noise_band`; the result is written on every Fichero-trained
    contender's card either way. Through `training.measure_reasons_ab`; 422 without held-out pages."""
    try:
        return registry.invoke(db, "training.measure_reasons_ab", request.model_dump(), ctx).result
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/reasons-ab/{job_id}", summary="The reasons A/B's scores and verdicts")
async def reasons_ab_status(job_id: str, db: Database = Depends(get_library_database)) -> dict[str, Any]:
    try:
        return _reasons_job().status(db, job_id, _reasons_job().KIND_AB)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
