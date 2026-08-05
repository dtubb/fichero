"""A live workflow SSE stream must not block uvicorn's shutdown drain.

The workflow SSE generator is ``while True`` around a blocking
``subscriber.get(timeout=60)``: it emits keepalives forever and never ends on
its own, because a run's stream is long-lived by design. uvicorn's graceful
shutdown waits for open connections to close, so one live subscriber blocked
the drain indefinitely, and the app SIGKILLed the engine after its 2-second
SIGTERM grace. Twelve engine spawns in one session, each preceded by::

    INFO:     Shutting down
    INFO:     Waiting for connections to close. (CTRL+C to force quit)

Every kill orphaned an in-flight run with no terminal event, leaving the zombie
``workflow_runs`` rows that #4554's recovery then failed to clean.
"""
from __future__ import annotations

import queue

import pytest

from fichero_server.execution import runner
from fichero_server.execution.runner import (
    WorkflowEventHub,
    close_all_event_hubs_for_shutdown,
)


@pytest.fixture(autouse=True)
def _isolated_registry(monkeypatch):
    """Swap the module-level registry so these tests never see, or leak into,
    another test's runs. Must go through the MODULE — binding the dict by
    import captures the old object and the monkeypatch would not be seen."""
    monkeypatch.setattr(runner, "_running_workflows", {})


def _live_run(thread_id: str) -> tuple[WorkflowEventHub, "queue.Queue"]:
    hub = WorkflowEventHub()
    subscriber = hub.subscribe()
    runner._running_workflows[thread_id] = {"events": hub}
    return hub, subscriber


def test_shutdown_ends_every_live_stream():
    """RED before the fix: nothing closed the hubs, so each subscriber sat on
    its blocking get and the generator never returned."""
    hub_a, sub_a = _live_run("thread-a")
    hub_b, sub_b = _live_run("thread-b")

    closed = close_all_event_hubs_for_shutdown()

    assert closed == 2
    # `None` is the generator's existing end-of-stream sentinel: its
    # `if event is None: break` fires and the response completes.
    assert sub_a.get(timeout=1) is None
    assert sub_b.get(timeout=1) is None
    assert hub_a.is_closed()
    assert hub_b.is_closed()


def test_a_stream_that_already_ended_is_not_closed_twice():
    hub, subscriber = _live_run("thread-done")
    hub.put(None)
    assert subscriber.get(timeout=1) is None

    assert close_all_event_hubs_for_shutdown() == 0, (
        "a finished run has nothing to close; counting it would misreport how "
        "many live streams the shutdown had to interrupt"
    )


def test_shutdown_with_no_live_runs_is_a_no_op():
    assert close_all_event_hubs_for_shutdown() == 0


def test_events_already_buffered_still_reach_a_late_subscriber():
    """Closing on shutdown must not destroy the replay buffer — a client that
    reconnects still needs to see what it missed before reconciling."""
    hub, _ = _live_run("thread-replay")
    hub.put("node_begin")

    close_all_event_hubs_for_shutdown()

    late = hub.subscribe()
    assert late.get(timeout=1) == "node_begin"
    assert late.get(timeout=1) is None
