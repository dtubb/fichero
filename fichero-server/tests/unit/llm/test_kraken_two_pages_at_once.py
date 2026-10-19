"""Two pages at once for a person-started run (`source.read.two-pages-at-once`, speed round 2): the gate, the
per-thread page notes, the load lock and the idle release."""
from __future__ import annotations

import threading
import time

import pytest

from fichero_server.llm import kraken_runtime as kr

GIB = 1024**3


def _in_threads(n, target):
    threads = [threading.Thread(target=target, args=(i,)) for i in range(n)]
    [t.start() for t in threads]
    return threads


def test_a_two_slot_gate_holds_two_pages_and_makes_the_third_wait():
    gate = kr._PageGate()
    inside, peak, lock = [0], [0], threading.Lock()

    def page(_i):
        with gate.page(2):
            with lock:
                inside[0] += 1
                peak[0] = max(peak[0], inside[0])
            time.sleep(0.05)
            with lock:
                inside[0] -= 1

    [t.join() for t in _in_threads(5, page)]
    assert peak[0] == 2


def test_one_slot_is_one_page_at_a_time():
    gate = kr._PageGate()
    inside, peak, lock = [0], [0], threading.Lock()

    def page(_i):
        with gate.page(1):
            with lock:
                inside[0] += 1
                peak[0] = max(peak[0], inside[0])
            time.sleep(0.03)
            with lock:
                inside[0] -= 1

    [t.join() for t in _in_threads(4, page)]
    assert peak[0] == 1


def test_taking_the_gate_whole_waits_for_the_running_pages_and_locked_means_a_page_runs():
    gate = kr._PageGate()
    release = threading.Event()
    started = threading.Event()

    def page(_i):
        with gate.page(2):
            started.set()
            release.wait(2)

    t = _in_threads(1, page)[0]
    started.wait(2)
    assert gate.locked() and not gate.acquire(blocking=False)
    got = []
    waiter = threading.Thread(target=lambda: (gate.acquire(), got.append(True), gate.release()))
    waiter.start()
    time.sleep(0.05)
    assert not got, "whole waits while a page runs"
    release.set()
    t.join()
    waiter.join(2)
    assert got and not gate.locked()


def test_a_page_cannot_start_while_the_gate_is_held_whole():
    gate = kr._PageGate()
    gate.acquire()
    entered = []
    t = threading.Thread(target=lambda: (gate.page(2).__enter__(), entered.append(True)))
    t.start()
    time.sleep(0.05)
    assert not entered
    gate.release()
    t.join(2)
    assert entered


def test_the_page_notes_are_each_threads_own():
    seen = {}

    def note(i):
        kr._PAGE.clear()
        kr._PAGE["name"] = f"page-{i}"
        time.sleep(0.03)
        seen[i] = kr._PAGE.get("name")

    [t.join() for t in _in_threads(2, note)]
    assert seen == {0: "page-0", 1: "page-1"}


def test_a_model_asked_for_by_two_pages_at_the_same_moment_loads_once(monkeypatch):
    kr._RESIDENT.clear()
    loads = []

    def slow_load():
        loads.append(1)
        time.sleep(0.05)
        return object()

    [t.join() for t in _in_threads(2, lambda _i: kr._resident("read", "reader-a", slow_load))]
    assert len(loads) == 1
    kr._RESIDENT.clear()


def test_the_idle_release_never_frees_a_model_while_a_page_runs():
    kr._RESIDENT.clear()
    kr._RESIDENT["read"] = ("reader-a", object())
    inside, release = threading.Event(), threading.Event()

    def page(_i):
        with kr._INFERENCE_LOCK.page(2):
            inside.set()
            release.wait(2)

    t = _in_threads(1, page)[0]
    inside.wait(2)
    kr._release_if_idle()
    assert "read" in kr._RESIDENT, "a page is running: nothing is let go"
    release.set()
    t.join()
    kr._release_if_idle()
    assert "read" not in kr._RESIDENT


@pytest.mark.parametrize("priority, memory_gib, expected", [
    ("fast", 12, 2), ("fast", 3, 1), ("balanced", 12, 1), ("background", 12, 1)])
def test_only_a_fast_run_with_room_for_two_reads_two_pages(monkeypatch, priority, memory_gib, expected):
    from fichero_server.core import compute_preferences

    monkeypatch.setattr(compute_preferences, "priority_for", lambda person: priority)
    monkeypatch.setattr(kr, "_available_memory_bytes", lambda: memory_gib * GIB)
    monkeypatch.setattr(kr.os, "cpu_count", lambda: 10)
    assert kr.pages_at_once(person=True) == expected


def test_a_small_mac_reads_one_page_whatever_the_priority(monkeypatch):
    from fichero_server.core import compute_preferences

    monkeypatch.setattr(compute_preferences, "priority_for", lambda person: "fast")
    monkeypatch.setattr(kr, "_available_memory_bytes", lambda: 4 * GIB)  # an 8 GB Mac with the system's share used
    monkeypatch.setattr(kr.os, "cpu_count", lambda: 8)
    assert kr.pages_at_once(person=True) == 1
