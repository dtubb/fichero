"""One job model, first slice: background work as durable rows, run by one scheduler (#5353).

Spec: `docs/contributor_manual/specs/ui/activity-and-automatic-work.md` (sections 1, 3, 4, 5) and
the residency rules of `ai/local-runtimes.md` section 3.

A job is a row in the project database's `jobs` table: what it is (`kind`, from the recipe job
registry's vocabulary where one fits), what it works on (`subject`), the heavy model it needs
(`model`), its `state` (waiting, running, done, failed) and, in plain words, why (`reason`). The
row is written in the same transaction as the change that implied it (`enqueue` inside an action's
transaction), so a crash cannot lose it.

One scheduler for the whole engine runs every library's jobs, in LANES by the resource a kind
needs, each lane with its own threads:

* **The local ML lane runs one job at a time.** Heavy models (the embedder, Kraken, a local
  reader, spaCy) never run two at once on this lane, and a heavy job waits while a Kraken page is
  being read outside the queue (holding `kraken_runtime._INFERENCE_LOCK`), saying so.
* **The images lane runs two at a time** (thumbnails): more concurrent texture decodes once
  destabilised the window server (#1400).
  ponytail: two lanes; network and database lanes are added when their first kind moves here.
* **Grouped by model.** The next job is one for the model already loaded, if any is waiting;
  only then the oldest job for another model. Loading a model once and using it fully is the
  point (#5370).
* **Throttled.** Each kind declares its QoS class, set on this thread (which the scheduler owns,
  so a class never leaks onto a pooled worker): background for work nobody waits on, utility for
  heavy work a person is waiting for (`core/background_compute.py`).
* **One pause.** *Pause Background Work* is stored in app settings, so a Mac paused at quit is
  paused at launch. While paused nothing is claimed; a job already running finishes.
* **Durable.** A row survives quit. A `running` row found when a library opens was interrupted:
  it goes back to `waiting`; one interrupted three times fails with its reason (a poison page does
  not loop forever).

The scheduler finds a library through the database manager on every scan and never holds a
closed one: querying a closed `Database` would silently reopen its file.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import sys
import threading
import time
import uuid
from concurrent.futures import Future
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from fichero_server.core.background_compute import set_background_qos, set_utility_qos
from fichero_server.core.timeutil import utc_now

if TYPE_CHECKING:
    from fichero_server.db import Database

logger = logging.getLogger(__name__)

#: App setting holding the global pause (`activity.pause.global-survives-relaunch`).
PAUSE_SETTING_KEY = "background_work_paused"
#: A row interrupted this many times is failed rather than retried (`activity.durable.poison-item`).
MAX_ATTEMPTS = 3
#: Kraken models are named `kraken:<reader id>` (or `kraken:blla`, the line finder alone).
KRAKEN_MODEL_PREFIX = "kraken:"
#: Modules that register kinds, imported before the first scan so a job left waiting at quit runs
#: after relaunch even before anything in this session enqueues one.
_KIND_MODULES = ("fichero_server.actions.page_text_cache", "fichero_server.importers.derivatives",
                 "fichero_server.training.job", "fichero_server.workflows.task_workers",
                 "fichero_server.remote_read.job", "fichero_server.training.reasons_job",
                 "fichero_server.training.local", "fichero_server.sync_folder", "fichero_server.checking.job")
#: Lane -> how many of its jobs run at once (`activity.throttle.lanes`). `remote`: work sent to another
#: place (a training run on Hugging Face Jobs, #5398). It waits on the network, holds no model here and
#: never holds the local ML lane.
LANES = {"local-ml": 1, "images": 2, "remote": 2, "database": 1, "network": 4}
#: Finished jobs older than this are deleted when their library opens (spec open question 8).
KEEP_FINISHED_DAYS = 30

_SCHEMA = """
    CREATE TABLE IF NOT EXISTS jobs (
        id TEXT PRIMARY KEY,
        kind TEXT NOT NULL,
        subject TEXT NOT NULL,
        model TEXT,
        state TEXT NOT NULL,
        reason TEXT,
        attempts INTEGER NOT NULL DEFAULT 0,
        started_by TEXT,
        created_at TIMESTAMP NOT NULL,
        started_at TIMESTAMP,
        finished_at TIMESTAMP
    )
"""
#: What a job sent away adds to its row (`compute.job.one-state-machine`): where it runs, and its
#: detail as JSON (the request, the far side's id, the phase and its history). Added to existing
#: libraries in place.
_ADDED_COLUMNS = (
    "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS target TEXT",
    "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS detail TEXT",
    # A job's parent (#5353, `activity.jobs-are-a-tree`): a step's run, a page's step.
    "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS parent_id TEXT",
    # Not before this time: a quiet period after a change (a synced folder's rewrite, #4952).
    "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS run_after TIMESTAMP",
    # A person waits on it (`activity.throttle.watched-first`): first in its lane, at utility QoS.
    "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS watched BOOLEAN DEFAULT FALSE",
)
_ENSURED: set[str] = set()


class JobCancelled(Exception):
    """Raised by a job's run when it was stopped: the row ends `cancelled`, not `failed`."""


class JobDeferred(Exception):
    """Raised by a long job's run when it stops to come back later (memory got tight, background
    work was paused, a person is waiting for other work): the row goes back to `waiting` with the
    reason, and the attempt is not counted against it. The job resumes from its own checkpoint."""


@dataclass(frozen=True)
class Kind:
    """What the scheduler needs to know about a kind of job."""

    #: None for an ATTACHED kind: its work is handed in by a caller that waits for it (`submit`).
    run: Callable[["Database", str], None] | None
    #: The heavy model it loads; jobs are grouped by it. None for work that loads no model.
    model: str | None
    #: Sets this thread's QoS class before the job runs.
    qos: Callable[[], None] = set_background_qos
    #: Which lane runs it (`LANES`).
    lane: str = "local-ml"
    #: What Activity calls it, when the recipe job registry has no name for it.
    name: str | None = None
    #: How to stop one of these when the generic way cannot (work running somewhere else, such
    #: as a training Job on Hugging Face): `(db, job_id) -> state after the request`.
    cancel: Callable[["Database", str], str] | None = None
    #: How to pause or resume one of these when the generic way cannot (a workflow run pauses at
    #: its own next boundary): `(db, job_id, paused) -> state after the request`.
    pause: Callable[["Database", str, bool], str] | None = None


KINDS: dict[str, Kind] = {}


def register_kind(kind: str, run: Callable[["Database", str], Any] | None, *, model: str | None,
                  qos: Callable[[], None] = set_background_qos, lane: str = "local-ml",
                  name: str | None = None, cancel: Callable[["Database", str], str] | None = None,
                  pause: Callable[["Database", str, bool], str] | None = None) -> None:
    if lane not in LANES:
        raise ValueError(f"no lane {lane!r}")
    KINDS[kind] = Kind(run=run, model=model, qos=qos, lane=lane, name=name, cancel=cancel, pause=pause)


