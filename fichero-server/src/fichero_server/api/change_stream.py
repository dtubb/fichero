"""Per-library change-stream hub (#1863).

The foundation of the observable data layer: an in-process fan-out that lets
mutating routes broadcast ``ChangeEvent``s to every connected app window for a
given library. This is the backend half of the spec in
``docs/contributor_manual/architecture/fichero/observable_data_layer.md``.

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
import os
import threading
import weakref
from functools import lru_cache
from collections import OrderedDict, defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_SUBSCRIBER_QUEUE_MAXSIZE = 1000
_REPLAY_BUFFER_SIZE = 1000
_REPLAY_LIBRARY_CAP = 1024
_sse_shutdown_events: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()

#: Every typed id-list a `ChangeEvent` carries, in declaration order. THE ONE
#: place a new kind is added (source-model slice 2, #4920): `ChangeEvent`,
#: `emit_change`, `ActionRegistry._emit` (`actions/registry.py`) and the
#: activity fold (`api/routes/system/activity.py::_change_event_to_activity_response`)
#: all iterate this tuple instead of each naming its own hand-written list —
#: the four-site silent-omission risk this closes is written up in
#: `agent-work/source-model/recon-slice-2.md`.
CHANGE_ID_LISTS: tuple[str, ...] = (
    "entity_ids",
    "claim_ids",
    "document_ids",
    "artifact_ids",
    "citation_ids",
    "reference_ids",
    "interpretation_ids",
    "segment_ids",
    "pass_ids",
)


def _dedupe_keep_order(values: Iterable[str]) -> list[str]:
    """First occurrence wins, never sorted (ruled 2026-09-20, source-model
    slice 2): a store that patches items in place gains nothing from a
    duplicate, and the order things changed in can carry meaning."""
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out


def sse_shutdown_event() -> asyncio.Event:
    """Return this event loop's SSE shutdown signal."""
    loop = asyncio.get_running_loop()
    event = _sse_shutdown_events.get(loop)
    if event is None:
        event = asyncio.Event()
        _sse_shutdown_events[loop] = event
    return event


def signal_sse_shutdown() -> None:
    """Wake SSE generators so uvicorn can drain connections on shutdown."""
    for event in _sse_shutdown_events.values():
        event.set()


