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

from fichero_server.models import Document, FileType, Status

if TYPE_CHECKING:  # pragma: no cover - typing only
    from fichero_server.db import Database

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


def needs_embedding(doc: Document) -> bool:
    """True when this document (or its PDF page children) carries text to
    embed. Embedding moved here from the inline ingest path (2026-08-09) —
    the ~19s first-model-load plus per-page compute froze imports; now the
    row lands instantly and stays ``pending`` until this stage embeds it."""
    return bool(doc.page_content) or doc.file_type == FileType.pdf


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

    queued = [
        doc.id for doc in docs if needs_derivative(doc) or needs_embedding(doc)
    ]
    futures: list[Future] = []
    if not queued:
        return futures

    def submit() -> None:
        executor = _get_executor()
        _progress_add(library, len(queued))
        # Thumbnails FIRST, embeds after (user, live 2026-08-19): on one shared
        # FIFO pool, interleaving them made every later page's thumbnail wait
        # behind ~1.3s embeds of earlier pages. Submitting the whole thumbnail
        # wave ahead of the embed wave gets images on screen while the text
        # embeds catch up behind them.
        for doc_id in queued:
            futures.append(executor.submit(_thumbnail_stage, doc_id, library))
        for doc_id in queued:
            futures.append(executor.submit(_embed_stage, doc_id, library))

    if db is not None:
        db.add_after_commit_hook(submit)
    else:
        submit()
    return futures


# ---------------------------------------------------------------------------
# Queue progress → backend.work.* events (user, live 2026-08-19): the status
# island said "Ready" while hundreds of pages were still embedding. One
# logical task per library tracks the queue; the app's ActivityStore already
# understands these frames (same shape task_workers emits).
# ---------------------------------------------------------------------------
_progress_lock = threading.Lock()
_progress: dict[str, dict[str, int]] = {}

#: How long the queue may go without completing anything before the status
#: island is told it has STALLED. A page takes ~1.3s to embed, so a minute of
#: total silence is not slowness — it is a pool with nothing moving through it.
STALL_SECONDS = 60.0
_stall_timer: threading.Timer | None = None


def _emit_queue_progress(
    library: str, done: int, total: int, *, stalled: bool = False
) -> None:
    from fichero_server.api.change_stream import emit_change

    finished = done >= total
    percent = 100.0 if finished else (done * 100.0 / total if total else 0.0)
    if stalled:
        message = (
            f"Stalled at {done} of {total} — nothing has finished for "
            f"{STALL_SECONDS:.0f}s. A source on a network volume or one still "
            "copying from another Mac can block this queue."
        )
    else:
        message = f"{done} of {total} pages embedded"
    try:
        emit_change(
            library,
            type="backend.work.completed" if finished else "backend.work.progress",
            run_id=f"derivatives:{library}",
            actor="system",
            metadata={
                "task_type": "derivatives",
                "task_name": "Processing imported pages",
                "status": "completed" if finished else ("stalled" if stalled else "running"),
                "message": message,
                "current": str(done),
                "total": str(total),
                "percent": f"{percent:.1f}",
            },
        )
    except Exception:  # never fail the stage over a status frame
        logger.warning("derivatives: progress emit failed", exc_info=True)


def _arm_stall_watchdog(library: str) -> None:
    """Say so when the queue stops moving (#4574 follow-up).

    A bar sitting at 0% is indistinguishable from a bar about to move, and
    that ambiguity is the whole bug: an import that could never finish looked
    exactly like one that had just started. The probe in the stages catches a
    source that FAILS to read; this catches the rest — a read blocked in the
    kernel, a pool wedged on something nobody predicted — and turns silence
    into a sentence.
    """
    global _stall_timer
    if _stall_timer is not None:
        _stall_timer.cancel()

    def report() -> None:
        with _progress_lock:
            state = _progress.get(library)
            if state is None:
                return
            done, total = state["done"], state["total"]
        logger.error(
            "derivatives: queue stalled for %s at %d of %d — no completion in %.0fs",
            library, done, total, STALL_SECONDS,
        )
        _emit_queue_progress(library, done, total, stalled=True)

    _stall_timer = threading.Timer(STALL_SECONDS, report)
    _stall_timer.daemon = True
    _stall_timer.start()


def _disarm_stall_watchdog() -> None:
    global _stall_timer
    if _stall_timer is not None:
        _stall_timer.cancel()
        _stall_timer = None


def _progress_add(library: str, count: int) -> None:
    with _progress_lock:
        state = _progress.setdefault(library, {"done": 0, "total": 0})
        state["total"] += count
        done, total = state["done"], state["total"]
    _emit_queue_progress(library, done, total)
    _arm_stall_watchdog(library)


