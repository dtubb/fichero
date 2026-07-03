"""Tests for WorkflowEventHub — the SSE fan-out hub (#2546).

Root cause of #2546 (deep half): a RUNNING workflow viewed in Activity showed
0%% progress and an empty live log because ``state["events"]`` was a single
``queue.Queue`` drained with a destructive ``.get()``. That made the live SSE
stream **single-consumer**:

- A *second* concurrent subscriber (the Workflow editor that launched the run
  AND the Activity panel watching it) was starved — its events were stolen by
  whichever consumer drained first.
- A *late* subscriber (one that connected after the producer had pushed events
  another consumer already drained) received nothing.

``WorkflowEventHub`` fixes this: every subscriber gets its OWN queue and
receives EVERY event, with a bounded replay buffer so late subscribers catch
up. These tests lock that contract in.
"""

import queue

import pytest

from fichero.api.routes.workflow_execution.runner import WorkflowEventHub
from fichero.api.routes.workflow_execution.schemas import SSEEvent


def _evt(name: str, **data) -> SSEEvent:
    return SSEEvent(
        event=name,
        thread_id="thread-test",
        workflow_id="wf-test",
        data=data,
    )


def _drain(sub: "queue.Queue", *, stop_on_sentinel: bool = True) -> list:
    """Drain everything currently buffered in a subscriber queue."""
    out = []
    while True:
        try:
            item = sub.get_nowait()
        except queue.Empty:
            break
        if item is None and stop_on_sentinel:
            out.append(None)
            break
        out.append(item)
    return out


class TestFanOut:
    def test_two_subscribers_both_receive_all_events(self):
        """Fan-out: TWO subscribers to the same thread BOTH get every event.

        This is the editor + Activity case that was starved before the fix.
        """
        hub = WorkflowEventHub()
        a = hub.subscribe()
        b = hub.subscribe()

        e1 = _evt("start")
        e2 = _evt("node_begin", node="x")
        e3 = _evt("file_start", file_index=1, file_total=3)
        for e in (e1, e2, e3):
            hub.put(e)

        assert _drain(a) == [e1, e2, e3]
        assert _drain(b) == [e1, e2, e3]

    def test_sentinel_broadcast_to_all_active_subscribers(self):
        hub = WorkflowEventHub()
        a = hub.subscribe()
        b = hub.subscribe()

        done = _evt("complete")
        hub.put(done)
        hub.put(None)  # end-of-stream sentinel

        assert _drain(a) == [done, None]
        assert _drain(b) == [done, None]


class TestLateSubscriber:
    def test_late_subscriber_receives_subsequent_events(self):
        """A subscriber that connects AFTER events were produced still gets
        every subsequent event (and catches up on the buffered ones)."""
        hub = WorkflowEventHub()

        early = _evt("start")
        hub.put(early)  # produced before anyone subscribed

        late = hub.subscribe()  # connect late
        later = _evt("node_begin", node="y")
        hub.put(later)

        drained = _drain(late)
        # Replay of the missed event, then the subsequent one.
        assert drained == [early, later]

    def test_late_subscriber_catches_up_via_replay_buffer(self):
        hub = WorkflowEventHub()
        produced = [_evt("e", i=i) for i in range(5)]
        for e in produced:
            hub.put(e)

        late = hub.subscribe()
        assert _drain(late) == produced

    def test_subscribe_after_close_gets_replay_then_sentinel(self):
        """If the run already finished, a subscriber that connects afterward
        still gets the full replay followed by the sentinel so its generator
        terminates cleanly (no hang, no empty stream)."""
        hub = WorkflowEventHub()
        start, done = _evt("start"), _evt("complete")
        hub.put(start)
        hub.put(done)
        hub.put(None)  # closed

        sub = hub.subscribe()
        assert _drain(sub) == [start, done, None]


class TestParallelFileEvents:
    def test_file_start_complete_enqueued_and_fanned_out(self):
        """Under enable_parallel=True the runner forwards builder file_start /
        file_complete callbacks to ``hub.put`` (see runner.emit_parallel_event
        + builder._make_parallel_node_function). This asserts those event
        types are enqueued AND reach a late + second subscriber — the path the
        live progress bar depends on. (The builder's actual emission is covered
        by the parallel-checkpointer suite.)"""
        hub = WorkflowEventHub()

        first = hub.subscribe()
        hub.put(_evt("file_start", node_id="cat", file_index=1, file_total=2))

        # Activity connects late, mid-run.
        late = hub.subscribe()
        hub.put(_evt("file_complete", node_id="cat", file_index=1, file_total=2))
        hub.put(_evt("file_start", node_id="cat", file_index=2, file_total=2))
        hub.put(_evt("file_complete", node_id="cat", file_index=2, file_total=2))

        first_events = [e for e in _drain(first) if e is not None]
        late_events = [e for e in _drain(late) if e is not None]

        # Both subscribers see all four file events (late one via replay+live).
        assert [e.event for e in first_events] == [
            "file_start",
            "file_complete",
            "file_start",
            "file_complete",
        ]
        assert [e.event for e in late_events] == [
            "file_start",
            "file_complete",
            "file_start",
            "file_complete",
        ]


class TestReplayBufferBound:
    def test_replay_buffer_is_bounded(self):
        """Thousands-of-files runs must not grow the replay buffer without
        bound; the buffer keeps only the most recent window."""
        hub = WorkflowEventHub(replay_limit=10)
        for i in range(100):
            hub.put(_evt("e", i=i))

        late = hub.subscribe()
        drained = [e for e in _drain(late) if e is not None]
        assert len(drained) == 10
        # Keeps the MOST RECENT events.
        assert [e.data["i"] for e in drained] == list(range(90, 100))


class TestUnsubscribe:
    def test_unsubscribe_stops_feeding(self):
        hub = WorkflowEventHub()
        a = hub.subscribe()
        b = hub.subscribe()
        hub.unsubscribe(a)

        start = _evt("start")
        hub.put(start)

        assert _drain(a) == []  # no longer fed
        assert _drain(b) == [start]

    def test_unsubscribe_unknown_queue_is_noop(self):
        hub = WorkflowEventHub()
        stray: "queue.Queue" = queue.Queue()
        # Must not raise even though `stray` was never subscribed.
        hub.unsubscribe(stray)
        assert stray.empty()


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
