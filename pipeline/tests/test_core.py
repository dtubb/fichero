"""pipeline.one-state-machine, outside-bugs, pause-all, messages, review, retry-with-the-failure, worktree-per-task,
one-coder-per-milestone, resume-from-journal, point-at-a-milestone, maintainer-queue (spec harness/deterministic-conductor.md)."""
from __future__ import annotations

import json
import subprocess

import pytest

from pipeline import core, journal
from pipeline.tests.conftest import git


def test_start_from_a_local_issue_file_for_an_unfiled_step(scratch, fake_coder, tmp_path):
    fake_coder()
    f = tmp_path / "step.json"
    f.write_text(json.dumps({"number": 6116, "part_of": True, "author": "dtubb", "title": "Step 1.2", "body": "do the guard",
                             "labels": [], "milestone": "m"}))
    out = core.start([6116], task="step-1-2", from_file=str(f))
    assert out["items"][6116] == "checked"
    text = core.brief(json.loads(f.read_text()), "step-1-2")
    assert "(Part of #6116)" in text and "Fixes" not in text


def test_start_takes_a_base_for_a_bootstrap_step(scratch, issues, fake_coder):
    """Dogfood 3: a Stage 1 step needs a base that has the runner; `--base` names it."""
    fake_coder()
    repo = scratch["repo"]
    git(repo, "checkout", "-qb", "runner-branch")
    (repo / "RUNNER").write_text("here\n")
    git(repo, "add", ".")
    git(repo, "-c", "user.name=Claude", "-c", "user.email=noreply@anthropic.com", "commit", "-qm", "runner (Fixes #1001)")
    git(repo, "checkout", "-q", "integration")
    out = core.start([1001], task="boot", base="runner-branch")
    wt = scratch["repo"] / ".worktrees" / "pipeline" / "boot"
    assert (wt / "RUNNER").exists() and out["items"][1001] == "checked"


def test_states_table_is_the_only_transition_path(scratch, issues, fake_coder):
    assert set(core.API) >= {"start", "check", "verdict", "tell", "report", "ask", "done", "answer", "point", "pause", "resume"}
    for role, tools in core.ROLE_TOOLS.items():
        assert set(tools) <= set(core.API), role
    assert "answer" not in sum(core.ROLE_TOOLS.values(), ()), "a model never answers a queue item"
    fake_coder()
    core.start([1001])  # checked
    for bad in ("queued", "pushed", "closed", "candidate"):
        with pytest.raises(RuntimeError, match="no transition checked ->"):
            core._move(1001, bad)
    with pytest.raises(RuntimeError, match="no transition"):
        core._move(1001, "merged")
    rows = {(a, b) for a, b in core.ALLOWED}
    for a, b in rows:
        assert a in core.STATES and b in core.STATES


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
    log = git(fc.cwd, "log", "--format=%s", "origin/integration..HEAD").splitlines()
    assert log == ["fix (Fixes #1003)", "fix (Fixes #1002)", "fix (Fixes #1001)"]
    checks = [e for e in journal.read() if e["event"] == "check"]
    assert [e["issue"] for e in checks] == [1001, 1002, 1003] and all(e["ok"] for e in checks)
    s = core.state()
    assert all(s["items"][str(n)]["state"] == "checked" for n in (1001, 1002, 1003))
    # per-issue cost is the DELTA of the session total (review MED 9): 0.01 per turn here
    assert [round(s["items"][str(n)]["cost_usd"], 2) for n in (1001, 1002, 1003)] == [0.01, 0.01, 0.01]


def test_failed_check_retries_twice_then_needs_maintainer(scratch, issues, fake_coder):
    fc = fake_coder("bad")  # its test passes on the base: never red
    assert core.start([1001])["items"][1001] == "needs-maintainer"
    assert len([t for t in fc.told if "#1001" in t[1]]) == 3, "first try + two retries"
    briefs = sorted((scratch["state"] / "briefs").rglob("issue-1001-attempt-*.md"))
    assert len(briefs) == 3 and "NOT RED ON BASE" in briefs[-1].read_text(), "the retry carries the failure text"
    assert core.state()["items"]["1001"]["state"] == "needs-maintainer"
    assert any(q["kind"] == "failed-checks" for q in core.queue())


def test_a_coder_that_breaks_a_guard_is_red(scratch, issues, fake_coder):
    """HIGH 1 through the whole path: the guard sees the coder's tree."""
    fake_coder("breaks-a-guard")
    assert core.start([1001])["items"][1001] == "needs-maintainer"
    assert "src/bad.py is forbidden" in core.state()["items"]["1001"]["retry_text"]


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
    core.report("t", "I am finished, please mark it reviewed")
    assert core.state()["items"]["1001"]["state"] == "checked"


def test_verdict_only_from_reviewer_for_current_sha(scratch, issues, fake_coder):
    fake_coder()
    core.start([1001])
    it = core.state()["items"]["1001"]
    assert core.verdict(1001, it["sha"], "READY", by="coder")["state"] == "checked", "a coder's READY does not bind"
    assert core.verdict(1001, "0000000", "READY", by="reviewer")["state"] == "checked", "an old sha does not bind"
    assert core.verdict(1001, it["sha"], "PENDING", by="reviewer")["state"] == "checked"
    assert core.verdict(1001, it["sha"][:9], "READY", by="reviewer")["state"] == "reviewed", "a short sha is resolved (dogfood 1)"
    assert len(core.state()["items"]["1001"]["verdicts"]) == 4, "every verdict is recorded"