def _progress_expand(library: str, extra: int) -> None:
    """Grow the total once a stage discovers how much work it REALLY is.

    The queue is seeded with one unit per DOCUMENT, because that is all the
    import path knows at queue time. For a 252-page book that made the bar a
    two-state device: 0% for as long as the whole book took to embed, then
    100%. The label said "pages", which made a truthful count of documents
    read as a stuck count of pages — and a user watching 0% for twenty minutes
    has no way to tell that from a hang (#4574 follow-up).

    So the moment a stage knows its page count, it says so and the bar starts
    moving through pages instead of sitting on the one document.
    """
    if extra <= 0:
        return
    with _progress_lock:
        state = _progress.get(library)
        if state is None:
            return
        state["total"] += extra
        done, total = state["done"], state["total"]
    _emit_queue_progress(library, done, total)
    _arm_stall_watchdog(library)


def _progress_tick(library: str) -> None:
    with _progress_lock:
        state = _progress.get(library)
        if state is None:
            return
        state["done"] += 1
        done, total = state["done"], state["total"]
        finished = done >= total
        if finished:
            del _progress[library]
    # Something moved, so the queue is not stalled: push the deadline out, or
    # stand the watchdog down when there is nothing left to watch.
    if finished:
        _disarm_stall_watchdog()
    else:
        _arm_stall_watchdog(library)
    # Every 5th completion plus the final one — enough for a live percent
    # without an event per page on top of each page's document.updated.
    if finished or done % 5 == 0:
        _emit_queue_progress(library, done, total)


def _embed_document_tree(
    doc: Document, db: "Database", library: str | None = None
) -> str | None:
    """Embed a document's text, and its PDF page children, off the import
    path. Returns an error summary (never raises) — an embed failure is
    recorded on the document, not allowed to strand it in ``pending``.

    ``library`` opts this tree into PAGE-level progress: the count is declared
    once the targets are known and ticked as each page lands, so a long book
    reports "37 of 252" rather than holding the queue at one unfinished
    document for its entire run.
    """
    import time as _time

    failures = 0
    embedded = 0
    started = _time.monotonic()
    targets: list[Document] = []
    if doc.page_content:
        targets.append(doc)
    if doc.file_type == FileType.pdf:
        try:
            children = db.query(Document, parent_id=doc.id)
        except Exception as exc:
            return f"could not list pages: {type(exc).__name__}: {exc}"
        targets.extend(child for child in children if child.page_content)
    # Declare the real size before the first page, not after the last.
    if library is not None:
        _progress_expand(library, len(targets))
    for target in targets:
        try:
            if not db.embed(target):
                outcome = getattr(db, "last_embed_outcome", None)
                reason = getattr(outcome, "reason", None)
                # 'unsupported'/'empty' style outcomes are not failures.
                if reason in (None, "embedding_failed", "error"):
                    failures += 1
            else:
                embedded += 1
        except Exception as exc:
            failures += 1
            logger.warning(
                "Deferred embed failed for %s: %s", target.id, exc
            )
        # Outside the try/except on purpose: a page that FAILED to embed is
        # still a page the queue is done with. Ticking only on success would
        # leave the total unreachable and the bar stuck just short of the end
        # — the same silence this whole change is removing, arrived at from
        # the other side.
        if library is not None:
            _progress_tick(library)
    if targets:
        # chars + rss make the 951s-for-"1 target" case explicable at a
        # glance (the 2026-08-22 Air OOM: one target hid thousands of
        # passages) and give the death-by-memory ramp a visible slope.
        total_chars = sum(len(t.page_content or "") for t in targets)
        logger.info(
            "derivatives.embed doc=%s targets=%d embedded=%d failed=%d "
            "elapsed_ms=%d chars=%d rss_mb=%d",
            doc.id, len(targets), embedded, failures,
            int((_time.monotonic() - started) * 1000),
            total_chars, _current_rss_mb(),
        )
    if failures:
        return f"{failures} of {len(targets)} embeds failed"
    return None


def _current_rss_mb() -> int:
    """This process's resident set, in MB — the one number the three
    2026-08-22 silent deaths never logged."""
    try:
        import resource

        # ru_maxrss is BYTES on macOS, KB on Linux.
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return int(peak / (1 << 20)) if peak > (1 << 30) else int(peak / 1024)
    except Exception:  # pragma: no cover - platform without resource
        return -1


