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
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from fastapi import Request
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_SUBSCRIBER_QUEUE_MAXSIZE = 1000
_REPLAY_BUFFER_SIZE = 1000


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
    interpretation_ids: list[str] = Field(default_factory=list)
    run_id: str | None = None
    actor: str = "system"  # ui | chat | workflow | import | system
    origin_window: str | None = None  # self-echo de-dup seam (spec §3.5)
    origin_user: str | None = None  # user-level self-echo de-dup seam (#2023)
    event_id: int | None = None
    replay_required: bool = False
    gap_reason: str | None = None
    dropped_event_count: int = 0
    last_event_id: int | None = None
    oldest_available_event_id: int | None = None
    latest_available_event_id: int | None = None
    ts: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def format_change_sse(event: ChangeEvent) -> str:
    """Format a ChangeEvent as an SSE ``data:`` frame."""
    id_line = f"id: {event.event_id}\n" if event.event_id is not None else ""
    return f"{id_line}data: {event.model_dump_json()}\n\n"


@dataclass(eq=False)
class _Subscriber:
    queue: asyncio.Queue
    loop: asyncio.AbstractEventLoop | None
    active: bool = True


@dataclass
class _Subscription:
    queue: asyncio.Queue
    replay_events: list[ChangeEvent]
    resync_event: ChangeEvent | None


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

    def __init__(
        self,
        *,
        subscriber_queue_maxsize: int = _SUBSCRIBER_QUEUE_MAXSIZE,
        replay_buffer_size: int = _REPLAY_BUFFER_SIZE,
    ) -> None:
        if subscriber_queue_maxsize < 2:
            raise ValueError("subscriber_queue_maxsize must be at least 2")
        if replay_buffer_size < 1:
            raise ValueError("replay_buffer_size must be at least 1")
        self._subscriber_queue_maxsize = subscriber_queue_maxsize
        self._replay_buffer_size = replay_buffer_size
        self._subscribers: dict[str, set[_Subscriber]] = defaultdict(set)
        self._subscriber_by_queue: dict[asyncio.Queue, _Subscriber] = {}
        self._replay_buffers: dict[str, deque[ChangeEvent]] = defaultdict(
            lambda: deque(maxlen=self._replay_buffer_size)
        )
        self._next_event_id = 0
        self._lock = threading.Lock()

    def subscribe(self, library_path: str) -> asyncio.Queue:
        """Register a new subscriber queue for ``library_path`` and return it."""
        return self.connect(library_path).queue

    def connect(
        self,
        library_path: str,
        *,
        last_event_id: str | None = None,
    ) -> _Subscription:
        """Register a subscriber and atomically snapshot replay state."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        queue: asyncio.Queue = asyncio.Queue(maxsize=self._subscriber_queue_maxsize)
        subscriber = _Subscriber(queue=queue, loop=loop)
        with self._lock:
            self._subscribers[library_path].add(subscriber)
            self._subscriber_by_queue[queue] = subscriber
            replay_events, resync_event = self._replay_after_locked(
                library_path, last_event_id
            )
        logger.debug(
            "change-hub: +subscriber lib=%s (now %d)",
            library_path,
            self.subscriber_count(library_path),
        )
        return _Subscription(
            queue=queue,
            replay_events=replay_events,
            resync_event=resync_event,
        )

    def unsubscribe(self, library_path: str, queue: asyncio.Queue) -> None:
        """Remove a subscriber queue (on window disconnect)."""
        with self._lock:
            subscriber = self._subscriber_by_queue.pop(queue, None)
            if subscriber is not None:
                subscriber.active = False
            subs = self._subscribers.get(library_path)
            if subs is not None:
                if subscriber is not None:
                    subs.discard(subscriber)
                if not subs:
                    self._subscribers.pop(library_path, None)
        logger.debug("change-hub: -subscriber lib=%s", library_path)

    def emit(self, library_path: str, event: ChangeEvent) -> int:
        """Put ``event`` on every subscriber queue for ``library_path``.

        Returns the number of queues delivered to. Best-effort: a failing
        queue is skipped, never raised.
        """
        with self._lock:
            self._assign_event_id_locked(event)
            self._replay_buffers[library_path].append(event)
            subs = list(self._subscribers.get(library_path, ()))
        delivered = 0
        for subscriber in subs:
            try:
                self._dispatch_to_subscriber(library_path, subscriber, event)
                delivered += 1
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug("change-hub: drop event for one queue: %s", exc)
        return delivered

    def subscriber_count(self, library_path: str) -> int:
        with self._lock:
            return len(self._subscribers.get(library_path, ()))

    def _dispatch_to_subscriber(
        self,
        library_path: str,
        subscriber: _Subscriber,
        event: ChangeEvent,
    ) -> None:
        if subscriber.loop is None:
            self._enqueue_on_loop(library_path, subscriber, event)
            return
        subscriber.loop.call_soon_threadsafe(
            self._enqueue_on_loop, library_path, subscriber, event
        )

    def _enqueue_on_loop(
        self,
        library_path: str,
        subscriber: _Subscriber,
        event: ChangeEvent,
    ) -> None:
        if not subscriber.active:
            return
        try:
            subscriber.queue.put_nowait(event)
            return
        except asyncio.QueueFull:
            dropped_count = self._drop_oldest_for_overflow(
                subscriber.queue, slots_needed=2
            )
            gap_event = self._make_gap_event(
                dropped_count=dropped_count,
                latest_available_event_id=event.event_id,
            )
            try:
                subscriber.queue.put_nowait(gap_event)
                subscriber.queue.put_nowait(event)
                logger.warning(
                    "change-hub: subscriber fell behind lib=%s dropped=%d",
                    library_path,
                    dropped_count,
                )
            except asyncio.QueueFull:  # pragma: no cover - defensive
                logger.debug(
                    "change-hub: overflow recovery failed lib=%s maxsize=%d",
                    library_path,
                    subscriber.queue.maxsize,
                )

    def _drop_oldest_for_overflow(
        self,
        queue: asyncio.Queue,
        *,
        slots_needed: int,
    ) -> int:
        dropped = 0
        while queue.maxsize > 0 and queue.qsize() > queue.maxsize - slots_needed:
            old_event = queue.get_nowait()
            if old_event.type == "stream.gap":
                dropped += max(old_event.dropped_event_count, 1)
            else:
                dropped += 1
        return dropped

    def _replay_after_locked(
        self,
        library_path: str,
        last_event_id: str | None,
    ) -> tuple[list[ChangeEvent], ChangeEvent | None]:
        if last_event_id is None:
            return [], None
        try:
            parsed_id = int(last_event_id)
        except (TypeError, ValueError):
            return [], self._make_resync_event_locked(
                reason="invalid_last_event_id",
                last_event_id=None,
                library_path=library_path,
            )
        if parsed_id < 0:
            return [], self._make_resync_event_locked(
                reason="invalid_last_event_id",
                last_event_id=parsed_id,
                library_path=library_path,
            )
        ring = self._replay_buffers.get(library_path)
        if not ring:
            return [], None
        oldest = ring[0].event_id
        if oldest is not None and parsed_id < oldest:
            return [], self._make_resync_event_locked(
                reason="last_event_id_too_old",
                last_event_id=parsed_id,
                library_path=library_path,
            )
        replay = [event for event in ring if (event.event_id or 0) > parsed_id]
        return replay, None

    def _make_gap_event(
        self,
        *,
        dropped_count: int,
        latest_available_event_id: int | None,
    ) -> ChangeEvent:
        with self._lock:
            return self._assign_event_id_locked(
                ChangeEvent(
                    type="stream.gap",
                    actor="system",
                    replay_required=True,
                    gap_reason="subscriber_overflow",
                    dropped_event_count=dropped_count,
                    latest_available_event_id=latest_available_event_id,
                )
            )

    def _make_resync_event_locked(
        self,
        *,
        reason: str,
        last_event_id: int | None,
        library_path: str,
    ) -> ChangeEvent:
        ring = self._replay_buffers.get(library_path)
        oldest = ring[0].event_id if ring else None
        latest = ring[-1].event_id if ring else None
        return self._assign_event_id_locked(
            ChangeEvent(
                type="stream.resync_required",
                actor="system",
                replay_required=True,
                gap_reason=reason,
                last_event_id=last_event_id,
                oldest_available_event_id=oldest,
                latest_available_event_id=latest,
            )
        )

    def _assign_event_id_locked(self, event: ChangeEvent) -> ChangeEvent:
        self._next_event_id += 1
        event.event_id = self._next_event_id
        return event


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
    interpretation_ids: Iterable[str] = (),
    run_id: str | None = None,
    actor: str = "system",
    origin_window: str | None = None,
    origin_user: str | None = None,
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
            interpretation_ids=list(interpretation_ids),
            run_id=run_id,
            actor=actor,
            origin_window=origin_window,
            origin_user=origin_user,
        )
        _change_hub.emit(library_path, event)
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("emit_change failed (best-effort, ignored): %s", exc)


def emit_request_change(
    request: Request,
    library_path: str,
    *,
    type: str,
    entity_ids: Iterable[str] = (),
    claim_ids: Iterable[str] = (),
    document_ids: Iterable[str] = (),
    artifact_ids: Iterable[str] = (),
    citation_ids: Iterable[str] = (),
    reference_ids: Iterable[str] = (),
    interpretation_ids: Iterable[str] = (),
    run_id: str | None = None,
    origin_window: str | None = None,
) -> None:
    """Emit a user-initiated change with a request-state-derived actor."""
    from fichero.api.auth import actor_from_request  # local: avoid import cycle

    actor = actor_from_request(request)
    emit_change(
        library_path,
        type=type,
        entity_ids=entity_ids,
        claim_ids=claim_ids,
        document_ids=document_ids,
        artifact_ids=artifact_ids,
        citation_ids=citation_ids,
        reference_ids=reference_ids,
        interpretation_ids=interpretation_ids,
        run_id=run_id,
        actor=actor,
        origin_window=origin_window,
        origin_user=actor,
    )
