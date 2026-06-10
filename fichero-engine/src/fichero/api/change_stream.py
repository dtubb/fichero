"""Per-library change-stream hub (#1863).

The foundation of the observable data layer: an in-process fan-out that lets
mutating routes broadcast ``ChangeEvent``s to every connected app window for a
given library. This is the backend half of the spec in
``docs/architecture/swiftui/observable_data_layer.md``.

It deliberately mirrors the proven workflow-run SSE infra
(``api/routes/workflow_execution`` — ``StreamingResponse(text/event-stream)``
draining a queue with keepalive comments). The one generalization: keyed by
*library path* instead of a single workflow thread id, so one connection per
window receives every mutation in its library.

Design notes:
- One ``asyncio.Queue`` per connected window (subscriber). The SSE endpoint in
  ``api/routes/changes.py`` drains it; ``emit_change`` feeds it.
- ``emit_change`` is **best-effort**: it must never break the mutation that
  called it. All failures are swallowed (logged at debug).
- In-process only (no broker) — matches the single-backend-process reality.
  Reconnect/replay is a frontend concern (reload-on-reconnect, spec §5.5).
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections import defaultdict
from datetime import datetime, timezone
from typing import Iterable

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# =============================================================================
# Event schema (transport projection of the audit record — spec §3.2)
# =============================================================================


class ChangeEvent(BaseModel):
    """A single data-layer change broadcast to a library's windows.

    ``type`` is ``"{domain}.{verb}"`` — e.g. ``entity.created``,
    ``entity.updated``, ``entity.deleted``, ``entity.merged``,
    ``claim.updated``, ``document.updated``. The id lists are domain-typed so a
    document-scoped store can cheaply decide whether it cares.
    """

    type: str
    entity_ids: list[str] = Field(default_factory=list)
    claim_ids: list[str] = Field(default_factory=list)
    document_ids: list[str] = Field(default_factory=list)
    artifact_ids: list[str] = Field(default_factory=list)
    citation_ids: list[str] = Field(default_factory=list)
    reference_ids: list[str] = Field(default_factory=list)
    run_id: str | None = None
    actor: str = "system"  # ui | chat | workflow | import | system
    origin_window: str | None = None  # self-echo de-dup seam (spec §3.5)
    ts: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


def format_change_sse(event: ChangeEvent) -> str:
    """Format a ChangeEvent as an SSE ``data:`` frame."""
    return f"data: {event.model_dump_json()}\n\n"


# =============================================================================
# The hub — library_path → set[asyncio.Queue]
# =============================================================================


class _ChangeHub:
    """Process-global registry of subscriber queues keyed by library path.

    Thread-safe registry mutation (a plain ``threading.Lock`` guards the
    dict/set bookkeeping) so workflow worker threads can ``emit`` safely. The
    per-queue ``put_nowait`` is itself thread-affine to the loop that drains it;
    in the interim emit points the producer and consumer share the FastAPI
    event loop, and put_nowait from another thread degrades gracefully (the
    event is dropped best-effort rather than raising into the mutation).
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)
        self._lock = threading.Lock()

    def subscribe(self, library_path: str) -> asyncio.Queue:
        """Register a new subscriber queue for ``library_path`` and return it."""
        queue: asyncio.Queue = asyncio.Queue()
        with self._lock:
            self._subscribers[library_path].add(queue)
        logger.debug(
            "change-hub: +subscriber lib=%s (now %d)",
            library_path,
            self.subscriber_count(library_path),
        )
        return queue

    def unsubscribe(self, library_path: str, queue: asyncio.Queue) -> None:
        """Remove a subscriber queue (on window disconnect)."""
        with self._lock:
            subs = self._subscribers.get(library_path)
            if subs is not None:
                subs.discard(queue)
                if not subs:
                    self._subscribers.pop(library_path, None)
        logger.debug("change-hub: -subscriber lib=%s", library_path)

    def emit(self, library_path: str, event: ChangeEvent) -> int:
        """Put ``event`` on every subscriber queue for ``library_path``.

        Returns the number of queues delivered to. Best-effort: a failing
        queue is skipped, never raised.
        """
        with self._lock:
            subs = list(self._subscribers.get(library_path, ()))
        delivered = 0
        for queue in subs:
            try:
                queue.put_nowait(event)
                delivered += 1
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug("change-hub: drop event for one queue: %s", exc)
        return delivered

    def subscriber_count(self, library_path: str) -> int:
        with self._lock:
            return len(self._subscribers.get(library_path, ()))


# Process-global singleton.
_change_hub = _ChangeHub()


def emit_change(
    library_path: str,
    *,
    type: str,
    entity_ids: Iterable[str] = (),
    claim_ids: Iterable[str] = (),
    document_ids: Iterable[str] = (),
    artifact_ids: Iterable[str] = (),
    citation_ids: Iterable[str] = (),
    reference_ids: Iterable[str] = (),
    run_id: str | None = None,
    actor: str = "system",
    origin_window: str | None = None,
) -> None:
    """Broadcast a change to every window subscribed to ``library_path``.

    Best-effort: never raises. Call at the end of a mutating route so a failure
    here can never roll back or break the mutation itself.
    """
    if not library_path:
        return
    try:
        event = ChangeEvent(
            type=type,
            entity_ids=list(entity_ids),
            claim_ids=list(claim_ids),
            document_ids=list(document_ids),
            artifact_ids=list(artifact_ids),
            citation_ids=list(citation_ids),
            reference_ids=list(reference_ids),
            run_id=run_id,
            actor=actor,
            origin_window=origin_window,
        )
        _change_hub.emit(library_path, event)
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("emit_change failed (best-effort, ignored): %s", exc)
