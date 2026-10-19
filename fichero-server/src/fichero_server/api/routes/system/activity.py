"""
Activity Tracking API Routes.

Endpoints for monitoring workflow and batch activity:
- Query historical activities
- Real-time activity streaming via SSE (the ONE live transport — see the
  tombstone where /ws used to be)
- Activity statistics and metrics

NOTE: All activity data is stored per-library in the library's database file.
Routes require the X-Fichero-Library-Path header.
"""

import asyncio
import re
import json
import logging
from datetime import datetime, timedelta, timezone
from fichero_server.core.timeutil import utc_now
from fichero_server.core.single_flight import single_flight
from pathlib import Path
from typing import Any, Literal, Optional
from uuid import uuid4

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from fichero_server.api.auth import action_context
from fichero_server.api.change_stream import CHANGE_ID_LISTS, ChangeEvent, _change_hub
from fichero_server.api.main import get_library_database, get_library_database_for_write
from fichero_server.actions.registry import ActionContext, ChangeSpec, action, registry
from fichero_server.db import Database
from fichero_server.workflows.activity import (
    Activity,
    ActivityFilter,
    ActivityLevel,
    ActivityStats,
    ActivityType,
    get_activity_tracker,
)
from fichero_server.models import ActivityListResponse
from fichero_server.workflows.run_account import RunAccount
from fichero_server.recipes.run_view import RecipeRunStep, RecipeRunSummary

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/activity", tags=["activity"])
_KEEPALIVE_TIMEOUT = 10.0


def _parse_iso_to_naive_utc(value: str) -> datetime:
    """Parse ISO-8601 timestamps and normalize to naive UTC for DuckDB."""
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


# Pydantic models for API


class ActivityResponse(BaseModel):
    """Response model for an activity event."""

    id: str
    type: str
    level: str
    timestamp: str
    message: str
    workflow_id: Optional[str] = None
    batch_id: Optional[str] = None
    thread_id: Optional[str] = None
    node_id: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    duration_ms: Optional[float] = None
    error: Optional[str] = None

    @classmethod
    def from_activity(cls, activity: Activity) -> "ActivityResponse":
        # Convert metadata values to strings for Swift client compatibility
        string_metadata = {
            k: str(v) if v is not None else None for k, v in activity.metadata.items()
        }
        return cls(
            id=activity.id,
            type=activity.type.value,
            level=activity.level.value,
            timestamp=activity.timestamp.isoformat(),
            message=activity.message,
            workflow_id=activity.workflow_id,
            batch_id=activity.batch_id,
            thread_id=activity.thread_id,
            node_id=activity.node_id,
            metadata=string_metadata,
            duration_ms=activity.duration_ms,
            error=activity.error,
        )


def _change_event_to_activity_response(event: ChangeEvent) -> ActivityResponse:
    # Iterates the one declared tuple (source-model slice 2, #4920) instead
    # of naming each id list here by hand -- this is the fold's own
    # serialization site, what Swift's `init?(activityMetadata:)` decodes,
    # and it used to be a second hardcoded list nothing kept in sync with
    # `_emit`'s (agent-work/source-model/recon-slice-2.md).
    id_list_metadata = {name: json.dumps(getattr(event, name)) for name in CHANGE_ID_LISTS}
    return ActivityResponse(
        id=f"change-{event.event_id or uuid4().hex}",
        type=ActivityType.SYSTEM_INFO.value,
        level=ActivityLevel.INFO.value,
        timestamp=event.ts,
        message=f"{event.type} changed",
        metadata={
            "change_type": event.type,
            "actor": event.actor,
            "run_id": event.run_id,
            "origin_window": event.origin_window,
            "origin_user": event.origin_user,
            "ts": event.ts,
            "change_metadata": json.dumps(event.metadata),
            **id_list_metadata,
        },
    )


class RemoteRunRow(BaseModel):
    target: Optional[str] = None
    far_state: str
    shards: str
    pages_landed: int = 0
    offers: list[str] = Field(default_factory=list)


class BackgroundJob(BaseModel):
    """One live background job (a running derivative/embed queue, …).

    First-class so the Activity UI can show the user WHAT is consuming compute
    and how far along it is ([[user-machine-always-useful]] FIX 2).
    """

    id: str
    task_type: str  # derivatives | workflow
    name: str
    library: str = ""
    current: int
    total: int
    percent: float
    state: str  # running | stalled | failed | paused | waiting (a queued job)
    # For a failed job (e.g. a Kraken run when the runtime/model isn't installed),
    # the actionable reason — so the user sees WHY, not just that it stopped.
    reason: Optional[str] = None
    # The job this one belongs to: a page's step (whose own parent is its run), #5353. A step's row id is its
    # run's id and the step's name, "<run id>:<step name>" (the id every step row has been written under); look
    # it up as any job, or look up `run_id`.
    parent_id: Optional[str] = None
    # The workflow run a page's work is for (#5615): its thread id, a job id `GET /api/activity/jobs/{id}`
    # reads; null for a row that is not under a run.
    run_id: Optional[str] = None
    # A workflow run's account (#5555): `current`/`total` are its pages done and in all.
    account: Optional[RunAccount] = None
    # What the row offers (#5615): "Resume" for a job set aside after its interruptions, done by
    # `POST /api/activity/jobs/{id}/retry`, which carries it on from where it was; null when nothing.
    offer: Optional[str] = None
    # When a failed job failed (ISO 8601, UTC), so a list of errors can say when each happened rather than guess;
    # null for any job that has not failed, and cleared when it is retried.
    failed_at: Optional[datetime] = None
    # Who started it: the person, plus the paired Mac when it came from another one ("alice on Alice's Mac",
    # `sharing.remote-run-in-host-activity`, #5732); "automatic" for work the app queued itself.
    started_by: Optional[str] = None
    # A run sent to another place (a cluster, Hugging Face Jobs), under the recipe step that sent it
    # (`activity.remote-under-its-step`): target, far-side state, shards done of total, pages landed, and what the
    # row offers (Cancel, Retry failed shards, Catch up). Null for any other row.
    remote: Optional[RemoteRunRow] = None
    # Where Activity puts the row (`activity.window.history-group`): "live" is the run going now and the queues
    # beside it, shown at the top; "earlier" is a run that is stopped, interrupted, failed or old, folded below.
    # The list is already in this order.
    group: Literal["live", "earlier"] = "live"


#: A row in one of these states has ended: stopped, interrupted, failed or done.
_ENDED_STATES = ("failed", "cancelled", "done", "interrupted", "stopped", "completed")
#: The kinds that are a run of their own (a workflow, a batch, a recipe run, a try): the live block.
_RUN_TASK_TYPES = ("workflow", "batch", "run-a-recipe", "try-a-stage")


def order_for_activity(jobs: "list[BackgroundJob]") -> "list[BackgroundJob]":
    """Every row ranked by its state (`activity.window.history-group`, `activity.window.next-in-run-order`; #5839, #5851):
    a live run first, then the queues beside it, then whatever has ended (a stopped, interrupted or failed run, batch,
    recipe run, try or queue row), folded as History. Each keeps the order it came in (a run list is newest first).
    Marks each row's `group`."""
    def rank(job: "BackgroundJob") -> int:
        if job.state in _ENDED_STATES:
            return 2
        return 0 if job.task_type in _RUN_TASK_TYPES else 1

    for job in jobs:
        job.group = "earlier" if rank(job) == 2 else "live"
    return sorted(jobs, key=rank)  # stable


def _remote_row(db, row: dict) -> "RemoteRunRow | None":
    """The summary a remote run's row shows; nothing for any other kind of job."""
    from fichero_server.remote_read import job as read_job

    if row["kind"] != read_job.KIND:
        return None
    try:
        return RemoteRunRow(**read_job.remote_row(read_job.status(db, row["id"])))
    except Exception as exc:  # noqa: BLE001 -- the row still shows, without its summary
        logger.warning("list_background_jobs: no remote summary for %s: %s", row["id"], exc)
        return None


