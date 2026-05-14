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
from concurrent.futures import Future
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pydantic import BaseModel

    from fichero.db import Database

logger = logging.getLogger(__name__)

# Sentinel pushed onto the queue to tell the writer thread to exit.
_SHUTDOWN = object()


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

    def stop(self, *, drain: bool = True) -> None:
        """Stop the writer thread.

        With ``drain=True`` (default), blocks until every already-queued
        write has been applied before shutting down. Idempotent.
        """
        if not self._started:
            return
        if drain:
            self._queue.join()
        self._started = False  # reject further enqueues before sending shutdown
        self._queue.put(_SHUTDOWN)
        if self._thread is not None:
            self._thread.join(timeout=10.0)
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

    def flush(self) -> None:
        """Block until every write enqueued so far has been applied."""
        self._queue.join()

    @property
    def pending(self) -> int:
        """Approximate number of writes still queued (not yet applied)."""
        return self._queue.qsize()

    def _enqueue(self, op: _WriteOp) -> Future:
        if not self._started:
            raise RuntimeError("DBWriter is not running — call start() first")
        self._queue.put(op)
        return op.future

    # -- worker ------------------------------------------------------------

    def _run(self) -> None:
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
