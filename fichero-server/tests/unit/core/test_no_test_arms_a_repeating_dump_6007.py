"""No test arms a repeating faulthandler dump (#6007): the api part hung at 41% because the stall test's leaked `repeat=True` timer kept
firing, faulthandler walking another thread's live frames at 99% CPU with its dump_file at 1.6 MB."""
from __future__ import annotations

import ast
import importlib.util
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
# scripts/ is not a package: load the repo's scan helper by path, so a nested worktree is never walked (see test_scan_files_skips_nested_worktrees).
_spec = importlib.util.spec_from_file_location("_scan_files", Path(__file__).resolve().parents[4] / "scripts" / "_scan_files.py")
scan_files = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scan_files)


def test_the_suite_runs_with_the_loop_dump_switched_off():
    assert os.environ.get("FICHERO_LOOP_DUMP") == "0", "tests/conftest.py must set FICHERO_LOOP_DUMP=0 for the whole suite"


def test_nothing_arms_a_repeating_dump_and_the_watcher_arms_only_behind_the_switch():
    armed = set()
    for path in [*scan_files.scan_rglob(ROOT / "src", "*.py"), *scan_files.scan_rglob(ROOT / "tests", "*.py")]:
        if path == Path(__file__):
            continue
        text = path.read_text()
        if "dump_traceback_later" not in text:  # a text prefilter: parsing every source and test file took most of the test's time
            continue
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "dump_traceback_later":
                if any(k.arg == "repeat" and not (isinstance(k.value, ast.Constant) and k.value.value is False) for k in node.keywords):
                    armed.add(str(path.relative_to(ROOT)))
    assert armed == set(), f"a repeating faulthandler dump is armed (one stack dump per stall, #6007): {armed}"
    watcher = (ROOT / "src/fichero_server/core/loop_lag.py").read_text()
    arm = watcher[watcher.index("def _arm_dump"):]
    assert arm.index("_dump_enabled()") < arm.index("dump_traceback_later"), "the watcher arms the dump before checking the switch"


def test_the_watchers_dump_is_one_shot_per_stall(monkeypatch):
    """The product's `_arm_dump` arms `repeat=False`: a stall over `DUMP_SECONDS` gets one dump, and the heartbeat after the loop answers
    arms the next (#6008, found in #6007)."""
    import faulthandler

    from fichero_server.core import loop_lag

    armed = []
    monkeypatch.setenv("FICHERO_LOOP_DUMP", "1")
    monkeypatch.setattr(faulthandler, "cancel_dump_traceback_later", lambda: None)
    monkeypatch.setattr(faulthandler, "dump_traceback_later", lambda seconds, **kw: armed.append((seconds, kw)))
    loop_lag._arm_dump(30.0, None)
    assert len(armed) == 1 and armed[0][0] == 30.0
    assert armed[0][1].get("repeat") is False, f"the dump repeats: {armed}"


def test_each_heartbeat_arms_a_fresh_one_shot_so_a_second_stall_is_dumped_too(monkeypatch):
    """The re-arm (## 997): a one-shot dump fires once per stall, so every heartbeat must put a new one in place. Two heartbeats cancel
    the old timer and arm a new non-repeating one each time; a loop that answers, then stalls again, is dumped again (#6008)."""
    import asyncio
    import faulthandler

    from fichero_server.core import loop_lag

    events = []
    monkeypatch.setenv("FICHERO_LOOP_DUMP", "1")
    monkeypatch.setattr(faulthandler, "cancel_dump_traceback_later", lambda: events.append("cancel"))
    monkeypatch.setattr(faulthandler, "dump_traceback_later", lambda seconds, **kw: events.append(("arm", seconds, kw.get("repeat"))))
    loop = asyncio.new_event_loop()
    try:
        async def beat_twice():
            stop = loop_lag.start(loop, ping_seconds=0.02, slow_seconds=5, dump_seconds=30.0)
            events.clear()  # the arm made at start
            await asyncio.sleep(0.25)  # the watcher pings every 20 ms: several heartbeats ran on this loop
            stop.set()

        loop.run_until_complete(beat_twice())
    finally:
        loop.close()
        loop_lag.stop_watchdog()
    arms = [e for e in events if e != "cancel"]
    assert len(arms) >= 2, f"fewer than two heartbeats re-armed the dump: {events}"
    assert all(a == ("arm", 30.0, False) for a in arms), f"a re-arm was not a fresh one-shot: {arms}"
    assert events.count("cancel") >= len(arms), "a re-arm did not cancel the timer it replaced"
