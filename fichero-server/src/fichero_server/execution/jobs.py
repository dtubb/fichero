"""One job model, first slice: background work as durable rows, run by one scheduler (#5353).

Spec: `docs/contributor_manual/specs/ui/activity-and-automatic-work.md` (sections 1, 3, 4, 5) and
the residency rules of `ai/local-runtimes.md` section 3.

A job is a row in the project database's `jobs` table: what it is (`kind`, from the recipe job
registry's vocabulary where one fits), what it works on (`subject`), the heavy model it needs
(`model`), its `state` (waiting, running, done, failed) and, in plain words, why (`reason`). The
row is written in the same transaction as the change that implied it (`enqueue` inside an action's
transaction), so a crash cannot lose it.

One scheduler thread, for the whole engine, runs every library's jobs:

* **The local ML lane runs one job at a time.** Heavy models (the embedder, Kraken, a local
  reader) never run two at once on this lane, and a heavy job waits while a Kraken page is being
  read outside the queue (a workflow run holding `kraken_runtime._INFERENCE_LOCK`), saying so.
  ponytail: one lane with one slot; light lanes with their own concurrency (images, network,
  database) are added when the first light kind moves onto the queue.
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

import logging
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from fichero_server.core.background_compute import set_background_qos
from fichero_server.core.timeutil import utc_now

if TYPE_CHECKING:
    from fichero_server.db import Database

logger = logging.getLogger(__name__)

#: App setting holding the global pause (`activity.pause.global-survives-relaunch`).
PAUSE_SETTING_KEY = "background_work_paused"
#: A row interrupted this many times is failed rather than retried (`activity.durable.poison-item`).
MAX_ATTEMPTS = 3
#: The model whose lock outside the queue a heavy job waits on.
KRAKEN_MODEL = "kraken"
#: Modules that register kinds, imported before the first scan so a job left waiting at quit runs
#: after relaunch even before anything in this session enqueues one.
_KIND_MODULES = ("fichero_server.actions.page_text_cache",)

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

    run: Callable[["Database", str], None]
    #: The heavy model it loads; jobs are grouped by it. None for work that loads no model.
    model: str | None
    #: Sets this thread's QoS class before the job runs.
    qos: Callable[[], None] = set_background_qos


KINDS: dict[str, Kind] = {}


def register_kind(kind: str, run: Callable[["Database", str], None], *, model: str | None,
                  qos: Callable[[], None] = set_background_qos) -> None:
    KINDS[kind] = Kind(run=run, model=model, qos=qos)


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
        job_id = str(uuid.uuid4())
        model = KINDS[kind].model if kind in KINDS else None
        db.execute(
            "INSERT INTO jobs (id, kind, subject, model, state, attempts, started_by, created_at) "
            "VALUES (?, ?, ?, ?, 'waiting', 0, ?, ?)",
            [job_id, kind, subject, model, started_by, utc_now()],
        )
    key = _key(db)
    db.add_after_commit_hook(lambda: _scheduler.wake(key))
    return job_id


def resume(db: "Database") -> None:
    """On library open: jobs left running were interrupted. Back to waiting, or failed after
    `MAX_ATTEMPTS`; then, if anything is waiting, wake the scheduler for this library. A library
    with nothing waiting is never scanned, so opening one adds no traffic on its connection."""
    _ensure(db)
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
    """The jobs worth showing: every waiting and running one, and the most recent failures, each
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
    out = []
    for job_id, kind, subject, state, reason, attempts, created_at in rows:
        if state == "waiting" and paused:
            reason = "Paused by you"
        out.append({"id": job_id, "kind": kind, "subject": subject, "state": state,
                    "reason": reason, "attempts": attempts, "created_at": created_at})
    return out


def _kraken_busy() -> bool:
    # Only if the module is loaded: when it is not, no Kraken page can be running, and importing
    # it here would cost the engine its startup time.
    runtime = sys.modules.get("fichero_server.llm.kraken_runtime")
    return runtime is not None and runtime._INFERENCE_LOCK.locked()


