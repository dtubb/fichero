"""Unit contract for the canonical UTC clock (#4347)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from fichero_server.core.timeutil import ensure_utc, naive_utc, utc_now, utc_now_iso


def test_utc_now_is_timezone_aware_utc() -> None:
    now = utc_now()
    assert now.tzinfo is not None
    assert now.utcoffset() == timedelta(0)


def test_utc_now_tracks_real_time() -> None:
    # Guards against a stub that returns a fixed instant: the aware value must
    # be within a minute of the system clock's own UTC reading.
    delta = abs(utc_now() - datetime.now(timezone.utc))
    assert delta < timedelta(minutes=1)


def test_utc_now_iso_carries_an_offset() -> None:
    text = utc_now_iso()
    assert text.endswith("+00:00")
    assert datetime.fromisoformat(text).tzinfo is not None


def test_utc_now_iso_honours_timespec() -> None:
    text = utc_now_iso(timespec="seconds")
    # "YYYY-MM-DDTHH:MM:SS+00:00" — no fractional seconds.
    assert "." not in text
    assert text.endswith("+00:00")


def test_ensure_utc_treats_naive_as_utc_without_shifting_the_clock() -> None:
    naive = datetime(2026, 7, 30, 12, 30, 45, 123456)
    aware = ensure_utc(naive)
    assert aware.tzinfo == timezone.utc
    # Same wall clock — a naive stored value IS UTC, it is not re-interpreted.
    assert aware.replace(tzinfo=None) == naive


def test_ensure_utc_converts_a_non_utc_offset_to_the_same_instant() -> None:
    adt = timezone(timedelta(hours=-3))
    aware = ensure_utc(datetime(2026, 7, 30, 9, 0, tzinfo=adt))
    assert aware == datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)
    assert aware.utcoffset() == timedelta(0)


def test_ensure_utc_is_idempotent() -> None:
    once = ensure_utc(datetime(2026, 1, 2, 3, 4))
    assert ensure_utc(once) == once
    assert ensure_utc(ensure_utc(once)) == once


def test_ensure_utc_passes_none_through() -> None:
    assert ensure_utc(None) is None


def test_ensure_utc_raises_on_a_non_datetime() -> None:
    # Prefer raising over silently yielding a plausible-looking instant.
    with pytest.raises(TypeError):
        ensure_utc("2026-07-30T12:00:00")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        ensure_utc(1_753_000_000)  # type: ignore[arg-type]


def test_naive_utc_strips_the_offset_but_keeps_the_utc_wall_clock() -> None:
    adt = timezone(timedelta(hours=-3))
    stripped = naive_utc(datetime(2026, 7, 30, 9, 0, tzinfo=adt))
    assert stripped == datetime(2026, 7, 30, 12, 0)
    assert stripped.tzinfo is None


def test_naive_utc_defaults_to_now() -> None:
    stripped = naive_utc()
    assert stripped.tzinfo is None
    assert abs(stripped - datetime.now(timezone.utc).replace(tzinfo=None)) < timedelta(
        minutes=1
    )


def test_ensure_utc_and_naive_utc_round_trip() -> None:
    original = utc_now()
    assert ensure_utc(naive_utc(original)) == original
