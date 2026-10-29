"""#5819: Find Lines slept between pages whenever "you're using the Mac" or "a build is running". Work the person
started waits only for memory and heat; any work goes slower, never stops, while the Mac is used or a build runs.

Spec: docs/contributor_manual/specs/ui/activity-and-automatic-work.md (`activity.throttle.use-means-slower`).
The throttle's real probes with the Mac's signals faked; the pages have no image, so only the waiting is exercised.
"""
from __future__ import annotations

from tests._this_thread import sleep_here
from types import SimpleNamespace

import pytest

from fichero_server.execution import jobs, throttle
from fichero_server.recipes import regions


@pytest.fixture
def mac(monkeypatch):
    state = {"build": False, "idle": 600.0, "battery": False, "pressure": 1, "sleeps": []}
    monkeypatch.setenv("FICHERO_JOB_THROTTLE", "1")
    monkeypatch.setattr(throttle, "memory_pressure_level", lambda: state["pressure"])
    monkeypatch.setattr(throttle, "memory_available_bytes", lambda: 64 * 1024**3)
    monkeypatch.setattr(throttle, "thermal_state_level", lambda: 0)
    monkeypatch.setattr(throttle, "battery_or_low_power", lambda: state["battery"])
    monkeypatch.setattr(throttle, "seconds_since_input", lambda: state["idle"])
    monkeypatch.setattr(throttle, "a_build_is_running", lambda: throttle.BUILD_REASON if state["build"] else None)
    monkeypatch.setattr(regions.time, "sleep", sleep_here(lambda seconds: state["sleeps"].append(seconds)))
    return state


def _find_lines(monkeypatch, tmp_path, person: bool, pages: int = 3, stop_after_sleeps: int = 50):
    monkeypatch.setattr(jobs, "person_waits_on", lambda _db, _id: person)
    said = []
    db = SimpleNamespace(path=tmp_path / "lib" / "x.duckdb",
                         get=lambda *_a: SimpleNamespace(path=str(tmp_path / "no-such-image.jpg"), id="d", name="n", metadata={}))  # a Document has metadata; the path lookup reads it
    account = regions.find_regions(db, [f"d{i}" for i in range(pages)], "run", "m", provider="yolo", say=said.append)
    return account, said


def test_a_person_started_run_over_3_pages_finishes_without_waiting_on_use_or_a_build(mac, monkeypatch, tmp_path):
    mac.update(build=True, idle=1.0)  # the Mac is in use and a build runs
    account, said = _find_lines(monkeypatch, tmp_path, person=True)
    assert account["no_image"] == 3 and mac["sleeps"] == []  # no sleep at all
    assert not any("build" in s or "using the Mac" in s for s in said)


def test_a_background_run_makes_progress_slower_under_a_build_or_use(mac, monkeypatch, tmp_path):
    mac.update(build=True, idle=1.0)
    account, said = _find_lines(monkeypatch, tmp_path, person=False)
    assert account["no_image"] == 3  # all three pages were reached
    assert mac["sleeps"] == [regions.SLOWER_YIELD_SECONDS] * 3  # one short yield per page, never the 5 s wait loop
    assert any("going slower" in s for s in said)


def test_memory_still_holds_a_person_started_run(mac, monkeypatch, tmp_path):
    mac["pressure"] = 4  # critical
    calls = {"n": 0}

    def clears_after_two_sleeps(seconds):
        mac["sleeps"].append(seconds)
        calls["n"] += 1
        if calls["n"] == 2:
            mac["pressure"] = 1

    monkeypatch.setattr(regions.time, "sleep", sleep_here(clears_after_two_sleeps))
    account, _ = _find_lines(monkeypatch, tmp_path, person=True, pages=1)
    assert mac["sleeps"] == [regions.WAIT_POLL_SECONDS] * 2 and account["no_image"] == 1  # held, then went on


def test_on_battery_slows_a_person_started_run_and_says_so_but_does_not_stop_it(mac, monkeypatch, tmp_path):
    mac["battery"] = True
    account, said = _find_lines(monkeypatch, tmp_path, person=True, pages=2)
    assert account["no_image"] == 2 and mac["sleeps"] == [regions.SLOWER_YIELD_SECONDS] * 2  # slower, every page done
    assert any("on battery: going slower" in s for s in said)


def test_battery_still_holds_background_work(mac, monkeypatch, tmp_path):
    mac["battery"] = True
    calls = {"n": 0}

    def plugged_in_after_one_wait(seconds):
        mac["sleeps"].append(seconds)
        calls["n"] += 1
        mac["battery"] = False

    monkeypatch.setattr(regions.time, "sleep", sleep_here(plugged_in_after_one_wait))
    account, _ = _find_lines(monkeypatch, tmp_path, person=False, pages=1)
    assert mac["sleeps"] == [regions.WAIT_POLL_SECONDS] and account["no_image"] == 1  # waited for the charger, then went


