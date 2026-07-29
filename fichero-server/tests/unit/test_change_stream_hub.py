"""Direct tests for the _ChangeHub SSE fan-out registry (#1979 Test Coverage).

The hub is the process-global change broadcaster behind the live data layer:
monotonic per-library event ids, a bounded replay ring for reconnect catch-up,
resync/gap events when a client falls too far behind, a per-library buffer cap,
and best-effort subscriber-queue overflow recovery. None of these edges had a
direct test.

All tests drive the PUBLIC api (`connect`/`emit`/`subscribe`/`unsubscribe`).
`connect()` called outside an event loop records ``loop=None``, so `emit`
dispatches synchronously via ``put_nowait`` — no async harness needed.
"""

from __future__ import annotations

import pytest

from fichero_server.api.change_stream import ChangeEvent, _ChangeHub

LIB = "/lib/Test.fichero"


def _ev(type_: str = "entity.updated") -> ChangeEvent:
    return ChangeEvent(type=type_)


def _drain(queue) -> list[ChangeEvent]:
    out = []
    while not queue.empty():
        out.append(queue.get_nowait())
    return out


# ---------------------------------------------------------------------------
# Constructor validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs",
    [
        {"subscriber_queue_maxsize": 1},
        {"replay_buffer_size": 0},
        {"replay_library_cap": 0},
    ],
)
def test_constructor_rejects_degenerate_sizes(kwargs) -> None:
    with pytest.raises(ValueError):
        _ChangeHub(**kwargs)


# ---------------------------------------------------------------------------
# Event-id assignment: monotonic, per-library
# ---------------------------------------------------------------------------


def test_event_ids_are_monotonic_per_library() -> None:
    hub = _ChangeHub()
    e1, e2 = _ev(), _ev()
    hub.emit(LIB, e1)
    hub.emit(LIB, e2)
    assert e1.event_id == 1
    assert e2.event_id == 2

    other = _ev()
    hub.emit("/lib/Other.fichero", other)
    assert other.event_id == 1  # independent counter per library


def test_emit_returns_delivered_count() -> None:
    hub = _ChangeHub()
    assert hub.emit(LIB, _ev()) == 0  # no subscribers
    hub.connect(LIB)
    hub.connect(LIB)
    assert hub.emit(LIB, _ev()) == 2


# ---------------------------------------------------------------------------
# Replay ring: catch-up on reconnect
# ---------------------------------------------------------------------------


def test_connect_without_last_event_id_replays_nothing() -> None:
    hub = _ChangeHub()
    hub.emit(LIB, _ev())
    sub = hub.connect(LIB)
    assert sub.replay_events == []
    assert sub.resync_event is None


def test_connect_replays_only_events_after_last_seen() -> None:
    hub = _ChangeHub()
    for _ in range(3):
        hub.emit(LIB, _ev())  # ids 1,2,3
    sub = hub.connect(LIB, last_event_id="1")
    assert [e.event_id for e in sub.replay_events] == [2, 3]
    assert sub.resync_event is None


def test_connect_on_empty_buffer_does_not_resync() -> None:
    hub = _ChangeHub()
    sub = hub.connect(LIB, last_event_id="5")  # never emitted anything
    assert sub.replay_events == []
    assert sub.resync_event is None


# ---------------------------------------------------------------------------
# Resync: invalid / too-old last_event_id
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", ["not-an-int", "-1", "3.5"])
def test_invalid_last_event_id_triggers_resync(bad: str) -> None:
    hub = _ChangeHub()
    hub.emit(LIB, _ev())
    sub = hub.connect(LIB, last_event_id=bad)
    assert sub.replay_events == []
    assert sub.resync_event is not None
    assert sub.resync_event.type == "stream.resync_required"
    assert sub.resync_event.gap_reason == "invalid_last_event_id"
    assert sub.resync_event.event_id is not None  # resync gets its own id


def test_too_old_last_event_id_resyncs_with_window() -> None:
    hub = _ChangeHub(replay_buffer_size=2)
    for _ in range(3):
        hub.emit(LIB, _ev())  # ids 1,2,3; ring keeps only [2,3]
    sub = hub.connect(LIB, last_event_id="1")  # 1 < oldest(2)
    assert sub.replay_events == []
    assert sub.resync_event is not None
    assert sub.resync_event.gap_reason == "last_event_id_too_old"
    assert sub.resync_event.oldest_available_event_id == 2
    assert sub.resync_event.latest_available_event_id == 3


def test_replay_ring_evicts_oldest_beyond_buffer_size() -> None:
    hub = _ChangeHub(replay_buffer_size=2)
    for _ in range(4):
        hub.emit(LIB, _ev())  # ids 1..4; ring keeps [3,4]
    # last_event_id=3 is still in the ring -> clean replay of [4], no resync.
    sub = hub.connect(LIB, last_event_id="3")
    assert [e.event_id for e in sub.replay_events] == [4]
    assert sub.resync_event is None


# ---------------------------------------------------------------------------
# Per-library buffer cap: oldest library evicted, its id counter reset
# ---------------------------------------------------------------------------


def test_library_cap_evicts_oldest_library_and_resets_counter() -> None:
    hub = _ChangeHub(replay_library_cap=2)
    hub.emit("/lib/A.fichero", _ev())  # A id 1
    hub.emit("/lib/B.fichero", _ev())  # B id 1
    hub.emit("/lib/C.fichero", _ev())  # C id 1 -> evicts A (oldest)
    # A's buffer + counter were dropped; emitting to A again restarts ids at 1.
    again = _ev()
    hub.emit("/lib/A.fichero", again)
    assert again.event_id == 1


# ---------------------------------------------------------------------------
# unsubscribe
# ---------------------------------------------------------------------------


def test_unsubscribe_stops_delivery() -> None:
    hub = _ChangeHub()
    queue = hub.subscribe(LIB)
    assert hub.subscriber_count(LIB) == 1
    hub.unsubscribe(LIB, queue)
    assert hub.subscriber_count(LIB) == 0
    assert hub.emit(LIB, _ev()) == 0


# ---------------------------------------------------------------------------
# Subscriber-queue overflow -> gap event (concurrency / backpressure edge)
# ---------------------------------------------------------------------------


def test_slow_subscriber_overflow_inserts_gap_event() -> None:
    hub = _ChangeHub(subscriber_queue_maxsize=2)
    sub = hub.connect(LIB)  # loop=None -> synchronous dispatch
    # Never drain; push past the queue cap to force overflow recovery.
    for _ in range(5):
        hub.emit(LIB, _ev())

    events = _drain(sub.queue)
    gaps = [e for e in events if e.type == "stream.gap"]
    assert gaps, "overflow should inject a stream.gap marker"
    assert gaps[0].replay_required is True
    assert gaps[0].gap_reason == "subscriber_overflow"
    assert gaps[0].dropped_event_count >= 1
    # The most recent real event survives after the gap (latest-wins recovery).
    assert events[-1].type == "entity.updated"
