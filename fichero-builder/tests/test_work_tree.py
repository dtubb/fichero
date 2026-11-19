"""builder-console.work.counts-are-live (#6645): a milestone's step counts come from the lanes' steps, with ages, the lane and the last failure."""
from __future__ import annotations

from fichero_builder import work_tree

NOW = 10_000.0


def _lane(lid, milestone, *steps, **kw):
    return {"id": lid, "milestone": milestone, "paused": False, "steps": [
        {"step": n, "state": st, "why": why, "entered_at": at, "rounds": 0} for n, st, why, at in steps], **kw}


def test_counts_come_from_the_tree():
    lanes = [_lane("a", "m1", ("1.1", "checking", "", NOW - 600), ("1.2", "blocked", "QUESTION: which file?\nmore", NOW - 7200),
                   ("1.3", "queued", "", NOW - 50)),
             _lane("b", "m2", ("1.1", "landed", "", NOW - 3600), ("1.2", "landed", "", NOW - 100))]
    t = work_tree.counts(lanes, now=NOW)
    m1 = t["m1"]
    assert m1["states"]["waiting"] == {"n": 1, "oldest_age_s": 600.0, "lanes": ["a"]}
    assert m1["states"]["blocked"] == {"n": 1, "oldest_age_s": 7200.0, "lanes": ["a"]}
    assert m1["states"]["queued"]["n"] == 1
    assert m1["last_failure"] == "QUESTION: which file?" and m1["running_lane"] == "a"
    m2 = t["m2"]
    assert m2["running_lane"] == "" and m2["last_lane"] == "b" and m2["states"]["landed"]["n"] == 2 and m2["last_failure"] == ""


def test_a_lane_with_no_milestone_is_unfiled_and_a_paused_lane_is_a_flag_not_a_state():
    t = work_tree.counts([_lane("x", None, ("1.1", "done", "", NOW - 5), paused=True)], now=NOW)
    assert list(t) == ["unfiled"] and t["unfiled"]["states"]["waiting"]["n"] == 1 and t["unfiled"]["paused"] == ["x"]


def test_the_newest_failure_wins_and_a_red_check_counts_as_red():
    lanes = [_lane("a", "m", ("1.1", "blocked", "red at rung lint", NOW - 90), ("1.2", "blocked", "older question", NOW - 900))]
    lanes[0]["steps"][0]["red_head"] = "abc"
    t = work_tree.counts(lanes, now=NOW)["m"]
    assert t["states"]["red"]["n"] == 1 and t["states"]["blocked"]["n"] == 1 and t["last_failure"] == "red at rung lint"
