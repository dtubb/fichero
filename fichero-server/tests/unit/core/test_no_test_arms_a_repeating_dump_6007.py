"""No test arms a repeating faulthandler dump (#6007): the api part hung at 41% because the stall test's leaked `repeat=True` timer kept
firing, faulthandler walking another thread's live frames at 99% CPU with its dump_file at 1.6 MB."""
from __future__ import annotations

import ast
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_the_suite_runs_with_the_loop_dump_switched_off():
    assert os.environ.get("FICHERO_LOOP_DUMP") == "0", "tests/conftest.py must set FICHERO_LOOP_DUMP=0 for the whole suite"


def test_only_the_loop_watcher_arms_a_repeating_dump_and_only_behind_the_switch():
    armed = []
    for path in [*(ROOT / "src").rglob("*.py"), *(ROOT / "tests").rglob("*.py")]:
        if path == Path(__file__):
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "dump_traceback_later":
                if any(k.arg == "repeat" and not (isinstance(k.value, ast.Constant) and k.value.value is False) for k in node.keywords):
                    armed.append(str(path.relative_to(ROOT)))
    assert armed == ["src/fichero_server/core/loop_lag.py"], f"a repeating dump is armed outside the loop watcher: {armed}"
    watcher = (ROOT / "src/fichero_server/core/loop_lag.py").read_text()
    arm = watcher[watcher.index("def _arm_dump"):]
    assert arm.index("_dump_enabled()") < arm.index("dump_traceback_later"), "the watcher arms the dump before checking the switch"