class MachineState(BaseModel):
    """This Mac's state, as the throttle reads it (`activity.popover.summary`, #5415)."""

    # None when the level cannot be read (not macOS, a sandbox refusal).
    memory_pressure: Optional[Literal["normal", "warn", "critical"]] = None
    thermal_state: Optional[Literal["nominal", "fair", "serious", "critical"]] = None
    # On battery power or in Low Power Mode.
    on_battery: bool = False
    # The person touched keyboard or mouse in the last 30 seconds.
    in_use: bool = False
    # Why heavy local work is held back right now, in words; None when it may go ahead.
    why_wait: Optional[str] = None


def _utc(value: Any) -> Optional[datetime]:
    """A stored time as an aware UTC datetime (the jobs table keeps naive UTC); None stays None."""
    if value is None:
        return None
    from fichero_server.core.timeutil import ensure_utc

    return ensure_utc(value)


class QueueSummary(BaseModel):
    """The whole queue in one line (`activity.window.queue-summary`, #5839)."""

    done: int
    left: int
    seconds_left: Optional[int] = Field(default=None, description=(
        "about how long is left, from the measured time per item; absent when nothing queued has been measured"))


class QueuedItem(BaseModel):
    id: str
    subject: str
    state: str
    reason: Optional[str] = None


class LiveBlock(BaseModel):
    """What is working right now (`activity.window.live-block`, `activity.popover.same-summary`; #5839, #5851, #5852):
    the recipe, the stage it is in and the workflow that stage runs, with the pages done, failed and left."""

    id: str = Field(description="the run's row id: the recipe run, or a workflow run outside any recipe")
    recipe: Optional[str] = Field(None, description="null for a workflow run started on its own")
    stage: Optional[str] = Field(None, description="what the running stage does, in words")
    workflow: Optional[str] = None
    state: str
    reason: Optional[str] = Field(None, description="what it waits for, when it waits (a waiting block looks waiting)")
    done: int = 0
    failed: int = 0
    left: int = 0
    total: int = 0
    folders_done: Optional[int] = None
    folders_total: Optional[int] = None


class BackgroundLine(BaseModel):
    """One kind of background work and its total (`activity.window.background-group`, #5851)."""

    kind: str
    name: str
    state: str
    reason: Optional[str] = None
    done: int = 0
    total: int = 0


class ActivitySummary(BaseModel):
    """The ONE engine summary the window and the toolbar popover both read (`activity.popover.same-summary`, #5852):
    the live blocks, the background group, and how many ended runs are folded into History."""

    live: list[LiveBlock] = Field(default_factory=list)
    background: list[BackgroundLine] = Field(default_factory=list)
    history: int = 0


_LIVE_STATES = ("running", "waiting", "paused")


def background_lines(jobs: "list[BackgroundJob]") -> list[BackgroundLine]:
    """One line per kind of work nobody runs as a run of their own, with its total; none for an ended row."""
    return [BackgroundLine(kind=j.task_type, name=j.name, state=j.state, reason=j.reason, done=j.current, total=j.total)
            for j in jobs if j.task_type not in _RUN_TASK_TYPES and j.state in _LIVE_STATES]


def workflow_block(job: "BackgroundJob") -> LiveBlock:
    """A workflow run outside any recipe, from its account."""
    account = job.account
    return LiveBlock(
        id=job.id, workflow=job.name, state=job.state, reason=job.reason if job.state != "running" else
        (account.waiting_reason if account else None), done=account.pages_done if account else 0,
        failed=account.pages_failed if account else 0, left=account.pages_left if account else 0,
        total=account.pages_total if account else 0)


def recipe_block(job: "BackgroundJob", status: dict[str, Any], workflow_name: Optional[str]) -> LiveBlock:
    """A recipe run: its recipe, the stage running now and the workflow of that stage, the pages of that stage's account."""
    steps = status.get("steps") or []
    running = next((st for st in steps if st.get("state") == "running"), None) \
        or next((st for st in steps if st.get("state") in ("waiting", "paused")), None)
    account = (running or {}).get("account")
    waiting = status.get("reason") if status.get("state") == "waiting" else status.get("waiting_for")
    return LiveBlock(
        id=job.id, recipe=job.name, stage=(running or {}).get("doing"), workflow=workflow_name, state=job.state,
        reason=waiting, done=account.pages_done if account else 0, failed=account.pages_failed if account else 0,
        left=account.pages_left if account else 0, total=account.pages_total if account else 0,
        folders_done=status.get("folders_done"), folders_total=status.get("folders_total"))


async def live_blocks(db: Database, jobs: "list[BackgroundJob]",
                      statuses: "dict[str, dict[str, Any]] | None" = None) -> list[LiveBlock]:
    """The live recipe runs first, then the workflow runs that belong to no recipe (a recipe's stage is its block's)."""
    blocks: list[LiveBlock] = []
    owned: set[str] = set()
    tracker = get_activity_tracker(str(db.path))
    for job in jobs:
        if job.task_type != "run-a-recipe" or job.state not in _LIVE_STATES:
            continue
        try:
            # The status the list already read for this row (one derivation per poll); read here only for a row without
            status = (statuses or {}).get(job.id)
            if status is None:
                _state, _reason, status = await _recipe_state(db, job.id)
        except Exception as exc:  # noqa: BLE001 -- the block stands without its stage; said in the log
            logger.warning("activity summary: no status for recipe run %s: %s", job.id, exc)
            blocks.append(LiveBlock(id=job.id, recipe=job.name, state=job.state, reason=job.reason))
            continue
        owned.update(st["child_id"] for st in status.get("steps", []) if st.get("child_id"))
        running = next((st for st in status.get("steps", []) if st.get("state") == "running" and st.get("child_id")), None)
        run = await tracker.store.get_workflow_run(running["child_id"]) if running else None
        blocks.append(recipe_block(job, status, run.workflow_name if run else None))
    blocks += [workflow_block(j) for j in jobs
               if j.task_type == "workflow" and j.state in _LIVE_STATES and j.id not in owned]
    return blocks


async def activity_summary(db: Database, jobs: "list[BackgroundJob]",
                           statuses: "dict[str, dict[str, Any]] | None" = None) -> ActivitySummary:
    """THE summary (`activity.popover.same-summary`): built once per poll from the ordered job list, so the popover and
    the window can only agree."""
    return ActivitySummary(live=await live_blocks(db, jobs, statuses), background=background_lines(jobs),
                           history=sum(1 for j in jobs if j.group == "earlier"))


class BackgroundJobsResponse(BaseModel):
    """Snapshot of running background jobs + rough process CPU usage."""

    jobs: list[BackgroundJob] = Field(default_factory=list)
    count: int
    # Process CPU% since the last poll (100 == one core busy; can exceed 100 on
    # multiple cores). None on the very first poll (no interval yet) or if the
    # sample is unavailable. Per-job attribution is intentionally not attempted.
    process_cpu_percent: Optional[float] = None
    # The engine's memory (bytes), with its child processes, and average power since the last poll (watts) from the OS (#5358);
    # None off macOS or on the first poll. Per-job and GPU/Neural Engine attribution are not measured.
    process_memory_bytes: Optional[int] = None
    process_energy_watts: Optional[float] = None
    cpu_count: int
    # Pause Background Work is on (`activity.pause.global`): nothing that runs by itself starts.
    paused: bool = False
    # How background work runs (`activity.mode.start-stop`, #5621): automatic (the throttle holds heavy work
    # while the Mac is in use or on battery), started (those holds lifted until set back), or paused.
    mode: Literal["automatic", "started", "paused"] = "automatic"
    # This Mac's memory, heat, power and use, and why heavy work waits (#5415).
    machine: MachineState
    # Done, left and about how long: the whole queue (`activity.window.queue-summary`); absent when nothing is queued.
    summary: Optional[QueueSummary] = None
    # The ONE summary the window and the popover read (`activity.popover.same-summary`, #5852).
    activity: Optional[ActivitySummary] = None


