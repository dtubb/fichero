"""plan <spec>: deterministic facts, one model call (replaced here by its answer), a validated PROPOSED section, a queued question."""
from __future__ import annotations

import types

import pytest

from pipeline import coder, core, journal, plan

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


def test_a_plan_with_problems_is_still_proposed_but_says_what_is_wrong(scratch, planned):
    planned.answer = GOOD.replace("`demo.three`", "`demo.two`").replace("`demo.one`, `demo.two`", "`demo.one`, `demo.two`, `demo.ghost`")
    out = plan.plan("specs/demo.md")
    assert any("demo.three" in p and "0 steps" in p for p in out["problems"]) and any("demo.two" in p and "2 steps" in p for p in out["problems"])
    assert any("demo.ghost" in p for p in out["problems"])
    (q,) = [q for q in core.queue() if q["kind"] == "plan"]
    assert "problem(s)" in q["text"]


def test_no_proposal_in_the_answer_writes_nothing(scratch, planned):
    planned.answer = "I could not."
    before = (scratch["repo"] / "specs" / "demo.md").read_text()
    with pytest.raises(RuntimeError, match="returned no"):
        plan.plan("specs/demo.md")
    assert (scratch["repo"] / "specs" / "demo.md").read_text() == before and not core.queue()
