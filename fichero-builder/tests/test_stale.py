"""builder-console.stale.acted-on (#6646): a step older than its state's hours gets one action and one `stale` row per tick."""
from __future__ import annotations

import pytest
import test_queue_verb as tq

from fichero_builder import journal, queue, stale

lane, steps = tq.lane, tq.steps
state = tq.state  # the fixture

T0 = 1_000_000.0


class _Fut:
    def __init__(self, done):
        self._d = done

    def done(self):
        return self._d


def _step(**kw):
    ln = queue.load()
    ln[0]["steps"][0].update(kw)
    queue.save(ln)


@pytest.fixture(autouse=True)
def _clock(monkeypatch):
    monkeypatch.setattr(queue, "BLOCKED_H", [10_000.0])
    monkeypatch.setattr(queue, "_gh_quiet", lambda gh, args, cwd=None: "")


def _rows():
    return [r for r in journal.read() if r["event"] == "stale"]


def test_each_state_past_its_hours_gets_its_action_and_row_and_a_step_under_its_hours_none(state):
    lane(state)
    _step(state="done", entered_at=T0)  # said-done
    assert stale.act(queue.load()[0], q=queue, chains={}, hours=stale.HOURS, now=T0 + 0.5 * 3600) is None
    assert _rows() == [] and steps()["1.1"]["state"] == "done", "30 minutes is under the 1 h of said-done: untouched"
    assert stale.act(queue.load()[0], q=queue, chains={"m1": _Fut(True)}, hours=stale.HOURS, now=T0 + 2 * 3600) == "run-check"
    (r,) = _rows()
    assert (r["step"], r["state"], r["action"]) == ("1.1", "said-done", "run-check") and r["age_h"] == 2.0

    _step(state="checking", entered_at=T0, stale_at=0.0, stale_n=0)
    assert stale.act(queue.load()[0], q=queue, chains={"m1": _Fut(False)}, hours=stale.HOURS, now=T0 + 4 * 3600) is None, "a live check is left alone"
    assert stale.act(queue.load()[0], q=queue, chains={}, hours=stale.HOURS, now=T0 + 4 * 3600) == "restart"
    assert steps()["1.1"]["state"] == "done"


def test_a_red_step_is_re_briefed_once_then_blocked_with_an_alert(state):
    lane(state)
    _step(state="blocked", red_head="abc", why="pytest: test_x failed", entered_at=T0)
    assert stale.act(queue.load()[0], q=queue, chains={}, hours=stale.HOURS, now=T0 + 13 * 3600) == "re-brief"
    s = steps()["1.1"]
    assert s["state"] == "queued" and "test_x failed" in open(s["resume_brief"]).read()
    _step(state="blocked", red_head="def", entered_at=T0 + 13 * 3600)
    assert stale.act(queue.load()[0], q=queue, chains={}, hours=stale.HOURS, now=T0 + 27 * 3600) == "block"
    assert steps()["1.1"]["state"] == "blocked" and [r for r in journal.read() if r["event"] == "alert"]


def test_a_blocked_step_is_asked_again_once_then_its_residue_is_filed_and_it_is_closed_out(state):
    lane(state)
    _step(state="blocked", why="needs a decision", entered_at=T0, issues=[7])
    calls = []
    queue._gh_quiet = lambda gh, args, cwd=None: calls.append(args) or ""
    assert stale.act(queue.load()[0], q=queue, chains={}, hours=stale.HOURS, now=T0 + 49 * 3600) == "ask"
    assert any(a[:2] == ["issue", "edit"] for a in calls)
    assert stale.act(queue.load()[0], q=queue, chains={}, hours=stale.HOURS, now=T0 + 60 * 3600) is None, "the clock restarted at the ask"
    assert stale.act(queue.load()[0], q=queue, chains={}, hours=stale.HOURS, now=T0 + 98 * 3600) == "close-out"
    assert calls[-1][:2] == ["issue", "create"] and steps()["1.1"]["state"] == "closed-out" and queue.load()[0]["cursor"] == 1
    assert [r["action"] for r in _rows()] == ["ask", "close-out"]


def test_one_tick_never_acts_twice_on_a_step(state):
    lane(state)
    _step(state="done", entered_at=T0)
    now = T0 + 2 * 3600
    assert stale.act(queue.load()[0], q=queue, chains={}, hours=stale.HOURS, now=now) == "run-check"
    assert stale.act(queue.load()[0], q=queue, chains={}, hours=stale.HOURS, now=now) is None
    assert len(_rows()) == 1


def test_loop_stale_hours_override_the_defaults_each_tick():
    queue.apply_loop_cfg({"stale_hours": {"red": 2}})
    try:
        assert queue.STALE_H[0]["red"] == 2.0 and queue.STALE_H[0]["blocked"] == stale.HOURS["blocked"]
    finally:
        queue.apply_loop_cfg({})


def test_the_loop_tick_runs_the_stale_watch_before_the_lane(state, monkeypatch):
    """Through queue.tick: a blocked step 60 h old, asked once, is closed out by the tick itself and a `stale` row says so."""
    lane(state)
    _step(state="blocked", why="needs a decision", entered_at=T0, blocked_at=T0, stale_n=1, stale_at=T0)
    monkeypatch.setattr(queue, "_now", lambda: T0 + 60 * 3600)
    fake = tq.Fake()
    queue.tick(fake.procs, {}, workers_n=1, push=False, out=lambda s: None)
    assert [r["action"] for r in _rows()] == ["close-out"] and steps()["1.1"]["state"] == "closed-out"


def test_an_outside_change_made_during_the_tick_survives_a_stale_action(state, monkeypatch):
    """#6589 reliab-1: the tick's copy of the lane is snapshotted before the stale watch stores it, so a change made from outside
    (here: a mark on step 1.2) between the tick's load and the watch's store is kept."""
    lane(state)
    _step(state="blocked", why="needs a decision", entered_at=T0, blocked_at=T0, stale_n=1, stale_at=T0)
    monkeypatch.setattr(queue, "_now", lambda: T0 + 60 * 3600)
    real = stale.act

    def act_after_an_outside_change(lane_, **kw):
        ln = queue.load()
        ln[0]["steps"][1]["outside"] = "kept"
        queue.save(ln)
        return real(lane_, **kw)

    monkeypatch.setattr(stale, "act", act_after_an_outside_change)
    queue.tick(tq.Fake().procs, {}, workers_n=1, push=False, out=lambda s: None)
    assert steps()["1.1"]["state"] == "closed-out" and steps()["1.2"].get("outside") == "kept"