class JobTree(BaseModel):
    """A job and everything under it: a run, its steps, their pages (`activity.jobs-are-a-tree`)."""

    id: str
    kind: str
    name: str
    subject: str
    # A page's document and what a person calls it (#5560, #5561): its file name (SM_NPQ_C01_004.jpg), not
    # its id; null for a run or a step, and for work on no file.
    document_id: Optional[str] = None
    display_name: Optional[str] = None
    model: Optional[str] = None
    state: str
    reason: Optional[str] = None
    parent_id: Optional[str] = None
    # The details view's record (#5561): when it started and ended, as the engine recorded them (ISO 8601,
    # UTC); null when it has not started or not ended. Never filled with "now".
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    # Who or what started it ("automatic", "schedule:...", "read-again:<run>"; "workflow" for a run's own
    # rows), as the job row has it.
    started_by: Optional[str] = None
    # What a running row works on now, by name: its running child, and what that one works on.
    working_on: Optional[str] = None
    done: int = Field(description="pages (or other leaf jobs) under this one that are done")
    total: int = Field(description="pages (or other leaf jobs) under this one in all")
    failed: int = Field(0, description="pages (or other leaf jobs) under this one that failed; each says why")
    seconds: Optional[float] = Field(None, description="how long it took, start to finish (or until now)")
    tokens: int = Field(0, description="the model tokens used under this one")
    cost_usd: Optional[float] = Field(
        None, description="what its model calls cost, from the vendored price list; null unless every one is priced")
    unpriced_models: list[str] = Field(default_factory=list, description="models under it the price list does not know")
    places: dict[str, int] = Field(default_factory=dict, description=(
        "where the model calls under this one ran, and how many went to each place: this_mac, own_machine, "
        "provider (`ai.where.row-names-the-place`, #5582)"))
    # A workflow run's account (#5555): its status shows the same one. Its pages are what `done`,
    # `total` and `failed` count on the run's own node.
    account: Optional[RunAccount] = None
    # A recipe run's stages (#5576): every card of the run in order, those not started yet and those not run
    # included, each workflow stage with its run's account; null on any other job.
    stages: Optional[list[RecipeRunStep]] = None
    # A recipe run that has ended: what it made (#5577, GET /api/recipes/project/runs/{id}/summary).
    summary: Optional[RecipeRunSummary] = None
    children: list["JobTree"] = Field(default_factory=list)
    children_omitted: int = Field(0, description=(
        "children left out because the tree was asked for to a `depth`; this row's counts still include them"))


class BackgroundPauseRequest(BaseModel):
    paused: bool = Field(description="true pauses all background work; false resumes it")


class BackgroundModeRequest(BaseModel):
    mode: Literal["automatic", "started", "paused"] = Field(description=(
        "automatic: heavy work waits while the Mac is in use or on battery; started: it goes ahead anyway "
        "(memory and heat still hold it) until set back; paused: nothing that runs by itself starts"))


class BackgroundModeResponse(BaseModel):
    mode: Literal["automatic", "started", "paused"]


class BackgroundPauseResponse(BaseModel):
    paused: bool


class CleanupResponse(BaseModel):
    deleted: int
    older_than: str


class ActivityCleanupParams(BaseModel):
    days: int = Field(ge=1, le=365)


class ActivityDeleteParams(BaseModel):
    activity_id: str = Field(min_length=1)


class ActivityDeleteResponse(BaseModel):
    deleted: int
    activity_id: str


class ActivityStatsResponse(BaseModel):
    """Response model for activity statistics."""

    total_activities: int
    activities_by_type: dict[str, int]
    activities_by_level: dict[str, int]
    error_count: int
    warning_count: int
    avg_workflow_duration_ms: Optional[float] = None
    success_rate: float
    period_start: str
    period_end: str

    @classmethod
    def from_stats(cls, stats: ActivityStats) -> "ActivityStatsResponse":
        return cls(
            total_activities=stats.total_activities,
            activities_by_type=stats.activities_by_type,
            activities_by_level=stats.activities_by_level,
            error_count=stats.error_count,
            warning_count=stats.warning_count,
            avg_workflow_duration_ms=stats.avg_workflow_duration_ms,
            success_rate=stats.success_rate,
            period_start=stats.period_start.isoformat(),
            period_end=stats.period_end.isoformat(),
        )


# API Endpoints


@router.get("", response_model=ActivityListResponse)
async def list_activities(
    db: Database = Depends(get_library_database),
    types: Optional[str] = Query(None, description="Comma-separated activity types"),
    levels: Optional[str] = Query(
        None, description="Comma-separated levels (info,warning,error)"
    ),
    workflow_id: Optional[str] = None,
    batch_id: Optional[str] = None,
    thread_id: Optional[str] = None,
    since: Optional[str] = Query(None, description="ISO datetime string"),
    until: Optional[str] = Query(None, description="ISO datetime string"),
    search: Optional[str] = Query(None, description="Search in message text"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> list[ActivityResponse]:
    """
    Query historical activities with filtering.

    Supports filtering by type, level, workflow/batch/thread IDs, time range,
    and full-text search in messages.
    """
    tracker = get_activity_tracker(str(db.path))

    # Parse types
    type_list = None
    if types:
        try:
            type_list = [ActivityType(t.strip()) for t in types.split(",")]
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid activity type: {e}")

    # Parse levels
    level_list = None
    if levels:
        try:
            level_list = [ActivityLevel(lvl.strip()) for lvl in levels.split(",")]
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid activity level: {e}")

    # Parse timestamps (handle ISO8601 with Z suffix)
    since_dt = None
    until_dt = None
    if since:
        try:
            since_dt = _parse_iso_to_naive_utc(since)
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Invalid 'since' datetime format"
            )
    if until:
        try:
            until_dt = _parse_iso_to_naive_utc(until)
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Invalid 'until' datetime format"
            )

    filter = ActivityFilter(
        types=type_list,
        levels=level_list,
        workflow_id=workflow_id,
        batch_id=batch_id,
        thread_id=thread_id,
        since=since_dt,
        until=until_dt,
        search=search,
        limit=limit,
        offset=offset,
    )

    activities = await tracker.query(filter)
    items = [ActivityResponse.from_activity(a) for a in activities]
    return ActivityListResponse(items=items, count=len(items))


@router.get("/recent", response_model=ActivityListResponse)
async def get_recent_activities(
    db: Database = Depends(get_library_database),
    limit: int = Query(50, ge=1, le=200),
) -> list[ActivityResponse]:
    """
    Get recent activities from memory buffer.

    This is faster than querying the database and useful for
    real-time dashboards.
    """
    tracker = get_activity_tracker(str(db.path))
    activities = tracker.get_recent(limit)
    return ActivityListResponse(items=[ActivityResponse.from_activity(a) for a in activities], count=len(activities))


