"""New heavy work waits while this Mac is PAGING NOW under memory pressure, and Kraken reads one page at a time then (#6075,
`activity.throttle.hold-when-swapping`): the owner's engine was killed with the Pro at 15 GB of swap. STATIC swap never holds
(macOS keeps swap it wrote long after the pressure is gone, and a 16 GB Mac sits at warn with swap in use all day: the 2026-09-28
ruling); pageouts or swap GROWING over the last minute, with pressure at warn or above, does."""
from __future__ import annotations

from fichero_server.execution import throttle
from fichero_server.llm import kraken_runtime

GB = 1024**3
MB = 1024**2


def _short(level, paging, free=8 * GB):
    return throttle.memory_short(available_bytes=lambda: free, pressure_level=lambda: level, paging_now=lambda: paging)


def test_paging_now_under_pressure_holds_new_work_and_says_why():
    reason = _short(level=2, paging=True)
    assert reason and "paging to disk right now" in reason


def test_paging_without_pressure_does_not_hold():
    assert _short(level=1, paging=True) is None


def test_pressure_without_paging_does_not_hold():
    assert _short(level=2, paging=False) is None


def test_a_caller_that_supplies_its_own_pressure_reading_is_not_judged_on_the_real_mac(monkeypatch):
    monkeypatch.setattr(throttle, "paging_now_on_this_mac", lambda **_: True)
    assert throttle.memory_short(available_bytes=lambda: 8 * GB, pressure_level=lambda: 2) is None


def _clock():
    throttle._PAGING_SAMPLES.clear()


def test_static_swap_of_15_gb_is_not_paging():
    _clock()
    for t in (0, 10, 20, 30, 40):
        assert not throttle.paging_now_on_this_mac(now=float(t), pageouts=lambda: 5 * GB, swap=lambda: 15 * GB)


def test_growing_swap_is_paging():
    _clock()
    swap = {"v": 15 * GB}
    results = []
    for t in (0, 10, 20, 30):
        swap["v"] += 40 * MB
        results.append(throttle.paging_now_on_this_mac(now=float(t), pageouts=lambda: None, swap=lambda: swap["v"]))
    assert results[-1] is True and results[0] is False


def test_growing_pageouts_is_paging():
    _clock()
    pageouts = {"v": 1 * GB}
    last = False
    for t in (0, 10, 20):
        pageouts["v"] += 50 * MB
        last = throttle.paging_now_on_this_mac(now=float(t), pageouts=lambda: pageouts["v"], swap=lambda: 0)
    assert last is True


def test_growth_older_than_the_window_is_forgotten():
    _clock()
    swap = {"v": 0}
    throttle.paging_now_on_this_mac(now=0.0, pageouts=lambda: None, swap=lambda: swap["v"])
    swap["v"] = 500 * MB
    assert throttle.paging_now_on_this_mac(now=10.0, pageouts=lambda: None, swap=lambda: swap["v"])
    assert not throttle.paging_now_on_this_mac(now=200.0, pageouts=lambda: None, swap=lambda: swap["v"])  # it has stopped growing


def test_the_kraken_guard_refuses_a_page_while_the_mac_is_paging(monkeypatch):
    monkeypatch.setattr(throttle, "paging_now_on_this_mac", lambda **_: True)
    monkeypatch.setattr(kraken_runtime, "_available_memory_bytes", lambda: 8 * GB)
    monkeypatch.setattr(kraken_runtime, "_memory_pressure_level", lambda: 2)
    assert throttle.memory_short(pressure_level=lambda: 2, paging_now=lambda: True) is not None


def test_the_guard_with_injected_readings_ignores_the_real_mac(monkeypatch):
    """## 1095: a test (or caller) that supplies the pressure reading is not judged on the machine's real paging."""
    monkeypatch.setattr(throttle, "paging_now_on_this_mac", lambda **_: True)
    kraken_runtime.assert_memory_available_for_kraken(available_bytes=lambda: 8 * GB, pressure_level=lambda: 2)  # does not raise


def test_pages_at_once_is_one_when_paging_under_pressure_even_for_a_person(monkeypatch):
    monkeypatch.setattr(throttle, "memory_is_busy", lambda: True)
    monkeypatch.setattr(throttle, "paging_now_on_this_mac", lambda **_: True)
    assert kraken_runtime.pages_at_once(True) == 1
