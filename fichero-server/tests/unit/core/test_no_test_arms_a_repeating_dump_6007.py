"""No test arms a repeating faulthandler dump (#6007): the api part hung at 41% because the stall test's leaked `repeat=True` timer kept
firing, faulthandler walking another thread's live frames at 99% CPU with its dump_file at 1.6 MB."""
from __future__ import annotations

import ast
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_the_suite_runs_with_the_loop_dump_switched_off():
    assert os.environ.get("FICHERO_LOOP_DUMP") == "0", "tests/conftest.py must set FICHERO_LOOP_DUMP=0 for the whole suite"


def test_nothing_arms_a_repeating_dump_and_the_watcher_arms_only_behind_the_switch():
    armed = []
    for path in [*(ROOT / "src").rglob("*.py"), *(ROOT / "tests").rglob("*.py")]:
        if path == Path(__file__):
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "dump_traceback_later":
                if any(k.arg == "repeat" and not (isinstance(k.value, ast.Constant) and k.value.value is False) for k in node.keywords):
                    armed.append(str(path.relative_to(ROOT)))
    assert armed == [], f"a repeating faulthandler dump is armed (one stack dump per stall, #6007): {armed}"
    watcher = (ROOT / "src/fichero_server/core/loop_lag.py").read_text()
    arm = watcher[watcher.index("def _arm_dump"):]
    assert arm.index("_dump_enabled()") < arm.index("dump_traceback_later"), "the watcher arms the dump before checking the switch"


def test_the_watchers_dump_is_one_shot_per_stall(monkeypatch):
    """The product's `_arm_dump` arms `repeat=False`: a stall over `DUMP_SECONDS` gets one dump, and the heartbeat after the loop answers
    arms the next (#6007)."""
    import faulthandler

    from fichero_server.core import loop_lag

    armed = []
    monkeypatch.setenv("FICHERO_LOOP_DUMP", "1")
    monkeypatch.setattr(faulthandler, "cancel_dump_traceback_later", lambda: None)
    monkeypatch.setattr(faulthandler, "dump_traceback_later", lambda seconds, **kw: armed.append((seconds, kw)))
    loop_lag._arm_dump(30.0, None)
    assert len(armed) == 1 and armed[0][0] == 30.0
    assert armed[0][1].get("repeat") is False, f"the dump repeats: {armed}"
