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


def test_the_agents_run_unbuffered_so_loop_log_is_current(state):
    """#6466: launchd block-buffers stdout, so loop.log lagged the journal by hours; every agent runs with PYTHONUNBUFFERED."""
    for p in queue.launch_agents("/r", state / "la", state=state / "s"):
        assert plistlib.loads(p.read_bytes())["EnvironmentVariables"]["PYTHONUNBUFFERED"] == "1", p.name


def test_a_dead_pane_with_no_session_to_take_marks_the_lane_no_session_once_with_an_alert_and_dispatch_hands_it_to_the_loop(state, monkeypatch):
    """#6500: a lane whose registered pane is gone and whose worktree holds no Claude session was idle forever with no row. Now:
    pane cleared, `no_session` stamped, one `queue` row and one alert (dispatch, park); the next tick is quiet; a session that appears
    later is taken and the mark cleared; `dispatch` makes the loop manage the lane (as [loop].dispatch would)."""
    wa = str(state / "a")
    os.mkdir(wa)
    (state / "b1.1").write_text("brief")
    queue.add("a", wa, "batch-1", str(state / "b1.1"), [7], kind="external", pane="%1")
    assert queue.repane("%6\tzsh\t" + wa) == ["a: pane %1 gone, no session in its tree: no-session"]
    x = queue.load()[0]
    assert x["pane"] == "" and x["no_session"]
    rows = [r for r in journal.read() if r.get("state") == "no-session"]
    a = [r for r in journal.read() if r["event"] == "alert"]
    assert len(rows) == 1 and len(a) == 1 and a[0]["actions"] == ["dispatch", "park"] and "nobody is on it" in a[0]["what"]
    assert queue.repane("%6\tzsh\t" + wa) == [] and len([r for r in journal.read() if r["event"] == "alert"]) == 1, "once"
    assert queue.repane(f"%9\t2.1.317\t{wa}") == ["a: pane  -> %9"] and "no_session" not in queue.load()[0], "a session that appears is taken"
    queue.repane("%6\tzsh\t" + wa)
    aid = [r for r in journal.read() if r["event"] == "alert"][-1]["id"]
    assert queue.answer(aid, "dispatch")[0] == 0 and queue.load()[0].get("dispatch") is True
    from test_queue_verb import Fake
    monkeypatch.setattr(queue, "DISPATCH", [()])
    fake = Fake()
    fake.procs.workroot = str(state / "wr")
    queue.run(fake.procs, workers_n=1, push=True, out=lambda s: None)
    x = queue.load()[0]
    assert x["kind"] == "worker" and "no_session" not in x and fake.starts == [("a", "batch-1", 1)], "the loop runs it as a managed lane"


def test_a_no_session_alert_is_one_per_lane_per_day_and_none_for_a_lane_whose_step_is_not_queued(state):
    """2026-11-10 (lead, after #6500 deployed): six alerts fired at the first tick. A lane whose cursor step is not `queued` (done,
    checking, blocked: nothing a session would do now) gets none; a lane gets at most one a day while nobody is on it."""
    wa, wb = str(state / "a"), str(state / "b")
    os.mkdir(wa), os.mkdir(wb)
    (state / "b1.1").write_text("brief")
    queue.add("a", wa, "batch-1", str(state / "b1.1"), [7], kind="external", pane="%1")
    queue.add("b", wb, "batch-1", str(state / "b1.1"), [8], kind="external", pane="%2")
    lanes = queue.load()
    next(x for x in lanes if x["id"] == "b")["steps"][0]["state"] = "done"
    queue.save(lanes)
    listing = f"%6\tzsh\t{wa}\n%7\tzsh\t{wb}"
    queue.repane(listing)
    alerts = lambda: [r for r in journal.read() if r["event"] == "alert"]  # noqa: E731
    assert [r["lane"] for r in alerts()] == ["a"], "b's step is done: no session would move it; no alert"
    queue.repane(listing)
    assert len(alerts()) == 1, "the same day: no second alert"
    lanes = queue.load()
    next(x for x in lanes if x["id"] == "a")["no_session"] = "2026-11-09T08:23:00"
    queue.save(lanes)
    queue.repane(listing)
    assert [r["lane"] for r in alerts()] == ["a", "a"] and queue.load()[0]["no_session"] > "2026-11-10", "a day later, still nobody: one more, stamped today"
