"""builder-console.work.counts-are-live (#6645): a milestone's step counts come from the lanes' steps, with ages, the lane and the last failure."""
from __future__ import annotations

import json
import types

import pytest

from fichero_builder import __main__ as cli
from fichero_builder import journal, order, queue, work_store, work_tree

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


def test_a_landed_step_whose_head_is_not_on_origin_counts_as_done_not_landed():
    lanes = [_lane("a", "m", ("1.1", "landed", "", NOW - 60), ("1.2", "landed", "", NOW - 30))]
    off = lambda lane, s: s["step"] != "1.1"  # noqa: E731
    t = work_tree.counts(lanes, now=NOW, on_origin=off)["m"]["states"]
    assert t["done-not-landed"]["n"] == 1 and t["landed"]["n"] == 1
    assert "done-not-landed" not in work_tree.counts(lanes, now=NOW)["m"]["states"]


class Store:
    """milestone title -> open issue numbers."""

    def __init__(self, **ms):
        self.ms = ms

    def milestones(self):
        return [{"title": t, "open": len(n), "closed": 0} for t, n in self.ms.items()]

    def issues(self, milestone):
        return [{"number": n, "title": "", "body": "", "labels": []} for n in self.ms[milestone]]

    def milestone_of(self, issue):
        self.asked = getattr(self, "asked", []) + [issue]
        return next((t for t, n in self.ms.items() if issue in n), "")


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    monkeypatch.setattr(work_store, "open_store", lambda name, **kw: Store(**{"performance-sweep": [6600, 6601], "Builder": [6645]}))
    return tmp_path


def test_queue_add_with_issues_puts_the_lane_under_the_issues_milestone(state, capsys):
    brief = state / "b.txt"
    brief.write_text("x")
    for lane, issue in (("x", "6600"), ("y", "9999")):
        assert cli.main(["queue", "add", "--lane", lane, "--worktree", "/w", "--step", "1.1", "--brief", str(brief), "--issues", issue,
                         "--state", str(state / "s")]) == 0
    lanes = queue.load()
    assert [(x["id"], x["milestone"]) for x in lanes] == [("x", "performance-sweep"), ("y", "unfiled")]
    assert set(work_tree.counts(lanes)) == {"performance-sweep", "unfiled"}


def test_issues_in_two_milestones_refuse_the_queue_add_and_the_lane_is_not_made(state, capsys):
    brief = state / "b.txt"
    brief.write_text("x")
    rc = cli.main(["queue", "add", "--lane", "x", "--worktree", "/w", "--step", "1.1", "--brief", str(brief), "--issues", "6600", "6645",
                   "--state", str(state / "s")])
    assert rc == 1 and "more than one milestone" in capsys.readouterr().out and queue.load() == []


def test_the_order_verb_refuses_a_name_with_no_milestone_by_name_and_writes_the_record_when_saved(state, monkeypatch, capsys):
    f = state / "req.json"
    args = types.SimpleNamespace(file=str(f), root=str(state))
    (state / "harness.toml").write_text('[land]\nbranch = "integration"\n')
    f.write_text(json.dumps({"order": ["Builder", "dev-workflows"]}))
    saved = []
    monkeypatch.setattr(order, "save", lambda *a: (saved.append(a), (0, "saving"))[1])
    assert order.main(args, Store(Builder=[1])) == 1
    assert "'dev-workflows'" in capsys.readouterr().out and saved == [] and work_tree.read_order() == []
    f.write_text(json.dumps({"order": ["performance-sweep", "Builder"]}))
    assert order.main(args, Store(**{"performance-sweep": [], "Builder": []})) == 0
    assert work_tree.read_order() == ["performance-sweep", "Builder"] and len(saved) == 1


def test_a_refused_save_leaves_the_record_as_it_was(state, monkeypatch):
    work_tree.write_order(["Builder"])
    (state / "harness.toml").write_text("")
    (state / "req.json").write_text(json.dumps({"order": ["a", "Builder"]}))
    monkeypatch.setattr(order, "save", lambda *a: (1, "a reorder is still saving"))
    assert order.main(types.SimpleNamespace(file=str(state / "req.json"), root=str(state)), Store(a=[], Builder=[])) == 1
    assert work_tree.read_order() == ["Builder"]


def test_triage_order_appends_what_the_record_lacks_and_never_reorders(state):
    work_tree.write_order(["b", "a"])
    known = ["a", "b", "c", "d"]
    assert work_tree.append_order(["a", "d", "c"], known) == ["d", "c"]
    assert work_tree.read_order() == ["b", "a", "d", "c"]
    assert work_tree.append_order(["a"], known) == []
    with pytest.raises(ValueError, match="'zzz'"):
        work_tree.append_order(["zzz"], known)
    assert work_tree.read_order() == ["b", "a", "d", "c"]


def test_milestone_of_asks_once_per_issue_not_once_per_milestone():
    store = Store(a=[1], b=[2], c=[3], d=[4])
    assert work_tree.milestone_of(store, [3]) == "c" and store.asked == [3]


def test_the_github_store_reads_an_issues_milestone_with_one_gh_view():
    calls = []

    def gh(*args):
        calls.append(list(args))
        return json.dumps({"milestone": {"title": "Builder"}} if args[2] == "7" else {"milestone": None})
    s = work_store.GithubStore(run=gh)
    assert s.milestone_of(7) == "Builder" and s.milestone_of(8) == "" and calls[0] == ["issue", "view", "7", "--json", "milestone"]
