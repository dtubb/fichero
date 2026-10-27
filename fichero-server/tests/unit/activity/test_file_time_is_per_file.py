"""A file's time counts from when it got its slot, not from when the fan-out started (#6178)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fichero_server.execution.runner import file_duration_ms

T0 = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)


def test_a_file_that_waited_is_timed_from_its_slot():
    entry = {"started_at": T0.isoformat(), "running_at": (T0 + timedelta(seconds=6500)).isoformat()}
    assert file_duration_ms(entry, T0 + timedelta(seconds=6525)) == 25_000


def test_a_file_with_no_slot_event_is_timed_from_its_start():
    assert file_duration_ms({"started_at": T0.isoformat()}, T0 + timedelta(seconds=3)) == 3_000


def test_a_rehydrated_run_keeps_each_files_own_time():
    """The run record is rebuilt from the progress events: a file that waited for its slot is timed from file_running."""
    from fichero_server.workflows.activity_store import _hydrate_progress_steps

    def ev(kind, secs):
        return {"event": kind, "timestamp": (T0 + timedelta(seconds=secs)).isoformat(), "node_id": "n", "file_path": "a.png"}

    steps = _hydrate_progress_steps([ev("file_start", 0), ev("file_running", 6500), ev("file_complete", 6525)])
    assert steps[0]["duration_ms"] == 25_000
