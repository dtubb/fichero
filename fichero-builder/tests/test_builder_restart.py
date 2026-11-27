"""#6589 dev-workflows.run.restart-resets-nothing: a builder restart resets no worker session. The workers start in their own session
and the loop's LaunchAgent abandons its process group; a restarted loop adopts a lane's live tmux window; harness.toml's [loop] is read
at every tick; and the loop re-execs only for a landing that changes the builder's own code."""
from __future__ import annotations

import plistlib
import types

import pytest

from fichero_builder import journal, queue
from test_queue_verb import Fake, lane, steps


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    monkeypatch.setattr(queue, "ONLY", [()])
    monkeypatch.setattr(queue, "DISPATCH", [()])
    for n in ("1.1", "1.2"):
        (tmp_path / f"b{n}").write_text(f"brief {n}")
    return tmp_path


def _restarted_with_a_lost_handle(state, adopt):
    lane(state)
    fake = Fake()
    fake.procs.adopt = adopt
    fake.procs.head_of, fake.procs.descends = (lambda ln: "h0"), (lambda ln, sha: sha == "h0")  # the session's step and head match the queue
    queue.tick(fake.procs, {}, workers_n=1, push=False, out=lambda s: None)  # the old loop starts the session
    assert fake.starts and steps()["1.1"]["state"] == "sent"
    handles: dict = {}  # the restarted loop has no handle
    queue.tick(fake.procs, handles, workers_n=1, push=False, out=lambda s: None)
    return fake, handles


def test_a_restarted_loop_adopts_a_live_session_and_stops_nothing(state):
    fake, handles = _restarted_with_a_lost_handle(state, lambda ln: "adopted-handle")
    assert fake.stops == [] and handles == {"m1": "adopted-handle"} and steps()["1.1"]["state"] == "sent"
    assert [r["state"] for r in journal.read() if r.get("state") == "adopted"] == ["adopted"]


def test_a_restarted_loop_still_stops_a_session_it_cannot_adopt(state, monkeypatch):
    fake, handles = _restarted_with_a_lost_handle(state, lambda ln: None)
    assert fake.stops == [] and steps()["1.1"]["state"] == "sent", "sent moments ago: still starting, never stopped at once"
    later = queue._now() + queue.START_GRACE_S + 1
    monkeypatch.setattr(queue, "_now", lambda: later)
    queue.tick(fake.procs, handles, workers_n=1, push=False, out=lambda s: None)
    assert fake.stops == ["m1"] and handles == {} and steps()["1.1"]["state"] == "queued", "past the grace with nothing to adopt: stopped"


def test_a_re_exec_while_a_session_is_still_starting_waits_for_it_and_adopts_it_once_it_shows(state, monkeypatch):
    """2026-11-27 12:14:52: the loop re-execed 40-90 s after sending seg-tools, training and perf-optimize; their sessions had no window,
    process id or watcher yet, and the restarted loop stopped all three as "the session this loop lost track of"."""
    shown = {"up": False}
    fake, handles = _restarted_with_a_lost_handle(state, lambda ln: "adopted" if shown["up"] else None)
    assert fake.stops == [] and steps()["1.1"]["state"] == "sent"
    queue.tick(fake.procs, handles, workers_n=1, push=False, out=lambda s: None)
    assert [r["state"] for r in journal.read() if r.get("state") == "start-wait"] == ["start-wait"], "one row, not one a tick"
    shown["up"] = True  # the session's window and watcher came up
    queue.tick(fake.procs, handles, workers_n=1, push=False, out=lambda s: None)
    assert fake.stops == [] and handles == {"m1": "adopted"} and steps()["1.1"]["state"] == "sent"


