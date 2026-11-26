"""#6589 reliab-1: the loop never sits idle with work queued. A parked cursor step, idle windows holding lane slots, a tick that
overwrites a manager's `queue park`, and a silent idle loop."""
from __future__ import annotations

import time

import pytest

from fichero_builder import journal, queue
from test_queue_verb import Fake, steps


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    monkeypatch.setattr(queue, "ONLY", [()])
    monkeypatch.setattr(queue, "DISPATCH", [()])
    monkeypatch.setattr(queue, "IDLE", {"since": 0.0, "alerted": set()})
    for n in ("1.1", "1.2", "x"):
        (tmp_path / f"b{n}").write_text(f"brief {n}")
    return tmp_path


def _tick(fake, handles=None, workers_n=1):
    return queue.tick(fake.procs, {} if handles is None else handles, workers_n=workers_n, push=False, out=lambda s: None)


def _set(lane_id, **by_step):
    lanes = queue.load()
    (ln,) = [x for x in lanes if x["id"] == lane_id]
    for st in ln["steps"]:
        if st["step"] in by_step:
            st["state"] = by_step[st["step"]]
    queue.save(lanes)


def test_a_cursor_on_a_parked_step_with_a_queued_step_behind_it_starts_the_queued_one(state):
    queue.add("m1", "/w/m1", "1.1", str(state / "b1.1"), [7])
    queue.add("m1", "/w/m1", "1.2", str(state / "b1.2"), [8], alone=True)
    _set("m1", **{"1.1": "parked"})
    fake = Fake()
    _tick(fake)
    assert [s[1] for s in fake.starts] == ["1.2"], "the queued step starts"
    assert [x["step"] for x in queue.load()[0]["steps"]] == ["1.2", "1.1"] and steps()["1.1"]["state"] == "parked", "the parked one waits at the end"
    assert [r["state"] for r in journal.read() if r.get("state") == "cursor-advanced"] == ["cursor-advanced"]


def test_seven_idle_windows_hold_no_slot_so_five_queued_steps_all_start(state):
    handles = {}
    for i in range(7):  # a session idle at a prompt: its step landed
        queue.add(f"idle{i}", f"/w/idle{i}", "1.1", str(state / "b1.1"), [i])
        lanes = queue.load()
        ln = next(x for x in lanes if x["id"] == f"idle{i}")
        ln["steps"][0]["state"], ln["cursor"] = "landed", 1
        queue.save(lanes)
        handles[f"idle{i}"] = object()
    for i in range(5):
        queue.add(f"q{i}", f"/w/q{i}", "1.1", str(state / "b1.1"), [100 + i])
    fake = Fake()
    _tick(fake, handles, workers_n=5)
    assert sorted(s[0] for s in fake.starts) == [f"q{i}" for i in range(5)], "all five start"
    assert sorted(fake.stops) == [f"idle{i}" for i in range(7)] and not any(k.startswith("idle") for k in handles), "the idle windows are closed"
    closed = [r for r in journal.read() if r.get("state") == "idle-window-closed"]
    assert sorted(r["lane"] for r in closed) == [f"idle{i}" for i in range(7)], "one row each"


def test_a_park_made_during_a_tick_survives_the_ticks_store(state):
    queue.add("m1", "/w/m1", "1.1", str(state / "b1.1"), [7])
    queue.add("m1", "/w/m1", "1.2", str(state / "b1.2"), [8], alone=True)
    fake = Fake()
    start = fake.start

    def start_and_park(lane, step):  # the manager parks 1.2 while the tick works on 1.1
        assert queue.reorder("m1", "1.2", "park") == ""
        return start(lane, step)
    fake.procs.start = start_and_park
    _tick(fake)
    assert steps()["1.1"]["state"] == "sent" and steps()["1.2"]["state"] == "parked", "the tick's store kept the park"


def test_a_drop_and_a_move_made_during_a_tick_survive_too(state):
    for n in ("1.1", "1.2"):
        queue.add("m1", "/w/m1", n, str(state / f"b{n}"), [1], alone=True)
    queue.add("m1", "/w/m1", "x", str(state / "bx"), [3], alone=True)
    _set("m1", **{"1.2": "parked"})
    lane = queue.load()[0]
    queue.snapshot(lane)  # the tick took its copy
    assert queue.reorder("m1", "1.2", "drop", why="superseded") == ""
    assert queue.reorder("m1", "x", "move", to=0) == ""
    lane["steps"][0]["why"] = "the tick touched 1.1"
    queue.store(lane)
    assert [x["step"] for x in queue.load()[0]["steps"]] == ["x", "1.1"], "the drop and the move stand"
    assert steps()["1.1"]["why"] == "the tick touched 1.1", "and the tick's own change is written"