# --- the owner's second ruling: a person's run goes flat out; background stays balanced ------------------------------


def test_the_priority_of_a_page_by_who_started_it(monkeypatch):
    from fichero_server.core import compute_preferences as prefs

    monkeypatch.delenv("FICHERO_COMPUTE_PRIORITY", raising=False)
    monkeypatch.setattr(prefs, "stored_preferences", lambda: {"priority": "balanced", "device": "auto"})
    monkeypatch.setenv("FICHERO_JOB_THROTTLE", "1")
    monkeypatch.setattr(throttle, "memory_pressure_level", lambda: 1)
    monkeypatch.setattr(throttle, "memory_available_bytes", lambda: 64 * 1024**3)
    monkeypatch.setattr(throttle, "thermal_state_level", lambda: 0)
    monkeypatch.setattr(throttle, "seconds_since_input", lambda: 600.0)
    monkeypatch.setattr(throttle, "a_build_is_running", lambda: None)
    battery = {"on": False}
    monkeypatch.setattr(throttle, "battery_or_low_power", lambda: battery["on"])
    assert prefs.priority_for(True) == "fast"  # Start: flat out
    assert prefs.priority_for(False) == "balanced"  # background: balanced
    battery["on"] = True
    assert prefs.priority_for(True) == "balanced"  # only battery slows a person's run
    monkeypatch.setenv("FICHERO_COMPUTE_PRIORITY", "background")
    assert prefs.priority_for(True) == "background"  # the environment's override wins


def test_fast_is_every_core_at_user_initiated_and_balanced_is_the_lanes_share(monkeypatch):
    from fichero_server.core import background_compute as bc
    from fichero_server.core import compute_preferences as prefs

    classes = []
    monkeypatch.setattr(bc, "set_background_qos", lambda qos=0x09: classes.append(qos))
    assert prefs.apply_to_this_thread("fast") == bc.cpu_count() and classes == [bc._QOS_CLASS_USER_INITIATED]
    classes.clear()
    assert prefs.apply_to_this_thread("balanced") == max(1, bc.embed_threads()) and classes == [bc._QOS_CLASS_UTILITY]


def test_a_kraken_page_of_a_persons_run_gets_fast_threads_and_a_background_one_balanced(monkeypatch):
    import sys
    import types

    from fichero_server.core import compute_preferences as prefs
    from fichero_server.llm import kraken_runtime as kr

    threads = []
    fake_torch = types.SimpleNamespace(set_num_threads=threads.append, set_num_interop_threads=lambda n: None)
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setattr(kr, "require_installed", lambda: None)
    monkeypatch.setattr(kr, "assert_memory_available_for_kraken", lambda: None)
    monkeypatch.setattr(kr, "_release_when_idle", lambda: None)
    monkeypatch.setattr(kr, "bound_native_thread_pools", lambda n: None)
    monkeypatch.setattr(kr, "pages_at_once", lambda person: 1)  # one page a plan: the priority alone sets the threads (#6229)
    monkeypatch.setattr(prefs, "stored_preferences", lambda: {"priority": "balanced", "device": "auto"})
    monkeypatch.delenv("FICHERO_COMPUTE_PRIORITY", raising=False)
    monkeypatch.setenv("FICHERO_JOB_THROTTLE", "0")  # off: a person's page is fast, background balanced
    monkeypatch.setattr("fichero_server.core.background_compute.set_background_qos", lambda qos=0x09: None)

    jobs._current.person = True
    kr._kraken_call(lambda: None)
    jobs._current.person = False
    kr._kraken_call(lambda: None)
    from fichero_server.core.background_compute import cpu_count, embed_threads

    assert threads == [cpu_count(), max(1, embed_threads())]  # fast, then balanced


def test_another_threads_sleep_is_not_this_runs_wait(mac, monkeypatch, tmp_path):
    """Order-dependent before: the fake replaced time.sleep for every thread, so a lane thread an earlier test left
    running counted its own sleeps as this run's waiting."""
    import threading
    import time

    stop = threading.Event()

    def lane():  # a thread an earlier test left behind, sleeping between claims
        while not stop.is_set():
            time.sleep(0.01)

    thread = threading.Thread(target=lane, daemon=True)
    thread.start()
    try:
        mac.update(build=True, idle=1.0)
        for _ in range(20):  # let the lane sleep while the run goes
            _find_lines(monkeypatch, tmp_path, person=True)
    finally:
        stop.set()
        thread.join(5)
    assert mac["sleeps"] == []