def kind_name(kind: str) -> str:
    """The kind in words: the recipe job registry's name, the kind's own, or its id."""
    from fichero_server.recipes.jobs import get_job

    job = get_job(kind)
    if job is not None:
        return job.name
    registered = KINDS.get(kind)
    return (registered.name if registered else None) or kind


# Kraken's line finding and line reading, and a page read by a model served on this Mac, handed
# in by a workflow step that waits for each page. Named as the recipe job registry names them.
# Utility QoS: a person is waiting for these pages, and background measured ~18 times slower for
# Kraken (#4959).
for _attached in ("find-lines", "read-a-line", "read-a-page", "ask-a-model"):
    register_kind(_attached, None, model=None, qos=set_utility_qos)

#: True while this task holds a lane slot: a model call made inside work that already holds one
#: (a vision page's own `llm.vision` call) does not ask for a second, which a one-wide lane could
#: never grant.
_holding: ContextVar[bool] = ContextVar("_holding_a_lane", default=False)


# A workflow run and its steps, as rows (#5353, spec "Workflow runs inside the one job model"). The
# runner runs them; these rows are their record in the one job table (written where the run's own
# record is written: `activity_store.save/update_workflow_run`, the tracker's node events). The
# run's id IS its thread id. Pause and Stop on the run's row reach the runner's own Pause and Stop.
def _pause_run(db: "Database", job_id: str, paused: bool) -> str:
    from fichero_server.execution.cancellation import request_pause

    if not paused:
        raise ValueError("A paused run is resumed with its Resume (it restarts from its checkpoint)")
    request_pause(job_id)
    # Said on the row at once: the runner clears its flag as it settles, and the row is what keeps
    # the run's pages off the lanes in between (`_run_stopped`).
    db.execute("UPDATE jobs SET reason = ? WHERE id = ? AND state = 'running'", [PAUSING, job_id])
    return _job_row(db, job_id)[1]


def _cancel_run(db: "Database", job_id: str) -> str:
    from fichero_server.execution.cancellation import request_cancellation

    request_cancellation(job_id)
    db.execute("UPDATE jobs SET reason = ? WHERE id = ? AND state = 'running'", [STOPPING, job_id])
    return _job_row(db, job_id)[1]


PAUSING = "Pausing at its next step"
STOPPING = "Stopping at its next step"
register_kind("workflow", None, model=None, name="Workflow run", cancel=_cancel_run, pause=_pause_run)
register_kind("workflow-step", None, model=None, name="Step")
RUN_KINDS = ("workflow", "workflow-step")
#: The run record's words for its state -> the job table's.
_RUN_STATES = {"accepted": "waiting", "running": "running", "completed": "done", "failed": "failed",
               "cancelled": "cancelled", "paused": "paused"}


def _library_from_db_path(db_path: str | Path) -> "Database | None":
    from fichero_server.db.manager import DatabaseManager, db_manager

    return db_manager.open_database(DatabaseManager._cache_key(Path(db_path).parent))


def _record(db: "Database", job_id: str, *, kind: str, subject: str, parent_id: str | None, state: str,
            reason: str | None, name: str | None) -> None:
    _ensure(db)
    now = utc_now()
    finished = now if state in ("done", "failed", "cancelled") else None
    db.execute(
        "INSERT INTO jobs (id, kind, subject, state, reason, attempts, started_by, created_at, started_at, "
        "finished_at, parent_id, detail) VALUES (?, ?, ?, ?, ?, 0, 'workflow', ?, ?, ?, ?, ?) "
        "ON CONFLICT (id) DO UPDATE SET state = excluded.state, reason = excluded.reason, "
        "finished_at = excluded.finished_at",
        [job_id, kind, subject, state, reason, now, now if state == "running" else None, finished, parent_id,
         json.dumps({"name": name}) if name else None],
    )


def record_run(db_path: str | Path, thread_id: str, *, status: str, name: str | None = None,
               reason: str | None = None) -> None:
    """The run's row follows the run's own record (`activity.jobs-are-a-tree`)."""
    db = _library_from_db_path(db_path)
    if db is None or status not in _RUN_STATES:
        return
    _record(db, thread_id, kind="workflow", subject=thread_id, parent_id=None, state=_RUN_STATES[status],
            reason=reason, name=name)


def record_step(db_path: str | Path, thread_id: str, node_id: str, *, status: str, name: str | None = None,
                reason: str | None = None) -> None:
    """A step's row, a child of its run's."""
    db = _library_from_db_path(db_path)
    if db is None or not thread_id or node_id in _ROUTING_NODES:
        return
    _record(db, step_id(thread_id, node_id), kind="workflow-step", subject=step_id(thread_id, node_id),
            parent_id=thread_id, state=_RUN_STATES.get(status, status), reason=reason, name=name)


#: The builder's routing functions, which LangGraph reports like steps; not steps of the workflow.
_ROUTING_NODES = frozenset({"fan_out", "route_and_fan_out"})


def step_id(thread_id: str, node_id: str) -> str:
    return f"{thread_id}:{node_id}"


def _current_step() -> str | None:
    """The step the calling code runs in (the builder stamps it on the node context), if any."""
    from fichero_server.workflows.node_context import get_current_node

    node = get_current_node()
    return step_id(node.run_id, node.step or node.node_id) if node and node.run_id else None


def tree(db: "Database", job_id: str) -> dict[str, Any] | None:
    """A job and its descendants, each with the pages under it done and in all
    (`activity.jobs-are-a-tree`: "progress ... roll[s] up the tree")."""
    _ensure(db)
    rows = db.execute_fetchall(
        "WITH RECURSIVE t AS (SELECT * FROM jobs WHERE id = ? UNION ALL "
        "SELECT j.* FROM jobs j JOIN t ON j.parent_id = t.id) "
        "SELECT id, kind, subject, model, state, reason, parent_id, created_at, finished_at FROM t", [job_id])
    if not rows:
        return None
    names = ("id", "kind", "subject", "model", "state", "reason", "parent_id", "created_at", "finished_at")
    nodes = {row[0]: {**dict(zip(names, row)), "children": []} for row in rows}
    for node in sorted(nodes.values(), key=lambda n: n["created_at"]):
        if node["id"] != job_id and node["parent_id"] in nodes:
            nodes[node["parent_id"]]["children"].append(node)

    def roll(node: dict[str, Any]) -> tuple[int, int]:
        if not node["children"] and node["kind"] in RUN_KINDS:
            node["done"], node["total"] = 0, 0  # a step that handed nothing to a lane has no pages
        elif not node["children"]:
            node["done"], node["total"] = (1 if node["state"] == "done" else 0), 1
        else:
            counts = [roll(child) for child in node["children"]]
            node["done"], node["total"] = sum(c[0] for c in counts), sum(c[1] for c in counts)
        node["name"] = kind_name(node["kind"])
        return node["done"], node["total"]

    root = nodes[job_id]
    roll(root)
    return root


