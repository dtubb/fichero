"""plan <spec>: deterministic facts, one model call (replaced here by its answer), a validated PROPOSED section, a queued question."""
from __future__ import annotations

import types

import pytest

from pipeline import coder, core, feeder, journal, plan

SPEC = """# Demo spec

> Milestone: demo-spec
> Status: DRAFT

## The journey

- `demo.one` [PARTIAL] (#1) — does one. Test: `tests/test_base.py::test_base` and `base()`.
- `demo.two` [MISSING] — does two.
- `demo.done` [OK] — done already.
- `demo.three` [GAP] — does three. Test: tests/test_three.py

## Build order

0. The author's own prose list.
"""

GOOD = """Here you go.
## Proposed build order (anything the model says here is replaced)

#### Step 1.1 — one and two
- Behaviours: `demo.one`, `demo.two`
- Tests: tests/test_base.py, tests/test_two.py
- Size: S

#### Step 1.2 — three
- Behaviours: `demo.three`
- Tests: tests/test_three.py
- Depends on: 1.1
- Size: M
"""


@pytest.fixture
def planned(scratch, monkeypatch):
    root = scratch["repo"]
    (root / "specs" / "demo.md").write_text(SPEC)
    scratch["cfg"]["roles"]["manager"] = [{"kind": "pi", "provider": "anthropic", "model": "claude-sonnet-5-5"}]
    fake = types.SimpleNamespace(asked=[], answer=GOOD)

    def ask_once(cfg, worker, prompt, session):
        fake.asked.append((worker, prompt))
        return {"answer": fake.answer, "cost_usd": 0.12, "tokens": 900, "model": worker["model"]}
    monkeypatch.setattr(coder, "ask_once", ask_once)
    return fake


def test_the_facts_list_only_behaviours_that_owe_a_step_with_their_tests(scratch):
    bs = plan.behaviours(SPEC)
    assert [(b["id"], b["tag"]) for b in bs] == [("demo.one", "PARTIAL"), ("demo.two", "MISSING"), ("demo.three", "GAP")]
    assert bs[0]["tests"] == ["tests/test_base.py::test_base"]
    e = plan.exists(scratch["repo"], bs[0])
    assert e["tests_present"] == ["tests/test_base.py"] and "src/mod.py" in e["symbols"].get("base()", [])


def test_plan_makes_one_call_appends_a_proposal_and_queues_the_question(scratch, planned):
    out = plan.plan("specs/demo.md")
    assert out["steps"] == 2 and out["problems"] == [] and len(planned.asked) == 1
    assert planned.asked[0][0]["model"] == "claude-sonnet-5-5" and "demo.three" in planned.asked[0][1] and "demo.done" not in planned.asked[0][1]
    text = (scratch["repo"] / "specs" / "demo.md").read_text()
    assert text.startswith(SPEC.rstrip("\n")), "existing lines are untouched"
    assert "\n## Proposed build order (proposed, not approved)\n" in text and "Here you go" not in text
    (q,) = [q for q in core.queue() if q["kind"] == "plan"]
    assert "Approve the build order proposed for specs/demo.md?" in q["text"] and "passes the shape check" in q["text"]
    assert any(e["event"] == "cost" and e["key"] == "plan:specs/demo.md" for e in journal.read())
    with pytest.raises(RuntimeError, match="already has a proposed build order"):
        plan.plan("specs/demo.md")


def test_a_plan_with_problems_writes_nothing_queues_why_and_can_be_run_again(scratch, planned):
    planned.answer = GOOD.replace("`demo.three`", "`demo.two`").replace("`demo.one`, `demo.two`", "`demo.one`, `demo.two`, `demo.ghost`")
    before = (scratch["repo"] / "specs" / "demo.md").read_text()
    out = plan.plan("specs/demo.md")
    assert out["written"] is False and any("demo.three" in p and "0 steps" in p for p in out["problems"]) and any("demo.ghost" in p for p in out["problems"])
    assert (scratch["repo"] / "specs" / "demo.md").read_text() == before
    (q,) = [q for q in core.queue() if q["kind"] == "plan"]
    assert "NOT written" in q["text"]
    planned.answer = GOOD
    assert plan.plan("specs/demo.md")["written"] is True, "a retry is allowed when no section exists"


