"""Post-ingest derivative generation, off the import fast path (#4225).

Import records rows at ~900 files/sec (#4203) precisely because it does the
minimum per file. Thumbnail generation is slow, failure-prone, and needs
decoding — putting it inline would destroy that. So ingest queues the work
here and returns; this module drains the queue on its own bounded pool and
emits a ``document.updated`` change per document as each derivative lands, so
the row gains its thumbnail in place with no refresh and no polling.

Bounded on purpose. ``MAX_CONCURRENT_DERIVATIVES`` is small because unbounded
concurrent texture decode destabilised the window server once already (#1400,
the reason the canvas caps at 250 nodes). The same hazard applies to bulk
thumbnail generation, so the ceiling is designed in rather than discovered.

Failure is recorded, never silent: a document whose derivative could not be
produced keeps ``Status.pending`` and gains ``metadata["derivative_error"]``,
which is what makes it distinguishable from one that is merely waiting and
what a retry can select on.
"""

from __future__ import annotations

import logging
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING, Iterable

from fichero.models import Document, FileType, Status

if TYPE_CHECKING:  # pragma: no cover - typing only
    from fichero.db import Database

logger = logging.getLogger(__name__)

# Two at a time. See the module docstring: this is the #1400 hazard, not a
# tuning knob to raise casually.
MAX_CONCURRENT_DERIVATIVES = 2

# Types whose derivative is worth generating eagerly. Everything else keeps the
# existing lazy path (the storage endpoints still call ensure_thumbnail on a
# miss), so this stage never becomes a bottleneck for types that cannot
# produce an image anyway.
DERIVATIVE_FILE_TYPES = frozenset({FileType.image, FileType.pdf})

_executor: ThreadPoolExecutor | None = None
_executor_lock = threading.Lock()


def _get_executor() -> ThreadPoolExecutor:
    global _executor
    with _executor_lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(
                max_workers=MAX_CONCURRENT_DERIVATIVES,
                thread_name_prefix="derivative",
            )
    return _executor


def needs_derivative(doc: Document) -> bool:
    """True when this document should get an eager derivative."""
    return doc.file_type in DERIVATIVE_FILE_TYPES


def queue_derivatives(
    docs: Iterable[Document],
    *,
    library_path: str | Path,
    db: "Database | None" = None,
) -> list[Future]:
    """Schedule derivative generation for freshly ingested documents.

    Returns the futures so a caller (and the tests) can wait; the ingest path
    deliberately does NOT wait.

    Pass ``db`` when the caller might be inside a transaction — the audited
    ``import.file`` action is atomic, so submitting immediately would let a
    worker look up a document id that has not been COMMITTED yet, find
    nothing, and drop the thumbnail on the floor. ``add_after_commit_hook``
    runs the submission immediately when there is no open transaction, so this
    is the same call either way; the returned list fills in on commit.
    """
    library = str(library_path)
    if not library:
        logger.warning("Not queueing derivatives: no library path given")
        return []

    queued = [doc.id for doc in docs if needs_derivative(doc)]
    futures: list[Future] = []
    if not queued:
        return futures

    def submit() -> None:
        executor = _get_executor()
        for doc_id in queued:
            futures.append(executor.submit(generate_derivative, doc_id, library))

    if db is not None:
        db.add_after_commit_hook(submit)
    else:
        submit()
    return futures


def generate_derivative(doc_id: str, library_path: str | Path) -> Path | None:
    """Generate one document's thumbnail and record the outcome.

    Runs on a worker thread with its own database handle — the request-scoped
    one belongs to a connection whose lifetime this outlives (#1216).
    """
    from fichero.api.change_stream import emit_change
    from fichero.db.manager import db_manager
    from fichero.db.storage import ensure_thumbnail

    library = str(library_path)
    try:
        db: "Database" = db_manager.get_database(library)
    except Exception as exc:
        logger.error("Derivative stage could not open %s: %s", library, exc)
        return None

    doc = db.get(Document, doc_id)
    if doc is None:
        # Loud: a queued id that no longer resolves means the row vanished
        # between ingest and this stage, which is worth seeing.
        logger.warning("Derivative stage: document %s no longer exists", doc_id)
        return None

    thumb: Path | None = None
    error: str | None = None
    try:
        thumb = ensure_thumbnail(doc, package_path=Path(library), db=db)
        if thumb is None:
            error = "Thumbnail generation produced no image"
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        logger.warning("Derivative generation failed for %s: %s", doc_id, error)

    metadata = dict(doc.metadata or {})
    if error:
        metadata["derivative_error"] = error
    else:
        metadata.pop("derivative_error", None)
        if doc.status == Status.pending:
            # The status model, pinned (#4225): ingest records a row as
            # `pending` and the derivative stage is what clears it. A document
            # that already moved on (failed, completed) is left alone.
            doc.status = Status.completed
    doc.metadata = metadata

    try:
        db.save(doc)
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Could not persist derivative outcome for %s: %s", doc_id, exc)
        return thumb

    emit_change(
        library,
        type="document.updated",
        document_ids=[doc_id],
        actor="derivatives",
    )
    return thumb


def shutdown(wait: bool = True) -> None:
    """Stop the derivative pool (engine shutdown, and between test modules)."""
    global _executor
    with _executor_lock:
        executor, _executor = _executor, None
    if executor is not None:
        executor.shutdown(wait=wait)