def _key(db: "Database") -> str:
    from fichero_server.db.manager import DatabaseManager

    return DatabaseManager._cache_key(Path(db.path).parent)


def _ensure(db: "Database") -> None:
    db.execute(_SCHEMA)
    key = str(db.path)
    if key not in _ENSURED:
        for statement in _ADDED_COLUMNS:
            db.execute(statement)
        _ENSURED.add(key)


def enqueue(db: "Database", kind: str, subject: str, *, started_by: str = "automatic",
            detail: str | None = None, run_after: Any = None, watched: bool = False) -> str:
    """Queue one job, inside the caller's transaction if it has one. A job of this kind already
    WAITING for this subject is reused: it reads its input when it runs, so it covers this change
    too (many corrections to a page make one job). `detail` (JSON) is written with a new row.
    `watched`: a person waits on it, so it goes first in its lane at utility QoS
    (`activity.throttle.watched-first`); a reused job becomes watched too. Returns the job id."""
    _ensure(db)
    row = db.execute_fetchone(
        "SELECT id FROM jobs WHERE kind = ? AND subject = ? AND state = 'waiting'", [kind, subject]
    )
    if row:
        job_id = row[0]
    else:
        job_id = _insert(db, kind, subject, KINDS[kind].model if kind in KINDS else None, started_by)
        if detail is not None:
            db.execute("UPDATE jobs SET detail = ? WHERE id = ?", [detail, job_id])
    if run_after is not None:  # a quiet period: each new change pushes it later (one job for a run of changes)
        db.execute("UPDATE jobs SET run_after = ? WHERE id = ?", [run_after, job_id])
    if watched:
        db.execute("UPDATE jobs SET watched = TRUE WHERE id = ?", [job_id])
    key = _key(db)
    db.add_after_commit_hook(lambda: _scheduler.wake(key))
    return job_id


def enqueue_remote(db: "Database", kind: str, subject: str, *, target: str, detail: str,
                   reason: str, started_by: str) -> str:
    """Queue one job sent to another place, with where it runs and its detail (JSON) written in the
    same statement, so the scheduler never claims it before it knows what to do."""
    _ensure(db)
    job_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO jobs (id, kind, subject, model, state, reason, attempts, started_by, created_at, target, detail) "
        "VALUES (?, ?, ?, NULL, 'waiting', ?, 0, ?, ?, ?, ?)",
        [job_id, kind, subject, reason, started_by, utc_now(), target, detail],
    )
    key = _key(db)
    db.add_after_commit_hook(lambda: _scheduler.wake(key))
    return job_id


def requeue(db: "Database", job_id: str, *, reason: str) -> None:
    """Put a finished stored job back to waiting (a reading run whose failed shards are re-sent)."""
    _ensure(db)
    db.execute("UPDATE jobs SET state = 'waiting', reason = ?, finished_at = NULL WHERE id = ?", [reason, job_id])
    key = _key(db)
    db.add_after_commit_hook(lambda: _scheduler.wake(key))


def read_job(db: "Database", job_id: str) -> dict[str, Any] | None:
    """One job's row (its `detail` as stored, JSON text), or None."""
    _ensure(db)
    row = db.execute_fetchone(
        "SELECT id, kind, subject, state, reason, detail, created_at, started_by FROM jobs WHERE id = ?", [job_id])
    if row is None:
        return None
    return dict(zip(("id", "kind", "subject", "state", "reason", "detail", "created_at", "started_by"), row))


def save_detail(db: "Database", job_id: str, detail: str, *, reason: str | None = None) -> None:
    """Store a job's `detail` (JSON text) and, when given, its reason in words."""
    db.execute("UPDATE jobs SET detail = ?, reason = COALESCE(?, reason) WHERE id = ?", [detail, reason, job_id])


def job_id_for(db: "Database", kind: str, subject: str) -> str | None:
    """The newest job of this kind on this subject."""
    row = db.execute_fetchone("SELECT id FROM jobs WHERE kind = ? AND subject = ? ORDER BY created_at DESC LIMIT 1",
                              [kind, subject])
    return row[0] if row else None


def cancel_waiting(db: "Database", job_id: str) -> None:
    """End a job that has not started: `cancelled`, "Stopped by you"."""
    db.execute("UPDATE jobs SET state = 'cancelled', reason = 'Stopped by you', finished_at = ? "
               "WHERE id = ? AND state IN ('waiting', 'paused')", [utc_now(), job_id])


def enqueue_many(db: "Database", kind: str, subjects: list[str], *,
                 started_by: str = "automatic") -> list[Future]:
    """`enqueue` for many subjects in a few statements (an import queues thousands of pages
    inside its own transaction, where a statement per page would be felt). Returns one future
    per subject, resolved with the job's result when it finishes in this process; a job finished
    after a restart resolves nothing (nobody is waiting on it any more)."""
    if not subjects:
        return []
    _ensure(db)
    ids: dict[str, str] = {}
    for chunk in _chunks(list(dict.fromkeys(subjects)), 500):
        marks = ", ".join("?" for _ in chunk)
        ids.update(db.execute_fetchall(
            f"SELECT subject, id FROM jobs WHERE kind = ? AND state = 'waiting' AND subject IN ({marks})",
            [kind, *chunk]))
    new = [subject for subject in dict.fromkeys(subjects) if subject not in ids]
    model = KINDS[kind].model if kind in KINDS else None
    now = utc_now()
    for chunk in _chunks(new, 200):
        rows = [(str(uuid.uuid4()), subject) for subject in chunk]
        ids.update((subject, job_id) for job_id, subject in rows)
        db.execute(
            "INSERT INTO jobs (id, kind, subject, model, state, attempts, started_by, created_at) VALUES "
            + ", ".join("(?, ?, ?, ?, 'waiting', 0, ?, ?)" for _ in rows),
            [value for job_id, subject in rows for value in (job_id, kind, subject, model, started_by, now)],
        )
    futures = [_scheduler.watch(ids[subject]) for subject in subjects]
    key = _key(db)
    db.add_after_commit_hook(lambda: _scheduler.wake(key))
    return futures


def _chunks(items: list, size: int) -> list[list]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def _is_attached(kind: str) -> bool:
    return kind in KINDS and KINDS[kind].run is None


def _insert(db: "Database", kind: str, subject: str, model: str | None, started_by: str) -> str:
    job_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO jobs (id, kind, subject, model, state, attempts, started_by, created_at) "
        "VALUES (?, ?, ?, ?, 'waiting', 0, ?, ?)",
        [job_id, kind, subject, model, started_by, utc_now()],
    )
    return job_id


