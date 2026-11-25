"""local.watchdog.slow-work (#6589): the loop notices work taking too long and acts once per cause: one alert with the evidence and
the action (a nudge), then, one period later, the session stopped and the step retried once. Fakes only."""
from __future__ import annotations

import pytest

from fichero_builder import journal, watchdog

T0 = 1_800_000_000.0


def _ts(epoch: float) -> str:
    from datetime import datetime
    return datetime.fromtimestamp(epoch).isoformat(timespec="seconds")


class World:
    def __init__(self, tmp_path):
        self.alerts, self.nudges, self.retries, self.cancels = [], [], [], []
        self.state = tmp_path / "watchdog.json"
        self.output: dict = {}

    def run(self, lanes, rows, now, median=lambda rows, lane: 600.0, timeout=lambda r: 0.0, only=(), loop_start=0.0, delivered=""):
        return watchdog.check(lanes, rows, now, last_output=lambda lane: self.output.get(lane["id"]), rung_timeout=timeout,
                              nudge=lambda lane, text: self.nudges.append((lane["id"], text)) or delivered, only=only, loop_start=loop_start,
                              stop_retry=lambda lane, step, aid: self.retries.append((lane, step, aid)) or "",
                              cancel=self.cancels.append, alert=lambda lane, step, why: self.alerts.append((lane, step, why)) or f"a{len(self.alerts)}",
                              state=self.state, median=median)


