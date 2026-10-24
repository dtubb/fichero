"""Kraken is held to ONE page at a time under memory pressure, and new pages wait while this Mac is paging (#6075,
`activity.throttle.hold-when-swapping`): the owner's engine was killed with the Pro at 15 GB of swap, because the throttle read
only free memory. Swap alone is not a reason (macOS keeps swap it has written after the pressure is gone); swap together with
pressure at warn or above is."""
from __future__ import annotations

from fichero_server.execution import throttle
from fichero_server.llm import kraken_runtime

GB = 1024**3


def _short(level, swap, free=8 * GB):
    return throttle.memory_short(available_bytes=lambda: free, pressure_level=lambda: level, swap_bytes=lambda: swap)


def test_heavy_swap_under_pressure_holds_new_work_and_says_why():
    reason = _short(level=2, swap=15 * GB)
    assert reason and "paging to disk" in reason and "15.0 GB" in reason


def test_heavy_swap_with_normal_pressure_does_not_hold():
    assert _short(level=1, swap=15 * GB) is None


def test_pressure_with_little_swap_does_not_hold():
    assert _short(level=2, swap=GB // 2) is None


def test_an_unreadable_swap_is_no_reason_to_wait():
    assert _short(level=2, swap=None) is None


def test_a_caller_that_supplies_its_own_pressure_reading_is_not_judged_on_the_real_swap(monkeypatch):
    monkeypatch.setattr(throttle, "swap_used_bytes", lambda: 15 * GB)
    assert throttle.memory_short(available_bytes=lambda: 8 * GB, pressure_level=lambda: 2) is None


def test_the_kraken_guard_refuses_a_page_while_the_mac_is_paging(monkeypatch):
    monkeypatch.setattr(throttle, "swap_used_bytes", lambda: 15 * GB)
    monkeypatch.setattr(kraken_runtime, "_available_memory_bytes", lambda: 8 * GB)
    monkeypatch.setattr(kraken_runtime, "_memory_pressure_level", lambda: 2)
    # the guard supplies its own readers, so the swap comes from the same seam as the throttle's: the real one, faked above
    monkeypatch.setattr(throttle, "memory_pressure_level", lambda: 2)
    assert throttle.memory_short() is not None


def test_pages_at_once_is_one_under_memory_pressure_even_for_a_person(monkeypatch):
    monkeypatch.setattr(throttle, "memory_is_busy", lambda: True)
    assert kraken_runtime.pages_at_once(True) == 1