def submit(db: "Database", kind: str, subject: str, *, model: str, fn: Callable[[], Any],
           started_by: str = "workflow", lane: str = "local-ml", run_id: str | None = None) -> Future:
    """Hand the local-model lane one piece of work a caller is WAITING for (a workflow step's
    Kraken page) and return a future for its result.

    The work is a row like any job: visible in Activity, grouped with the other work for `model`
    (a folder's pages keep one reader loaded), and never run beside another heavy model. Only the
    model work belongs here: anything after it that waits on the network (a vision model reading
    the lines Kraken found) runs in the caller, off the lane.

    A person is waiting, so the global pause does not hold it (spec open question 2); the row says
    it ran although background work is paused. Cancelling the future before the work starts
    cancels the row (an awaiting task that is cancelled does this). Not re-run after a restart:
    the row holds no recipe for the work, and the caller's run resumes or fails on its own, so
    `resume` cancels it."""
    _ensure(db)
    future: Future = Future()
    job_id = _insert(db, kind, subject, model, started_by)
    parent = _current_step()
    if parent:  # a page of a step of a run (`activity.jobs-are-a-tree`)
        db.execute("UPDATE jobs SET parent_id = ? WHERE id = ?", [parent, job_id])
    future.job_id = job_id  # type: ignore[attr-defined] -- what `withdraw` cancels
    _scheduler.attach(job_id, fn, future, lane, run_id)
    key = _key(db)
    db.add_after_commit_hook(lambda: _scheduler.wake(key))
    return future


def _open_library(library_path: str | None) -> "Database | None":
    if not library_path:
        return None
    from fichero_server.db.manager import DatabaseManager, db_manager

    return db_manager.open_database(DatabaseManager._cache_key(library_path))


#: How often a page waiting for the lane looks at its run's Stop flag.
STOP_POLL_SECONDS = 0.25


async def run_on_lane(library_path: str | None, kind: str, subject: str, *, model: str,
                      fn: Callable[[], Any], run_id: str | None = None) -> Any:
    """`submit` for an async caller with a library path. Work outside an open project has no
    table to be a row in, and runs on a worker thread as it did before the queue.

    With `run_id`, Stop on that run reaches the page while it is still WAITING for the lane:
    its row is cancelled ("Stopped by you") and `WorkflowCancelled` is raised, the runner's
    signal for a stop, not a failure. A page already running is waited for (the call has no
    way to be interrupted yet)."""
    db = _open_library(library_path)
    if db is None:
        return await asyncio.to_thread(fn)
    future = submit(db, kind, subject, model=model, fn=fn, run_id=run_id)
    return await _wait_for_lane(db, future, asyncio.wrap_future(future), run_id)


async def _wait_for_lane(db: "Database", future: Future, signal: "asyncio.Future", run_id: str | None) -> Any:
    """Wait for `signal`, withdrawing the job and raising `WorkflowCancelled` if the run is
    stopped while the job is still waiting for the lane."""
    while True:
        done, _ = await asyncio.wait({signal}, timeout=STOP_POLL_SECONDS)
        if done:
            if signal.cancelled() and run_id:  # the scheduler withdrew it: its run stopped or paused
                from fichero_server.execution.cancellation import WorkflowCancelled, WorkflowPaused

                if _stop_requested(run_id):
                    raise WorkflowCancelled(run_id)
                if _pause_requested(run_id):
                    raise WorkflowPaused(run_id)
            return signal.result()
        if run_id and _stop_requested(run_id) and _scheduler.withdraw(db, future):
            from fichero_server.execution.cancellation import WorkflowCancelled

            raise WorkflowCancelled(run_id)
        if run_id and _pause_requested(run_id) and _scheduler.withdraw(db, future, reason="Paused with its run"):
            from fichero_server.execution.cancellation import WorkflowPaused

            raise WorkflowPaused(run_id)


def _run_stopped(run_id: str | None, db: "Database | None" = None) -> str | None:
    """Why handed-in work of this run must not start now, or None: its Stop or Pause was pressed,
    or its row says it already ended or paused (the runner clears its flags once it has settled,
    and a branch can still reach the lane after that)."""
    if not run_id:
        return None
    if _stop_requested(run_id):
        return "Stopped by you"
    if _pause_requested(run_id):
        return "Paused with its run"
    if db is not None:
        row = db.execute_fetchone("SELECT state, reason FROM jobs WHERE id = ? AND kind = 'workflow'", [run_id])
        if row and (row[0] == "paused" or row[1] == PAUSING):
            return "Paused with its run"
        if row and (row[0] in ("cancelled", "failed", "done") or row[1] == STOPPING):
            return "Stopped by you" if row[1] == STOPPING or row[0] == "cancelled" else "Its run had ended"
    return None


def _pause_requested(run_id: str) -> bool:
    from fichero_server.execution.cancellation import pause_requested

    return pause_requested(run_id)


#: How soon the model lane looks again at a job held by the throttle.
THROTTLE_LOOK_AGAIN_SECONDS = 5.0

#: Longest the lane is held for one model call before it carries on regardless (a caller that
#: vanished without letting go must not wedge the lane for good).
HOLD_LIMIT_SECONDS = 900.0


async def hold_lane(library_path: str | None, kind: str, subject: str, *, model: str,
                    work: Callable[[], Any], run_id: str | None = None, lane: str = "local-ml") -> Any:
    """Run async `work` (a call to a model) as a job on a lane: `lane_slot` around it."""
    async with lane_slot(library_path, kind, subject, model=model, run_id=run_id, lane=lane):
        return await work()


@contextlib.asynccontextmanager
async def lane_slot(library_path: str | None, kind: str, subject: str, *, model: str,
                    run_id: str | None = None, lane: str = "local-ml"):
    """Hold a slot on a lane while the body runs (a call to a model: one served on this Mac on the
    local-model lane, a cloud one on the network lane). The call stays in the caller, on its event
    loop; the lane's thread holds the slot while it runs, so the lane's cap holds for the whole
    Mac, and its row is shown, grouped by model and stoppable while it waits, like a Kraken page.
    No library, or a slot already held by this task: the body just runs."""
    db = _open_library(library_path)
    if db is None or _holding.get():
        yield
        return
    loop = asyncio.get_running_loop()
    granted: asyncio.Future = loop.create_future()
    release = threading.Event()
    #: What the caller's work came to, so the row says it: None (the caller went away), "done", or
    #: the error in words.
    outcome: dict[str, str | None] = {"result": None}

    def hold() -> None:
        try:
            loop.call_soon_threadsafe(lambda: granted.done() or granted.set_result(None))
        except Exception as exc:  # noqa: BLE001 -- the caller's loop is gone: so is the caller
            raise JobCancelled("Its run had ended before this page started") from exc
        release.wait(HOLD_LIMIT_SECONDS)
        if outcome["result"] is None:
            raise JobCancelled("Its run had ended before this page was read")
        if outcome["result"] != "done":
            raise RuntimeError(outcome["result"])

    future = submit(db, kind, subject, model=model, fn=hold, lane=lane, run_id=run_id)
    token = None
    try:
        waiting = asyncio.wrap_future(future)
        try:
            await _wait_for_lane(db, future, _first_of(granted, waiting), run_id)
        except asyncio.CancelledError:
            # its caller is gone: the slot is not wanted
            _scheduler.withdraw(db, future, reason="Its run had ended before this page started")
            raise
        token = _holding.set(True)
        try:
            yield
        except Exception as exc:
            outcome["result"] = str(exc) or type(exc).__name__
            raise
        outcome["result"] = "done"
    finally:
        if token is not None:
            _holding.reset(token)
        release.set()