def test_queued_work_and_nothing_running_for_ten_minutes_is_one_alert_naming_the_lane(state):
    queue.add("m1", "/w/m1", "1.1", str(state / "b1.1"), [7], waits=["gone"])
    queue.idle_alert(None)
    assert not [r for r in journal.read() if r["event"] == "alert"], "not yet"
    queue.IDLE["since"] = time.time() - queue.IDLE_S - 1
    for _ in range(3):
        queue.idle_alert(None)
    (a,) = [r for r in journal.read() if r["event"] == "alert"]
    assert "m1" in a["what"] and "gone" in a["what"], "it names the lane and why"
    _set("m1", **{"1.1": "sent"})
    queue.idle_alert(None)
    assert queue.IDLE["since"] == 0.0 and not queue.IDLE["alerted"], "a step in flight ends the idleness"


def test_a_paused_lane_or_a_disk_hold_explains_the_idleness_and_raises_nothing(state):
    queue.add("m1", "/w/m1", "1.1", str(state / "b1.1"), [7])
    lanes = queue.load()
    lanes[0]["paused"] = True
    queue.save(lanes)
    queue.IDLE["since"] = time.time() - queue.IDLE_S - 1
    queue.idle_alert(None)
    assert not [r for r in journal.read() if r["event"] == "alert"]
    queue.DISK_HELD[:] = ["m1"]  # the disk floor holds it instead
    lanes = queue.load()
    lanes[0]["paused"] = False
    queue.save(lanes)
    queue.idle_alert(None)
    queue.DISK_HELD.clear()
    assert not [r for r in journal.read() if r["event"] == "alert"], "a disk hold explains it"
    queue.IDLE["since"] = time.time() - queue.IDLE_S - 1
    queue.idle_alert(None)
    assert [r for r in journal.read() if r["event"] == "alert"], "control: with no hold the same state alerts"


def test_a_night_hold_the_drain_and_a_heavy_lock_explain_the_idleness_and_raise_nothing(state, monkeypatch):
    queue.add("m1", "/w/m1", "1.1", str(state / "b1.1"), [7])
    alerts = lambda: [r for r in journal.read() if r["event"] == "alert"]  # noqa: E731
    queue.IDLE["since"] = time.time() - queue.IDLE_S - 1
    lanes = queue.load()
    lanes[0]["steps"][0]["held"] = "night"
    queue.save(lanes)
    queue.idle_alert(None)
    assert not alerts(), "a night hold"
    lanes[0]["steps"][0].pop("held")
    queue.save(lanes)
    monkeypatch.setattr(queue, "DRAIN", [True])
    queue.idle_alert(None)
    assert not alerts(), "the drain"
    monkeypatch.setattr(queue, "DRAIN", [False])
    monkeypatch.setattr(journal, "manual_hold", lambda: "heavy: xcode")
    queue.idle_alert(None)
    assert not alerts(), "a heavy-lock hold"


def test_blocked_and_red_windows_keep_their_slot(state):
    handles = {}
    for i, st in enumerate(("blocked", "blocked")):
        queue.add(f"b{i}", f"/w/b{i}", "1.1", str(state / "b1.1"), [i])
        _set(f"b{i}", **{"1.1": st})
        handles[f"b{i}"] = object()
    queue.add("q0", "/w/q0", "1.1", str(state / "b1.1"), [100])
    fake = Fake()
    _tick(fake, handles, workers_n=2)
    assert not fake.starts, "two live blocked sessions fill a cap of two"
    assert not fake.stops


def test_a_red_window_counts_against_the_lanes_cap(state):
    # a tick moves a red step on at once, so the count is asserted on the step state itself
    queue.add("r0", "/w/r0", "1.1", str(state / "b1.1"), [1])
    queue.add("p0", "/w/p0", "1.1", str(state / "b1.1"), [2])
    _set("r0", **{"1.1": "red"})
    _set("p0", **{"1.1": "parked"})
    handles = {"r0": object(), "p0": object()}
    assert queue._working(handles) == 1, "the red window counts, the parked one does not"
