"""Single-writer DB queue — #1000 Phase 2.

Serializes write operations through one dedicated thread + connection.

The scale goal (500 folders x 500 files) means a workflow fans its
*compute* out across many workers — but DuckDB is single-writer, so
those workers must not all call ``db.save()`` concurrently or they
contend on the write lock. The pattern: parallelise the compute,
serialise the persistence. Workers enqueue write requests; this
``DBWriter`` applies them, in order, against its own connection.

Reads still go direct against per-thread connections (DuckDB MVCC means
readers never block) — only *writes* funnel through here.

This module is the infrastructure. Migrating callers
(``extract_all``, ``_write_kg_rows``, ...) onto it is a separate,
incremental step. Batching of queued writes is Phase 3.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from concurrent.futures import Future
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pydantic import BaseModel

    from fichero.db import Database

logger = logging.getLogger(__name__)

# Sentinel pushed onto the queue to tell the writer thread to exit.
_SHUTDOWN = object()

# Default upper bound on how long flush()/stop() will wait for the queue
# to drain before failing loud (#1000). Generous — a real drain of queued
# artifact writes is sub-second even under DuckDB load — but finite, so a
# wedged or dead writer thread raises instead of hanging the caller (and,
# via db_manager._stop_writers, the whole db_manager lock) forever.
_DEFAULT_DRAIN_TIMEOUT = 120.0


class DBWriterError(RuntimeError):
    """The DBWriter can't make progress — its thread died with writes
    still pending, or a drain exceeded its timeout. Raised instead of
    blocking forever so a wedged writer fails loud (#1000)."""


@dataclass
class _WriteOp:
    """One queued write. ``future`` resolves to None on success, or
    carries the exception if the write failed."""

    kind: str  # "save" | "delete"
    obj: "BaseModel"
    future: Future = field(default_factory=Future)
    auto_embed: bool = False


class DBWriter:
    """Serializes DB writes through one dedicated thread + connection.

    The passed ``Database`` is owned *exclusively* by this writer while
    it is running — callers must not write through that same
    ``Database`` directly, or the single-writer guarantee is broken.
    Reads through other (per-thread) connections are fine.

    Lifecycle::

        writer = DBWriter(db)
        writer.start()
        fut = writer.save(some_model)   # enqueue, returns a Future
        fut.result()                   # block until applied (optional)
        writer.flush()                 # block until queue fully drained
        writer.stop()                  # drain + shut the thread down

    Or as a context manager::

        with DBWriter(db) as writer:
            writer.save(model_a)
            writer.save(model_b)
        # exit drains + stops
    """

    def __init__(self, db: "Database", *, name: str = "db-writer") -> None:
        self._db = db
        self._queue: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None
        self._name = name
        self._started = False

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        """Start the writer thread. Idempotent."""
        if self._started:
            return
        self._thread = threading.Thread(
            target=self._run, name=self._name, daemon=True
        )
        self._thread.start()
        self._started = True
        logger.debug("DBWriter %s started", self._name)

    def stop(
        self, *, drain: bool = True, timeout: float | None = _DEFAULT_DRAIN_TIMEOUT
    ) -> None:
        """Stop the writer thread.

        With ``drain=True`` (default), waits up to ``timeout`` seconds for
        every already-queued write to be applied before shutting down. A
        wedged or dead writer does NOT block shutdown — the drain failure
        is logged loud and the thread is shut down anyway, dropping any
        un-applied writes. This is critical: ``stop()`` is called by
        ``db_manager._stop_writers`` while holding the db_manager lock, so
        it must always return (#1000). Idempotent.
        """
        if not self._started:
            return
        if drain:
            try:
                self._drain(timeout, what="stop")
            except DBWriterError as exc:
                logger.error(
                    "%s — shutting down without a full drain", exc
                )
        self._started = False  # reject further enqueues before sending shutdown
        self._queue.put(_SHUTDOWN)
        if self._thread is not None:
            self._thread.join(timeout=10.0)
            if self._thread.is_alive():
                logger.error(
                    "DBWriter %s thread did not exit within 10s of shutdown",
                    self._name,
                )
        logger.debug("DBWriter %s stopped", self._name)

    def __enter__(self) -> "DBWriter":
        self.start()
        return self

    def __exit__(self, *_exc: object) -> bool:
        self.stop()
        return False

    # -- enqueue API -------------------------------------------------------

    def save(self, obj: "BaseModel", *, auto_embed: bool = False) -> Future:
        """Enqueue a save. Returns a Future that resolves to None once
        applied, or carries the exception if the write failed."""
        return self._enqueue(_WriteOp("save", obj, auto_embed=auto_embed))

    def delete(self, obj: "BaseModel") -> Future:
        """Enqueue a delete. Returns a Future (see :meth:`save`)."""
        return self._enqueue(_WriteOp("delete", obj))

    def flush(self, timeout: float | None = _DEFAULT_DRAIN_TIMEOUT) -> None:
        """Block until every write enqueued so far has been applied.

        Never blocks forever (#1000): raises :class:`DBWriterError` if the
        writer thread has died with writes still pending, or if the queue
        does not drain within ``timeout`` seconds. Pass ``timeout=None``
        only where an unbounded wait is genuinely safe.
        """
        self._drain(timeout, what="flush")

    @property
    def pending(self) -> int:
        """Approximate number of writes still queued (not yet applied)."""
        return self._queue.qsize()

    def _drain(self, timeout: float | None, *, what: str) -> None:
        """Wait until the queue is fully applied, or fail loud.

        Shared by :meth:`flush` and :meth:`stop`. Replaces a bare
        ``queue.join()`` (which has no timeout and no liveness check) with
        a bounded wait on the queue's own ``all_tasks_done`` condition,
        re-checking the writer thread's liveness each tick. ``unfinished_tasks``
        and ``all_tasks_done`` are stable CPython ``queue.Queue`` internals
        — the same ones ``Queue.join()`` itself uses.
        """
        if not self._started or self._thread is None:
            raise DBWriterError(f"DBWriter {self._name} is not running")
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._queue.all_tasks_done:
            while self._queue.unfinished_tasks:
                if not self._thread.is_alive():
                    raise DBWriterError(
                        f"DBWriter {self._name} thread died with "
                        f"{self._queue.unfinished_tasks} write(s) pending"
                    )
                if deadline is not None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise DBWriterError(
                            f"DBWriter {self._name} {what} exceeded "
                            f"{timeout}s with {self._queue.unfinished_tasks} "
                            f"write(s) still pending"
                        )
                    wait_for = min(remaining, 1.0)
                else:
                    wait_for = 1.0
                # wait() releases the lock; the worker's task_done() wakes
                # us when unfinished_tasks hits 0. The 1s cap re-checks
                # thread liveness even while the worker is mid-drain.
                self._queue.all_tasks_done.wait(wait_for)

    def _enqueue(self, op: _WriteOp) -> Future:
        if not self._started:
            raise RuntimeError("DBWriter is not running — call start() first")
        self._queue.put(op)
        return op.future

    # -- worker ------------------------------------------------------------

    def _run(self) -> None:
        try:
            while True:
                item = self._queue.get()
                if item is _SHUTDOWN:
                    self._queue.task_done()
                    break
                op: _WriteOp = item
                try:
                    if op.kind == "save":
                        self._db.save(op.obj, auto_embed=op.auto_embed)
                    elif op.kind == "delete":
                        self._db.delete(op.obj)
                    else:  # pragma: no cover - guarded by the enqueue API
                        raise ValueError(f"unknown write op: {op.kind!r}")
                    op.future.set_result(None)
                except Exception as exc:  # noqa: BLE001 - surfaced via the Future
                    logger.error("DBWriter %s op failed: %s", op.kind, exc)
                    op.future.set_exception(exc)
                finally:
                    self._queue.task_done()
        except Exception:  # noqa: BLE001 - last-resort: a dead worker must be loud
            # Per-op failures are handled above; reaching here means the
            # loop itself died (e.g. queue.get raised). Log loud — _drain's
            # is_alive() check turns this into a DBWriterError for callers
            # instead of an infinite hang (#1000).
            logger.exception(
                "DBWriter %s worker thread crashed — writer is dead", self._name
            )