class _Scheduler:
    #: How long the thread sleeps with nothing to do before looking again (a missed wake costs
    #: at most this).
    IDLE_SECONDS = 30.0
    KRAKEN_POLL_SECONDS = 0.2

    def __init__(self) -> None:
        #: Libraries that may have waiting jobs; one found with none is forgotten until woken.
        self._libraries: set[str] = set()
        #: Woken since the current scan began: not forgotten by it (its enqueue may not have
        #: committed when the scan looked).
        self._rewoken: set[str] = set()
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self._kinds_loaded = False
        #: The model the last job loaded: the next job prefers it (`activity.lane.group-by-model`).
        self.loaded_model: str | None = None

    def wake(self, key: str | None) -> None:
        with self._lock:
            if key is not None:
                self._libraries.add(key)
                self._rewoken.add(key)
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._loop, name="fichero-jobs", daemon=True)
                self._thread.start()
        self._wake.set()

    def _loop(self) -> None:
        if not self._kinds_loaded:
            import importlib

            for module in _KIND_MODULES:
                importlib.import_module(module)
            self._kinds_loaded = True
        while True:
            self._wake.wait(self.IDLE_SECONDS)
            self._wake.clear()
            # An error in a scan ends this thread (logged by threading's excepthook); the next
            # wake (an enqueue, a library open, a pause change) starts a new one.
            while (picked := self._next()) is not None:
                self._run(*picked)

    def _next(self) -> tuple[str, Any, tuple] | None:
        if is_paused() or not KINDS:
            return None
        from fichero_server.db.manager import db_manager

        kinds = list(KINDS)
        marks = ", ".join("?" for _ in kinds)
        candidates = []
        with self._lock:
            keys = list(self._libraries)
            self._rewoken.clear()
        idle = []
        for key in keys:
            db = db_manager.open_database(key)
            if db is None:  # closed: opening it again resumes its jobs
                idle.append(key)
                continue
            row = db.execute_fetchone(
                f"SELECT id, kind, subject, model, created_at FROM jobs "
                f"WHERE state = 'waiting' AND kind IN ({marks}) "
                f"ORDER BY (model IS NOT DISTINCT FROM ?) DESC, created_at, rowid LIMIT 1",
                [*kinds, self.loaded_model],
            )
            if row:
                candidates.append((key, db, row))
            else:
                idle.append(key)
        with self._lock:
            self._libraries.difference_update(set(idle) - self._rewoken)
        if not candidates:
            return None
        # Across libraries the same rule: the loaded model first, then the oldest.
        candidates.sort(key=lambda c: (c[2][3] != self.loaded_model, c[2][4]))
        return candidates[0]

    def _run(self, key: str, db: "Database", row: tuple) -> None:
        from fichero_server.db.manager import db_manager

        job_id, kind_name, subject, model, _ = row
        kind = KINDS[kind_name]
        if model != KRAKEN_MODEL and _kraken_busy():
            db.execute("UPDATE jobs SET reason = 'Waiting for Kraken (another page is using it)' "
                       "WHERE id = ?", [job_id])
            while _kraken_busy():
                time.sleep(self.KRAKEN_POLL_SECONDS)
        db.execute(
            "UPDATE jobs SET state = 'running', started_at = ?, attempts = attempts + 1, reason = NULL "
            "WHERE id = ? AND state = 'waiting'",
            [utc_now(), job_id],
        )
        self.loaded_model = model
        kind.qos()
        state, reason = "done", None
        try:
            kind.run(db, subject)
        except Exception as exc:  # noqa: BLE001 -- recorded on the row: the failure is the job's, shown with its reason
            logger.warning("job %s (%s on %s) failed: %s", job_id, kind_name, subject, exc)
            state, reason = "failed", str(exc) or type(exc).__name__
        if db_manager.open_database(key) is not db:
            return  # closed while it ran: the row stays `running` and resumes when the library opens
        db.execute("UPDATE jobs SET state = ?, reason = ?, finished_at = ? WHERE id = ?",
                   [state, reason, utc_now(), job_id])


_scheduler = _Scheduler()
