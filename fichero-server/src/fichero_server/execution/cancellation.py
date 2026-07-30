"""One cancellation primitive shared by single runs and batches (#4317).

Single-run cancel used to be a dict flag on the in-memory registry entry,
checked once per LangGraph event tick — unreachable after registry eviction
and invisible inside the parallel fan-out; batches had their own separate
``asyncio.Event``. This module is the ONE registry both consult.

``threading.Event`` (not ``asyncio.Event``) on purpose: the cancel endpoint
runs on the FastAPI loop while each workflow runs on its own worker thread
with its own loop, and the fan-out checks from ``asyncio.to_thread`` workers.
All consumers only need non-blocking ``set()``/``is_set()``, which
``threading.Event`` provides safely across threads and loops.

Keys are run ids: the run's ``thread_id`` for single runs and batch items,
the ``batch_id`` for batch-level cancel.
"""

from __future__ import annotations

import threading

_lock = threading.Lock()
_events: dict[str, threading.Event] = {}
_EVENTS_LIMIT = 500


class WorkflowCancelled(Exception):
    """Raised at a work boundary when the run has been cancelled (#4402).

    Distinct from every other exception on purpose. A tool that stops because
    the user pressed Stop has not FAILED, and reducing it to a generic error
    would report a cancelled run as a failure — the run would be marked
    'failed' in Activity and its error surfaced as though something broke.

    Carries the run id so the handler can confirm which run stopped rather
    than inferring it from context.
    """

    def __init__(self, run_id: str) -> None:
        super().__init__(f"Workflow run {run_id} cancelled by user")
        self.run_id = run_id


def cancellation_event(run_id: str) -> threading.Event:
    """Get (or create) the cancellation event for ``run_id``."""
    if not run_id:
        raise ValueError("cancellation_event: run_id must be non-empty")
    with _lock:
        event = _events.get(run_id)
        if event is None:
            event = threading.Event()
            _events[run_id] = event
            while len(_events) > _EVENTS_LIMIT:
                _events.pop(next(iter(_events)))
        return event


def request_cancellation(run_id: str) -> None:
    """Signal every checker of ``run_id`` — loop tick, per-file fan-out,
    batch item — to stop at its next boundary."""
    cancellation_event(run_id).set()


def cancellation_requested(run_id: str | None) -> bool:
    """Non-blocking check; safe with a missing/empty id (returns False)."""
    if not run_id:
        return False
    with _lock:
        event = _events.get(run_id)
    return event is not None and event.is_set()


def clear_cancellation(run_id: str | None) -> None:
    """Drop the event once its run reaches a terminal state."""
    if not run_id:
        return
    with _lock:
        _events.pop(run_id, None)