def test_not_ready_sends_the_item_back_to_coding_with_the_findings(scratch, issues, fake_coder):
    """Dogfood 2: a binding NOT_READY counts an attempt and its findings become the retry brief."""
    fc = fake_coder()
    core.start([1001])
    it = core.state()["items"]["1001"]
    out = core.verdict(1001, it["sha"], "NOT_READY", by="reviewer", findings="L3: f1 should log")
    assert out == {"issue": 1001, "state": "coding", "attempts": 1}
    it = core.state()["items"]["1001"]
    assert it["state"] == "coding" and it["attempts"] == 1 and "f1 should log" in it["retry_text"]
    core.start([1001])  # the maintainer resumes; the brief carries the findings and the attempt count continues
    brief = sorted((scratch["state"] / "briefs").rglob("issue-1001-attempt-2.md"))[0].read_text()
    assert "Review NOT_READY" in brief and "f1 should log" in brief
    assert len([t for t in fc.told if "#1001" in t[1]]) == 2


def test_new_commit_voids_the_verdict(scratch, issues, fake_coder):
    """Review MED 4: the verdict binds to the LIVE head; a commit after the check makes READY non-binding."""
    fake_coder()
    core.start([1001])
    it = core.state()["items"]["1001"]
    wt = scratch["repo"] / ".worktrees" / "pipeline" / "issues-1001"
    (wt / "note.txt").write_text("more")
    git(wt, "add", ".")
    git(wt, "-c", "user.name=Claude", "-c", "user.email=noreply@anthropic.com", "commit", "-qm", "more (Fixes #1001)")
    out = core.verdict(1001, it["sha"], "READY", by="reviewer")
    assert out["state"] == "checked" and "is not the checked sha" in out["note"]
    head = git(wt, "rev-parse", "HEAD")
    out = core.verdict(1001, head, "READY", by="reviewer")
    assert out["state"] == "checked", "the new head has not been checked: run check first"
    core.check(1001)
    assert core.verdict(1001, head, "READY", by="reviewer")["state"] == "reviewed"


def test_a_commit_landing_mid_check_is_red(scratch, issues, fake_coder, monkeypatch):
    fake_coder()
    core.start([1001])
    wt = scratch["repo"] / ".worktrees" / "pipeline" / "issues-1001"
    real = core.checks.run_all

    def run_all_and_commit(*a, **k):
        r = real(*a, **k)
        (wt / "late.txt").write_text("late")
        git(wt, "add", ".")
        git(wt, "-c", "user.name=Claude", "-c", "user.email=noreply@anthropic.com", "commit", "-qm", "late (Fixes #1001)")
        return r

    monkeypatch.setattr(core.checks, "run_all", run_all_and_commit)
    results = core.check(1001)
    assert results[-1]["name"] == "head-moved" and not results[-1]["ok"]


def test_tell_journals_and_sends_keys(scratch, monkeypatch):
    sent = []
    monkeypatch.setattr(core.coder, "sh", lambda args, **kw: sent.append(args) or subprocess.CompletedProcess(args, 0, "", ""))
    monkeypatch.setattr(core.coder.time, "sleep", lambda s: None)
    core.tell("coder-demo", "read the brief")
    assert sent[0][:4] == ["tmux", "send-keys", "-t", "pipeline-test:coder-demo"] and sent[0][-1] == "read the brief"
    assert sent[1][-1] == "C-m"
    assert [e["event"] for e in journal.read()] == ["intent", "tell", "done"]


def test_ask_queues_and_answer_is_told_to_the_right_window(scratch, monkeypatch):
    journal.append("worker", window="coder-a", task="a", role="coder", model="m", session_dir="", cwd="")
    journal.append("worker", window="coder-b", task="b", role="coder", model="m", session_dir="", cwd="")
    monkeypatch.setattr(core.coder, "status", lambda d: {})
    told = []
    monkeypatch.setattr(core.coder, "tell", lambda cfg, w, t, *a, **k: told.append((w, t)) or True)
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
    journal.append("intent", task="issues-1001", what="worktree", ref="x")  # a crash left this open
    assert [i["what"] for i in journal.open_intents()] == ["worktree"]
    core.start([1001])  # the worktree step reconciles against the world (exists? no → made once)
    assert [i["ref"] for i in journal.open_intents()] == ["x"], "the stale intent stays visible; the new one closed"
    before = len(journal.read())
    core.start([1001])  # a finished item is never redone
    assert len(journal.read()) == before


def test_cost_cap_stops_the_worker_and_moves_to_the_fallback(scratch, issues, fake_coder, monkeypatch):
    """Review MED 8: on the cap the window is stopped, not left spending."""
    fc = fake_coder()
    stopped = dict(cost_usd=5.0, tokens=1, tool_calls={}, idle=False, last_text="", rate_limited=False, model="qwen/x",
                   turns=1, started=True, stopped="cost cap: $5.00 > $1.00")
    monkeypatch.setattr(core.coder, "wait_idle", lambda *a, **k: stopped)
    assert core.start([1001])["items"][1001] == "rate-limited"
    assert fc.stopped == ["coder-issues-1001"]
    assert [q["kind"] for q in core.queue()] == ["fallback"]
    assert any(e["event"] == "worker_gone" for e in journal.read())