@router.get("/jobs", response_model=BackgroundJobsResponse)
@single_flight
async def list_background_jobs(
    db: Database = Depends(get_library_database),
) -> BackgroundJobsResponse:
    """The SINGLE source of running background jobs, so every activity surface
    (toolbar popover AND full viewer) agrees (FIX 3). Merges:

    - the derivative/embed queue (embedding + importing/processing), from the
      live in-memory progress map; and
    - workflow runs (Kraken Detect Regions / HTR, transcription, …) that are
      RUNNING or recently FAILED — with the failure reason, so a run that died
      on "Kraken not installed" shows a clear FAILED entry instead of vanishing.

    Read-only and cheap (a point-in-time read + recent-run query + one CPU
    sample), so the UI can poll it without adding load of its own. Per-library,
    matching the rest of /activity.
    """
    from pathlib import Path as _Path

    from fichero_server.core.background_compute import (
        cpu_count,
        process_cpu_percent,
        process_energy_watts,
        process_tree_rusage,
    )
    from fichero_server.execution import throttle
    from fichero_server.importers import derivatives
    from fichero_server.importers.derivatives import background_jobs_snapshot

    library = str(_Path(db.path).parent)
    jobs = [BackgroundJob(**job) for job in background_jobs_snapshot(library)]
    if jobs:
        # The import's progress row waits when none of its stages runs, and says for what, as any
        # waiting row does (`activity.waiting-says-why`, #5606: it sat at 100 of 406 with no reason).
        from fichero_server.execution import jobs as job_queue

        # Off the loop (#5843): the read waits on the database's transaction gate behind a write.
        held = await asyncio.to_thread(
            job_queue.waiting_reason_of,
            db, [derivatives.THUMBNAIL_KIND, derivatives.EMBED_KIND, derivatives.NLP_KIND])
        if held:
            for job in jobs:
                job.state, job.reason = "waiting", held

    # Workflow runs that are running, paused or recently failed. A completed run is not a
    # "job" the user needs to watch; a running, paused or failed one is.
    try:
        tracker = get_activity_tracker(str(db.path))
        runs = await tracker.store.list_workflow_runs(limit=50)
        from fichero_server.workflows.run_account import run_account

        # A failed run whose pages were read again by a newer run (Retry, or Read Again) is that run's now: one
        # row, not two (`activity.retry.one-row`).
        from fichero_server.execution.jobs import read_again_runs

        read_again = await asyncio.to_thread(read_again_runs, db)
        for run in runs:
            status = (run.status or "").lower()
            if status == "failed" and run.thread_id in read_again:
                continue
            # A paused run is listed too (#5357): it waits for its Resume, after a relaunch as before.
            if status not in ("running", "paused", "failed"):
                continue
            # The run's account, the one its status shows (#5555): its pages done and in all, not the
            # saved timeline's last event (which read "total 0" for a fanned-out run).
            # A run whose account cannot be read still shows, with its own state and reason: a failed
            # run must never vanish from the list (FIX 3).
            try:
                account = await run_account(db, run.thread_id, run=run)
            except Exception as exc:  # noqa: BLE001 -- the row stands without its account; said in the log
                logger.warning("list_background_jobs: no account for run %s: %s", run.thread_id, exc)
                account = None
            current = account.pages_done if account else 0
            total = account.pages_total if account else 0
            # Its pages done, whatever its state: a failed run with no page done is at 0, not 100 (#5615).
            percent = current * 100.0 / total if total else 0.0
            jobs.append(
                BackgroundJob(
                    id=run.thread_id,
                    task_type="workflow",
                    name=run.workflow_name or "Workflow",
                    library=library,
                    current=current,
                    total=total,
                    percent=round(percent, 1),
                    state=status,
                    reason=(run.error or None) if status == "failed" else (account.waiting_reason if account else None),
                    account=account,
                    # A run without its end time still lists, with its reason: never vanish over a timestamp.
                    failed_at=_utc(getattr(run, "completed_at", None)) if status == "failed" else None,
                )
            )
    except Exception as exc:  # never let the jobs list fail over the workflow half
        logger.warning("list_background_jobs: workflow-run merge failed: %s", exc)

    # Queued jobs (the one job model, #5353): running, waiting (one row per kind, `total` = how
    # many wait) and recently failed, with why.
    from fichero_server.execution import jobs as job_queue

    from fichero_server.recipes.runner import KIND as RECIPE_KIND

    from fichero_server.recipes import runner as recipe_runner

    # Once per poll: the summary reads this one too. Off the loop (#5843): the reads wait on the transaction gate.
    listed = await asyncio.to_thread(job_queue.snapshot, db)
    recipe_statuses: dict[str, dict[str, Any]] = {}  # each live recipe run's status, read once for the list and the summary
    for row in listed:
        state, reason = row["state"], row["reason"]
        name, current, total = job_queue.kind_name(row["kind"]), 0, row["count"]
        if row.get("done"):  # one row for a whole kind of work: "12 of 41" (#5839)
            current, total = row["done"], row["done"] + row["count"]
        if row["kind"] == RECIPE_KIND and row["count"] == 1:
            # A recipe run's row says what its tree says, from the one place (#5606). A run whose stages
            # cannot be read still shows, with its row's own state and reason (FIX 3).
            try:
                state, reason, status = await _recipe_state(db, row["id"])
                recipe_statuses[row["id"]] = status
                current = _recipe_pages_done(status)
            except Exception as exc:  # noqa: BLE001 -- the row stands, and says its stages could not be read
                logger.warning("list_background_jobs: no status for recipe run %s: %s", row["id"], exc)
                reason = f"{reason or state}; its stages could not be read: {exc}"
            # Named by its recipe, with the pages it runs over (#5615), never its kind's id.
            name, pages = recipe_runner.name_and_pages(db, row["id"])
            total = pages if pages is not None else 0
        jobs.append(
            BackgroundJob(
                id=row["id"],
                task_type=row["kind"],
                name=name,
                library=library,
                current=min(current, total) if total else current,
                total=total,
                # What is done, whatever its state: a failed row with nothing done is at 0, not 100 (#5615).
                percent=round(current * 100.0 / total, 1) if total and current else 0.0,
                state=state,
                reason=reason,
                parent_id=row.get("parent_id"),
                run_id=row.get("run_id"),
                offer=job_queue.offer_for(row["kind"], state, reason),
                failed_at=_utc(row.get("failed_at")) if state == "failed" else None,
                started_by=row.get("started_by"),
                remote=_remote_row(db, row),
            )
        )

    usage = process_tree_rusage()  # once per poll, shared by memory and energy (#5358)
    jobs = order_for_activity(jobs)
    return BackgroundJobsResponse(
        jobs=jobs,
        count=len(jobs),
        process_cpu_percent=process_cpu_percent(),
        process_memory_bytes=(usage or {}).get("memory_bytes"),
        process_energy_watts=process_energy_watts(usage),
        cpu_count=cpu_count(),
        paused=job_queue.is_paused(),
        mode=job_queue.mode(),
        machine=MachineState(**throttle.machine_state()),
        summary=await asyncio.to_thread(_queue_summary, db, listed),
        activity=await activity_summary(db, jobs, recipe_statuses),
    )


def _queue_summary(db: Database, listed: list[dict[str, Any]]) -> Optional[QueueSummary]:
    from fichero_server.execution import jobs as job_queue

    said = job_queue.queue_summary(db, listed)
    return QueueSummary(**said) if said else None


@router.get("/jobs/kind/{kind}/items", response_model=list[QueuedItem])
async def list_queued_items(
    kind: str,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Database = Depends(get_library_database),
) -> list[QueuedItem]:
    """The pages of one kind's row (`activity.window.expands-to-pages`, #5839): its queued jobs, each a line, in the
    order the lane will pick them, running first."""
    from fichero_server.execution import jobs as job_queue

    items = await asyncio.to_thread(job_queue.items_of_kind, db, kind, limit=limit, offset=offset)
    return [QueuedItem(**i) for i in items]


