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
