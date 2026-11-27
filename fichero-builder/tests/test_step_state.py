"""builder-console.step.one-state: a step has one state, a `why` about that state, an age that resets on every move; paused and held are lane flags."""
from __future__ import annotations

import copy

from fichero_builder import queue
from test_queue_verb import Fake, lane, run, state, steps  # noqa: F401  (the fixture and the fake procs the queue tests use)


def _walk(monkeypatch, fake, tick):
    """Every write of the lane's row during the run, as the step's one-state view at the clock of that write."""
    seen, real = [], queue.store

    def spy(lane_, expect=None):
        ok = real(lane_, expect)
        s = next(x for x in lane_["steps"] if x["step"] == "1.1")
        seen.append((queue.state_view(lane_, s, now=tick[0]), copy.deepcopy(s)))
        return ok
    monkeypatch.setattr(queue, "store", spy)
    monkeypatch.setattr(queue, "_now", lambda: tick.__setitem__(0, tick[0] + 10) or tick[0])
    return seen


def test_a_step_walks_queued_to_landed_in_one_state_each_with_its_own_why_and_a_resetting_age(state, monkeypatch):  # noqa: F811
    lane(state)
    tick = [1000.0]
    fake = Fake(chains={"1.1": [{"ok": False, "kind": "red", "why": "the check is red at rung lint", "findings": "lint: x"}]})
    assert queue.state_view(queue.load()[0], steps()["1.1"], now=1000.0)["state"] == "queued"
    seen = _walk(monkeypatch, fake, tick)
    assert run(fake) == 0
    names = []
    for v, _ in seen:
        if not names or names[-1] != v["state"]:
            names.append(v["state"])
    assert names == ["sent", "said-done", "checking", "reviewing", "red", "fixing", "said-done", "checking", "reviewing", "landed"]
    for v, raw in seen:
        assert v["state"] in queue.STATES and v["why"] == raw["why"] and v["since"] == raw["entered_at"]
    red = next(v for v, _ in seen if v["state"] == "red")
    assert "rung lint" in red["why"]
    fixing = next(v for v, _ in seen if v["state"] == "fixing")
    assert "round 1" in fixing["why"]
    sd = [v for v, _ in seen if v["state"] == "said-done"]
    assert sd[0]["why"] == "" and sd[1]["why"] == "" and sd[0]["since"] < sd[1]["since"], "the age restarts on the second DONE"
    assert all(v["age_s"] >= 0 for v, _ in seen)


def test_a_green_step_whose_head_is_not_on_the_integration_branch_is_done_not_landed(state):  # noqa: F811
    s = {"step": "1.1", "state": "landed", "why": "landed abc (not pushed)", "entered_at": 50.0}
    assert queue.state_view({"paused": False}, s, now=80.0, on_origin=True)["state"] == "landed"
    v = queue.state_view({"paused": False}, s, now=80.0, on_origin=False)
    assert v["state"] == "done-not-landed" and v["age_s"] == 30.0


def test_pausing_the_lane_changes_the_flag_and_nothing_else(state):  # noqa: F811
    s = {"step": "1.1", "state": "done", "why": "", "entered_at": 50.0}
    a = queue.state_view({"paused": False, "paused_at": 0}, s, now=80.0)
    b = queue.state_view({"paused": True, "paused_at": 70.0}, s, now=80.0)
    assert a["flags"] == [] and b["flags"] == ["paused"]
    assert {k: v for k, v in a.items() if k != "flags"} == {k: v for k, v in b.items() if k != "flags"}
    assert queue.state_view({"paused": True, "hold": True}, s, now=80.0)["flags"] == ["paused", "held"]


def test_a_block_that_is_a_question_is_blocked_and_a_failed_check_after_the_fix_rounds_is_red(state):  # noqa: F811
    lane(state)
    assert run(Fake(chains={"1.1": [{"ok": False, "kind": "error", "why": "rules file broken"}]})) == 0
    s = steps()["1.1"]
    assert s["state"] == "blocked" and queue.state_view(queue.load()[0], s)["state"] == "blocked"
    queue.save([])
    lane(state)
    bad = {"ok": False, "kind": "red", "why": "still wrong", "findings": "f"}
    assert run(Fake(chains={"1.1": [dict(bad), dict(bad), dict(bad)]})) == 0
    s = steps()["1.1"]
    assert s["state"] == "blocked" and queue.state_view(queue.load()[0], s)["state"] == "red"


def test_a_step_green_on_the_cheap_rungs_waits_in_the_train_state(state):  # noqa: F811
    s = {"step": "1.1", "state": "train", "why": "green on the cheap rungs at abc; waits for a merge train", "entered_at": 50.0}
    v = queue.state_view({"paused": False}, s, now=80.0)
    assert v["state"] == "train" and v["state"] in queue.STATES and v["age_s"] == 30.0