def test_adopt_session_takes_a_live_window_named_for_the_lane_with_a_fake_session(monkeypatch):
    j = types.SimpleNamespace(user="w", sudo="sudo")
    up = {"cmd": "node"}
    monkeypatch.setattr(queue, "tmux_as_worker", lambda j_, *a: f"@1\tm1\t{up['cmd']}\n@2\tother\tnode\n" if up["cmd"] else "")
    monkeypatch.setattr(queue, "pid_alive", lambda pid: False)
    watched = {"on": True}
    monkeypatch.setattr(queue, "run_alive", lambda j_, feed: watched["on"])
    ln = {"id": "m1", "feed": "/f"}
    h = queue.adopt_session(j, ln)
    assert h is not None and h.poll() is None, "alive while the window is"
    up["cmd"] = ""
    assert h.poll() == 0, "gone with its window"
    up["cmd"] = "node"
    watched["on"] = False
    assert queue.adopt_session(j, ln) is None, "no `builder run` on its feed: not adopted, the #6850 alert says so"
    watched["on"] = True
    up["cmd"] = "zsh"
    assert queue.adopt_session(j, ln) is None, "an idle shell is not a session"
    up["cmd"] = "node"
    assert queue.adopt_session(j, {"id": "m2", "feed": "/f"}) is None, "a window of another name is not this lane's"
    assert queue.adopt_session(None, ln) is None


def test_a_re_exec_with_five_live_windows_adopts_five_and_stops_none(state, monkeypatch):
    """#6589 local.run.reexec-adopts-by-window-or-pid: no `builder run` on any feed, five lanes whose window runs a session."""
    j = types.SimpleNamespace(user="w", sudo="sudo")
    monkeypatch.setattr(queue, "tmux_as_worker", lambda j_, *a: "".join(f"@{i}\tm{i}\tnode\n" for i in range(1, 6)))
    monkeypatch.setattr(queue, "pid_alive", lambda pid: False)
    monkeypatch.setattr(queue, "run_alive", lambda j_, feed: True)
    handles = [queue.adopt_session(j, {"id": f"m{i}", "feed": "/f"}) for i in range(1, 6)]
    assert all(h is not None and h.poll() is None for h in handles), "five adopted"
    fake, hs = _restarted_with_a_lost_handle(state, lambda ln: queue.adopt_session(j, {**ln, "id": "m1", "feed": "/f"}))
    assert fake.stops == [] and "m1" in hs and steps()["1.1"]["state"] == "sent", "none stopped, the step keeps its state"
    assert [r["state"] for r in journal.read() if r.get("state") == "adopted"] == ["adopted"], "one adopted row"


def test_a_live_process_id_with_a_renamed_window_is_adopted(monkeypatch):
    j = types.SimpleNamespace(user="w", sudo="sudo")
    alive = {"pid": True}
    monkeypatch.setattr(queue, "tmux_as_worker", lambda j_, *a: "@1\trenamed\tnode\n")
    monkeypatch.setattr(queue, "pid_alive", lambda pid: alive["pid"] and pid == 4242)
    monkeypatch.setattr(queue, "run_alive", lambda j_, feed: True)
    h = queue.adopt_session(j, {"id": "m1", "feed": "/f", "session_pid": 4242})
    assert h is not None and h.poll() is None
    alive["pid"] = False
    assert h.poll() == 0


def test_a_lane_with_neither_a_live_window_nor_a_live_process_is_queued_once(state, monkeypatch):
    j = types.SimpleNamespace(user="w", sudo="sudo")
    monkeypatch.setattr(queue, "tmux_as_worker", lambda j_, *a: "")
    monkeypatch.setattr(queue, "pid_alive", lambda pid: False)
    monkeypatch.setattr(queue, "run_alive", lambda j_, feed: True)
    fake, handles = _restarted_with_a_lost_handle(state, lambda ln: queue.adopt_session(j, ln))
    later = queue._now() + queue.START_GRACE_S + 1  # past the start-up grace: nothing came up
    monkeypatch.setattr(queue, "_now", lambda: later)
    queue.tick(fake.procs, handles, workers_n=1, push=False, out=lambda s: None)
    assert fake.stops == ["m1"] and handles == {} and steps()["1.1"]["state"] == "queued"
    assert len([r for r in journal.read() if r.get("state") == "queued" and "lost track" in r.get("detail", "")]) == 1


def test_start_records_the_process_id_the_lane_can_be_adopted_by(state):
    lane(state)
    fake = Fake()
    fake.start = lambda ln, st: types.SimpleNamespace(pid=4242, poll=lambda: None)
    fake.procs.start = fake.start
    queue.tick(fake.procs, {}, workers_n=1, push=False, out=lambda s: None)
    assert queue.load()[0]["session_pid"] == 4242


def test_the_loop_agent_abandons_its_process_group_so_a_kickstart_leaves_the_workers(state):
    loop, heartbeat, console, _release = (plistlib.loads(p.read_bytes()) for p in queue.launch_agents("/r", state / "la", state=state / "s", branch="main"))
    assert loop["AbandonProcessGroup"] is True and "AbandonProcessGroup" not in heartbeat


