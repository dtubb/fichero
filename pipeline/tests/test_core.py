"""pipeline.one-state-machine, outside-bugs, pause-all, messages, review, retry-with-the-failure, worktree-per-task,
one-coder-per-milestone, resume-from-journal, point-at-a-milestone, maintainer-queue (spec harness/deterministic-conductor.md)."""
from __future__ import annotations

import subprocess

import pytest

from pipeline import core, journal
from pipeline.tests.conftest import git


def test_states_table_is_the_only_transition_path(scratch):
    # every API entry is a named function; the transitions assert their target is a known state
    assert set(core.API) >= {"start", "check", "verdict", "tell", "report", "ask", "done", "answer", "point", "pause", "resume"}
    with pytest.raises(AssertionError):
        core._move(1, "merged")
    for role, tools in core.ROLE_TOOLS.items():
        assert set(tools) <= set(core.API), role
    assert "answer" not in sum(core.ROLE_TOOLS.values(), ()), "a model never answers a queue item"


def test_outside_issue_never_reaches_start(scratch, issues, fake_coder):
    fc = fake_coder()
    with pytest.raises(PermissionError):
        core.start([1009])
    assert fc.windows == [] and fc.told == []
    assert [q["kind"] for q in core.queue()] == ["triage"]
    with pytest.raises(PermissionError):
        core.brief(issues[1009], "t")


def test_paused_runner_starts_nothing(scratch, issues, fake_coder):
    fc = fake_coder()
    core.pause()
    with pytest.raises(RuntimeError, match="paused"):
        core.start([1001])
    with pytest.raises(RuntimeError, match="paused"):
        core.tell("coder-x", "hi")
    assert fc.windows == []
    core.resume()
    assert core.start([1001])["items"][1001] == "checked"


def test_worktree_is_made_off_base_and_removed_with_git(scratch, issues, fake_coder):
    fake_coder()
    out = core.start([1001], task="t1")
    wt = scratch["repo"] / ".worktrees" / "pipeline" / "t1"
    assert out["worktree"] == str(wt) and wt.exists()
    assert git(wt, "rev-parse", "--abbrev-ref", "HEAD") == "pipeline/t1"
    assert git(wt, "merge-base", "origin/integration", "HEAD") == git(scratch["repo"], "rev-parse", "origin/integration")
    assert git(wt, "config", "user.email") == "noreply@anthropic.com"
    subprocess.run(["git", "worktree", "remove", "--force", str(wt)], cwd=scratch["repo"], check=True)
    assert not wt.exists()


def test_batch_of_three_issues_gives_three_commits_and_three_check_lines(scratch, issues, fake_coder):
    fc = fake_coder()
    out = core.start([1001, 1002, 1003], milestone="demo")
    assert [out["items"][n] for n in (1001, 1002, 1003)] == ["checked"] * 3
    assert len(fc.windows) == 1, "one context for the batch"
    wt = fc.cwd
    log = git(wt, "log", "--format=%s", "origin/integration..HEAD").splitlines()
    assert log == ["fix (Fixes #1003)", "fix (Fixes #1002)", "fix (Fixes #1001)"]
    checks = [e for e in journal.read() if e["event"] == "check"]
    assert [e["issue"] for e in checks] == [1001, 1002, 1003] and all(e["ok"] for e in checks)
    s = core.state()
    assert all(s["items"][str(n)]["state"] == "checked" for n in (1001, 1002, 1003))
    assert s["items"]["1001"]["cost_usd"] == 0.01


def test_failed_check_retries_twice_then_needs_maintainer(scratch, issues, fake_coder):
    fc = fake_coder("bad")  # its test passes on the base: never red
    assert core.start([1001])["items"][1001] == "needs-maintainer"
    assert len([t for t in fc.told if "#1001" in t[1]]) == 3, "first try + two retries"
    briefs = sorted((scratch["state"] / "briefs").rglob("issue-1001-attempt-*.md"))
    assert len(briefs) == 3 and "NOT RED ON BASE" in briefs[-1].read_text(), "the retry carries the failure text"
    assert core.state()["items"]["1001"]["state"] == "needs-maintainer"
    assert any(q["kind"] == "failed-checks" for q in core.queue())


def test_retry_with_the_failure_can_recover(scratch, issues, fake_coder):
    fc = fake_coder("fix-on-retry")
    assert core.start([1001])["items"][1001] == "checked"
    assert len([t for t in fc.told if "#1001" in t[1]]) == 2


