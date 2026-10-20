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


def _sysctl(monkeypatch, **values):
    """A Mac's hw.* values, by name (a name not given does not exist there, as on an Intel Mac)."""
    monkeypatch.setattr(kr, "_sysctl_int", lambda name: values.get(name))


@pytest.mark.parametrize("sysctl, expected", [
    ({"hw.perflevel0.physicalcpu": 4, "hw.physicalcpu": 8}, 4),     # an M1/M4 Air or an M1 Pro-class laptop
    ({"hw.perflevel0.physicalcpu": 10, "hw.physicalcpu": 14}, 10),  # a Pro with ten performance cores
    ({"hw.physicalcpu": 8}, 4),                                      # Intel: no performance levels, half the physical cores
    ({"hw.physicalcpu": 2}, 1),
    ({"hw.perflevel0.physicalcpu": 0, "hw.physicalcpu": 6}, 3),      # a level that reads zero is no level
    ({}, max(1, (kr.os.cpu_count() or 2) // 2)),                     # nothing readable: half the logical cores
    ({"hw.perflevel0.physicalcpu": -1, "hw.physicalcpu": 8}, 4),     # a negative level is no level
    ({"hw.perflevel0.physicalcpu": None, "hw.physicalcpu": 8}, 4),
    ({"hw.physicalcpu": -4}, max(1, (kr.os.cpu_count() or 2) // 2)),  # a negative or zero count is no count
    ({"hw.physicalcpu": 0}, max(1, (kr.os.cpu_count() or 2) // 2)),
])
def test_pages_at_once_is_the_performance_cores_else_half_the_physical_ones_never_below_one(monkeypatch, sysctl, expected):
    _sysctl(monkeypatch, **sysctl)
    assert kr.performance_cores() == expected >= 1


@pytest.mark.parametrize("priority, perf_cores, memory_gib, expected", [
    ("fast", 4, 40, 2),    # four performance cores, gated at two until #5929 closes
    ("fast", 10, 40, 2),   # ten performance cores, still two
    ("fast", 1, 40, 1),    # the gate never raises
    ("fast", 4, 6, 2),     # memory sets it below the cores
    ("fast", 4, 3, 1),     # and never below one
    ("balanced", 4, 40, 1), ("background", 4, 40, 1)])
def test_only_a_fast_run_reads_a_page_per_performance_core_held_down_by_the_free_memory(
        monkeypatch, priority, perf_cores, memory_gib, expected):
    from fichero_server.core import compute_preferences

    monkeypatch.setattr(compute_preferences, "priority_for", lambda person: priority)
    monkeypatch.setattr(kr, "_available_memory_bytes", lambda: memory_gib * GIB)
    _sysctl(monkeypatch, **{"hw.perflevel0.physicalcpu": perf_cores, "hw.physicalcpu": perf_cores + 4})
    assert kr.pages_at_once(person=True) == expected


def test_a_small_mac_reads_one_page_whatever_the_priority(monkeypatch):
    from fichero_server.core import compute_preferences

    monkeypatch.setattr(compute_preferences, "priority_for", lambda person: "fast")
    monkeypatch.setattr(kr, "_available_memory_bytes", lambda: 4 * GIB)  # an 8 GB Mac with the system's share used
    _sysctl(monkeypatch, **{"hw.perflevel0.physicalcpu": 4, "hw.physicalcpu": 8})
    assert kr.pages_at_once(person=True) == 1


def test_unknown_memory_reads_one_page(monkeypatch):
    from fichero_server.core import compute_preferences

    monkeypatch.setattr(compute_preferences, "priority_for", lambda person: "fast")
    monkeypatch.setattr(kr, "_available_memory_bytes", lambda: None)
    _sysctl(monkeypatch, **{"hw.perflevel0.physicalcpu": 10})
    assert kr.pages_at_once(person=True) == 1


def test_the_real_sysctl_answers_an_integer_or_nothing_and_never_starts_a_process(monkeypatch):
    """sysctlbyname through ctypes: a sandboxed app cannot exec `sysctl` (#4555)."""
    import subprocess

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("started a child process"))
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("started a child process"))
    assert kr._sysctl_int("hw.no.such.name") is None
    cores = kr.performance_cores()
    assert isinstance(cores, int) and cores >= 1


def test_the_cores_are_split_by_the_pages_actually_inside(monkeypatch):
    """Review 341: one page reads with every core, two with half each, whatever the policy allows."""
    import sys
    import types

    from fichero_server.core import background_compute
    from fichero_server.execution import jobs, throttle

    seen = []
    monkeypatch.setitem(sys.modules, "torch", types.SimpleNamespace(
        set_num_threads=lambda n: seen.append(n), set_num_interop_threads=lambda n: None))
    monkeypatch.setattr(throttle, "decide", lambda person_waiting=False, **_: throttle.Decision("go", None, "fast"))
    monkeypatch.setattr(jobs, "current_job_is_a_persons", lambda: True)
    monkeypatch.setattr(kr, "pages_at_once", lambda person: 2)
    monkeypatch.setattr(kr, "require_installed", lambda: None)
    monkeypatch.setattr(kr, "assert_memory_available_for_kraken", lambda: None)
    monkeypatch.setattr(kr, "_release_when_idle", lambda: None)
    cores = background_compute.cpu_count()

    kr._kraken_call(lambda: None)  # a lone page
    assert seen[-1] == cores

    inside, release = threading.Event(), threading.Event()

    def other(_i):
        kr._kraken_call(lambda: (inside.set(), release.wait(2)))

    t = _in_threads(1, other)[0]
    inside.wait(2)
    kr._kraken_call(lambda: None)  # a second page while the first is inside
    assert seen[-1] == max(1, cores // 2)
    release.set()
    t.join()


def test_two_pages_reading_found_lines_each_get_their_own_reader(tmp_path, monkeypatch):
    """The read of lines already found (the path Find Regions' kept lines take) used the ONE resident reader for both pages:
    Kraken keeps a page's state on the model, so they clobbered each other (M4 realrun 2026-10-20, 'list index out of
    range'). Each page reads on its own handle, and a failure is said in words, the raw error in the log."""
    pytest.importorskip("kraken")
    from PIL import Image

    path = tmp_path / "p.png"
    Image.new("RGB", (40, 40), (250, 250, 250)).save(path)
    lines = [{"id": "l1", "baseline": [[2, 20], [38, 20]], "polygon": [[2, 10], [38, 10], [38, 30], [2, 30]]}]
    seen, lock, both_inside = [], threading.Lock(), threading.Barrier(2, timeout=5)

    class Reader:
        def predict(self, image, segmentation, config):
            with lock:
                seen.append(id(self))
            try:
                both_inside.wait()  # the other page is inside its predict at the same time
            except threading.BrokenBarrierError:
                pass
            return []

    shared = Reader()
    monkeypatch.setattr(kr, "_resident", lambda kind, key, load: shared)
    monkeypatch.setattr(kr, "_reader_config", lambda cls: None)
    monkeypatch.setattr(kr, "_page_is", lambda p: None)
    [t.join() for t in _in_threads(2, lambda _i: kr._read_given_raw(path, "m", lines))]
    assert len(seen) == 2 and len(set(seen)) == 2 and id(shared) not in seen, "each page reads on its own copy"


def test_a_failed_read_of_found_lines_says_it_in_words_and_keeps_the_raw_error_in_the_log(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(kr, "_read_given_raw", lambda *a: (_ for _ in ()).throw(IndexError("list index out of range")))
    monkeypatch.setattr(kr, "_kraken_call", lambda op: op())
    lines = [{"id": "l1", "baseline": [[2, 20], [38, 20]], "polygon": [[2, 10], [38, 10], [38, 30], [2, 30]]}]
    with pytest.raises(kr.KrakenSegmentationError) as caught:
        kr.read_given_lines(tmp_path / "p.png", "m", lines)
    assert "index out of range" not in str(caught.value) and "Kraken could not read this page's lines" in str(caught.value)
    assert "list index out of range" in caplog.text