def test_harness_toml_loop_is_read_at_every_tick_so_a_new_lane_needs_no_restart(state):
    (state / "harness.toml").write_text('[loop]\nonly = ["m1"]\n')
    fake = Fake()
    fake.procs.root = str(state)
    out = lambda s: None  # noqa: E731
    queue.run(fake.procs, workers_n=1, push=False, once=True, out=out)
    assert queue.ONLY[0] == ("m1",)
    (state / "harness.toml").write_text('[loop]\nonly = ["m1", "m2"]\ndispatch = ["m2"]\n')
    queue.run(fake.procs, workers_n=1, push=False, once=True, out=out)
    assert queue.ONLY[0] == ("m1", "m2") and queue.DISPATCH[0] == ("m2",)
    (state / "harness.toml").write_text("[loop\nbroken")
    queue.run(fake.procs, workers_n=1, push=False, once=True, out=out)
    assert queue.ONLY[0] == ("m1", "m2"), "an unreadable file keeps what was set"


def test_a_rules_edit_alone_is_not_a_re_exec_and_a_changed_package_is_even_with_a_live_session(state, monkeypatch):
    (state / "harness.toml").write_text("[loop]\nonly = []\n")
    mark = queue.code_mark(state)
    (state / "harness.toml").write_text("[loop]\nonly = ['x']\n")
    assert queue.code_mark(state) == mark and not queue.restart_due(mark, state, None), "a rules edit is read next tick, never a restart"
    monkeypatch.setattr(queue, "code_mark", lambda root="": ("changed",))
    assert queue.restart_due(mark, state, None), "a landing under fichero-builder/ re-execs; a live worker session no longer holds it off"
    busy = types.SimpleNamespace(done=lambda: False)
    assert not queue.restart_due(mark, state, {"pool": object(), "m1": busy}), "a running check still holds it off"
    assert not queue.restart_due(mark, state, None, [types.SimpleNamespace(is_alive=lambda: True)]), "so does a dev build"


def test_a_live_window_the_loop_cannot_adopt_is_one_alert_with_its_id_and_is_never_stopped(state):
    """#6850: a window that runs more than a shell is never ended by the lost-track branch, and never queued again beside itself."""
    lane(state)
    fake = Fake()
    fake.procs.adopt = lambda ln: None
    fake.procs.live_windows = lambda ln: ["@7"]
    queue.tick(fake.procs, {}, workers_n=1, push=False, out=lambda s: None)  # the old loop starts the session
    fake.seqs.clear()  # the session has said nothing yet
    handles: dict = {}  # the restarted loop has no handle
    for _ in range(3):
        queue.tick(fake.procs, handles, workers_n=1, push=False, out=lambda s: None)
    assert fake.stops == [] and steps()["1.1"]["state"] == "sent", "the session is left running and the step keeps its state"
    (a,) = [r for r in journal.read() if r["event"] == "alert"]
    assert "@7" in a["what"] and a["lane"] == "m1" and a["step"] == "1.1", "one alert, with the window's id, lane and step"


def test_a_step_that_was_checking_before_a_restart_still_gets_the_automatic_split(state):
    """#6850: the restarted loop has no handle for the lane; a red on the file bound still splits the step."""
    lane(state)
    over = {"ok": False, "kind": "red", "why": "red", "findings": "failed rung: diff-bound\ndiff bound: 40 files, over 25"}
    fake = Fake(chains={"1.1": [over]})
    fake.procs.push_part2 = lambda the_lane, branch: (0, "abc1234 the rest")
    queue.tick(fake.procs, {}, workers_n=1, push=False, out=lambda s: None)  # the old loop starts the session
    lanes = queue.load()
    lanes[0]["steps"][0].update(state="checking", head="h1.1")  # it was checking when the loop went down
    queue.save(lanes)
    queue.run(fake.procs, workers_n=1, push=True, out=lambda s: None)  # the restarted loop: no handles
    assert "1.1-part2" in steps() and "m1-part2" in fake.sent[-1] + "".join(fake.sent)


