"""pipeline.feeder-picks-the-milestone, pipeline.brief-lint, pipeline.bug-intake ordering (spec harness/deterministic-conductor.md)."""
from __future__ import annotations

from pipeline import core, feeder, gh

LABELS = {"bug": "type:bug", "urgent": "urgent", "claimed": "claimed", "from_user": "from-user"}
GOOD = "Spec `demo.one`. Acceptance: f(1) returns 1. Test: tests/test_1.py"


def iss(n, body=GOOD, labels=(), author="dtubb", milestone="m1"):
    return {"number": n, "title": f"t{n}", "body": body, "labels": list(labels), "author": author, "milestone": milestone}


def pick(issues, approved=frozenset({"demo.one"}), taken=frozenset()):
    return feeder.pick(issues, LABELS, ["dtubb"], set(approved), set(taken))


def test_brief_lint_names_each_missing_field():
    assert feeder.lint(iss(1), LABELS, {"demo.one"}) == []
    miss = feeder.lint(iss(2, "nothing here"), LABELS, {"demo.one"})
    assert [m.split()[1] for m in miss] == ["spec", "acceptance", "test"]
    assert feeder.lint(iss(3, "`demo.one` Acceptance: x"), LABELS, {"demo.one"}) == ["a test path"]


def test_only_approved_spec_or_bug_is_dispatched():
    assert pick([iss(1)], approved=set())["write_up"][1][0].startswith("an APPROVED spec")
    bug = iss(2, "Saw x. Expected y. Test: tests/test_x.py", ["type:bug"])
    assert [i["number"] for i in pick([bug], approved=set())["ready"]] == [2]
    text = "**Status: APPROVED**\n- `demo.one` [MISSING]"
    assert feeder.approved_ids([text]) == {"demo.one"} and feeder.approved_ids(["# x\n**Status: DRAFT**\n`demo.one`"]) == set()


def test_bug_without_test_path_goes_to_queue():
    got = pick([iss(5, "Saw a crash. Expected none.", ["type:bug"])])
    assert got["ready"] == [] and got["write_up"] == {5: ["a test path"]}


def test_urgent_bug_is_ordered_first():
    bug_body = "Saw x. Expected y. Test: tests/test_x.py"
    issues = [iss(1, labels=["stage:demo-1"]), iss(2, bug_body, ["type:bug"]), iss(3, bug_body, ["type:bug", "urgent"])]
    assert [i["number"] for i in pick(issues)["ready"]] == [3, 2, 1]


def test_claimed_issues_are_skipped():
    got = pick([iss(1, labels=["claimed"]), iss(2), iss(3)], taken={3})
    assert [i["number"] for i in got["ready"]] == [2]


def test_outside_author_goes_to_triage_never_ready():
    got = pick([iss(1, author="stranger"), iss(2, labels=["from-user"])])
    assert got["ready"] == [] and got["triage"] == [1, 2]


def test_a_step_waits_for_its_open_dependency():
    got = pick([iss(1), iss(2, GOOD + "\nDepends on: #1")])
    assert [i["number"] for i in got["ready"]] == [1]


def test_pointed_milestone_wins_then_build_order(scratch, monkeypatch):
    (scratch["repo"] / "specs" / "s.md").write_text("**Status: APPROVED**\n- `demo.one` [MISSING]\n")
    data = {"m1": [iss(10, labels=["stage:demo-2"]), iss(11, labels=["stage:demo-1"])], "m2": [iss(20)]}

    def read(*args):
        if args[0] == "api":
            return [{"title": "m2", "due_on": "2026-11-01"}, {"title": "m1", "due_on": "2026-10-30"}]
        return [dict(d, labels=[{"name": x} for x in d["labels"]], author={"login": d["author"]}, milestone={"title": d["milestone"]})
                for d in data[args[args.index("--milestone") + 1]]]

    monkeypatch.setattr(gh, "read", read)
    out = core.next_issues(2)
    assert out["milestone"] == "m1" and [i["number"] for i in out["ready"]] == [11, 10], "first due milestone, build order"
    core.point("m2")
    assert core.next_issues()["milestone"] == "m2"
    data["m1"][:] = []
    core.point("m1")
    assert core.next_issues()["ready"] == [], "a pointed milestone with nothing ready does not fall through"