def _first_of(granted: "asyncio.Future", lane: "asyncio.Future") -> "asyncio.Future":
    """`granted`, or the lane's own failure if the job fails before it is granted."""
    def failed(done: "asyncio.Future") -> None:
        if granted.done():
            return
        if done.cancelled():
            granted.cancel()
        elif done.exception() is not None:
            granted.set_exception(done.exception())

    lane.add_done_callback(failed)
    return granted


def _stop_requested(run_id: str) -> bool:
    from fichero_server.execution.cancellation import cancellation_requested

    return cancellation_requested(run_id)


def run_on_lane_blocking(library_path: str | None, kind: str, subject: str, *, model: str,
                         fn: Callable[[], Any]) -> Any:
    """`run_on_lane` for a synchronous caller."""
    db = _open_library(library_path)
    if db is None:
        return fn()
    return submit(db, kind, subject, model=model, fn=fn).result()


def resume(db: "Database") -> None:
    """On library open: jobs left running were interrupted. Back to waiting, or failed after
    `MAX_ATTEMPTS`; then, if anything is waiting, wake the scheduler for this library. A library
    with nothing waiting is never scanned, so opening one adds no traffic on its connection."""
    _ensure(db)
    db.execute(
        "DELETE FROM jobs WHERE state IN ('done', 'cancelled') AND finished_at < ?",
        [utc_now() - timedelta(days=KEEP_FINISHED_DAYS)],
    )
    attached = [name for name in KINDS if _is_attached(name)]
    db.execute(
        f"UPDATE jobs SET state = 'cancelled', finished_at = ?, "
        f"reason = 'Its workflow run stopped before this page was done' "
        f"WHERE state IN ('waiting', 'running') AND kind IN ({', '.join('?' for _ in attached)})",
        [utc_now(), *attached],
    )
    db.execute(
        "UPDATE jobs SET state = 'failed', finished_at = ?, "
        "reason = 'Interrupted ' || attempts || ' times; set aside' "
        "WHERE state = 'running' AND attempts >= ?",
        [utc_now(), MAX_ATTEMPTS],
    )
    db.execute(
        "UPDATE jobs SET state = 'waiting', reason = 'Interrupted; carries on' WHERE state = 'running'"
    )
    if db.execute_fetchone("SELECT 1 FROM jobs WHERE state = 'waiting' LIMIT 1"):
        _scheduler.wake(_key(db))

def count_jobs(db: "Database", kind: str, *, subject_prefix: str,
               states: tuple[str, ...] = ("waiting", "running", "paused")) -> int:
    """How many jobs of this kind, on subjects starting so, are not finished."""
    _ensure(db)
    return int(db.execute_fetchone(
        f"SELECT count(*) FROM jobs WHERE kind = ? AND subject LIKE ? AND state IN ({', '.join('?' for _ in states)})",
        [kind, subject_prefix + "%", *states])[0])


