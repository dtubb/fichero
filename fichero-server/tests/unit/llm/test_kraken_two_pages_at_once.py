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


def _cores(monkeypatch, n, source="mac-performance-cores"):
    """The machine this run is on, as `core.cores.cores_available` reports it."""
    from fichero_server.core import cores

    monkeypatch.setattr(cores, "cores_available", lambda: (n, source))


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
    _cores(monkeypatch, perf_cores)
    assert kr.pages_at_once(person=True) == expected


@pytest.mark.parametrize("source", ["slurm", "cgroup", "affinity", "none"])
def test_a_cluster_task_or_a_container_reads_one_page_pipeline(monkeypatch, source):
    """Parallelism there is array tasks, not pages side by side (`source.read.threads-fit-the-machine`)."""
    from fichero_server.core import compute_preferences

    monkeypatch.setattr(compute_preferences, "priority_for", lambda person: "fast")
    monkeypatch.setattr(kr, "_available_memory_bytes", lambda: 64 * GIB)
    _cores(monkeypatch, 16, source)
    assert kr.pages_at_once(person=True) == 1


def test_a_small_mac_reads_one_page_whatever_the_priority(monkeypatch):
    from fichero_server.core import compute_preferences

    monkeypatch.setattr(compute_preferences, "priority_for", lambda person: "fast")
    monkeypatch.setattr(kr, "_available_memory_bytes", lambda: 4 * GIB)  # an 8 GB Mac with the system's share used
    _cores(monkeypatch, 4)
    assert kr.pages_at_once(person=True) == 1


def test_unknown_memory_reads_one_page(monkeypatch):
    from fichero_server.core import compute_preferences

    monkeypatch.setattr(compute_preferences, "priority_for", lambda person: "fast")
    monkeypatch.setattr(kr, "_available_memory_bytes", lambda: None)
    _cores(monkeypatch, 10)
    assert kr.pages_at_once(person=True) == 1


def test_the_cores_are_split_by_the_pages_actually_inside(monkeypatch):
    """Review 341: one page reads with every core, two with half each, whatever the policy allows."""
    import sys
    import types

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
    from fichero_server.core.cores import cores_available

    cores = cores_available()[0]

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
    monkeypatch.setattr(kr, "_resident", lambda kind, key, load: shared if kind == "read" else load())  # the pool is its own resident
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


# -- the reader is copied once for each pipeline, not once for each page (`runtime.kraken.no-reader-copy-per-page`, #5952) --
class _Reader:
    """A stand-in reader that counts how often it is deep-copied."""

    copies = 0

    def __deepcopy__(self, memo):
        type(self).copies += 1
        return _Reader()


@pytest.fixture
def reader_world(monkeypatch):
    _Reader.copies = 0
    kr._RESIDENT.clear()
    loads = []
    template = _Reader()
    monkeypatch.setattr(kr, "_stage", lambda name: __import__("contextlib").nullcontext())
    yield types_ns(template=template, loads=loads, load=lambda: loads.append(1) or template)
    kr._RESIDENT.clear()


def types_ns(**kw):
    import types

    return types.SimpleNamespace(**kw)


def test_reading_many_pages_one_after_another_makes_one_copy_not_one_a_page(reader_world):
    seen = []
    for _ in range(25):
        with kr._own_reader("m.mlmodel", reader_world.load) as net:
            seen.append(net)
    assert _Reader.copies == 1 and len({id(n) for n in seen}) == 1  # the same copy, handed from page to page
    assert reader_world.loads == [1]  # and the model was loaded once


def test_pages_at_once_each_hold_a_copy_and_no_more_are_made_than_pages_at_once(reader_world):
    first = kr._own_reader("m.mlmodel", reader_world.load)
    second = kr._own_reader("m.mlmodel", reader_world.load)
    a, b = first.__enter__(), second.__enter__()
    assert a is not b and _Reader.copies == 2  # two pages in flight: two readers, never the same object
    first.__exit__(None, None, None)
    second.__exit__(None, None, None)
    for _ in range(10):
        with kr._own_reader("m.mlmodel", reader_world.load):
            pass
    assert _Reader.copies == 2  # still two: the idle ones were reused


def test_a_reader_a_failed_page_held_is_dropped_not_reused(reader_world):
    with pytest.raises(RuntimeError):
        with kr._own_reader("m.mlmodel", reader_world.load):
            raise RuntimeError("the page failed with Kraken's state half way")
    with kr._own_reader("m.mlmodel", reader_world.load):
        pass
    assert _Reader.copies == 2  # a fresh copy, not the one whose state is unknown


