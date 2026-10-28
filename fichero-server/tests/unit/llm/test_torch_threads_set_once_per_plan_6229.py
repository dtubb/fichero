"""`activity.lane.torch-threads-set-once-per-plan` (#6229): torch's thread count is process-wide, so it is set once for a
plan (N pages at once, T = the cores // N threads each), when the plan changes, never per page from the pages inside the
gate (a page that entered alone at four dropped to two when a second entered, and stayed there after it left)."""
from __future__ import annotations

import sys
import threading
import types

from fichero_server.llm import kraken_runtime as kr


def _lane(monkeypatch, pages_at_once):
    from fichero_server.execution import jobs, throttle

    seen: list[int] = []
    monkeypatch.setitem(sys.modules, "torch", types.SimpleNamespace(
        set_num_threads=seen.append, set_num_interop_threads=lambda n: None))
    monkeypatch.setattr(throttle, "decide", lambda person_waiting=False, **_: throttle.Decision("go", None, "fast"))
    monkeypatch.setattr(jobs, "current_job_is_a_persons", lambda: True)
    monkeypatch.setattr(kr, "pages_at_once", lambda person: pages_at_once[0])
    monkeypatch.setattr(kr, "require_installed", lambda: None)
    monkeypatch.setattr(kr, "assert_memory_available_for_kraken", lambda: None)
    monkeypatch.setattr(kr, "_release_when_idle", lambda: None)
    monkeypatch.setattr("fichero_server.core.compute_preferences.apply_to_this_thread",
                        lambda priority, lift_to_utility=False: 8)
    return seen


def test_two_pages_under_one_plan_set_the_threads_once(monkeypatch):
    plan = [2]
    seen = _lane(monkeypatch, plan)
    inside, release = threading.Event(), threading.Event()
    first = threading.Thread(target=kr._kraken_call, args=(lambda: (inside.set(), release.wait(2)),))
    first.start()
    inside.wait(2)
    kr._kraken_call(lambda: None)  # a second page while the first is inside
    release.set()
    first.join()
    kr._kraken_call(lambda: None)  # and one alone after it left

    assert seen == [4]  # 8 cores, 2 pages at once: 4 each, once


def test_a_plan_change_sets_them_once_more(monkeypatch):
    plan = [2]
    seen = _lane(monkeypatch, plan)
    kr._kraken_call(lambda: None)
    plan[0] = 1
    kr._kraken_call(lambda: None)
    kr._kraken_call(lambda: None)

    assert seen == [4, 8]