def test_a_restarted_loop_attaches_a_new_watcher_to_a_live_window_instead_of_alerting(state):
    """local.run.sessions-survive-watchers: five "this loop cannot watch it" alerts on 2026-11-25; the session is watched again."""
    lane(state)
    fake = Fake()
    fake.procs.adopt = lambda ln: None
    fake.procs.live_windows = lambda ln: ["@7"]
    attached = []
    fake.procs.attach = lambda ln, st, w: attached.append((ln["id"], st["step"], st["state"], w)) or "watcher-2"
    fake.procs.head_of, fake.procs.descends = (lambda ln: "h0"), (lambda ln, sha: sha == "h0")
    queue.tick(fake.procs, {}, workers_n=1, push=False, out=lambda s: None)
    fake.seqs.clear()
    handles: dict = {}
    queue.tick(fake.procs, handles, workers_n=1, push=False, out=lambda s: None)
    assert attached == [("m1", "1.1", "sent", "@7")] and handles == {"m1": "watcher-2"}
    assert fake.stops == [] and steps()["1.1"]["state"] == "sent" and not [r for r in journal.read() if r["event"] == "alert"]
    assert [r["detail"][:30] for r in journal.read() if r.get("state") == "attached"] == ["a restarted loop found the ses"]


def test_a_watcher_that_exits_while_its_session_lives_is_re_attached_with_no_restart(state):
    """2026-11-25: the loop ran from 11:12 with no restart, and run-seg-tools.log ended at 11:24 with `seg-tools: gone` while the
    session lived on; the step was queued again beside it. Now the session gets a new watcher and the step stays sent."""
    lane(state)
    fake = Fake()
    fake.procs.live_windows = lambda ln: ["@7"]
    fake.procs.attach = lambda ln, st, w: "watcher-2"
    handles: dict = {}
    queue.tick(fake.procs, handles, workers_n=1, push=False, out=lambda s: None)
    _feed("/w/feed")
    fake.seqs.clear()
    fake.alive_now = False  # the watcher process is gone; the window is not
    queue.tick(fake.procs, handles, workers_n=1, push=False, out=lambda s: None)
    assert handles == {"m1": "watcher-2"} and steps()["1.1"]["state"] == "sent" and steps()["1.1"]["restarts"] == 0
    assert len(fake.starts) == 1, "no second session beside the live one"


def test_an_idle_session_after_done_gets_no_new_watcher_and_its_ready_chain_is_collected(state):
    """2026-11-25, seg-inspector swift-green-2: READY at 14:52, then 64 "watcher ended ... a new watcher on window @22" rows to 15:29.
    The session idled after DONE, so each new watcher ended at once, and the re-attach's `return` came before the finished chain was
    collected: the READY never landed. Past `sent` the watcher is not replaced, the feed stays, and the READY lands that tick."""
    from concurrent.futures import Future, ThreadPoolExecutor
    lane(state)
    fake = Fake()
    fake.procs.live_windows = lambda ln: ["@22"]
    attached = []
    fake.procs.attach = lambda ln, st, w: attached.append(st["state"]) or "watcher-2"
    handles: dict = {}
    queue.tick(fake.procs, handles, workers_n=1, push=False, out=lambda s: None)
    _feed("/w/feed")
    lanes = queue.load()
    lanes[0]["steps"][0]["state"] = "reviewing"
    queue.save(lanes)
    ready: Future = Future()
    ready.set_result({"ok": True, "head": "bf62549fc" + "0" * 31})
    ready.head = ""  # a worker lane's step has no head until its chain is green
    chains = {"pool": ThreadPoolExecutor(max_workers=1), "m1": ready}
    fake.alive_now = False  # the watcher read the old DONE and ended; the window lives
    queue.tick(fake.procs, handles, workers_n=1, push=False, out=lambda s: None, chains=chains)
    assert attached == [] and "m1" not in handles, "no watcher for an idle session past its DONE"
    assert fake.landed_calls == [("bf62549fc" + "0" * 31, False)], "the READY chain is collected the same tick"
    assert not [r for r in journal.read() if r.get("state") == "attached"]