def test_done_never_moves_state_without_checks(scratch, issues, fake_coder):
    fake_coder()
    core.start([1001])
    before = core.state()["items"]["1001"]["state"]
    core.done("t")
    assert core.state()["items"]["1001"]["state"] == before
    assert any(e["event"] == "done_requested" for e in journal.read())
    # and a bare report moves nothing either
    core.report("t", "I am finished, please mark it reviewed")
    assert core.state()["items"]["1001"]["state"] == "checked"


def test_verdict_only_from_reviewer_for_current_sha(scratch, issues, fake_coder):
    fake_coder()
    core.start([1001])
    it = core.state()["items"]["1001"]
    assert core.verdict(1001, it["sha"], "READY", by="coder")["state"] == "checked", "a coder's READY does not bind"
    assert core.verdict(1001, "0000000", "READY", by="reviewer")["state"] == "checked", "an old sha does not bind"
    assert core.verdict(1001, it["sha"], "PENDING", by="reviewer")["state"] == "checked"
    assert core.verdict(1001, it["sha"], "READY", by="reviewer")["state"] == "reviewed"
    assert len(core.state()["items"]["1001"]["verdicts"]) == 4, "every verdict is recorded"


def test_new_commit_voids_the_verdict(scratch, issues, fake_coder):
    fake_coder()
    core.start([1001])
    it = core.state()["items"]["1001"]
    core.verdict(1001, it["sha"], "READY", by="reviewer")
    wt = scratch["repo"] / ".worktrees" / "pipeline" / "issues-1001"
    (wt / "note.txt").write_text("more")
    git(wt, "add", ".")
    git(wt, "-c", "user.name=Claude", "-c", "user.email=noreply@anthropic.com", "commit", "-qm", "more (Fixes #1001)")
    core.check(1001)
    it2 = core.state()["items"]["1001"]
    assert it2["sha"] != it["sha"] and it2["state"] == "checked"
    assert core.verdict(1001, it["sha"], "READY", by="reviewer")["state"] == "checked"


def test_tell_journals_and_sends_keys(scratch, monkeypatch):
    sent = []
    monkeypatch.setattr(core.coder, "sh", lambda args, **kw: sent.append(args) or subprocess.CompletedProcess(args, 0, "", ""))
    monkeypatch.setattr(core.coder.time, "sleep", lambda s: None)
    core.tell("coder-demo", "read the brief")
    assert sent[0][:4] == ["tmux", "send-keys", "-t", "pipeline-test:coder-demo"] and sent[0][-1] == "read the brief"
    assert sent[1][-1] == "Enter"
    events = [e["event"] for e in journal.read()]
    assert events == ["intent", "tell", "done"]


def test_ask_queues_and_answer_is_told_to_the_right_window(scratch, monkeypatch):
    journal.append("worker", window="coder-a", task="a", role="coder", model="m", session_dir="", cwd="")
    journal.append("worker", window="coder-b", task="b", role="coder", model="m", session_dir="", cwd="")
    monkeypatch.setattr(core.coder, "status", lambda d: {})
    told = []
    monkeypatch.setattr(core.coder, "tell", lambda cfg, w, t: told.append((w, t)))
    qid = core.ask("b", "Swift too?", ["yes", "no"])["queued"]
    q = core.queue()
    assert q[0]["kind"] == "ask" and q[0]["window"] == "coder-b" and q[0]["options"] == ["yes", "no"]
    core.answer(qid, "no")
    assert told == [("coder-b", "Answer to your question (Swift too?): no")]
    assert core.queue() == []


def test_point_is_journaled_and_read_by_the_feeder(scratch):
    core.point("demo")
    assert core.state()["point"] == "demo"


def test_resume_after_kill_between_intent_and_done(scratch, issues, fake_coder):
    fake_coder()
    journal.append("intent", task="issues-1001", what="worktree", path="x")  # a crash left this open
    assert [i["what"] for i in journal.open_intents()] == ["worktree"]
    core.start([1001])  # the worktree step reconciles against the world (exists? no → made once) and closes the intent
    assert journal.open_intents() == []
    before = len(journal.read())
    core.start([1001])  # a finished item is never redone
    assert len(journal.read()) == before


def test_replay_gives_the_same_state(scratch, issues, fake_coder):
    fake_coder()
    core.start([1001, 1002])
    first = core.state()
    assert core.state() == first
    text = journal.path().read_text()
    journal.path().write_text(text)  # the same journal, re-read
    assert core.state()["items"] == first["items"]