def test_plan_only_touches_a_spec_file_and_only_what_the_model_returns_up_to_the_next_heading(scratch, planned):
    for bad in ("../README.md", "specs/../../outside.md", "specs/nothing.md", "src/mod.py"):
        with pytest.raises(RuntimeError, match="is not a spec"):
            plan.plan(bad)
    planned.answer = GOOD + "\n## Rulings\n\n- `demo.one` [OK] — the planner re-tagged this\n"
    plan.plan("specs/demo.md")
    text = (scratch["repo"] / "specs" / "demo.md").read_text()
    assert "Rulings" not in text and "re-tagged" not in text


def test_a_behaviour_looking_line_or_a_stray_heading_in_the_section_is_refused(scratch, planned):
    before = (scratch["repo"] / "specs" / "demo.md").read_text()
    for bad in ("- `demo.one` [OK] — now done", "### Rulings", "# Title"):
        planned.answer = GOOD.replace("- Size: S\n", f"- Size: S\n{bad}\n", 1)
        with pytest.raises(RuntimeError, match="not a plan"):
            plan.plan("specs/demo.md")
    assert (scratch["repo"] / "specs" / "demo.md").read_text() == before


def test_a_spec_edited_while_the_planner_worked_is_not_overwritten(scratch, planned, monkeypatch):
    path = scratch["repo"] / "specs" / "demo.md"
    real = coder.ask_once

    def edit_then_answer(*a):
        path.write_text(path.read_text() + "\nAn edit made meanwhile.\n")
        return real(*a)
    monkeypatch.setattr(coder, "ask_once", edit_then_answer)
    with pytest.raises(RuntimeError, match="changed while the planner worked"):
        plan.plan("specs/demo.md")
    assert path.read_text().endswith("An edit made meanwhile.\n") and "Proposed" not in path.read_text()


def test_no_proposal_in_the_answer_writes_nothing(scratch, planned):
    planned.answer = "I could not."
    before = (scratch["repo"] / "specs" / "demo.md").read_text()
    with pytest.raises(RuntimeError, match="returned no"):
        plan.plan("specs/demo.md")
    assert (scratch["repo"] / "specs" / "demo.md").read_text() == before and not core.queue()


def test_plan_approve_files_one_issue_per_step_in_order_and_renames_the_section(scratch, planned, monkeypatch):
    plan.plan("specs/demo.md")
    calls = []

    def write(*args, dry_run=True):
        calls.append(args)
        return f"https://github.com/o/r/issues/{900 + sum(1 for a in calls if a[:2] == ('issue', 'create'))}" if args[:2] == ("issue", "create") else ""
    monkeypatch.setattr(plan.gh, "write", write)
    dry = plan.plan_approve("specs/demo.md")
    assert dry["dry_run"] and dry["would_file"] == 2 and "(#" not in (scratch["repo"] / "specs" / "demo.md").read_text().split("## Proposed")[1]
    monkeypatch.setattr(core, "DRY_RUN", False)
    monkeypatch.setattr(plan.gh, "read", lambda *a: [{"title": "other"}])
    calls.clear()
    out = plan.plan_approve("specs/demo.md")
    assert out["filed"] == {"1.1": 901, "1.2": 902} and out["milestone"] == "demo-spec"
    assert calls[0] == ("api", "repos/{owner}/{repo}/milestones", "-f", "title=demo-spec"), "the milestone is made when it does not exist"
    issues = [a for a in calls if a[:2] == ("issue", "create")]
    assert [a[a.index("--label") + 1] for a in issues] == ["type:feature,stage:demo-1", "type:feature,stage:demo-2"]
    assert all(a[a.index("--milestone") + 1] == "demo-spec" for a in issues)
    assert "Depends on: #901" in issues[1][issues[1].index("--body") + 1] and "`demo.three`" in issues[1][issues[1].index("--body") + 1]
    text = (scratch["repo"] / "specs" / "demo.md").read_text()
    assert "\n## Build order\n" in text and "## Earlier build order notes" in text and "## Proposed build order" not in text
    assert "#### Step 1.1 — one and two (#901)" in text and "#### Step 1.2 — three (#902)" in text
    assert plan.guard()._check_spec(text)[1] == [] or all("demo.done" not in p for p in plan.guard()._check_spec(text)[1])


