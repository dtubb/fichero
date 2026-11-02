"""dev-workflows.run.heavy-lock: one heavy job at a time per machine; quick things stay free."""
from __future__ import annotations

import os
import subprocess
import sys

import pytest

from fichero_builder import __main__ as cli
from fichero_builder import check_tool, journal


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    monkeypatch.delenv(journal.HEAVY_ENV, raising=False)
    return tmp_path / "s"


def test_a_second_heavy_job_waits_and_a_wait_over_the_limit_names_the_holder(state, monkeypatch, capsys):
    import threading
    monkeypatch.setattr(journal.Lock, "WARN_S", 0.1)
    order = []
    with journal.heavy("the first"):
        def second():
            with journal.heavy("the second"):
                order.append("second")
        t = threading.Thread(target=second)
        t.start()
        t.join(1.3)
        assert t.is_alive() and order == [], "the second waits while the first holds it"
        order.append("first-done")
    t.join(5)
    assert order == ["first-done", "second"]
    assert "waiting for the heavy lock, held by" in capsys.readouterr().err


def test_builder_heavy_runs_the_command_under_the_lock_and_its_children_pass_through(state, capfd):
    code = f"import os; print('held' if os.environ.get({journal.HEAVY_ENV!r}) else 'free')"
    assert cli.main(["heavy", "--state", str(state), "--", sys.executable, "-c", code]) == 0
    assert "held" in capfd.readouterr().out
    assert cli.main(["heavy", "--state", str(state), "--", sys.executable, "-c", "raise SystemExit(3)"]) == 3
    assert cli.main(["heavy", "--state", str(state)]) == 2, "no command is refused"
    with journal.heavy("a child of builder heavy"):  # the env var makes a nested job pass, never deadlock
        os.environ[journal.HEAVY_ENV] = "1"
        try:
            with journal.heavy("nested"):
                pass
        finally:
            del os.environ[journal.HEAVY_ENV]


def test_the_guards_rung_the_build_rung_and_a_local_full_suite_take_it_a_remote_suite_does_not(state, monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(journal, "heavy", lambda what: __import__("contextlib").nullcontext(seen.append(what)))
    monkeypatch.setattr(check_tool, "_run", lambda *a, **k: {"ok": True, "exit_code": 0, "timed_out": False, "stdout_tail": "", "stderr_tail": "", "seconds": 0})
    monkeypatch.setattr(check_tool, "pytest_rung", lambda *a, **k: {"ok": True, "argv": [], "exit_code": 0, "seconds": 0, "stdout_tail": "", "stderr_tail": ""})
    check_tool.guards(tmp_path, check_tool.Config(guard_glob="ci/x_*.py", min_guards=0))
    check_tool.build(tmp_path, ["fichero/x"], check_tool.Config(build=("true",), build_paths=("fichero/",)))
    check_tool.green_runs(tmp_path, ["fichero-server/tests"], (), check_tool.Config(), 5)
    check_tool.green_runs(tmp_path, ["fichero-server/tests"], (), check_tool.Config(remote="imac:~/g"), 5)
    assert seen == ["the guards rung", "xcodebuild (the build rung)", "the full engine suite"], "the remote suite took no local lock"


def test_the_dev_build_takes_the_lock(state, monkeypatch, tmp_path):
    held = []
    monkeypatch.setattr(journal, "heavy", lambda what: __import__("contextlib").nullcontext(held.append(what)))
    root = tmp_path / "r"
    (root / "scripts").mkdir(parents=True)
    (root / "fichero" / "Configs").mkdir(parents=True)
    (root / "fichero" / "Configs" / "Version.xcconfig").write_text("MARKETING_VERSION = 1.2.3\n")
    script = root / "scripts" / "build-release-dmg.sh"
    script.write_text('#!/bin/sh\nmkdir -p "$(dirname "$FICHERO_DMG_PATH")" && echo x > "$FICHERO_DMG_PATH"\n')
    script.chmod(0o755)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    assert cli.main(["build", "--dev", "--root", str(root), "--state", str(state)]) == 0
    assert held == ["the dev build"]


def test_the_remote_wrapper_holds_the_machines_lock_while_its_script_runs_and_passes_the_exit_code(tmp_path):
    """The iMac's own lock (owner 2026-11-02): the wrapper `_remote_run` puts round a remote script serialises two runs on the
    lock file and returns the script's exit code; run here with the local python standing in for the remote one."""
    import shlex
    import time
    lock = str(tmp_path / "heavy.lock")
    log = tmp_path / "log"
    one = check_tool._remote_heavy(sys.executable, lock, f"echo a-start >> {log}; sleep 1; echo a-end >> {log}; exit 7")
    two = check_tool._remote_heavy(sys.executable, lock, f"echo b-start >> {log}; echo b-end >> {log}")
    p1 = subprocess.Popen(["sh", "-c", one])
    time.sleep(0.4)
    p2 = subprocess.Popen(["sh", "-c", two])
    assert p1.wait(10) == 7 and p2.wait(10) == 0
    assert log.read_text().split() == ["a-start", "a-end", "b-start", "b-end"], "the second waited for the first"
    assert shlex.split(one)[0] == sys.executable
