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
import logging
import sys
import threading
import time
import uuid
from concurrent.futures import Future
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
_KIND_MODULES = ("fichero_server.actions.page_text_cache", "fichero_server.importers.derivatives")
#: Lane -> how many of its jobs run at once (`activity.throttle.lanes`).
LANES = {"local-ml": 1, "images": 2}
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


KINDS: dict[str, Kind] = {}


def register_kind(kind: str, run: Callable[["Database", str], Any] | None, *, model: str | None,
                  qos: Callable[[], None] = set_background_qos, lane: str = "local-ml",
                  name: str | None = None) -> None:
    if lane not in LANES:
        raise ValueError(f"no lane {lane!r}")
    KINDS[kind] = Kind(run=run, model=model, qos=qos, lane=lane, name=name)


def kind_name(kind: str) -> str:
    """The kind in words: the recipe job registry's name, the kind's own, or its id."""
    from fichero_server.recipes.jobs import get_job

    job = get_job(kind)
    if job is not None:
        return job.name
    registered = KINDS.get(kind)
    return (registered.name if registered else None) or kind


# Kraken's line finding and line reading, handed in by a workflow step that waits for each page.
# Named as the recipe job registry names them. Utility QoS: a person is waiting for these pages,
# and background measured ~18 times slower for Kraken (#4959).
for _attached in ("find-lines", "read-a-line"):
    register_kind(_attached, None, model=None, qos=set_utility_qos)


def _key(db: "Database") -> str:
    from fichero_server.db.manager import DatabaseManager

    return DatabaseManager._cache_key(Path(db.path).parent)


def _ensure(db: "Database") -> None:
    db.execute(_SCHEMA)


def enqueue(db: "Database", kind: str, subject: str, *, started_by: str = "automatic") -> str:
    """Queue one job, inside the caller's transaction if it has one. A job of this kind already
    WAITING for this subject is reused: it reads its input when it runs, so it covers this change
    too (many corrections to a page make one job). Returns the job id."""
    _ensure(db)
    row = db.execute_fetchone(
        "SELECT id FROM jobs WHERE kind = ? AND subject = ? AND state = 'waiting'", [kind, subject]
    )
    if row:
        job_id = row[0]
    else:
        job_id = _insert(db, kind, subject, KINDS[kind].model if kind in KINDS else None, started_by)
    key = _key(db)
    db.add_after_commit_hook(lambda: _scheduler.wake(key))
    return job_id


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
           started_by: str = "workflow") -> Future:
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
    _scheduler.attach(job_id, fn, future)
    key = _key(db)
    db.add_after_commit_hook(lambda: _scheduler.wake(key))
    return future


def _open_library(library_path: str | None) -> "Database | None":
    if not library_path:
        return None
    from fichero_server.db.manager import DatabaseManager, db_manager

    return db_manager.open_database(DatabaseManager._cache_key(library_path))


async def run_on_lane(library_path: str | None, kind: str, subject: str, *, model: str,
                      fn: Callable[[], Any]) -> Any:
    """`submit` for an async caller with a library path. Work outside an open project has no
    table to be a row in, and runs on a worker thread as it did before the queue."""
    db = _open_library(library_path)
    if db is None:
        return await asyncio.to_thread(fn)
    return await asyncio.wrap_future(submit(db, kind, subject, model=model, fn=fn))


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


def snapshot(db: "Database", *, failed_limit: int = 20) -> list[dict[str, Any]]:
    """The jobs worth showing: every running one, the waiting ones (one row per kind when more
    than one waits, with `count`: an import queues thousands), and the most recent failures, each
    with the reason in words. Read by `/api/activity/jobs`."""
    _ensure(db)
    paused = is_paused()
    rows = db.execute_fetchall(
        "SELECT id, kind, subject, state, reason, attempts, created_at FROM ("
        " SELECT * FROM jobs WHERE state IN ('waiting', 'running')"
        " UNION ALL"
        " (SELECT * FROM jobs WHERE state = 'failed' ORDER BY finished_at DESC LIMIT ?)"
        ") ORDER BY CASE state WHEN 'running' THEN 0 WHEN 'waiting' THEN 1 ELSE 2 END, created_at",
        [failed_limit],
    )
    out: list[dict[str, Any]] = []
    waiting: dict[str, dict[str, Any]] = {}
    for job_id, kind, subject, state, reason, attempts, created_at in rows:
        if state == "waiting" and paused and not _is_attached(kind):
            reason = "Paused by you"
        row = {"id": job_id, "kind": kind, "subject": subject, "state": state, "reason": reason,
               "attempts": attempts, "created_at": created_at, "count": 1}
        if state != "waiting":
            out.append(row)
        elif kind in waiting:  # the first (oldest) row of a kind stands for all of them
            waiting[kind]["count"] += 1
            waiting[kind]["id"] = f"waiting:{kind}"
        else:
            waiting[kind] = row
            out.append(row)
    return out