def test_plan_approve_refuses_without_a_proposal_or_with_a_bad_one(scratch, planned):
    with pytest.raises(RuntimeError, match="run `plan` first"):
        plan.plan_approve("specs/demo.md")
    path = scratch["repo"] / "specs" / "demo.md"
    path.write_text(path.read_text() + "\n" + GOOD.replace("`demo.three`", "`demo.two`").split("\n", 1)[1].join(["## Proposed build order (proposed, not approved)\n", ""]))
    with pytest.raises(RuntimeError, match="has problems"):
        plan.plan_approve("specs/demo.md")



class Remote:
    """A fake GitHub for plan-approve: issues and milestones. `crash_on_create` = GitHub keeps the first issue, then the
    process dies before the number comes back (the crash a rerun must survive)."""

    def __init__(self, monkeypatch, milestones=None, crash_on_create=False):
        self.issues, self.creates, self.crash, self.made = [], 0, crash_on_create, []
        self.milestones = [{"title": "demo-spec"}] if milestones is None else milestones
        monkeypatch.setattr(core, "DRY_RUN", False)
        monkeypatch.setattr(plan.gh, "read", self.read)
        monkeypatch.setattr(plan.gh, "write", self.write)

    def read(self, *args):
        if args[0] == "api":
            page = int(args[1].split("&page=")[1]) if "&page=" in args[1] else 1
            return self.milestones[(page - 1) * 100: page * 100]
        return [{"number": 900 + i, "title": t, "body": b} for i, (t, b) in enumerate(self.issues, 1)]

    def write(self, *args, dry_run=True):
        if args[:2] == ("api", "repos/{owner}/{repo}/milestones"):
            self.made.append(args[-1])
            return ""
        if args[:2] != ("issue", "create"):
            return ""
        self.creates += 1
        self.issues.append((args[args.index("--title") + 1], args[args.index("--body") + 1]))
        if self.crash:
            self.crash = False
            raise RuntimeError("crash after GitHub accepted the issue")
        return f"https://github.com/o/r/issues/{900 + len(self.issues)}"


def test_a_crash_after_create_is_not_refiled_on_rerun(scratch, planned, monkeypatch):
    plan.plan("specs/demo.md")
    remote = Remote(monkeypatch, crash_on_create=True)
    with pytest.raises(RuntimeError, match="crash"):
        plan.plan_approve("specs/demo.md")
    creates_before = remote.creates
    out = plan.plan_approve("specs/demo.md")
    assert out["filed"] == {"1.1": 901, "1.2": 902}
    assert remote.creates == creates_before + 1 and len(remote.issues) == 2, "the rerun files only what was never filed"
    assert "#### Step 1.1 — one and two (#901)" in (scratch["repo"] / "specs" / "demo.md").read_text()


def test_milestone_lookup_reads_every_page(scratch, planned, monkeypatch):
    plan.plan("specs/demo.md")
    remote = Remote(monkeypatch, milestones=[{"title": f"m{i}"} for i in range(100)] + [{"title": "demo-spec"}])
    plan.plan_approve("specs/demo.md")
    assert remote.made == [], "demo-spec is on page 2 of the milestones: it exists, so none is made"
    assert remote.creates == 2


def test_behaviour_text_cannot_add_a_dependency(scratch, planned, monkeypatch):
    path = scratch["repo"] / "specs" / "demo.md"
    plan.plan("specs/demo.md")
    path.write_text(path.read_text().replace("does one.", "does one. Depends on: #7."))
    remote = Remote(monkeypatch)
    plan.plan_approve("specs/demo.md")
    body = remote.issues[0][1]
    assert "#7" not in body and not feeder.blocked({"body": body}, {7, 35}), "a behaviour's words never make an issue wait on another"