@router.get("/jobs/{job_id}", response_model=JobTree)
@single_flight
async def get_job_tree(
    job_id: str,
    depth: Optional[int] = Query(None, ge=0, description=(
        "levels below this job to include (1: a run and its steps); every row keeps its rolled-up counts and "
        "says how many children it left out. Omitted: the whole tree, every page")),
    db: Database = Depends(get_library_database),
) -> JobTree:
    """One job and everything under it, with progress rolled up (`activity.jobs-are-a-tree`): a
    workflow run (its id is its thread id), its steps, and the pages each step handed to a lane,
    each with its state and why. A large run's pages are thousands of rows: an agent asks for a `depth`
    (`activity.job-tree-to-a-depth`, #5605)."""
    from fichero_server.execution import jobs as job_queue

    # A row that stands for many jobs (the import's "Processing imported pages", one kind's counted
    # waiting jobs) reads as a tree of its stages (`activity.details.what-it-works-on-now`, #5623).
    # Off the loop (#5843): the tree's reads wait on the transaction gate behind a write.
    found = await asyncio.to_thread(
        lambda: job_queue.queue_tree(db, job_id) if job_queue.queue_of(job_id) else job_queue.tree(db, job_id))
    if found is None:
        raise HTTPException(status_code=404, detail=f"no job {job_id!r} in this project")
    if found["kind"] == "workflow":
        # A run's own node counts its pages from its account, the one its status shows (#5555): the
        # rows under its steps are lane work (a Kraken line, a model call), not pages, and a page read
        # without the lane has no row at all.
        from fichero_server.workflows.run_account import run_account

        account = await run_account(db, job_id)
        if account is not None:
            found["account"] = account
            # The account's pages, unless the rows under the run saw more: a sub-workflow's pages are in
            # its child run's checkpoint, and a step that failed outright never checkpointed its page.
            found.update(done=max(found["done"], account.pages_done), total=max(found["total"], account.pages_total),
                         failed=max(found["failed"], account.pages_failed))
            if account.waiting_reason and found["state"] in ("running", "waiting"):
                found["reason"] = account.waiting_reason
    elif found["kind"] == "run-a-recipe":
        await _recipe_run(db, found)
    if depth is not None:
        _cut(found, depth)
    # A waiting job under it says what the list says it waits for, from the one place (#5606), never the
    # reason an earlier scan left on its row. Only the rows returned are asked.
    def ask_waiting() -> None:
        for node in _walk(found):
            if node["state"] == "waiting" and node["kind"] not in job_queue.RUN_KINDS and node["kind"] != "run-a-recipe":
                now = job_queue.state_and_reason(db, node["id"])
                if now is not None:
                    node["reason"] = now[1]

    await asyncio.to_thread(ask_waiting)
    return JobTree.model_validate(found)


def _cut(node: dict[str, Any], depth: int) -> None:
    """Leave out the rows more than `depth` levels below `node`; the counts were rolled up before."""
    if depth == 0:
        node["children_omitted"], node["children"] = len(node["children"]), []
        return
    for child in node["children"]:
        _cut(child, depth - 1)


def _recipe_pages_done(status: dict[str, Any]) -> int:
    """A recipe run's pages done (#5615): those its furthest started workflow stage has done, by that stage's
    run account; 0 before one starts."""
    accounts = [s["account"] for s in status["steps"] if s.get("account") is not None]
    return accounts[-1].pages_done if accounts else 0


async def _recipe_state(db: Database, job_id: str) -> tuple[str, Optional[str], dict[str, Any]]:
    """A recipe run's state and reason, THE one derivation its row in the list and its tree both show (#5606):
    the row's own (`jobs.state_and_reason`: a waiting run says what it waits for as every waiting row does),
    and, while it runs, what its running stage waits for. Also its status with the stages' accounts."""
    from fichero_server.execution import jobs as job_queue
    from fichero_server.recipes import run_view, runner

    # Off the loop (#5843): `runner.status` reads the library's rows and waits on the transaction gate behind a write.
    status = await run_view.with_accounts(db, await asyncio.to_thread(runner.status, db, job_id))
    state, reason = job_queue.state_and_reason(db, job_id) or (status["state"], status["reason"])
    if state == "running" and status["waiting_for"]:
        reason = status["waiting_for"]
    return state, reason, status


async def _recipe_run(db: Database, found: dict[str, Any]) -> None:
    """A recipe run's node (#5576, #5577): its stages in order, each workflow stage with its run's account (the
    one that run's own node shows), its state and reason as its row in the list has them (`_recipe_state`),
    and, once it has ended, what it made."""
    from fichero_server.recipes import run_view

    found["state"], found["reason"], status = await _recipe_state(db, found["id"])
    found["stages"] = status["steps"]
    accounts = {s["child_id"]: s["account"] for s in status["steps"] if s.get("account") is not None}
    for child in found["children"]:
        account = accounts.get(child["id"])
        if account is not None:
            child["account"] = account
            child.update(done=max(child["done"], account.pages_done), total=max(child["total"], account.pages_total),
                         failed=max(child["failed"], account.pages_failed))
    if found["children"]:  # the roll-up, again, over the stages' own counts
        for key in ("done", "total", "failed"):
            found[key] = sum(c[key] for c in found["children"])
    if found["state"] in ("done", "failed", "cancelled"):
        found["summary"] = await run_view.summary(db, found["id"])


class JobLogLine(BaseModel):
    """One line the engine wrote for a job or a job under it (#5561)."""

    timestamp: Optional[str] = Field(None, description="ISO 8601, UTC; null for what a row waits for now")
    level: str = Field(description="info, warning or error")
    message: str
    job_id: str = Field(description="the row the line is about: the job asked for or one under it")
    detail: Literal["person", "developer"] = Field(
        "person", description="person: a page or stage done or failed, the person's log; developer: the debug lines "
        "(Node started, a row's start, what a row waits for now, a server's output), off unless asked for")


class JobLog(BaseModel):
    """The log of one job and the jobs under it, newest last (`activity.details.log-filtered-newest-last`)."""

    job_id: str
    lines: list[JobLogLine] = Field(default_factory=list)


#: The most lines a job's log returns: the newest are kept.
_JOB_LOG_LIMIT = 1000


_DEBUG_EVENT = re.compile(r"^Node '.*' (started|completed in \d+ms)$")


def _event_detail(level: str, message: str) -> str:
    """An activity event is the person's unless it is a debug line ("Node 'x' started", "completed in 12ms")."""
    return "developer" if level == "debug" or _DEBUG_EVENT.match(message) else "person"


def person_lines(lines: list["JobLogLine"]) -> list["JobLogLine"]:
    """The person's log (`activity.log.persons-log`): only person lines, and no sentence twice for the same row."""
    seen: set[tuple[str, str]] = set()
    kept = []
    for line in lines:
        if line.detail != "person" or (line.job_id, line.message) in seen:
            continue
        seen.add((line.job_id, line.message))
        kept.append(line)
    return kept


def _job_rows_log(node: dict[str, Any]) -> list[JobLogLine]:
    """The lines a job's own row says, and the rows under it: it started, how it ended, what it waits for."""
    name = node.get("display_name") or node.get("name") or node["id"]
    lines = []
    if node.get("started_at"):
        lines.append(JobLogLine(timestamp=node["started_at"], level="info", message=f"Started {name}",
                                job_id=node["id"], detail="developer"))
    state, reason = node.get("state") or "", node.get("reason")
    ended = {"done": ("info", f"Done: {name}"),
             "failed": ("error", f"Failed: {name}: {reason or 'no reason recorded'}"),
             "cancelled": ("warning", f"Stopped: {name}" + (f": {reason}" if reason else ""))}.get(state)
    if ended is not None:
        lines.append(JobLogLine(timestamp=node.get("finished_at"), level=ended[0], message=ended[1],
                                job_id=node["id"]))
    elif reason:
        lines.append(JobLogLine(timestamp=None, level="info", message=f"{state.capitalize()}: {name}: {reason}",
                                job_id=node["id"], detail="developer"))
    for child in node.get("children", []):
        lines.extend(_job_rows_log(child))
    return lines


def _walk(node: dict[str, Any]):
    yield node
    for child in node.get("children", []):
        yield from _walk(child)


def _event_threads(node: dict[str, Any], wanted: dict[str, Optional[set[str]]]) -> None:
    """The runs whose events belong to this job: a run's whole thread, a step's own node of its run."""
    if node["kind"] == "workflow":
        wanted[node["id"]] = None
    elif node["kind"] == "workflow-step" and ":" in node["id"]:
        thread, step = node["id"].rsplit(":", 1)
        if thread not in wanted:
            wanted[thread] = set()
        if wanted[thread] is not None:
            wanted[thread].add(step)
    for child in node.get("children", []):
        _event_threads(child, wanted)


