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
    queue.tick(fake.procs, {}, workers_n=1, push=False, out=lambda s: None)  # the old loop starts the session
    assert fake.starts and steps()["1.1"]["state"] == "sent"
    handles: dict = {}  # the restarted loop has no handle
    queue.tick(fake.procs, handles, workers_n=1, push=False, out=lambda s: None)
    return fake, handles


def test_a_restarted_loop_adopts_a_live_session_and_stops_nothing(state):
    fake, handles = _restarted_with_a_lost_handle(state, lambda ln: "adopted-handle")
    assert fake.stops == [] and handles == {"m1": "adopted-handle"} and steps()["1.1"]["state"] == "sent"
    assert [r["state"] for r in journal.read() if r.get("state") == "adopted"] == ["adopted"]


def test_a_restarted_loop_still_stops_a_session_it_cannot_adopt(state):
    fake, handles = _restarted_with_a_lost_handle(state, lambda ln: None)
    assert fake.stops == ["m1"] and handles == {} and steps()["1.1"]["state"] == "queued"


def test_adopt_session_takes_a_live_window_named_for_the_lane_with_a_fake_session(monkeypatch):
    j = types.SimpleNamespace(user="w", sudo="sudo")
    up = {"run": True, "cmd": "node"}
    monkeypatch.setattr(queue, "run_alive", lambda j_, feed: up["run"])
    monkeypatch.setattr(queue, "tmux_as_worker", lambda j_, *a: f"@1\tm1\t{up['cmd']}\n@2\tother\tnode\n")
    ln = {"id": "m1", "feed": "/f"}
    h = queue.adopt_session(j, ln)
    assert h is not None and h.poll() is None, "watched, and alive while the window is"
    up["run"] = False
    assert h.poll() == 0, "gone with its watcher"
    assert queue.adopt_session(j, ln) is None, "no `builder run` watching: not adopted"
    up.update(run=True, cmd="zsh")
    assert queue.adopt_session(j, ln) is None, "an idle shell is not a session"
    up["cmd"] = "node"
    assert queue.adopt_session(j, {"id": "m2", "feed": "/f"}) is None, "a window of another name is not this lane's"
    assert queue.adopt_session(j, {"id": "m1", "feed": ""}) is None and queue.adopt_session(None, ln) is None


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
