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
import json
import logging
from datetime import datetime, timedelta, timezone
from fichero_server.core.timeutil import utc_now
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
    # The job this one belongs to: a page's step (whose own parent is its run), #5353.
    parent_id: Optional[str] = None
    # A workflow run's account (#5555): `current`/`total` are its pages done and in all.
    account: Optional[RunAccount] = None


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


class BackgroundJobsResponse(BaseModel):
    """Snapshot of running background jobs + rough process CPU usage."""

    jobs: list[BackgroundJob] = Field(default_factory=list)
    count: int
    # Process CPU% since the last poll (100 == one core busy; can exceed 100 on
    # multiple cores). None on the very first poll (no interval yet) or if the
    # sample is unavailable. Per-job attribution is intentionally not attempted.
    process_cpu_percent: Optional[float] = None
    cpu_count: int
    # Pause Background Work is on (`activity.pause.global`): nothing that runs by itself starts.
    paused: bool = False
    # This Mac's memory, heat, power and use, and why heavy work waits (#5415).
    machine: MachineState


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

    from fichero_server.core.background_compute import cpu_count, process_cpu_percent
    from fichero_server.execution import throttle
    from fichero_server.importers import derivatives
    from fichero_server.importers.derivatives import background_jobs_snapshot

    library = str(_Path(db.path).parent)
    jobs = [BackgroundJob(**job) for job in background_jobs_snapshot(library)]
    if jobs:
        # The import's progress row waits when none of its stages runs, and says for what, as any
        # waiting row does (`activity.waiting-says-why`, #5606: it sat at 100 of 406 with no reason).
        from fichero_server.execution import jobs as job_queue

        held = job_queue.waiting_reason_of(
            db, [derivatives.THUMBNAIL_KIND, derivatives.EMBED_KIND, derivatives.NLP_KIND])
        if held:
            for job in jobs:
                job.state, job.reason = "waiting", held

    # Workflow runs that are running or recently failed. A completed run is not a
    # "job" the user needs to watch; a running or failed one is.
    try:
        tracker = get_activity_tracker(str(db.path))
        runs = await tracker.store.list_workflow_runs(limit=50)
        from fichero_server.workflows.run_account import run_account

        for run in runs:
            status = (run.status or "").lower()
            if status not in ("running", "failed"):
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
            percent = (
                100.0 if status == "failed"
                else (current * 100.0 / total if total else 0.0)
            )
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
                )
            )
    except Exception as exc:  # never let the jobs list fail over the workflow half
        logger.debug("list_background_jobs: workflow-run merge failed: %s", exc)

    # Queued jobs (the one job model, #5353): running, waiting (one row per kind, `total` = how
    # many wait) and recently failed, with why.
    from fichero_server.execution import jobs as job_queue

    from fichero_server.recipes.runner import KIND as RECIPE_KIND

    for row in job_queue.snapshot(db):
        state, reason = row["state"], row["reason"]
        if row["kind"] == RECIPE_KIND and row["count"] == 1:
            # A recipe run's row says what its tree says, from the one place (#5606). A run whose stages
            # cannot be read still shows, with its row's own state and reason (FIX 3).
            try:
                state, reason, _status = await _recipe_state(db, row["id"])
            except Exception as exc:  # noqa: BLE001 -- the row stands; said in the log
                logger.warning("list_background_jobs: no status for recipe run %s: %s", row["id"], exc)
        jobs.append(
            BackgroundJob(
                id=row["id"],
                task_type=row["kind"],
                name=job_queue.kind_name(row["kind"]),
                library=library,
                current=1 if state == "failed" else 0,
                total=row["count"],
                percent=100.0 if state == "failed" else 0.0,
                state=state,
                reason=reason,
                parent_id=row.get("parent_id"),
            )
        )

    return BackgroundJobsResponse(
        jobs=jobs,
        count=len(jobs),
        process_cpu_percent=process_cpu_percent(),
        cpu_count=cpu_count(),
        paused=job_queue.is_paused(),
        machine=MachineState(**throttle.machine_state()),
    )


@router.get("/jobs/{job_id}", response_model=JobTree)
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

    found = job_queue.tree(db, job_id)
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
    for node in _walk(found):
        if node["state"] == "waiting" and node["kind"] not in job_queue.RUN_KINDS and node["kind"] != "run-a-recipe":
            now = job_queue.state_and_reason(db, node["id"])
            if now is not None:
                node["reason"] = now[1]
    return JobTree.model_validate(found)


def _cut(node: dict[str, Any], depth: int) -> None:
    """Leave out the rows more than `depth` levels below `node`; the counts were rolled up before."""
    if depth == 0:
        node["children_omitted"], node["children"] = len(node["children"]), []
        return
    for child in node["children"]:
        _cut(child, depth - 1)