def _kraken_busy() -> bool:
    # Only if the module is loaded: when it is not, no Kraken page can be running, and importing
    # it here would cost the engine its startup time.
    runtime = sys.modules.get("fichero_server.llm.kraken_runtime")
    return runtime is not None and runtime._INFERENCE_LOCK.locked()


def _release_kraken() -> None:
    """Free Kraken's resident models before another heavy model loads (`activity.lane.group-by-
    model`: a switch unloads the old model first). Under Kraken's own lock, which guards them."""
    runtime = sys.modules.get("fichero_server.llm.kraken_runtime")
    if runtime is not None:
        with runtime._INFERENCE_LOCK:
            runtime.release_resident_models()


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

    def attach(self, job_id: str, fn: Callable[[], Any], future: Future) -> None:
        with self._lock:
            self._attached[job_id] = (fn, future)

    def watch(self, job_id: str) -> Future:
        future: Future = Future()
        with self._lock:
            self._watchers.setdefault(job_id, []).append(future)
        return future

    def _fail_attached(self, exc: BaseException) -> None:
        with self._lock:
            waiting, self._attached = self._attached, {}
        for _fn, future in waiting.values():
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
            lane.event.wait(self.IDLE_SECONDS)
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
            while (picked := self._next(lane)) is not None:
                key, db, row = picked
                with self._lock:
                    handed_in = self._attached.pop(row[0], None)
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
            return None

    def _next(self, lane: _Lane) -> tuple[str, Any, tuple] | None:
        from fichero_server.db.manager import db_manager

        # Stored kinds run unless paused; handed-in work runs whenever its caller is waiting.
        stored = [] if is_paused() else [
            name for name, kind in KINDS.items() if kind.run is not None and kind.lane == lane.name]
        with self._lock:
            keys = list(lane.libraries)
            lane.rewoken.clear()
            attached = [job_id for job_id in self._attached] if lane.name == "local-ml" else []
        if not stored and not attached:
            return None
        where = " OR ".join(filter(None, [
            f"kind IN ({', '.join('?' for _ in stored)})" if stored else "",
            f"id IN ({', '.join('?' for _ in attached)})" if attached else "",
        ]))
        candidates = []
        idle = []
        for key in keys:
            db = db_manager.open_database(key)
            if db is None:  # closed: opening it again resumes its jobs
                idle.append(key)
                continue
            row = db.execute_fetchone(
                f"SELECT id, kind, subject, model, created_at FROM jobs "
                f"WHERE state = 'waiting' AND ({where}) "
                f"ORDER BY (model IS NOT DISTINCT FROM ?) DESC, created_at, rowid LIMIT 1",
                [*stored, *attached, lane.loaded_model],
            )
            if row:
                candidates.append((key, db, row))
            else:
                idle.append(key)
        with self._lock:
            lane.libraries.difference_update(set(idle) - lane.rewoken)
        if not candidates:
            return None
        # Across libraries the same rule: the loaded model first, then the oldest.
        candidates.sort(key=lambda c: (c[2][3] != lane.loaded_model, c[2][4]))
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
            if (model is not None and (lane.loaded_model or "").startswith(KRAKEN_MODEL_PREFIX)
                    and not model.startswith(KRAKEN_MODEL_PREFIX)):
                _release_kraken()
            if model is not None:
                lane.loaded_model = model
        kind.qos()
        state, reason, result, error = "done", None, None, None
        try:
            result = handed_in[0]() if handed_in is not None else kind.run(db, subject)
        except Exception as exc:  # noqa: BLE001 -- recorded on the row, and handed to whoever waits
            logger.warning("job %s (%s on %s) failed: %s", job_id, kind_name, subject, exc)
            state, reason, error = "failed", str(exc) or type(exc).__name__, exc
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
        if db_manager.open_database(key) is not db:
            return  # closed while it ran: the row stays `running` and resumes when the library opens
        db.execute("UPDATE jobs SET state = ?, reason = ?, finished_at = ? WHERE id = ?",
                   [state, reason, utc_now(), job_id])


_scheduler = _Scheduler()
