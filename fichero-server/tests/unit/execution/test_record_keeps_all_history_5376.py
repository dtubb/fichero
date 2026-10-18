"""A long run's saved record keeps every step and page event from the start (#5376,
`activity.run.record-keeps-all-history`): the replay window holds the newest events for a late viewer, the record keeps
all but the log lines, in order, so a 200-page run does not lose its early history."""
from types import SimpleNamespace

from fichero_server.execution.runner import WorkflowEventHub, _workflow_event_timeline


class _Event(SimpleNamespace):
    def model_dump(self, mode="json"):
        return {"event": self.event, "n": self.n}


def _fill(hub, pages):
    n = 0
    for _ in range(pages):
        for kind in ("file_start", "log", "log", "log", "file_complete"):
            n += 1
            hub.put(_Event(event=kind, n=n))


def test_the_saved_timeline_keeps_the_early_pages_past_the_replay_window():
    hub = WorkflowEventHub(replay_limit=20)
    _fill(hub, 200)
    timeline = _workflow_event_timeline(hub)
    starts = [e["n"] for e in timeline if e["event"] == "file_start"]
    assert len(starts) == 200 and starts[0] == 1  # page 1's start survives


def test_the_record_is_in_order_and_holds_only_the_recent_log_lines():
    hub = WorkflowEventHub(replay_limit=20)
    _fill(hub, 200)
    timeline = _workflow_event_timeline(hub)
    assert [e["n"] for e in timeline] == sorted(e["n"] for e in timeline)
    assert len([e for e in timeline if e["event"] == "log"]) <= 20


def test_a_late_viewer_still_replays_only_the_window():
    hub = WorkflowEventHub(replay_limit=20)
    _fill(hub, 200)
    assert len(hub.snapshot()) == 20