def test_the_copies_are_freed_with_the_model_and_a_different_model_gets_its_own(reader_world):
    with kr._own_reader("m.mlmodel", reader_world.load):
        pass
    kr.release_resident_models("test")
    assert "read-copies" not in kr._RESIDENT and "read" not in kr._RESIDENT
    with kr._own_reader("m.mlmodel", reader_world.load):
        pass
    assert _Reader.copies == 2  # the pool went with the model
    with kr._own_reader("other.mlmodel", reader_world.load):
        pass
    assert _Reader.copies == 3  # another model, another pool


def test_idle_copies_are_trimmed_to_the_pages_at_once_now_allowed(reader_world, monkeypatch):
    gate = kr._PageGate()
    monkeypatch.setattr(kr, "_INFERENCE_LOCK", gate)
    with gate.page(2):  # two pages at once: two copies, both kept idle afterwards
        first, second = kr._own_reader("m.mlmodel", reader_world.load), kr._own_reader("m.mlmodel", reader_world.load)
        first.__enter__(), second.__enter__()
        first.__exit__(None, None, None)
        second.__exit__(None, None, None)
    pool = kr._RESIDENT["read-copies"][1]
    assert (pool.live, len(pool._idle), _Reader.copies) == (2, 2, 2)
    with gate.page(1):  # N dropped to one (memory, or a background run): the extra copy goes, not kept for nothing
        with kr._own_reader("m.mlmodel", reader_world.load):
            pass
    assert (pool.live, len(pool._idle), _Reader.copies) == (1, 1, 2)  # one copy kept, none made, one freed
    with gate.page(2):  # and back to two: one more copy is made, as before
        a, b = kr._own_reader("m.mlmodel", reader_world.load), kr._own_reader("m.mlmodel", reader_world.load)
        a.__enter__(), b.__enter__()
        assert _Reader.copies == 3 and pool.live == 2
        a.__exit__(None, None, None)
        b.__exit__(None, None, None)


def test_a_failed_pages_copy_leaves_the_count(reader_world):
    with pytest.raises(RuntimeError):
        with kr._own_reader("m.mlmodel", reader_world.load):
            raise RuntimeError("failed")
    pool = kr._RESIDENT["read-copies"][1]
    assert (pool.live, len(pool._idle)) == (0, 0)


def test_both_read_paths_take_their_reader_from_the_pool():
    import inspect

    assert "_own_reader(" in inspect.getsource(kr._recognize_raw) and "_own_reader(" in inspect.getsource(kr._read_given_raw)
    assert "deepcopy" not in inspect.getsource(kr._recognize_raw) + inspect.getsource(kr._read_given_raw)


# -- every name the engine takes from kraken_runtime exists (review 692: a rewrite once deleted ~290 live lines) -----------
def test_every_name_the_engine_takes_from_kraken_runtime_exists():
    """Guard: scan the engine's source for `kraken_runtime.<name>` and `from ...kraken_runtime import <name>` and require each
    to exist, and the seam's own entry points besides. A file rewritten over its neighbours' callers fails here, at once."""
    import ast
    from pathlib import Path

    src = Path(kr.__file__).parent.parent
    wanted: dict[str, set[str]] = {}
    for path in src.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        aliases = {"kraken_runtime"}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.endswith("kraken_runtime"):
                for a in node.names:
                    wanted.setdefault(a.name, set()).add(f"{path.relative_to(src)}:{node.lineno}")
            elif isinstance(node, ast.ImportFrom) and any(a.name == "kraken_runtime" for a in node.names):
                aliases.update(a.asname or a.name for a in node.names if a.name == "kraken_runtime")
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in aliases | {"kr"}:
                wanted.setdefault(node.attr, set()).add(f"{path.relative_to(src)}:{node.lineno}")
    missing = {name: sorted(where) for name, where in wanted.items() if not hasattr(kr, name)}
    assert missing == {}, f"names used but not in kraken_runtime: {missing}"
    for name in ("is_installed", "runtime_status", "require_installed", "assert_memory_available_for_kraken", "_PageGate",
                 "_INFERENCE_LOCK", "pages_at_once", "page_fan_out", "_kraken_call", "release_resident_models",
                 "_memory_free_percent", "_physical_memory_bytes", "_sysctl_int"):
        assert hasattr(kr, name), name


def test_the_memory_guards_sysctl_still_takes_a_byte_name_and_is_not_shadowed():
    """`_sysctl_int(b"kern.memorystatus_level")` is the memory guard's: a second `_sysctl_int` taking a str once shadowed it
    and made every memory reading None."""
    import inspect

    params = list(inspect.signature(kr._sysctl_int).parameters)
    assert params == ["name", "ctype"] and kr.__dict__["_sysctl_int"].__code__.co_argcount == 2