def test_a_kept_session_with_no_step_out_and_no_watcher_is_closed_and_the_step_sent_afresh(state):
    lane(state)
    fake = Fake()
    fake.procs.adopt = lambda ln: None
    windows = ["@7"]
    fake.procs.live_windows = lambda ln: list(windows)
    queue.tick(fake.procs, {}, workers_n=1, push=False, out=lambda s: None)
    lanes = queue.load()
    lanes[0]["steps"][0]["state"] = "queued"  # the session idles at its prompt: nothing in flight
    lanes[0]["feed"] = "/w/feed"
    queue.save(lanes)
    queue.tick(fake.procs, {}, workers_n=1, push=False, out=lambda s: None)
    assert fake.stops == ["m1"] and [r for r in journal.read() if r.get("state") == "window-closed"]
    assert not [r for r in journal.read() if r["event"] == "alert"]


def test_said_done_records_a_managed_lanes_missed_done_at_its_trees_head_only(state):
    """2026-11-25: `builder done` refuses a managed lane ("no external lane"); seven retries were spent on DONEs no watcher read."""
    from fichero_builder import __main__ as cli
    lane(state)
    fake = Fake()
    queue.tick(fake.procs, {}, workers_n=1, push=False, out=lambda s: None)
    head = lambda ln: "eab0a2072e0000"  # noqa: E731
    assert queue.said_done("m1", "1.1", "23462609bb", head) == "m1's tree is at eab0a2072, not 23462609b"
    assert queue.said_done("m1", "1.2", "eab0a2072e", head) == "'1.2' is not m1's cursor step"
    assert queue.said_done("m1", "1.1", "eab0a2072e", head) == ""
    assert steps()["1.1"]["state"] == "done"
    assert queue.said_done("m1", "1.1", "eab0a2072e", head) == "m1 1.1 is done, not sent"
    assert cli.main(["queue", "said-done", "--lane", "m1", "--step", "1.1", "--sha", "zz", "--state", str(journal.STATE)]) == 1


def _feed(path):
    lanes = queue.load()
    lanes[0]["feed"] = path
    queue.save(lanes)


def test_said_done_on_a_blocked_step_is_taken_for_a_new_sha_and_refused_for_the_one_it_was_blocked_at(state):
    """2026-11-26: the worker resolved a rebase conflict and said DONE, but `queue said-done` refused while the step was blocked."""
    lane(state)
    fake = Fake()
    queue.tick(fake.procs, {}, workers_n=1, push=False, out=lambda s: None)
    lanes = queue.load()
    lanes[0]["steps"][0].update(state="blocked", head="a84451832" + "0" * 31, why="rebase onto origin/integration stopped on a conflict in f")
    queue.save(lanes)
    old = lambda ln: "a84451832" + "0" * 31  # noqa: E731
    assert "blocked" in queue.said_done("m1", "1.1", "a84451832", old), "the sha it was blocked at: refused"
    new = lambda ln: "bbbbbbbbbb" + "0" * 30  # noqa: E731
    assert queue.said_done("m1", "1.1", "bbbbbbbbbb", new) == "" and steps()["1.1"]["state"] == "done"


def test_run_alive_finds_a_watcher_whose_command_line_holds_the_feed(tmp_path):
    """2026-11-27: `pgrep -f "--feed <dir>"` read the pattern as an option ("illegal option -- -", exit 2), so no watcher was ever
    found: a restarted loop never adopted, and attached a second and a third watcher to kg-readable-representation's one window."""
    import getpass
    import subprocess
    import sys
    feed = str(tmp_path / "inbox-x-1")
    j = types.SimpleNamespace(user=getpass.getuser(), sudo="sudo")
    p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)", "--feed", feed])
    try:
        assert queue.run_alive(j, feed) is True
        assert queue.run_alive(j, feed + "-other") is False
    finally:
        p.kill()
        p.wait()
    assert queue.run_alive(j, "") is False


def test_a_restarted_loop_never_attaches_a_second_watcher_to_a_session_one_already_watches(state):
    lane(state)
    fake = Fake()
    fake.procs.live_windows = lambda ln: ["@4"]
    attached = []
    fake.procs.attach = lambda ln, s, w: attached.append(w) or "h"
    s = {"step": "1.1"}
    fake.procs.watched = lambda ln: True
    assert queue.attach_live({"id": "m1"}, s, fake.procs, "a restarted loop found the session with no watcher") is None and attached == []
    assert [r["state"] for r in journal.read() if r.get("state") == "attach-refused"] == ["attach-refused"]
    fake.procs.watched = lambda ln: False
    assert queue.attach_live({"id": "m1"}, s, fake.procs, "its watcher ended") == "h" and attached == ["@4"]
