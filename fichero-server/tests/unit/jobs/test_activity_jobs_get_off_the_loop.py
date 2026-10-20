"""Fable review #2: `GET /api/activity/jobs` polls every 2 s and must not hold the event loop: its readings that run a
subprocess or a database read are on a thread, and `pmset` is never waited for on a loop."""
from __future__ import annotations

import ast
import asyncio
import time
from pathlib import Path

from fichero_server.api.routes.system import activity
from fichero_server.execution import throttle

#: Calls in the handler that read the database or run a subprocess.
BLOCKING = {"machine_state", "process_tree_rusage", "name_and_pages", "_remote_row", "snapshot", "waiting_reason_of",
            "read_again_runs", "_queue_summary"}


def test_the_jobs_handler_runs_every_blocking_reading_through_to_thread():
    tree = ast.parse(Path(activity.__file__).read_text())
    handler = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "list_background_jobs")
    on_loop = []
    for call in ast.walk(handler):
        if isinstance(call, ast.Call) and getattr(call.func, "attr", getattr(call.func, "id", "")) in BLOCKING:
            on_loop.append(call.func)
    # a reading handed to to_thread is an ARGUMENT (an attribute or name, not a call); a call in the handler body is on the loop
    assert [ast.unparse(f) for f in on_loop] == [], f"called on the event loop: {[ast.unparse(f) for f in on_loop]}"


def test_a_battery_reading_never_blocks_a_running_loop(monkeypatch):
    monkeypatch.setattr(throttle, "_battery", None)
    calls = []

    def slow_pmset(*a, **k):
        calls.append(1)
        time.sleep(0.5)
        return type("R", (), {"stdout": "Now drawing from 'Battery Power'"})()

    monkeypatch.setattr(throttle.subprocess, "run", slow_pmset)

    async def on_the_loop():
        started = time.monotonic()
        first = throttle.battery_or_low_power()
        return first, time.monotonic() - started

    first, took = asyncio.run(on_the_loop())
    assert took < 0.2, f"the loop waited {took:.2f}s for pmset"
    assert first is False, "no reading yet is no reason to wait"
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline and not (throttle._battery and throttle._battery[1]):
        time.sleep(0.02)
    assert throttle.battery_or_low_power() is True, "the thread's reading is served afterwards"
    assert len(calls) == 1


def test_off_a_loop_the_reading_is_still_taken_in_place(monkeypatch):
    monkeypatch.setattr(throttle, "_battery", None)
    monkeypatch.setattr(throttle.subprocess, "run",
                        lambda *a, **k: type("R", (), {"stdout": "Now drawing from 'AC Power'"})())
    assert throttle.battery_or_low_power() is False