def find_jobs(db: "Database", *, kinds: list[str], states: list[str] | None = None, job_id: str | None = None,
              limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
    """Rows of these kinds, newest first, optionally only in these states or only this id."""
    _ensure(db)
    sql = (f"SELECT id, kind, state, reason, detail, created_at, started_at, finished_at FROM jobs "
           f"WHERE kind IN ({', '.join('?' for _ in kinds)})")
    params: list[Any] = list(kinds)
    if states:
        sql += f" AND state IN ({', '.join('?' for _ in states)})"
        params += states
    if job_id is not None:
        sql += " AND id = ?"
        params.append(job_id)
    rows = db.execute_fetchall(sql + " ORDER BY created_at DESC LIMIT ? OFFSET ?", [*params, limit, offset])
    names = ("id", "kind", "state", "reason", "detail", "created_at", "started_at", "finished_at")
    return [dict(zip(names, row)) for row in rows]


def delete_job(db: "Database", job_id: str) -> None:
    """Forget one finished job's row."""
    db.execute("DELETE FROM jobs WHERE id = ?", [job_id])

def _job_row(db: "Database", job_id: str) -> tuple[str, str]:
    _ensure(db)
    row = db.execute_fetchone("SELECT kind, state FROM jobs WHERE id = ?", [job_id])
    if row is None:
        raise KeyError(f"no job {job_id!r} in this project")
    return row[0], row[1]


def pause_job(db: "Database", job_id: str, paused: bool) -> str:
    """Pause one waiting job, or resume one paused job (`activity.pause.per-job`). A paused job
    stays paused across relaunch until resumed. A job already running finishes its item; a page a
    workflow run is waiting for is paused with its run, not here. Returns the job's state."""
    kind, state = _job_row(db, job_id)
    registered = KINDS.get(kind)
    if registered is not None and registered.pause is not None:
        return registered.pause(db, job_id, paused)
    if _is_attached(kind):
        raise ValueError("This page belongs to a workflow run that is waiting for it: pause the run instead")
    if paused and state == "waiting":
        db.execute("UPDATE jobs SET state = 'paused', reason = 'Paused by you' WHERE id = ? AND state = 'waiting'",
                   [job_id])
        return "paused"
    if not paused and state == "paused":
        db.execute("UPDATE jobs SET state = 'waiting', reason = NULL WHERE id = ? AND state = 'paused'", [job_id])
        key = _key(db)
        db.add_after_commit_hook(lambda: _scheduler.wake(key))
        return "waiting"
    return state


def cancel_job(db: "Database", job_id: str) -> str:
    """Stop one job (`activity.pause.per-job`): a waiting or paused one ends `cancelled` now; a page
    a run is waiting for is withdrawn from the lane (the run sees it stopped); a kind that runs
    somewhere else stops there by its own `cancel`. A job running here finishes the item it is on
    (nothing can interrupt it midway yet). Returns the job's state after the request."""
    kind, state = _job_row(db, job_id)
    registered = KINDS.get(kind)
    if registered is not None and registered.cancel is not None:
        return registered.cancel(db, job_id)
    if state not in ("waiting", "paused"):
        return state
    with _scheduler._lock:
        handed_in = _scheduler._attached.get(job_id)
    if handed_in is not None:
        return "cancelled" if _scheduler.withdraw(db, handed_in[1]) else "running"
    cancel_waiting(db, job_id)
    return "cancelled"


def is_paused() -> bool:
    from fichero_server.db.app import get_app_db

    try:
        return get_app_db().get_setting(PAUSE_SETTING_KEY) == "1"
    except Exception as exc:  # noqa: BLE001 -- an unreadable setting must not stop the queue for good
        logger.warning("Could not read %s: %s", PAUSE_SETTING_KEY, exc)
        return False


def set_paused(paused: bool) -> None:
    from fichero_server.db.app import get_app_db

    get_app_db().set_setting(PAUSE_SETTING_KEY, "1" if paused else "0")
    _scheduler.wake(None)


def finished_seconds(db: "Database", model: str, *, limit: int = 200) -> list[float]:
    """How long each of `model`'s most recent finished jobs took, newest first: the measured
    speed `recipes/routes.py` reports (`source.onboard.routes-for-the-volume`)."""
    _ensure(db)
    rows = db.execute_fetchall(
        "SELECT epoch(finished_at) - epoch(started_at) FROM jobs WHERE model = ? AND state = 'done' "
        "AND started_at IS NOT NULL AND finished_at IS NOT NULL ORDER BY finished_at DESC LIMIT ?",
        [model, limit],
    )
    return [float(r[0]) for r in rows if r[0] is not None and r[0] >= 0]


def snapshot(db: "Database", *, failed_limit: int = 20) -> list[dict[str, Any]]:
    """The jobs worth showing: every running one, the waiting ones (one row per kind when more
    than one waits, with `count`: an import queues thousands), and the most recent failures, each
    with the reason in words. Read by `/api/activity/jobs`."""
    _ensure(db)
    paused = is_paused()
    rows = db.execute_fetchall(
        "SELECT id, kind, subject, state, reason, attempts, created_at, parent_id FROM ("
        " SELECT * FROM jobs WHERE state IN ('waiting', 'running', 'paused') AND kind NOT IN ('workflow', 'workflow-step')"
        " UNION ALL"
        " (SELECT * FROM jobs WHERE state = 'failed' AND kind NOT IN ('workflow', 'workflow-step')"
        " ORDER BY finished_at DESC LIMIT ?)"
        ") ORDER BY CASE state WHEN 'running' THEN 0 WHEN 'waiting' THEN 1 WHEN 'paused' THEN 2 ELSE 3 END, "
        "created_at",
        [failed_limit],
    )
    out: list[dict[str, Any]] = []
    waiting: dict[str, dict[str, Any]] = {}
    # Runs and their steps are listed from the run record (`/api/activity/jobs` merges them); their rows
    # are read as a tree with `tree()`. Pages carry their step as `parent_id`.
    for job_id, kind, subject, state, reason, attempts, created_at, parent_id in rows:
        if state == "waiting" and paused and not _is_attached(kind):
            reason = "Paused by you"
        row = {"id": job_id, "kind": kind, "subject": subject, "state": state, "reason": reason,
               "attempts": attempts, "created_at": created_at, "count": 1, "parent_id": parent_id}
        if state != "waiting":
            out.append(row)
        elif kind in waiting:  # the first (oldest) row of a kind stands for all of them
            waiting[kind]["count"] += 1
            waiting[kind]["id"] = f"waiting:{kind}"
        else:
            waiting[kind] = row
            out.append(row)
    return out


_current = threading.local()


def current_job_id() -> str | None:
    """The id of the job this thread is running, for a kind that reports progress on its row."""
    return getattr(_current, "job_id", None)


def _kraken_busy() -> bool:
    # Only if the module is loaded: when it is not, no Kraken page can be running, and importing
    # it here would cost the engine its startup time.
    runtime = sys.modules.get("fichero_server.llm.kraken_runtime")
    return runtime is not None and runtime._INFERENCE_LOCK.locked()


def _release_kraken() -> None:
    """Free Kraken's resident models. Under Kraken's own lock, which guards them."""
    runtime = sys.modules.get("fichero_server.llm.kraken_runtime")
    if runtime is not None:
        with runtime._INFERENCE_LOCK:
            runtime.release_resident_models()


def _release_embedder() -> None:
    """Free the embedding model, unless an embed or a search holds it right now."""
    embeddings = sys.modules.get("fichero_server.db.embeddings")
    if embeddings is not None:
        embeddings.release_idle_embedders(idle_seconds=0)


#: Providers whose models run in a server on this Mac (named `<provider>:<model>` on the lane).
LOCAL_MODEL_SERVERS = frozenset({"omlx", "ollama", "lmstudio"})


def _family(model: str | None) -> str | None:
    if (model or "").startswith(KRAKEN_MODEL_PREFIX):
        return "kraken"
    if (model or "").split(":", 1)[0] in LOCAL_MODEL_SERVERS:
        return "local-model"
    return model


def _keep_local_model_server() -> None:
    # ponytail: not stopped on a switch. Its server takes 30-300 s to start again and frees its
    # own memory when idle; stop it here once measured resident sizes say this Mac needs it.
    return None


#: The heavy models the lane frees when it switches from one to another (`activity.lane.group-by-
#: model`: a switch unloads the old model first). A light one (spaCy) stays loaded beside them.
_RELEASE = {"kraken": _release_kraken, "embedder": _release_embedder,
            # Converting a trained model for MLX (#5398) holds a 7B model's weights itself; it frees
            # nothing when it ends (its process exits), but switching TO it frees Kraken or the embedder.
            "mlx-convert": lambda: None,
            "local-model": _keep_local_model_server}
#: A background job for another heavy model waits until the loaded one has had no work for this
#: long, so work that arrives in bursts (a run's Kraken pages, each followed by its page's embed)
#: does not swap two models in and out page by page. Work a person waits for switches at once.
SWITCH_AFTER_QUIET_SECONDS = 20.0


def _heavy_switch(loaded: str | None, model: str | None) -> bool:
    return (_family(loaded) in _RELEASE and _family(model) in _RELEASE
            and _family(loaded) != _family(model))


class _Lane:
    """One lane's threads and what they share: the libraries that may have work for it, and the
    model its last job loaded."""

    def __init__(self, name: str, slots: int) -> None:
        self.name = name
        self.slots = slots
        self.event = threading.Event()
        self.threads: list[threading.Thread] = []
        #: Libraries that may have waiting jobs for this lane; one found with none is forgotten
        #: until woken.
        self.libraries: set[str] = set()
        #: Woken since the current scan began: not forgotten by it (its enqueue may not have
        #: committed when the scan looked).
        self.rewoken: set[str] = set()
        #: Held while a thread picks and claims a job, so two threads never take the same row.
        self.pick = threading.Lock()
        #: The model the last job loaded: the next job prefers it (`activity.lane.group-by-model`).
        self.loaded_model: str | None = None
        #: When the last job for that model finished (monotonic), and when to look again for a
        #: switch that is waiting for the quiet spell.
        self.loaded_used_at = 0.0
        self.look_again_at: float | None = None


class _Scheduler:
    #: How long a thread sleeps with nothing to do before looking again (a missed wake costs at
    #: most this).
    IDLE_SECONDS = 30.0
    KRAKEN_POLL_SECONDS = 0.2

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.lanes = {name: _Lane(name, slots) for name, slots in LANES.items()}
        self._kinds_loaded = False
        #: Work handed in by waiting callers, by job id: (the work, the caller's future).
        self._attached: dict[str, tuple[Callable[[], Any], Future]] = {}
        #: Futures waiting on stored jobs, by job id (`enqueue_many`).
        self._watchers: dict[str, list[Future]] = {}

    @property
    def loaded_model(self) -> str | None:
        return self.lanes["local-ml"].loaded_model

    def attach(self, job_id: str, fn: Callable[[], Any], future: Future, lane: str = "local-ml",
               run_id: str | None = None) -> None:
        with self._lock:
            self._attached[job_id] = (fn, future, lane, run_id)

    def watch(self, job_id: str) -> Future:
        future: Future = Future()
        with self._lock:
            self._watchers.setdefault(job_id, []).append(future)
        return future

    def withdraw(self, db: "Database", future: Future, reason: str = "Stopped by you") -> bool:
        """Cancel handed-in work that has not started. False when it already runs."""
        if not future.cancel():
            return False
        job_id = future.job_id  # type: ignore[attr-defined]
        with self._lock:
            self._attached.pop(job_id, None)
        db.execute("UPDATE jobs SET state = 'cancelled', reason = ?, finished_at = ? "
                   "WHERE id = ? AND state = 'waiting'", [reason, utc_now(), job_id])
        return True

    def someone_is_waiting(self, lane: str = "local-ml") -> bool:
        """Whether work a person is waiting for has been handed to this lane (a long job steps aside)."""
        with self._lock:
            return any(entry[2] == lane for entry in self._attached.values())

    def _fail_attached(self, exc: BaseException) -> None:
        with self._lock:
            waiting, self._attached = self._attached, {}
        for _fn, future, _lane, _run in waiting.values():
            if not future.done():
                future.set_exception(exc)

    def wake(self, key: str | None) -> None:
        with self._lock:
            for lane in self.lanes.values():
                if key is not None:
                    lane.libraries.add(key)
                    lane.rewoken.add(key)
                lane.threads = [t for t in lane.threads if t.is_alive()]
                while len(lane.threads) < lane.slots:
                    # The local-ML lane's one thread keeps the name tests and logs know it by.
                    name = "fichero-jobs" if lane.name == "local-ml" else f"fichero-jobs-{lane.name}"
                    thread = threading.Thread(target=self._loop, args=(lane,), name=name, daemon=True)
                    lane.threads.append(thread)
                    thread.start()
        for lane in self.lanes.values():
            lane.event.set()

    def _loop(self, lane: _Lane) -> None:
        with self._lock:
            if not self._kinds_loaded:
                import importlib

                for module in _KIND_MODULES:
                    # A module registers its kinds on import, or lazily through this hook.
                    getattr(importlib.import_module(module), "register_job_kinds", lambda: None)()
                self._kinds_loaded = True
        while True:
            timeout = self.IDLE_SECONDS
            if lane.look_again_at is not None:
                timeout = min(timeout, max(0.0, lane.look_again_at - time.monotonic()))
            lane.event.wait(timeout)
            lane.event.clear()
            # An error in a scan ends this thread (logged by threading's excepthook); the next
            # wake (an enqueue, a library open, a pause change) starts a new one. A caller waiting
            # on handed-in work hears the error rather than waiting forever.
            try:
                while (picked := self._claim(lane)) is not None:
                    self._run(lane, *picked)
            except Exception as exc:
                if lane.name == "local-ml":
                    self._fail_attached(exc)
                raise

    def _claim(self, lane: _Lane) -> tuple[str, Any, tuple, Any] | None:
        """Pick the next job for this lane and mark it running, as one step among its threads."""
        with lane.pick:
            # Heavy local work waits while the Mac needs itself (`activity.throttle.power-heat-
            # memory`). Background jobs wait on all four signals, so while any holds, only work a
            # person is waiting for is looked at; each held row says why, and the lane looks again.
            held = None
            if lane.name == "local-ml":
                from fichero_server.execution.throttle import why_wait

                held = why_wait(person_waiting=False)
                if held:
                    self._say_why_background_waits(lane, held)
                    lane_look_again = time.monotonic() + THROTTLE_LOOK_AGAIN_SECONDS
            while (picked := self._next(lane, background=held is None)) is not None:
                key, db, row = picked
                if lane.name == "local-ml":
                    reason = why_wait(person_waiting=True)  # memory and heat hold even these
                    if reason:
                        db.execute("UPDATE jobs SET reason = ? WHERE id = ? AND state = 'waiting'", [reason, row[0]])
                        lane.look_again_at = time.monotonic() + THROTTLE_LOOK_AGAIN_SECONDS
                        return None
                with self._lock:
                    handed_in = self._attached.pop(row[0], None)
                if handed_in is None and _is_attached(row[1]):
                    continue  # withdrawn between the scan and now (Stop, Pause, a caller gone)
                stopped = _run_stopped(handed_in[3], db) if handed_in is not None else None
                if stopped:  # its run was stopped or paused while it waited: nobody wants it now
                    handed_in[1].cancel()
                    db.execute("UPDATE jobs SET state = 'cancelled', reason = ?, finished_at = ? WHERE id = ?",
                               [stopped, utc_now(), row[0]])
                    continue
                if handed_in is not None and not handed_in[1].set_running_or_notify_cancel():
                    db.execute("UPDATE jobs SET state = 'cancelled', reason = 'Stopped before it started', "
                               "finished_at = ? WHERE id = ?", [utc_now(), row[0]])
                    continue
                db.execute(
                    "UPDATE jobs SET state = 'running', started_at = ?, attempts = attempts + 1, "
                    "reason = ? WHERE id = ? AND state = 'waiting'",
                    [utc_now(), "Running although background work is paused"
                     if handed_in is not None and is_paused() else None, row[0]],
                )
                return key, db, row, handed_in
            if held:
                lane.look_again_at = lane_look_again
            return None

    def _say_why_background_waits(self, lane: _Lane, reason: str) -> None:
        from fichero_server.db.manager import db_manager

        stored = [name for name, kind in KINDS.items() if kind.run is not None and kind.lane == lane.name]
        with self._lock:
            keys = list(lane.libraries)
        for key in keys:
            db = db_manager.open_database(key)
            if db is not None and stored:
                db.execute(f"UPDATE jobs SET reason = ? WHERE state = 'waiting' AND kind IN "
                           f"({', '.join('?' for _ in stored)}) AND reason IS DISTINCT FROM ?",
                           [reason, *stored, reason])

    def _next(self, lane: _Lane, *, background: bool = True) -> tuple[str, Any, tuple] | None:
        from fichero_server.db.manager import db_manager

        # Stored kinds run unless paused or held by the throttle; handed-in work runs whenever its
        # caller is waiting. Only a scan that looked at every kind may forget an idle library.
        full_scan = background and not is_paused()
        stored = [] if not full_scan else [
            name for name, kind in KINDS.items() if kind.run is not None and kind.lane == lane.name]
        with self._lock:
            keys = list(lane.libraries)
            lane.rewoken.clear()
            attached = [job_id for job_id, entry in self._attached.items() if entry[2] == lane.name]
        if not stored and not attached:
            return None
        where = " OR ".join(filter(None, [
            f"kind IN ({', '.join('?' for _ in stored)})" if stored else "",
            f"id IN ({', '.join('?' for _ in attached)})" if attached else "",
        ]))
        where, params = f"({where})", [*stored, *attached]
        # The quiet spell: while the loaded heavy model has had work recently, background jobs for
        # ANOTHER heavy model are left where they are -- excluded, so the work behind them (a
        # light model's, or a page someone waits for) still runs.
        lane.look_again_at = None
        quiet_from = lane.loaded_used_at + SWITCH_AFTER_QUIET_SECONDS
        others = [f for f in _RELEASE if f != _family(lane.loaded_model)]
        if _family(lane.loaded_model) in _RELEASE and time.monotonic() < quiet_from and others:
            held_parts, held_params = [], []
            for f in others:
                prefixes = ([KRAKEN_MODEL_PREFIX] if f == "kraken" else
                            [f"{p}:" for p in sorted(LOCAL_MODEL_SERVERS)] if f == "local-model" else [])
                if prefixes:
                    held_parts += ["COALESCE(model, '') LIKE ?"] * len(prefixes)
                    held_params += [p + "%" for p in prefixes]
                else:
                    held_parts.append("COALESCE(model, '') = ?")
                    held_params.append(f)
            held = " OR ".join(held_parts)
            if attached:
                where += f" AND (id IN ({', '.join('?' for _ in attached)}) OR NOT ({held}))"
                params += [*attached, *held_params]
            else:
                where += f" AND NOT ({held})"
                params += held_params
            lane.look_again_at = quiet_from  # look again when the spell ends
        # Work a person is waiting for goes first (`activity.throttle.watched-first`): a long
        # background job that stepped aside for it must not take the lane straight back.
        attached_first = f"(id IN ({', '.join('?' for _ in attached)})) DESC, " if attached else ""
        candidates = []
        idle = []
        for key in keys:
            db = db_manager.open_database(key)
            if db is None:  # closed: opening it again resumes its jobs
                idle.append(key)
                continue
            now = utc_now()
            row = db.execute_fetchone(
                f"SELECT id, kind, subject, model, created_at FROM jobs "
                f"WHERE state = 'waiting' AND (run_after IS NULL OR run_after <= ?) AND {where} "
                f"ORDER BY {attached_first}COALESCE(watched, FALSE) DESC, (model IS NOT DISTINCT FROM ?) DESC, "
                f"created_at, rowid LIMIT 1",
                [now, *params, *attached, lane.loaded_model],
            )
            later = db.execute_fetchone(
                f"SELECT min(run_after) FROM jobs WHERE state = 'waiting' AND run_after > ? AND {where}",
                [now, *params])[0]
            if later is not None:  # a job waiting out its quiet period: look again when it ends
                from fichero_server.core.timeutil import ensure_utc

                due = time.monotonic() + max(0.0, (ensure_utc(later) - ensure_utc(now)).total_seconds())
                lane.look_again_at = min(lane.look_again_at or due, due)
            if row:
                candidates.append((key, db, row))
            elif later is None:
                idle.append(key)
        if full_scan:
            with self._lock:
                lane.libraries.difference_update(set(idle) - lane.rewoken)
        if not candidates:
            return None
        # Across libraries the same rule: waited-for work first, then the loaded model, then the oldest.
        candidates.sort(key=lambda c: (c[2][0] not in attached, c[2][3] != lane.loaded_model, c[2][4]))
        return candidates[0]

    def _run(self, lane: _Lane, key: str, db: "Database", row: tuple, handed_in: Any) -> None:
        from fichero_server.db.manager import db_manager

        job_id, kind_name, subject, model, _ = row
        kind = KINDS[kind_name]
        if lane.name == "local-ml":
            if _kraken_busy():  # a Kraken page outside the queue: no second heavy model beside it
                db.execute("UPDATE jobs SET reason = 'Waiting for Kraken (another page is using it)' "
                           "WHERE id = ?", [job_id])
                while _kraken_busy():
                    time.sleep(self.KRAKEN_POLL_SECONDS)
            if _heavy_switch(lane.loaded_model, model):
                _RELEASE[_family(lane.loaded_model)]()
            if model is not None:
                lane.loaded_model = model
        if os.environ.get("FICHERO_JOB_QOS", "1") != "0":  # the test suite runs jobs at normal priority
            watched = handed_in is None and db.execute_fetchone(
                "SELECT COALESCE(watched, FALSE) FROM jobs WHERE id = ?", [job_id])[0]
            # A job a person waits on runs at utility QoS whatever its kind's class (`watched-first`).
            set_utility_qos() if watched else kind.qos()
        state, reason, result, error = "done", None, None, None
        _current.job_id = job_id
        try:
            result = handed_in[0]() if handed_in is not None else kind.run(db, subject)
        except JobCancelled as exc:
            state, reason, error = "cancelled", str(exc) or "Stopped by you", exc
        except JobDeferred as exc:
            state, reason, error = "waiting", str(exc), exc
        except Exception as exc:  # noqa: BLE001 -- recorded on the row, and handed to whoever waits
            logger.warning("job %s (%s on %s) failed: %s", job_id, kind_name, subject, exc)
            state, reason, error = "failed", str(exc) or type(exc).__name__, exc
        finally:
            _current.job_id = None
        if model is not None and model == lane.loaded_model:
            lane.loaded_used_at = time.monotonic()
        if state == "waiting":  # deferred: not finished; it comes back, and its watchers wait on
            if db_manager.open_database(key) is db:
                db.execute("UPDATE jobs SET state = 'waiting', reason = ?, attempts = attempts - 1 WHERE id = ?",
                           [reason, job_id])
            lane.look_again_at = time.monotonic() + THROTTLE_LOOK_AGAIN_SECONDS
            return
        # The row first, then whoever waits: a caller told the outcome must find it on the row.
        if db_manager.open_database(key) is db:
            db.execute("UPDATE jobs SET state = ?, reason = ?, finished_at = ? WHERE id = ?",
                       [state, reason, utc_now(), job_id])
        # (closed while it ran: the row stays `running` and resumes when the library opens)
        with self._lock:
            waiting = self._watchers.pop(job_id, [])
        if handed_in is not None:
            waiting.append(handed_in[1])
        for future in waiting:
            if future.done():
                continue
            if error is not None:
                future.set_exception(error)
            else:
                future.set_result(result)


_scheduler = _Scheduler()