@router.get("/jobs/{job_id}/log", response_model=JobLog)
async def get_job_log(
    job_id: str,
    detail: Literal["person", "developer"] = Query("person", description="developer adds the debug lines"),
    db: Database = Depends(get_library_database),
) -> JobLog:
    """The log of one row of Activity and the rows under it, newest last (#5561): what the engine wrote for
    a run (its activity events), for a step (the events of its node), and what each job's own row says (it
    started, it failed and why, it waits and for what). Nothing about another row."""
    from fichero_server.execution import jobs as job_queue

    found = await asyncio.to_thread(
        lambda: job_queue.queue_tree(db, job_id) if job_queue.queue_of(job_id) else job_queue.tree(db, job_id))
    if found is None:
        raise HTTPException(status_code=404, detail=f"no job {job_id!r} in this project")
    lines = _job_rows_log(found)
    wanted: dict[str, Optional[set[str]]] = {}
    _event_threads(found, wanted)
    rows = {node["id"] for node in _walk(found)}
    tracker = get_activity_tracker(str(db.path))
    for thread, steps in wanted.items():
        for event in await tracker.query(ActivityFilter(thread_id=thread, limit=_JOB_LOG_LIMIT)):
            if steps is not None and event.node_id not in steps:
                continue
            when = event.timestamp
            when = when.replace(tzinfo=timezone.utc) if when.tzinfo is None else when.astimezone(timezone.utc)
            error = f": {event.error}" if event.error and event.error not in event.message else ""
            level = event.level.value if isinstance(event.level, ActivityLevel) else str(event.level)
            lines.append(JobLogLine(
                timestamp=when.isoformat(), level=level, message=event.message + error,
                detail=_event_detail(level, event.message),
                # A node with no row of its own (the builder's routing) is the run's line.
                job_id=row if (row := job_queue.step_id(thread, event.node_id or "")) in rows else thread))

    for row, entry in job_queue.logged_lines(db, list(rows)):  # what a row's work kept (a server's output)
        lines.append(JobLogLine(timestamp=entry.get("at"), level=str(entry.get("level") or "info"),
                                message=str(entry["message"]), job_id=row, detail="developer"))

    def order(line: JobLogLine) -> tuple[int, datetime]:
        # A line with no time (what a row waits for now) is the newest.
        if line.timestamp is None:
            return (1, datetime.min)
        return (0, _parse_iso_to_naive_utc(line.timestamp))

    lines.sort(key=order)
    if detail == "person":
        lines = person_lines(lines)
    return JobLog(job_id=job_id, lines=lines[-_JOB_LOG_LIMIT:])


@router.put("/jobs/paused", response_model=BackgroundPauseResponse)
async def set_background_paused(
    request: BackgroundPauseRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> BackgroundPauseResponse:
    """Pause or resume ALL background work on this Mac (`activity.pause.global`). Kept across
    relaunch. While paused nothing is started by the queue; a job already running finishes."""
    result = registry.invoke(db, "background.pause", {"paused": request.paused}, ctx)
    return BackgroundPauseResponse.model_validate(result.result)


@router.put("/jobs/mode", response_model=BackgroundModeResponse)
async def set_background_mode(
    request: BackgroundModeRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> BackgroundModeResponse:
    """The Start / Stop control (`activity.mode.start-stop`, #5621), for the whole Mac: `started` lets
    waiting work go ahead although the person is at the Mac or it is on battery (memory and heat still
    hold it, and heavy work still runs one job at a time while memory is busy) until set back to
    `automatic`; `paused` pauses all background work. Kept across relaunch."""
    result = registry.invoke(db, "background.mode", {"mode": request.mode}, ctx)
    return BackgroundModeResponse.model_validate(result.result)


class JobPauseRequest(BaseModel):
    paused: bool = Field(description="true pauses this job; false resumes it")


class JobControlParams(BaseModel):
    job_id: str
    paused: Optional[bool] = None


class JobStateResponse(BaseModel):
    id: str
    state: str = Field(description="the job's state after the request: waiting, paused, running, cancelled, …")


class RetryResponse(JobStateResponse):
    replaces: Optional[str] = Field(default=None, description=(
        "a retried workflow run: the run this new one reads the pages of again (`id` is the new run's); the old "
        "one is no longer listed"))


def _control_job(db: Database, ctx: ActionContext, name: str, params: dict) -> JobStateResponse:
    try:
        result = registry.invoke(db, name, params, ctx)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc).strip("'\"")) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return JobStateResponse.model_validate(result.result)