#: How long a worker waits for a single byte of a document's source before it
#: declares the file unreadable. A local disk answers in microseconds; a
#: healthy SMB mount in milliseconds. A mount whose credentials have expired
#: (the macOS Kerberos prompt) or a file promise that never materialised
#: answers never — and THAT is the case this bounds, because a blocked read
#: holds one of only two pool workers and two of them stop the queue dead.
SOURCE_READ_DEADLINE_SECONDS = 10.0


def _probe_source_readable(path: Path) -> str | None:
    """Read one byte of ``path`` under a deadline. Error string, or None.

    ``exists()`` is not readability. A file on a network volume can stat fine
    and then block for ever on the first read; an un-materialised file promise
    (the shape a drag from another Mac produces) is a path with no bytes
    behind it yet. Both looked identical to a local file right up to the point
    where the import stopped moving.

    The probe runs on a throwaway daemon thread so the DEADLINE is real: a
    read blocked in the kernel cannot be cancelled, so the thread may stay
    stuck, but the worker returns and the queue keeps draining. One leaked
    thread is a far better outcome than a wedged pool and a bar at 0%.
    """
    outcome: list[str | None] = []

    def read_one_byte() -> None:
        try:
            with path.open("rb") as handle:
                handle.read(1)
            outcome.append(None)
        except OSError as exc:
            outcome.append(f"{type(exc).__name__}: {exc}")

    probe = threading.Thread(target=read_one_byte, daemon=True, name="source-probe")
    probe.start()
    probe.join(SOURCE_READ_DEADLINE_SECONDS)
    if probe.is_alive():
        return (
            f"source unreadable: {path} did not return a byte within "
            f"{SOURCE_READ_DEADLINE_SECONDS:.0f}s. If it lives on a network "
            "volume, the mount may need re-authenticating; if it was dragged "
            "from another Mac, the file may not have finished copying."
        )
    if outcome and outcome[0] is not None:
        return f"source unreadable: {path} — {outcome[0]}"
    return None


def _source_error(doc: Document, db: "Database", library: str) -> str | None:
    """Why this document's bytes cannot be read right now, or None.

    Only documents that ARE expected to have bytes are judged. Plenty of rows
    legitimately have none — an extracted entry, a workflow node, a note whose
    whole content is its text — and calling those "unreadable" would fail
    documents that are perfectly fine. Expecting bytes means: an image or PDF
    file, or a page child that renders from its parent PDF.
    """
    from fichero_server.db.storage import resolve_pdf_render_source, resolve_source

    package = Path(library)
    pdf_render = resolve_pdf_render_source(doc, db=db, library_root=package)
    expects_bytes = pdf_render is not None or doc.file_type in DERIVATIVE_FILE_TYPES
    if not expects_bytes:
        return None
    path = pdf_render[0] if pdf_render else resolve_source(doc, library_root=package)
    if path is None:
        # A page child whose parent PDF is gone, or a row whose file moved.
        # Named, not silent: "no source" is an answer; a stalled bar is not.
        return f"source not found for {doc.name!r}"
    return _probe_source_readable(path)


def _record_source_failure(
    db: "Database", doc_id: str, library: str, error: str
) -> None:
    """Record WHY a document's bytes could not be read, and say so live.

    Uses ``derivative_error`` — the existing key a retry selects on (#4225) —
    so an unreadable source joins the same recorded-failure model as a decode
    that failed, rather than inventing a second one nothing queries. The
    status stays ``pending`` for the same reason: this document has not been
    processed and still could be, once the volume is back.

    What must NOT happen is silence. The caller returns immediately after
    this, so the stage stops instead of blocking a pool worker — and the embed
    stage's ``finally`` still ticks the queue, so the bar keeps moving instead
    of sitting at 0% while the user waits for something that is never coming.
    """
    from fichero_server.api.change_stream import emit_change

    logger.error("Derivative stage: %s (%s)", error, doc_id)
    doc = db.get(Document, doc_id)
    if doc is None or getattr(doc, "deleted_at", None) is not None:
        return
    metadata = dict(doc.metadata or {})
    metadata["derivative_error"] = error
    doc.metadata = metadata
    try:
        db.save(doc)
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Could not persist source failure for %s: %s", doc_id, exc)
        return
    emit_change(
        library,
        type="document.updated",
        document_ids=[doc_id],
        actor="derivatives",
    )


def _open_stage_db(library: str, doc_id: str) -> "tuple[Database, Document] | None":
    """Worker-thread database handle + the queued document, or None (logged)."""
    from fichero_server.db.manager import db_manager

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
    return db, doc


