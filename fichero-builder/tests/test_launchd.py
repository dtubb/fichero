"""dev-workflows.run.loop-launchd: the loop and the console start at login by themselves, never two loops, and the lanes'
panes are found again after a reboot."""
from __future__ import annotations

import os
import plistlib
import subprocess
import sys

import pytest

from fichero_builder import __main__ as cli
from fichero_builder import journal, queue


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    (tmp_path / "s").mkdir()
    return tmp_path


def test_the_console_is_a_third_agent_kept_alive_and_started_at_login(state):
    paths = queue.launch_agents("/r", state / "la", state=state / "s", port=8766)
    con = plistlib.loads(paths[2].read_bytes())
    assert paths[2].name == "local.builder.console.plist" and con["KeepAlive"] is True and con["RunAtLoad"] is True
    assert con["ProgramArguments"][3:] == ["status", "--port", "8766", "--root", "/r", "--state", str(state / "s")]


def test_load_boots_out_then_bootstraps_each_agent_and_names_a_failure(state):
    calls = []

    def run(argv, **_):
        calls.append(argv[:2])
        bad = argv[1] == "bootstrap" and argv[-1].endswith("console.plist")
        return subprocess.CompletedProcess(argv, 5 if bad else 0, "", "Bootstrap failed: 5: Input/output error" if bad else "")

    lines = queue.load_agents([state / "local.builder.loop.plist", state / "local.builder.console.plist"], run=run)
    assert calls == [["launchctl", "bootout"], ["launchctl", "bootstrap"]] * 2
    assert lines == ["loaded local.builder.loop", "FAILED local.builder.console: Bootstrap failed: 5: Input/output error"]


def test_a_second_loop_is_refused_and_a_pid_the_reboot_left_is_not_a_loop(state):
    pidf = journal.STATE / "loop.pid"
    assert queue.other_loop() == 0, "no loop.pid"
    pidf.write_text(f"{os.getpid()}\n")
    assert queue.other_loop() == 0, "this process is not another loop"
    p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)", "fichero_builder loop"])
    try:
        pidf.write_text(f"{p.pid}\n")
        assert queue.other_loop() == p.pid
        assert cli.main(["loop", "--root", str(state), "--state", str(journal.STATE)]) == 1, "refused, nothing ticks"
    finally:
        p.kill(), p.wait()
    assert queue.other_loop() == 0, "a dead pid is no loop"
    q = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        pidf.write_text(f"{q.pid}\n")
        assert queue.other_loop() == 0, "a reused pid running another program is no loop"
    finally:
        q.kill(), q.wait()


def test_a_dead_pane_is_pointed_at_the_one_claude_session_in_the_lanes_worktree(state):
    wa, wb, wc = (str(state / n) for n in ("a", "b", "c"))
    for w in (wa, wb, wc):
        os.mkdir(w)
    queue.save([{"id": "a", "kind": "external", "pane": "%1", "worktree": wa, "cursor": 0, "steps": []},
                {"id": "b", "kind": "external", "pane": "%2", "worktree": wb, "cursor": 0, "steps": []},
                {"id": "c", "kind": "external", "pane": "%7", "worktree": wc, "cursor": 0, "steps": []},
                {"id": "w", "kind": "worker", "pane": "%3", "worktree": wa, "cursor": 0, "steps": []}])
    listing = "\n".join([f"%5\t2.1.317\t{wa}/sub", f"%6\tzsh\t{wa}", f"%8\t2.1.317\t{wb}", f"%9\t2.1.317\t{wb}", f"%7\tzsh\t{wc}"])
    assert queue.repane(listing) == ["a: pane %1 -> %5"], "b has two sessions: left; c's pane is alive; a worker lane is not an external one"
    assert {x["id"]: x["pane"] for x in queue.load()} == {"a": "%5", "b": "%2", "c": "%7", "w": "%3"}
    assert [r["detail"] for r in journal.read() if r.get("state") == "repane"] == ["a: pane %1 -> %5"]
    assert queue.repane(listing) == [], "a live pane is never moved again"


def test_no_tmux_on_the_path_is_nothing_to_re_point_never_an_error(state, monkeypatch):
    """The ladder runs these tests as the jail user, whose PATH has no tmux (L's red-on-base, 2026-11-03)."""
    monkeypatch.setenv("PATH", str(state))
    queue.save([{"id": "a", "kind": "external", "pane": "%1", "worktree": str(state), "cursor": 0, "steps": []}])
    assert queue.repane() == [] and queue.load()[0]["pane"] == "%1"