async def _recipe_state(db: Database, job_id: str) -> tuple[str, Optional[str], dict[str, Any]]:
    """A recipe run's state and reason, THE one derivation its row in the list and its tree both show (#5606):
    the row's own (`jobs.state_and_reason`: a waiting run says what it waits for as every waiting row does),
    and, while it runs, what its running stage waits for. Also its status with the stages' accounts."""
    from fichero_server.execution import jobs as job_queue
    from fichero_server.recipes import run_view, runner

    status = await run_view.with_accounts(db, runner.status(db, job_id))
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


class JobLog(BaseModel):
    """The log of one job and the jobs under it, newest last (`activity.details.log-filtered-newest-last`)."""

    job_id: str
    lines: list[JobLogLine] = Field(default_factory=list)


#: The most lines a job's log returns: the newest are kept.
_JOB_LOG_LIMIT = 1000


def _job_rows_log(node: dict[str, Any]) -> list[JobLogLine]:
    """The lines a job's own row says, and the rows under it: it started, how it ended, what it waits for."""
    name = node.get("display_name") or node.get("name") or node["id"]
    lines = []
    if node.get("started_at"):
        lines.append(JobLogLine(timestamp=node["started_at"], level="info", message=f"Started {name}",
                                job_id=node["id"]))
    state, reason = node.get("state") or "", node.get("reason")
    ended = {"done": ("info", f"Done: {name}"),
             "failed": ("error", f"Failed: {name}: {reason or 'no reason recorded'}"),
             "cancelled": ("warning", f"Stopped: {name}" + (f": {reason}" if reason else ""))}.get(state)
    if ended is not None:
        lines.append(JobLogLine(timestamp=node.get("finished_at"), level=ended[0], message=ended[1],
                                job_id=node["id"]))
    elif reason:
        lines.append(JobLogLine(timestamp=None, level="info", message=f"{state.capitalize()}: {name}: {reason}",
                                job_id=node["id"]))
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
async def get_job_log(job_id: str, db: Database = Depends(get_library_database)) -> JobLog:
    """The log of one row of Activity and the rows under it, newest last (#5561): what the engine wrote for
    a run (its activity events), for a step (the events of its node), and what each job's own row says (it
    started, it failed and why, it waits and for what). Nothing about another row."""
    from fichero_server.execution import jobs as job_queue

    found = job_queue.tree(db, job_id)
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
                # A node with no row of its own (the builder's routing) is the run's line.
                job_id=row if (row := job_queue.step_id(thread, event.node_id or "")) in rows else thread))

    for row, entry in job_queue.logged_lines(db, list(rows)):  # what a row's work kept (a server's output)
        lines.append(JobLogLine(timestamp=entry.get("at"), level=str(entry.get("level") or "info"),
                                message=str(entry["message"]), job_id=row))

    def order(line: JobLogLine) -> tuple[int, datetime]:
        # A line with no time (what a row waits for now) is the newest.
        if line.timestamp is None:
            return (1, datetime.min)
        return (0, _parse_iso_to_naive_utc(line.timestamp))

    lines.sort(key=order)
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


class JobPauseRequest(BaseModel):
    paused: bool = Field(description="true pauses this job; false resumes it")


class JobControlParams(BaseModel):
    job_id: str
    paused: Optional[bool] = None


class JobStateResponse(BaseModel):
    id: str
    state: str = Field(description="the job's state after the request: waiting, paused, running, cancelled, …")


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


def _invert_job_pause(before: dict | None, after: dict | None, ctx: ActionContext):
    return ("job.pause", {"job_id": (after or {})["id"], "paused": (before or {}).get("state") == "paused"})


@action("job.pause", JobControlParams, domains=["activity"], undoable=True, invert=_invert_job_pause)
def _action_job_pause(db: Database, params: JobControlParams, ctx: ActionContext) -> tuple[dict, ChangeSpec]:
    from fichero_server.execution import jobs as job_queue

    before = job_queue._job_row(db, params.job_id)[1]
    state = job_queue.pause_job(db, params.job_id, bool(params.paused))
    return {"id": params.job_id, "state": state}, ChangeSpec(
        domains=["activity"], target_ids=[params.job_id], before={"state": before},
        after={"id": params.job_id, "state": state}, emit_type="job.updated",
    )


@action("job.cancel", JobControlParams, domains=["activity"])
def _action_job_cancel(db: Database, params: JobControlParams, ctx: ActionContext) -> tuple[dict, ChangeSpec]:
    from fichero_server.execution import jobs as job_queue

    before = job_queue._job_row(db, params.job_id)[1]
    state = job_queue.cancel_job(db, params.job_id)
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


@router.get("/stats", response_model=ActivityStatsResponse)
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
