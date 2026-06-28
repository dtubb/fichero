"""Direct tests for scheduler.py timezone helpers (#1987 Test Coverage).

`_ensure_aware_utc` normalizes stored/naive datetimes before schedule
comparisons; a wrong tz here silently fires schedules early/late. `_utcnow`
must be tz-aware so comparisons never raise naive-vs-aware TypeErrors.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fichero.workflows.scheduler import _ensure_aware_utc, _utcnow


def test_utcnow_is_timezone_aware_utc() -> None:
    now = _utcnow()
    assert now.tzinfo is not None
    assert now.utcoffset() == timedelta(0)


def test_ensure_aware_utc_none_passthrough() -> None:
    assert _ensure_aware_utc(None) is None


def test_ensure_aware_utc_tags_naive_as_utc_same_wall_clock() -> None:
    naive = datetime(2026, 6, 28, 9, 0, 0)
    out = _ensure_aware_utc(naive)
    assert out.tzinfo == timezone.utc
    assert (out.year, out.hour, out.minute) == (2026, 9, 0)  # wall clock preserved


def test_ensure_aware_utc_already_utc_is_equivalent() -> None:
    aware = datetime(2026, 6, 28, 9, 0, 0, tzinfo=timezone.utc)
    out = _ensure_aware_utc(aware)
    assert out == aware
    assert out.utcoffset() == timedelta(0)


def test_ensure_aware_utc_converts_other_offset_to_utc() -> None:
    # 09:00 at +02:00 is 07:00 UTC — the instant must be preserved, not the wall clock.
    plus_two = datetime(2026, 6, 28, 9, 0, 0, tzinfo=timezone(timedelta(hours=2)))
    out = _ensure_aware_utc(plus_two)
    assert out.utcoffset() == timedelta(0)
    assert out.hour == 7
    assert out == plus_two  # same instant