@router.put("/jobs/{job_id}/paused", response_model=JobStateResponse)
async def set_job_paused(
    job_id: str,
    request: JobPauseRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> JobStateResponse:
    """Pause one waiting job, or resume a paused one (`activity.pause.per-job`). A paused job stays
    paused across relaunch. A running job finishes the item it is on; a page a workflow run is
    waiting for is paused with its run (409)."""
    return _control_job(db, ctx, "job.pause", {"job_id": job_id, "paused": request.paused})


@router.post("/jobs/{job_id}/cancel", response_model=JobStateResponse)
async def cancel_job(
    job_id: str,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> JobStateResponse:
    """Stop one job: a waiting or paused one ends cancelled; a page a run waits for is withdrawn;
    a training Job is cancelled on Hugging Face. A job running here finishes its item (the state
    returned says `running`)."""
    return _control_job(db, ctx, "job.cancel", {"job_id": job_id})


@router.post("/jobs/{job_id}/retry", response_model=RetryResponse, response_model_exclude_none=True)
async def retry_job(
    job_id: str,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> RetryResponse:
    """Run a failed or stopped job again: it goes back to waiting and carries on from its own
    checkpoint where it keeps one (the same row: one row in Activity, its `failed_at` cleared). A failed
    or stopped workflow run is run again over the pages it did not do, as a new run that takes its place
    in the list (`replaces`; `activity.retry.one-row`). A page a workflow run waits for, a training on
    Hugging Face, or work that is already waiting again cannot be retried here (409, with the reason)."""
    from fichero_server.execution import jobs as job_queue

    try:
        kind, _state = job_queue._job_row(db, job_id)
    except KeyError:
        kind = None
    if kind == "workflow":
        from fichero_server.api.routes.workflow_execution.core import read_again

        new_thread, _workflow, _pages = await read_again(db, job_id)
        return RetryResponse(id=new_thread, state="running", replaces=job_id)
    if kind is not None and job_queue._is_attached(kind) and job_queue.run_of_page(db, job_id):
        # A page a run handed in: Retry reads it again WITHIN its run (`activity.retry.page-within-run`): a run that has
        # ended reopens for it, a run still going takes it into its queue. Never a new run, never a 409 for a live one.
        from fichero_server.api.routes.workflow_execution.core import retry_page_in_run

        _run_id, how = await retry_page_in_run(db, job_id)
        return RetryResponse(id=job_id, state="running" if how == "reopened" else "waiting")
    return RetryResponse(**_control_job(db, ctx, "job.retry", {"job_id": job_id}).model_dump())


class ClearFailedResponse(BaseModel):
    cleared_ids: list[str] = Field(description="the failed jobs cleared: kept, no longer listed")
    count: int


@router.post("/jobs/clear-failed", response_model=ClearFailedResponse)
async def clear_failed_jobs(
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> ClearFailedResponse:
    """Clear Failed (`activity.window.clear-failed`, #5634): every failed job the jobs list shows is
    cleared. Its row is kept (its run's tree and the record still read it) and no longer listed; a
    retry lists it again. Failed workflow runs are cleared by `POST /api/workflow-execution/runs/delete`
    with `statuses: ["failed"]`."""
    result = registry.invoke(db, "job.clear_failed", {}, ctx)
    return ClearFailedResponse.model_validate(result.result)


class ClearFailedParams(BaseModel):
    pass


@action("job.clear_failed", ClearFailedParams, domains=["activity"])
def _action_job_clear_failed(db: Database, params: ClearFailedParams, ctx: ActionContext) -> tuple[dict, ChangeSpec]:
    from fichero_server.execution import jobs as job_queue

    ids = job_queue.clear_failed(db)
    return {"cleared_ids": ids, "count": len(ids)}, ChangeSpec(
        domains=["activity"], target_ids=ids, before={"state": "failed"},
        after={"cleared": len(ids)}, emit_type="job.updated",
    )


def _invert_job_pause(before: dict | None, after: dict | None, ctx: ActionContext):
    return ("job.pause", {"job_id": (after or {})["id"], "paused": (before or {}).get("state") == "paused"})


@action("job.pause", JobControlParams, domains=["activity"], undoable=True, invert=_invert_job_pause)
def _action_job_pause(db: Database, params: JobControlParams, ctx: ActionContext) -> tuple[dict, ChangeSpec]:
    from fichero_server.execution import jobs as job_queue

    before = job_queue.row_state(db, params.job_id)
    state = job_queue.pause_job(db, params.job_id, bool(params.paused))
    return {"id": params.job_id, "state": state}, ChangeSpec(
        domains=["activity"], target_ids=[params.job_id], before={"state": before},
        after={"id": params.job_id, "state": state}, emit_type="job.updated",
    )


@action("job.cancel", JobControlParams, domains=["activity"])
def _action_job_cancel(db: Database, params: JobControlParams, ctx: ActionContext) -> tuple[dict, ChangeSpec]:
    from fichero_server.execution import jobs as job_queue

    before = job_queue.row_state(db, params.job_id)
    job_queue.note_stopper(params.job_id, ctx.actor, ctx.client)  # the row says who stopped it
    state = job_queue.cancel_job(db, params.job_id)
    return {"id": params.job_id, "state": state}, ChangeSpec(
        domains=["activity"], target_ids=[params.job_id], before={"state": before},
        after={"id": params.job_id, "state": state}, emit_type="job.updated",
    )


@action("job.retry", JobControlParams, domains=["activity"])
def _action_job_retry(db: Database, params: JobControlParams, ctx: ActionContext) -> tuple[dict, ChangeSpec]:
    from fichero_server.execution import jobs as job_queue

    before = job_queue._job_row(db, params.job_id)[1]
    state = job_queue.retry_job(db, params.job_id)
    return {"id": params.job_id, "state": state}, ChangeSpec(
        domains=["activity"], target_ids=[params.job_id], before={"state": before},
        after={"id": params.job_id, "state": state}, emit_type="job.updated",
    )


def _invert_pause(before: dict | None, after: dict | None, ctx: ActionContext):
    return ("background.pause", {"paused": bool((before or {}).get("paused"))})


@action("background.pause", BackgroundPauseRequest, domains=["activity"], undoable=True, invert=_invert_pause)
def _action_background_pause(
    db: Database, params: BackgroundPauseRequest, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    from fichero_server.execution import jobs as job_queue

    before = job_queue.is_paused()
    # Applied once the audit commits: a rolled-back action leaves the switch as it was.
    db.add_after_commit_hook(lambda: job_queue.set_paused(params.paused))
    return {"paused": params.paused}, ChangeSpec(
        domains=["activity"], before={"paused": before}, after={"paused": params.paused},
        emit_type="background.paused" if params.paused else "background.resumed",
    )


def _invert_mode(before: dict | None, after: dict | None, ctx: ActionContext):
    return ("background.mode", {"mode": (before or {}).get("mode") or "automatic"})


@action("background.mode", BackgroundModeRequest, domains=["activity"], undoable=True, invert=_invert_mode)
def _action_background_mode(
    db: Database, params: BackgroundModeRequest, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    from fichero_server.execution import jobs as job_queue

    before = job_queue.mode()
    # Applied once the audit commits: a rolled-back action leaves the mode as it was.
    db.add_after_commit_hook(lambda: job_queue.set_mode(params.mode))
    return {"mode": params.mode}, ChangeSpec(
        domains=["activity"], before={"mode": before}, after={"mode": params.mode},
        emit_type="background.mode",
    )


@router.get("/stats", response_model=ActivityStatsResponse)
@single_flight
async def get_activity_stats(
    db: Database = Depends(get_library_database),
    hours: int = Query(24, ge=1, le=720, description="Number of hours to analyze"),
) -> ActivityStatsResponse:
    """
    Get aggregated activity statistics.

    Returns counts by type and level, error/warning counts,
    average workflow duration, and success rate.
    """
    tracker = get_activity_tracker(str(db.path))

    until = utc_now()
    since = until - timedelta(hours=hours)

    stats = await tracker.get_stats(since=since, until=until)
    return ActivityStatsResponse.from_stats(stats)


@router.get("/stream")
async def stream_activities(
    db: Database = Depends(get_library_database),
    types: Optional[str] = Query(None, description="Comma-separated activity types"),
    levels: Optional[str] = Query(None, description="Comma-separated levels"),
    workflow_id: Optional[str] = None,
    batch_id: Optional[str] = None,
):
    """
    Stream real-time activities via Server-Sent Events.

    Clients receive activity events as they occur, filtered by
    the provided criteria.
    """
    tracker = get_activity_tracker(str(db.path))
    library_path = str(Path(db.path).parent)

    # Parse filter
    type_list = None
    if types:
        try:
            type_list = [ActivityType(t.strip()) for t in types.split(",")]
        except ValueError:
            pass

    level_list = None
    if levels:
        try:
            level_list = [ActivityLevel(lvl.strip()) for lvl in levels.split(",")]
        except ValueError:
            pass

    filter = ActivityFilter(
        types=type_list,
        levels=level_list,
        workflow_id=workflow_id,
        batch_id=batch_id,
    )

    # Subscribe to activity stream
    sub_id = tracker.subscribe(filter)
    change_subscription = _change_hub.connect(library_path)

    async def event_generator():
        tracker_stream = tracker.stream(sub_id, filter)
        # PERSISTENT tasks across iterations (2026-08-10, the 11-second
        # reconnect churn in Daniel's log): the previous shape re-created and
        # then CANCELLED both tasks every iteration — including the keepalive
        # path, whose `continue` still runs the loop's finally. Cancelling an
        # `anext()` task FINALIZES the underlying async generator, so the very
        # next iteration got StopAsyncIteration and returned: every idle
        # stream died at its first 10s keepalive, and each client reconnected
        # a second later — one spurious access-log line, one
        # get_activity_tracker INFO, and a re-subscription every ~11s, forever.
        # A pending task now survives quiet ticks and is only awaited when it
        # actually completes.
        tracker_task = None
        change_task = None
        try:
            while True:
                if tracker_task is None:
                    tracker_task = asyncio.create_task(anext(tracker_stream))
                if change_task is None:
                    change_task = asyncio.create_task(change_subscription.queue.get())
                done, _pending = await asyncio.wait(
                    {tracker_task, change_task},
                    timeout=_KEEPALIVE_TIMEOUT,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if not done:
                    yield ": keepalive\n\n"
                    continue
                if change_task in done:
                    change_event = change_task.result()
                    change_task = None
                    response = _change_event_to_activity_response(change_event)
                    yield f"data: {response.model_dump_json()}\n\n"
                if tracker_task in done:
                    try:
                        activity = tracker_task.result()
                    except StopAsyncIteration:
                        return
                    tracker_task = None
                    response = ActivityResponse.from_activity(activity)
                    yield f"data: {response.model_dump_json()}\n\n"
        except asyncio.CancelledError:
            logger.info("activity-stream: client cancelled cleanly lib=%s", library_path)
            raise
        except GeneratorExit:
            logger.info("activity-stream: client closed cleanly lib=%s", library_path)
            raise
        except Exception as e:
            logger.exception("activity-stream: SSE failed lib=%s", library_path)
            error_event = {"error": str(e)}
            yield f"data: {json.dumps(error_event)}\n\n"
        finally:
            for task in (tracker_task, change_task):
                if task is not None and not task.done():
                    task.cancel()
            await asyncio.gather(
                *(task for task in (tracker_task, change_task) if task is not None),
                return_exceptions=True,
            )
            await tracker_stream.aclose()
            tracker.unsubscribe(sub_id)
            _change_hub.unsubscribe(library_path, change_subscription.queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# /ws (a second, parallel live transport duplicating GET /activity/stream) was
# deleted in the verify-then-prune pass (#3235, 2026-07-30). One live transport
# — SSE, which folds change frames (#3159) and carries the client's
# reconnect/backoff semantics — is the invariant worth protecting; the
# WebSocket path had no callers (app, CLI, MCP, docs all verified) and did not
# fold change events, so any client using it would silently miss remote
# mutations.


@router.get("/workflow/{workflow_id}", response_model=ActivityListResponse)
async def get_workflow_activity(
    workflow_id: str,
    db: Database = Depends(get_library_database),
    limit: int = Query(100, ge=1, le=1000),
) -> list[ActivityResponse]:
    """Get all activity for a specific workflow."""
    tracker = get_activity_tracker(str(db.path))

    filter = ActivityFilter(
        workflow_id=workflow_id,
        limit=limit,
    )

    activities = await tracker.query(filter)
    return ActivityListResponse(items=[ActivityResponse.from_activity(a) for a in activities], count=len(activities))


@router.get("/batch/{batch_id}", response_model=ActivityListResponse)
async def get_batch_activity(
    batch_id: str,
    db: Database = Depends(get_library_database),
    limit: int = Query(100, ge=1, le=1000),
) -> list[ActivityResponse]:
    """Get all activity for a specific batch."""
    tracker = get_activity_tracker(str(db.path))

    filter = ActivityFilter(
        batch_id=batch_id,
        limit=limit,
    )

    activities = await tracker.query(filter)
    return ActivityListResponse(items=[ActivityResponse.from_activity(a) for a in activities], count=len(activities))


@router.delete("/cleanup")
async def cleanup_old_activities(
    db: Database = Depends(get_library_database_for_write),
    days: int = Query(
        30, ge=1, le=365, description="Delete activities older than N days"
    ),
    ctx: ActionContext = Depends(action_context),
) -> CleanupResponse:
    """
    Delete old activities to manage database size.

    Returns the number of deleted activities.
    """
    result = registry.invoke(
        db,
        "activity.cleanup",
        {"days": days},
        ctx,
    )
    return CleanupResponse.model_validate(result.result)


@action(
    "activity.cleanup",
    ActivityCleanupParams,
    domains=["activity"],
    undoable=False,
)
def _action_cleanup_old_activities(
    db: Database,
    params: ActivityCleanupParams,
    ctx: ActionContext,
) -> tuple[dict[str, Any], ChangeSpec]:
    tracker = get_activity_tracker(str(db.path))
    older_than = utc_now() - timedelta(days=params.days)
    deleted = tracker.store.delete_old_sync(older_than)
    result = {"deleted": deleted, "older_than": older_than.isoformat()}
    spec = ChangeSpec(
        domains=["activity"],
        target_ids=[],
        before={"days": params.days},
        after=result,
        emit_type="activity.updated",
    )
    return result, spec


@router.delete("/{activity_id}")
async def delete_activity(
    activity_id: str,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> ActivityDeleteResponse:
    """Delete ONE activity entry the user chose to remove from the log.

    The bulk `/cleanup` deletes by age; this removes a single entry the user
    picked (Daniel: an old activity should be deletable). 404 when the id is
    unknown so the UI never claims a delete that removed nothing.
    """
    result = registry.invoke(
        db,
        "activity.delete",
        {"activity_id": activity_id},
        ctx,
    )
    response = ActivityDeleteResponse.model_validate(result.result)
    if response.deleted == 0:
        raise HTTPException(status_code=404, detail="Activity not found")
    return response


@action(
    "activity.delete",
    ActivityDeleteParams,
    domains=["activity"],
    undoable=False,
)
def _action_delete_activity(
    db: Database,
    params: ActivityDeleteParams,
    ctx: ActionContext,
) -> tuple[dict[str, Any], ChangeSpec]:
    tracker = get_activity_tracker(str(db.path))
    deleted = tracker.store.delete_by_id_sync(params.activity_id)
    result = {"deleted": deleted, "activity_id": params.activity_id}
    spec = ChangeSpec(
        domains=["activity"],
        target_ids=[params.activity_id],
        before={"activity_id": params.activity_id},
        after=result,
        emit_type="activity.updated",
    )
    return result, spec


# =============================================================================
# Enhanced Activity Metrics (Issue #425)
# =============================================================================
#
# /feed, /trends, /top and their response models (~420 lines of #425
# dashboard-shaped aggregation) were deleted in the verify-then-prune pass
# (#3235, 2026-07-30): no UI was ever built on them and no non-app caller
# existed (app, CLI, MCP, docs all verified — the CLI's `top_entities` reads
# /api/entities/top, not /activity/top). If an activity dashboard becomes
# real, rebuild the aggregations against the need it actually has, next to
# /metrics/summary below. (/entity-types — a hardcoded 4-element literal
# served over HTTP — went earlier, in the 2026-07-27 endpoint cleanup.)


class ActivityMetricsSummary(BaseModel):
    """Enhanced activity metrics summary."""

    total_activities: int
    total_workflows: int
    total_batches: int
    error_count: int
    warning_count: int
    success_rate: float
    avg_workflow_duration_ms: float | None
    avg_batch_duration_ms: float | None
    busiest_hour: int | None
    period_start: str
    period_end: str


# -----------------------------------------------------------------------------
# Enhanced Metrics Endpoint
# -----------------------------------------------------------------------------


@router.get("/metrics/summary", response_model=ActivityMetricsSummary)
async def get_activity_metrics_summary(
    db: Database = Depends(get_library_database),
    hours: int = Query(24, ge=1, le=720),
) -> ActivityMetricsSummary:
    """
    Get comprehensive activity metrics summary.

    Includes trends, rates, and busiest periods.
    """
    tracker = get_activity_tracker(str(db.path))

    until = utc_now()
    since = until - timedelta(hours=hours)

    # Get basic stats
    stats = await tracker.get_stats(since=since, until=until)

    # Get activities for enhanced metrics
    filter = ActivityFilter(since=since, until=until, limit=10000)
    activities = await tracker.query(filter)

    # Count by hour to find busiest
    hour_counts: dict[int, int] = {}
    workflow_durations: list[float] = []
    batch_durations: list[float] = []
    workflow_count = 0
    batch_count = 0

    for act in activities:
        # Hour distribution, in UTC. Timestamps are aware UTC as of #4347, so
        # `busiest_hour` below is a UTC hour-of-day — before the sweep it was
        # accidentally the *server's* local hour, which was never the viewer's
        # either. A client that wants a local hour converts the UTC one.
        hour = act.timestamp.hour
        hour_counts[hour] = hour_counts.get(hour, 0) + 1

        # Durations
        if act.type == ActivityType.WORKFLOW_COMPLETED and act.duration_ms:
            workflow_durations.append(act.duration_ms)
            workflow_count += 1
        elif act.type == ActivityType.BATCH_COMPLETED and act.duration_ms:
            batch_durations.append(act.duration_ms)
            batch_count += 1

    busiest_hour = max(hour_counts.items(), key=lambda x: x[1])[0] if hour_counts else None

    avg_workflow_duration = (
        sum(workflow_durations) / len(workflow_durations) if workflow_durations else None
    )
    avg_batch_duration = (
        sum(batch_durations) / len(batch_durations) if batch_durations else None
    )

    return ActivityMetricsSummary(
        total_activities=stats.total_activities,
        total_workflows=workflow_count,
        total_batches=batch_count,
        error_count=stats.error_count,
        warning_count=stats.warning_count,
        success_rate=stats.success_rate,
        avg_workflow_duration_ms=avg_workflow_duration,
        avg_batch_duration_ms=avg_batch_duration,
        busiest_hour=busiest_hour,
        period_start=stats.period_start.isoformat(),
        period_end=stats.period_end.isoformat(),
    )


# Resolve forward refs in ActivityListResponse (declared in models.py with
# items: list["ActivityResponse"]). Pydantic v2 needs this after both modules
# are loaded — see #1144.
from fichero_server.models import ActivityListResponse  # noqa: E402

ActivityListResponse.model_rebuild(_types_namespace={"ActivityResponse": ActivityResponse})