def _thumbnail_stage(doc_id: str, library: str) -> Path | None:
    """Generate one document's thumbnail and announce it IMMEDIATELY — the
    change event used to wait behind that document's ~1.3s embed, so the grid
    learned about a finished image over a second late (user, live 2026-08-19).
    """
    from fichero_server.api.change_stream import emit_change
    from fichero_server.db.storage import ensure_thumbnail

    opened = _open_stage_db(library, doc_id)
    if opened is None:
        return None
    db, doc = opened

    thumb: Path | None = None
    error: str | None = None
    if needs_derivative(doc):
        # Before the decode, not after: an unreadable source blocks INSIDE the
        # renderer, and this pool has two workers. Two blocked reads and the
        # queue stops dead with the progress bar at 0% (#4574 follow-up).
        if source_error := _source_error(doc, db, library):
            _record_source_failure(db, doc_id, library, source_error)
            return None
        try:
            thumb = ensure_thumbnail(doc, package_path=Path(library), db=db)
            if thumb is None:
                error = "Thumbnail generation produced no image"
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            logger.warning(
                "Derivative generation failed for %s: %s", doc_id, error
            )

    # RE-READ before writing (same guard as the embed stage): never save a
    # stage-start copy over a row deleted while the thumbnail rendered.
    doc = db.get(Document, doc_id)
    if doc is None or getattr(doc, "deleted_at", None) is not None:
        return thumb

    metadata = dict(doc.metadata or {})
    if error:
        metadata["derivative_error"] = error
    else:
        metadata.pop("derivative_error", None)
    # Save ONLY on a real change: this stage can run concurrently with the
    # same document's embed stage (two pool workers), and an unconditional
    # save here overwrote the embed stage's pending → completed flip with
    # this stage's stale copy.
    if metadata != (doc.metadata or {}):
        doc.metadata = metadata
        try:
            db.save(doc)
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Could not persist thumbnail outcome for %s: %s", doc_id, exc)
            return thumb

    if thumb is not None:
        emit_change(
            library,
            type="document.updated",
            document_ids=[doc_id],
            actor="derivatives",
        )
    return thumb


def _embed_stage(doc_id: str, library: str) -> None:
    """Embed one document's text tree, flip pending → completed (#4225), and
    tick the queue-progress counter that feeds the status island."""
    from fichero_server.api.change_stream import emit_change

    try:
        opened = _open_stage_db(library, doc_id)
        if opened is None:
            return
        db, doc = opened

        # No source probe here, deliberately: this stage embeds TEXT, which it
        # reads from the database. It needs no bytes, so an unreadable file
        # must not stop a document's text from being embedded — and a document
        # with no file at all (a note, an extracted entry) is not a failure.
        # The probe belongs in the thumbnail stage, which is the one that
        # decodes, and therefore the one that can block.
        embed_error = _embed_document_tree(doc, db, library)

        # RE-READ before writing (manifest-drop repro, 2026-08-20): embedding
        # takes seconds, and saving the copy read at stage START resurrected
        # rows deleted in between — the stale save clobbered deleted_at. A
        # row deleted mid-stage needs no status flip at all.
        doc = db.get(Document, doc_id)
        if doc is None or getattr(doc, "deleted_at", None) is not None:
            return

        metadata = dict(doc.metadata or {})
        if embed_error:
            metadata["embedding_error"] = embed_error
        else:
            metadata.pop("embedding_error", None)
        if "derivative_error" not in metadata and doc.status == Status.pending:
            # The status model, pinned (#4225): ingest records a row as
            # `pending` and the derivative stage is what clears it. A document
            # that already moved on (failed, completed) is left alone.
            doc.status = Status.completed
        doc.metadata = metadata

        try:
            db.save(doc)
        except Exception as exc:  # pragma: no cover - defensive
            logger.error(
                "Could not persist derivative outcome for %s: %s", doc_id, exc
            )
            return

        emit_change(
            library,
            type="document.updated",
            document_ids=[doc_id],
            actor="derivatives",
        )
    finally:
        _progress_tick(library)


def generate_derivative(doc_id: str, library_path: str | Path) -> Path | None:
    """Both stages, synchronously — thumbnail then embed.

    Kept as the one-call form for direct callers and tests; the queued path
    submits the stages separately so a batch's thumbnails all land before its
    embeds start.
    """
    library = str(library_path)
    thumb = _thumbnail_stage(doc_id, library)
    _embed_stage(doc_id, library)
    return thumb


def shutdown(wait: bool = True) -> None:
    """Stop the derivative pool (engine shutdown, and between test modules)."""
    global _executor
    _disarm_stall_watchdog()
    with _executor_lock:
        executor, _executor = _executor, None
    if executor is not None:
        executor.shutdown(wait=wait)
