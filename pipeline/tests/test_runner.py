"""The scheduler: journal-driven passes over core, no model call of its own. Model-spending core functions are
replaced by what they would journal (a review is a verdict); the coder is the conftest FakeCoder."""
from __future__ import annotations

import types

import pytest

from pipeline import core, journal, runner


def ready(*nums, write_up=()):
    return lambda count=3: {"milestone": "demo", "ready": [{"number": n, "title": ""} for n in nums], "write_up": list(write_up)}


def reviewer(monkeypatch, verdict="READY"):
    calls = []

    def review(key, worker_index=0):
        it = core.state()["items"][key]
        calls.append(key)
        core.verdict(key, it["sha"], verdict, "reviewer", "- LOW fine")
    monkeypatch.setattr(core, "review", review)
    return calls


def test_run_starts_checks_reviews_and_queues_ready_to_land_then_stops(scratch, issues, fake_coder, monkeypatch):
    fake_coder()
    monkeypatch.setattr(core, "next_issues", lambda count=3: ready(1001)() if "1001" not in core.state()["items"] else ready()())
    calls = reviewer(monkeypatch)
    out = runner.run()
    assert out["stopped"] == "nothing is ready" and calls == ["1001"]
    assert core.state()["items"]["1001"]["state"] == "reviewed"
    assert [q["text"] for q in core.queue() if q["kind"] == "ready-to-land"] == [
        f"1001 is reviewed READY at {core.state()['items']['1001']['sha'][:9]}: `python -m pipeline land 1001`"]
    runner.run()
    assert len([q for q in core.queue() if q["kind"] == "ready-to-land"]) == 1, "asked once, and a rerun reviews nothing twice"
    assert calls == ["1001"]


def test_an_answered_question_resumes_the_same_item_and_an_unanswered_one_waits(scratch, issues, fake_coder, monkeypatch):
    fake_coder("asks")
    monkeypatch.setattr(core, "next_issues", ready())
    reviewer(monkeypatch)
    core.start([1001])
    (q,) = [q for q in core.queue() if q["kind"] == "ask"]
    monkeypatch.setattr(core, "next_issues", ready())
    assert runner.run(once=True)["did"] == [] and core.state()["items"]["1001"]["state"] == "asking"
    core.answer(q["id"], "tabs", resume=False)
    out = runner.run()
    assert "1001: answered, resumed" in out["did"] and core.state()["items"]["1001"]["state"] == "reviewed"


def test_run_waits_for_an_answer_by_sleeping_the_poll_interval(scratch, issues, fake_coder, monkeypatch):
    fake_coder("asks")
    monkeypatch.setattr(core, "next_issues", ready())
    core.start([1001])
    (q,) = [q for q in core.queue() if q["kind"] == "ask"]
    naps = []

    def nap(s):
        naps.append(s)
        core.answer(q["id"], "tabs", resume=False)
    monkeypatch.setattr(runner, "time", types.SimpleNamespace(sleep=nap))  # not time.sleep itself: subprocess waits with it
    reviewer(monkeypatch)
    out = runner.run(poll_s=7)
    assert naps == [7] and out["stopped"] == "nothing is ready" and core.state()["items"]["1001"]["state"] == "reviewed"


def test_run_stops_at_the_daily_cap_and_when_paused(scratch, issues, monkeypatch):
    started = []
    monkeypatch.setattr(core, "start", lambda *a, **k: started.append(a))
    monkeypatch.setattr(core, "next_issues", ready(1001))
    journal.append("cost", issue=1, key="1", task="t", session="s", usd=scratch["cfg"]["workers"].get("daily_cap_usd", 25.0) + 1, tokens=1, model="m")
    assert "daily cap" in runner.run()["stopped"] and not started
    core.resume(raise_cap=1000)
    core.pause()
    assert "paused" in runner.run()["stopped"] and not started


def test_an_issue_brief_lint_refuses_is_started_with_the_writeup_flag(scratch, issues, monkeypatch):
    calls = []
    monkeypatch.setattr(core, "start", lambda nums, **k: calls.append((nums, k)) or {"items": {}})
    monkeypatch.setattr(core, "next_issues", ready(write_up=(1002, 1003)))
    runner.run(once=True)
    assert calls == [([1002], {"milestone": "demo", "writeup": True})], "one write-up at a time"


def test_the_coder_cap_holds_back_new_work(scratch, issues, monkeypatch):
    journal.append("worker", window="coder-x", task="x", role="coder", model="m", session_dir="/nowhere", cwd="/nowhere")
    monkeypatch.setattr(core, "start", lambda *a, **k: pytest.fail("the coder cap is 1"))
    monkeypatch.setattr(core, "next_issues", ready(1001))
    assert runner.run(once=True)["did"] == []


def test_not_ready_goes_back_to_its_coder_until_the_retries_are_spent_then_asks(scratch, issues, fake_coder, monkeypatch):
    fake_coder()
    monkeypatch.setattr(core, "next_issues", ready())
    core.start([1001])
    sent = []
    monkeypatch.setattr(core, "retry", lambda key, worker=None: sent.append(key))
    it = core.state()["items"]["1001"]
    core.verdict("1001", it["sha"], "READY", "manager")  # recorded only: not binding
    journal.append("verdict", issue=1001, key="1001", sha=it["sha"], verdict="NOT_READY", by="reviewer", findings="- HIGH x")
    core._move("1001", "reviewed", "test")
    core.verdict("1001", it["sha"], "NOT_READY", "reviewer", "- HIGH x")
    assert core.state()["items"]["1001"]["state"] == "coding"
    runner.run(once=True)
    assert sent == ["1001"]
    for _ in range(3):
        journal.append("retry", issue=1001, key="1001", text="Review NOT_READY at abc:\n- HIGH x")
    runner.run(once=True)
    runner.run(once=True)
    assert sent == ["1001"] and len([q for q in core.queue() if q["kind"] == "blocked"]) == 1, "asked once"


def test_a_review_that_leaves_no_verdict_is_asked_about_not_repeated(scratch, issues, fake_coder, monkeypatch):
    fake_coder()
    monkeypatch.setattr(core, "next_issues", ready())
    core.start([1001])
    calls = []
    monkeypatch.setattr(core, "review", lambda key, worker_index=0: calls.append(key))
    runner.run(once=True)
    runner.run(once=True)
    assert calls == ["1001"] and [q["text"][:6] for q in core.queue() if q["kind"] == "blocked"] == ["1001: "]