@pytest.fixture
def w(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    return World(tmp_path)


def lanes(state="sent", head="bbbbbbbbbbbb"):
    return [{"id": "l1", "cursor": 0, "steps": [{"step": "s1", "state": state, "head": head}]}]


SENT = [{"event": "queue", "lane": "l1", "step": "s1", "state": "sent", "ts": _ts(T0)}]


def test_a_step_past_twice_its_lanes_median_is_one_alert_with_a_nudge_then_a_stop_and_one_retry(w):
    assert w.run(lanes(), SENT, T0 + 1100) == [], "under 2x the 600 s median: nothing"
    did = w.run(lanes(), SENT, T0 + 1300)
    assert len(w.alerts) == 1 and "past 2x the lane's median land time (10 min)" in w.alerts[0][2] and "action: nudged the session" in w.alerts[0][2]
    assert w.nudges and w.nudges[0][0] == "l1" and did
    w.run(lanes(), SENT, T0 + 1500)
    assert len(w.alerts) == 1 and w.retries == [], "one alert per cause; the second strike waits one more median"
    w.run(lanes(), SENT, T0 + 1300 + 600)
    assert w.retries == [("l1", "s1", "a1")]
    rows = [r for r in journal.read() if r["event"] == "watchdog"]
    assert len(rows) == 1 and rows[0]["alert"] == "a1" and "stopped the session" in rows[0]["detail"]
    w.run(lanes(), SENT, T0 + 9000)
    assert len(w.alerts) == 1 and len(w.retries) == 1, "after the retry the cause is left to the person"


def test_a_session_with_no_output_for_twenty_minutes_is_nudged(w):
    w.output["l1"] = T0
    w.run(lanes(), [], T0 + 19 * 60, median=lambda rows, lane: None)
    assert w.alerts == []
    w.run(lanes(), [], T0 + 21 * 60, median=lambda rows, lane: None)
    assert len(w.alerts) == 1 and "no output for 21 min" in w.alerts[0][2] and len(w.nudges) == 1


def test_a_step_not_running_is_never_watched(w):
    w.output["l1"] = T0
    for st in ("queued", "landed", "parked", "blocked", "red"):
        w.run(lanes(st), SENT, T0 + 99999)
    assert w.alerts == [] and w.nudges == []


def test_a_rung_past_its_timeout_is_named_then_its_ladder_cancelled_and_the_step_retried(w):
    """A rung with no figure of its own (guards: guard_timeout_s is per guard) gets RUNG_S, one hour; the alert of 2026-11-25 said 1 min."""
    rows = [{"event": "activity", "kind": "check", "key": "check aaaaaaaaa..bbbbbbbbb", "state": "rung-start", "rung": "guards", "lane": "l1", "ts": _ts(T0)}]
    w.run(lanes("checking"), rows, T0 + 59 * 60, median=lambda rows, lane: None, timeout=lambda r: 60.0)
    assert w.alerts == [], "never under an hour, whatever the figure"
    w.run(lanes("checking"), rows, T0 + 61 * 60, median=lambda rows, lane: None)
    assert len(w.alerts) == 1 and "guards rung" in w.alerts[0][2] and "past its 60 min timeout" in w.alerts[0][2] and w.nudges == [] and w.cancels == []
    w.run(lanes("checking"), rows, T0 + 61 * 60 + 3600, median=lambda rows, lane: None)
    assert w.cancels == ["bbbbbbbbb"] and w.retries == [("l1", "s1", "a1")]


def test_a_rung_with_a_longer_figure_waits_for_it(w):
    rows = [{"event": "activity", "kind": "check", "key": "check aaaaaaaaa..bbbbbbbbb", "state": "rung-start", "rung": "build", "lane": "l1", "ts": _ts(T0)}]
    w.run(lanes("checking"), rows, T0 + 90 * 60, median=lambda rows, lane: None, timeout=lambda r: 7200.0)
    assert w.alerts == []
    w.run(lanes("checking"), rows, T0 + 121 * 60, median=lambda rows, lane: None, timeout=lambda r: 7200.0)
    assert len(w.alerts) == 1 and "past its 120 min timeout" in w.alerts[0][2]


def test_the_slow_clock_starts_at_the_latest_sent_row(w):
    """A retry or restart sends the step again: it is timed from then, not from its first send days ago."""
    rows = [*SENT, {"event": "queue", "lane": "l1", "step": "s1", "state": "sent", "ts": _ts(T0 + 86400)}]
    w.run(lanes(), rows, T0 + 86400 + 1100)
    assert w.alerts == []
    w.run(lanes(), rows, T0 + 86400 + 1300)
    assert len(w.alerts) == 1 and "has run 22 min" in w.alerts[0][2]


def test_a_slow_step_with_no_session_is_said_and_never_escalates(w):
    """2026-11-25: a nudge to a lane with no window said "not delivered: no window" and still counted a strike. With no session
    there is nothing to nudge or stop: the alert says so (the sent-with-no-live-session case) and there is no stop and retry."""
    w.run(lanes(), SENT, T0 + 1300, delivered="no window")
    assert len(w.alerts) == 1 and "no live session to nudge (no window)" in w.alerts[0][2] and "nudged" not in w.alerts[0][2]
    w.run(lanes(), SENT, T0 + 9000, delivered="no window")
    assert w.retries == [] and len(w.alerts) == 1 and not [r for r in journal.read() if r["event"] == "watchdog"]


def test_the_dead_rows_of_2026_11_25_and_lanes_the_loop_does_not_run_raise_nothing_and_one_live_slow_step_does(w):
    """The first live tick raised 22 false alerts: slow steps in paused, parked or not-run lanes (kg-store-and-query 2.4 at 3801
    min), and rung-starts of checks that died with a loop restart days before (lane-onboard red-on-base at 32736 min)."""
    now = T0 + 40000 * 60
    loop_start = now - 600
    ls = [{"id": "kg-store-and-query", "cursor": 0, "paused": True, "steps": [{"step": "2.4", "state": "sent", "head": "111111111aaa"}]},
          {"id": "kg-readable-representation", "cursor": 0, "steps": [{"step": "2.1", "state": "sent", "head": "222222222aaa"}]},  # not in only
          {"id": "ios-nav", "cursor": 0, "steps": [{"step": "nav-3", "state": "parked", "head": "333333333aaa"}]},
          {"id": "training", "cursor": 0, "hold": True, "steps": [{"step": "1b", "state": "queued"}]},
          {"id": "lane-onboard", "cursor": 0, "steps": [{"step": "o1", "state": "checking", "head": "444444444aaa"}]},
          {"id": "ux", "cursor": 0, "steps": [{"step": "u1", "state": "checking", "head": "555555555new"}]},
          {"id": "live", "cursor": 0, "steps": [{"step": "l1", "state": "sent", "head": "666666666aaa"}]}]
    only = ("kg-store-and-query", "ios-nav", "training", "lane-onboard", "ux", "live")
    old = now - 32736 * 60
    rows = [{"event": "queue", "lane": x["id"], "step": x["steps"][0]["step"], "state": "sent", "ts": _ts(now - 3801 * 60)} for x in ls[:4]]
    rows += [{"event": "activity", "kind": "check", "key": "check 000000000..444444444", "state": "rung-start", "rung": "red-on-base", "lane": "lane-onboard", "ts": _ts(old)},
             {"event": "activity", "kind": "check", "key": "check 000000000..555555555", "state": "rung-start", "rung": "guards", "lane": "ux", "ts": _ts(old)},
             {"event": "activity", "kind": "check", "key": "check 000000000..999999999", "state": "rung-start", "rung": "guards", "lane": "lane-ie", "ts": _ts(old)},
             {"event": "activity", "kind": "check", "key": "check 000000000..888888888", "state": "rung-start", "rung": "perf", "lane": "ux", "ts": _ts(now - 500)}]
    w.run(ls[:-1], rows, now, only=only, loop_start=loop_start)
    w.run(ls[:-1], rows, now + 86400, only=only, loop_start=loop_start)
    assert w.alerts == [] and w.nudges == [], "zero: no lane the loop runs is slow, and no rung is of a current check"
    rows.append({"event": "queue", "lane": "live", "step": "l1", "state": "sent", "ts": _ts(now - 1300)})
    w.run(ls, rows, now, only=only, loop_start=loop_start)
    assert [(a[0], a[1]) for a in w.alerts] == [("live", "l1")]


def test_a_rung_that_ended_is_not_open():
    rows = [{"event": "activity", "kind": "check", "key": "k", "state": "rung-start", "rung": "guards", "ts": _ts(T0)},
            {"event": "activity", "kind": "check", "key": "k", "state": "rung", "rung": "guards", "ts": _ts(T0 + 5)},
            {"event": "activity", "kind": "check", "key": "k2", "state": "rung-start", "rung": "build", "ts": _ts(T0)},
            {"event": "activity", "kind": "check", "key": "k2", "state": "end", "ts": _ts(T0 + 9)}]
    assert watchdog.open_rungs(rows) == []


def test_a_cause_that_ends_is_forgotten_and_a_new_episode_is_a_new_alert(w):
    w.output["l1"] = T0
    w.run(lanes(), [], T0 + 21 * 60, median=lambda rows, lane: None)
    w.output["l1"] = T0 + 22 * 60  # the nudge worked
    w.run(lanes(), [], T0 + 23 * 60, median=lambda rows, lane: None)
    assert w.retries == [] and "silent:l1:s1" not in (w.state.read_text())


def test_the_tick_runs_the_watchdog_and_an_error_in_it_is_a_row(tmp_path, monkeypatch):
    from fichero_builder import queue
    from test_queue_verb import Fake

    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    fake = Fake(chains={})
    seen = []
    fake.procs.watchdog = lambda ls: seen.append(len(ls)) or ["did one thing"]
    said = []
    queue.tick(fake.procs, {}, workers_n=1, push=False, out=said.append)
    assert seen and "watchdog: did one thing" in said
    fake.procs.watchdog = lambda ls: 1 / 0
    queue.tick(fake.procs, {}, workers_n=1, push=False, out=said.append)
    assert any(r.get("state") == "watchdog-error" for r in journal.read())


def test_the_real_watchdog_builds_from_the_rules_and_does_nothing_with_nothing_slow(tmp_path, monkeypatch):
    from fichero_builder import queue

    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    (tmp_path / "harness.toml").write_text('[check]\nguard_timeout_s = 120\n')
    run = queue.real_watchdog(tmp_path, stop=lambda lane: None, tell=lambda lane, text: "")
    assert run([{"id": "l1", "cursor": 1, "steps": [{"step": "s1", "state": "landed"}]}]) == []