def reset_sse_shutdown() -> None:
    """Reopen SSE streams for a newly started lifespan."""
    sse_shutdown_event().clear()


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
    #: Source-model slice 2 (#4920). Nothing emits these yet -- no segment
    #: action exists until slice 4 -- so every event today carries `[]` for
    #: both. Added now so `CHANGE_ID_LISTS` is complete from the start.
    segment_ids: list[str] = Field(default_factory=list)
    pass_ids: list[str] = Field(default_factory=list)
    run_id: str | None = None
    actor: str = "system"  # ui | chat | workflow | import | system
    document_parents: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Map of document id -> parent document id, for the ids in "
            "`document_ids`. Lets a client decide whether it cares about a "
            "document WITHOUT fetching it first (#4205): during a 100k-file "
            "import, only documents that are roots, in the selected "
            "collection, or under an already-loaded parent need fetching. "
            "A per-id map rather than a single parent field because "
            "`document_ids` is a list whose entries can have different "
            "parents. "
            "AN ID ABSENT FROM THIS MAP MEANS 'PARENT UNKNOWN — FETCH IT'. It "
            "NEVER means 'this is a root'. Treating absence as root files "
            "imported documents at the top level, which is the bug this exists "
            "to prevent, so a partial map is safe by construction and an "
            "emitter that cannot supply a parent simply omits the entry."
        ),
    )
    metadata: dict[str, str] = Field(default_factory=dict)
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
        replay_library_cap: int = _REPLAY_LIBRARY_CAP,
    ) -> None:
        if subscriber_queue_maxsize < 2:
            raise ValueError("subscriber_queue_maxsize must be at least 2")
        if replay_buffer_size < 1:
            raise ValueError("replay_buffer_size must be at least 1")
        if replay_library_cap < 1:
            raise ValueError("replay_library_cap must be at least 1")
        self._subscriber_queue_maxsize = subscriber_queue_maxsize
        self._replay_buffer_size = replay_buffer_size
        self._replay_library_cap = replay_library_cap
        self._subscribers: dict[str, set[_Subscriber]] = defaultdict(set)
        self._subscriber_by_queue: dict[asyncio.Queue, _Subscriber] = {}
        self._replay_buffers: OrderedDict[str, deque[ChangeEvent]] = OrderedDict()
        self._next_event_ids: dict[str, int] = {}
        self._lock = threading.Lock()

    @staticmethod
    @lru_cache(maxsize=512)
    def _canonical_key(library_path: str) -> str:
        """The canonical hub key form. BOTH seams — subscriber register
        (``connect``/``unsubscribe``) and publish (``emit``) — MUST funnel through
        this so a raw header (``/lib/Foo.fichero/``) and a path-derived emit key
        (``str(db.path.parent)`` → ``/lib/Foo.fichero``) map to the SAME subscriber
        set (#2518). ``Path()`` strips trailing slashes and redundant separators.

        Symlinks ARE resolved now (``os.path.realpath``): the #2518 follow-up's
        proof arrived on 2026-08-25 — Daniel's create-library log showed the
        SAME package opened under ``/private/var/…`` and ``/var/…`` spellings,
        emitting to zero subscribers. ``realpath`` (not ``Path.resolve``)
        resolves the symlinked prefix without requiring the leaf to exist, and
        the ``lru_cache`` keeps the per-emit filesystem walk off the hot path.
        """
        return os.path.realpath(library_path) if library_path else library_path

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
        library_path = self._canonical_key(library_path)
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
        library_path = self._canonical_key(library_path)
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
        library_path = self._canonical_key(library_path)
        with self._lock:
            self._assign_event_id_locked(library_path, event)
            self._replay_buffer_locked(library_path).append(event)
            subs = list(self._subscribers.get(library_path, ()))
            # Snapshot other live keys so a delivered=0 emit can name them — a
            # loud signal of key drift instead of a silent drop (#2518).
            other_live_keys = (
                [k for k, s in self._subscribers.items() if s and k != library_path]
                if not subs
                else []
            )
        delivered = 0
        for subscriber in subs:
            try:
                self._dispatch_to_subscriber(library_path, subscriber, event)
                delivered += 1
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug("change-hub: drop event for one queue: %s", exc)
        if delivered == 0 and other_live_keys:
            # Emitted into the void while OTHER libraries have subscribers — the
            # emit key and a subscribe key have drifted apart. No-silent-fallback:
            # make it a WARNING with both sides so the drift is debuggable.
            logger.warning(
                "change-hub: %s emit to key %r reached 0 subscribers, but "
                "%d subscriber(s) are live under different key(s): %r — "
                "library_path key drift? (#2518)",
                event.type,
                library_path,
                len(other_live_keys),
                other_live_keys,
            )
        return delivered

    def subscriber_count(self, library_path: str) -> int:
        library_path = self._canonical_key(library_path)
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
        self._replay_buffers.move_to_end(library_path)
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
        return ChangeEvent(
            type="stream.gap",
            actor="system",
            replay_required=True,
            gap_reason="subscriber_overflow",
            dropped_event_count=dropped_count,
            latest_available_event_id=latest_available_event_id,
        )

    def _make_resync_event_locked(
        self,
        *,
        reason: str,
        last_event_id: int | None,
        library_path: str,
    ) -> ChangeEvent:
        ring = self._replay_buffers.get(library_path)
        if ring:
            self._replay_buffers.move_to_end(library_path)
        oldest = ring[0].event_id if ring else None
        latest = ring[-1].event_id if ring else None
        return self._assign_event_id_locked(
            library_path,
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

    def _assign_event_id_locked(
        self, library_path: str, event: ChangeEvent
    ) -> ChangeEvent:
        next_event_id = self._next_event_ids.get(library_path, 0) + 1
        self._next_event_ids[library_path] = next_event_id
        event.event_id = next_event_id
        return event

    def _replay_buffer_locked(self, library_path: str) -> deque[ChangeEvent]:
        ring = self._replay_buffers.get(library_path)
        if ring is None:
            ring = deque(maxlen=self._replay_buffer_size)
            self._replay_buffers[library_path] = ring
        else:
            self._replay_buffers.move_to_end(library_path)
        self._enforce_replay_library_cap_locked()
        return ring

    def _enforce_replay_library_cap_locked(self) -> None:
        while len(self._replay_buffers) > self._replay_library_cap:
            library_path, _ring = self._replay_buffers.popitem(last=False)
            self._next_event_ids.pop(library_path, None)


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
    segment_ids: Iterable[str] = (),
    pass_ids: Iterable[str] = (),
    run_id: str | None = None,
    actor: str = "system",
    metadata: dict[str, str] | None = None,
    origin_window: str | None = None,
    origin_user: str | None = None,
    document_parents: dict[str, str] | None = None,
) -> None:
    """Broadcast a change to every window subscribed to ``library_path``.

    Best-effort: never raises. Call at the end of a mutating route so a failure
    here can never roll back or break the mutation itself.

    Every id list named in `CHANGE_ID_LISTS` is de-duplicated, keeping the
    order it was given (first occurrence wins) -- never sorted (source-model
    slice 2, #4920).
    """
    if not library_path:
        return
    try:
        given = {
            "entity_ids": entity_ids,
            "claim_ids": claim_ids,
            "document_ids": document_ids,
            "artifact_ids": artifact_ids,
            "citation_ids": citation_ids,
            "reference_ids": reference_ids,
            "interpretation_ids": interpretation_ids,
            "segment_ids": segment_ids,
            "pass_ids": pass_ids,
        }
        deduped = {name: _dedupe_keep_order(given[name]) for name in CHANGE_ID_LISTS}
        event = ChangeEvent(
            type=type,
            run_id=run_id,
            actor=actor,
            metadata=dict(metadata or {}),
            origin_window=origin_window,
            origin_user=origin_user,
            document_parents=dict(document_parents or {}),
            **deduped,
        )
        _change_hub.emit(library_path, event)
    except Exception as exc:  # pragma: no cover - defensive
        # warning, not debug: a mismatch between CHANGE_ID_LISTS and `given`
        # (or ChangeEvent's fields) raises HERE and silently stops EVERY
        # change event -- the exact silent failure the project forbids. A
        # test pins the alignment directly (test_change_stream_segment_ids.py)
        # so this branch should never fire in practice; if it does, it must
        # be loud.
        logger.warning("emit_change failed (best-effort, ignored): %s", exc)


def emit_change_all_libraries(
    *,
    type: str,
    actor: str = "system",
    metadata: dict[str, str] | None = None,
) -> int:
    """Broadcast an APP-SCOPED change to every library's subscribers (#4276).

    Providers (and their API keys / model lists) are app-wide, not per-library
    — but the change stream is keyed by library. A provider mutation therefore
    fans one event out to EVERY live subscriber key so each window can drop
    its provider-derived caches (the Run Workflow submenu's provider list).
    Each library gets its own ChangeEvent copy so per-library event-id /
    replay bookkeeping stays consistent. Best-effort: never raises. Returns
    the number of libraries reached.
    """
    reached = 0
    try:
        with _change_hub._lock:
            keys = [k for k, subs in _change_hub._subscribers.items() if subs]
        for key in keys:
            event = ChangeEvent(type=type, actor=actor, metadata=dict(metadata or {}))
            _change_hub.emit(key, event)
            reached += 1
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("emit_change_all_libraries failed (best-effort): %s", exc)
    return reached


