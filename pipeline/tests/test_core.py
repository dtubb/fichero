"""pipeline.one-state-machine, outside-bugs, pause-all, messages, review, retry-with-the-failure, worktree-per-task,
one-coder-per-milestone, resume-from-journal, point-at-a-milestone, maintainer-queue (spec harness/deterministic-conductor.md)."""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

import pytest

from pipeline import core, journal
from pipeline.tests.conftest import git


def test_start_from_a_local_issue_file_for_an_unfiled_step(scratch, fake_coder, tmp_path):
    fake_coder()
    f = tmp_path / "step.json"
    f.write_text(json.dumps({"number": 6116, "part_of": True, "author": "dtubb", "title": "Step 1.2", "body": "do the guard",
                             "labels": [], "milestone": "m"}))
    out = core.start([6116], task="step-1-2", from_file=str(f))
    assert out["items"]["6116@step-1-2"] == "checked", "a from-file step is keyed by number@task"
    text = core.brief(json.loads(f.read_text()), "step-1-2")
    assert "(Part of #6116)" in text and "Fixes" not in text


def test_two_unfiled_steps_sharing_part_of_one_issue_both_run(scratch, fake_coder, tmp_path):
    """Round-3 R3: every bootstrap step carries number 6116; keyed by number they collided and step 1.3 never ran."""
    fc = fake_coder()
    for step in ("1-2", "1-3"):
        (tmp_path / f"{step}.json").write_text(json.dumps({"number": 6116, "part_of": True, "author": "dtubb", "title": f"Step {step}",
                                                           "body": f"step {step}", "labels": [], "milestone": "m"}))
    core.start([6116], task="step-1-2", from_file=str(tmp_path / "1-2.json"))
    it = core.state()["items"]["6116@step-1-2"]
    assert core.verdict("6116@step-1-2", it["sha"], "READY", by="reviewer")["state"] == "reviewed"
    out = core.start([6116], task="step-1-3", from_file=str(tmp_path / "1-3.json"))
    assert out["items"]["6116@step-1-3"] == "checked" and len(fc.windows) == 2
    s = core.state()
    assert s["items"]["6116@step-1-2"]["state"] == "reviewed" and s["items"]["6116@step-1-3"]["attempts"] == 0
    with pytest.raises(KeyError, match="names several items"):
        core.check(6116)
    assert core.verdict("6116@step-1-3", s["items"]["6116@step-1-3"]["sha"], "PENDING", by="manager")["issue"] == "6116@step-1-3"


def test_retry_refuses_a_record_without_start_args_and_repair_fixes_it(scratch, issues, fake_coder):
    """Round-3: no more hand edits of the journal. An old record (no ids) is refused; `repair` appends the lines."""
    fake_coder("bad")
    core.start([1001])  # needs-maintainer after three reds; now forge an old-style record by replaying without ids
    lines = [json.loads(ln) for ln in journal.path().read_text().splitlines()]
    for e in lines:
        if e["event"] == "item":
            e.pop("ids", None)
    journal.path().write_text("\n".join(json.dumps(e) for e in lines) + "\n")
    assert core.state()["items"]["1001"]["start_args"]["ids"] is None
    with pytest.raises(RuntimeError, match="repair 1001"):
        core.retry(1001)
    out = core.repair(1001, base="origin/integration", since="origin/integration", why="record predates start args")
    assert out["repaired"] == ["start args", f"since {git(scratch['repo'], 'rev-parse', 'origin/integration')[:9]}"]
    it = core.state()["items"]["1001"]
    assert it["start_args"]["ids"] == [] and it["start_args"]["base"] == "origin/integration"
    assert it["notes"][-1].startswith("repair: start args, since")
    with pytest.raises(ValueError, match="journal item line lacks"):
        journal.append("item", issue=1, task="t", title="x", window="w", worktree="/wt")


def test_tag_flip_is_allowed_but_an_acceptance_rewrite_is_red(scratch, issues, fake_coder):
    """Round-3 R4: the reviewer's spec-diff rule expects [MISSING] -> [OK] on the item's own behaviour."""
    fc = fake_coder()
    real = fc._tell

    def tell_and_flip(window, text):
        real(window, text)
        spec = fc.cwd / "specs" / "s.md"
        spec.write_text(spec.read_text().replace("[MISSING]", "[OK] (#1001)"))
        git(fc.cwd, "add", ".")
        git(fc.cwd, "-c", "user.name=Claude", "-c", "user.email=noreply@anthropic.com", "commit", "-qm", "flip (Fixes #1001)")

    fc._tell = tell_and_flip
    assert core.start([1001])["items"]["1001"] == "checked"


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
    assert (wt / "RUNNER").exists() and out["items"]["1001"] == "checked"


def test_states_table_is_the_only_transition_path(scratch, issues, fake_coder):
    assert set(core.API) >= {"start", "check", "verdict", "tell", "report", "ask", "done", "answer", "point", "pause", "resume"}
    for role, tools in core.ROLE_TOOLS.items():
        assert set(tools) <= set(core.API), role
    assert "answer" not in sum(core.ROLE_TOOLS.values(), ()), "a model never answers a queue item"
    fake_coder()
    core.start([1001])  # checked
    for bad in ("queued", "pushed", "closed", "candidate"):
        with pytest.raises(RuntimeError, match="no transition checked ->"):
            core._move("1001", bad)
    with pytest.raises(RuntimeError, match="no transition"):
        core._move("1001", "merged")
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
    assert core.start([1001])["items"]["1001"] == "checked"


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
    assert [out["items"][n] for n in ("1001", "1002", "1003")] == ["checked"] * 3
    assert len(fc.windows) == 1, "one context for the batch"
    log = git(fc.cwd, "log", "--format=%s", "origin/integration..HEAD").splitlines()
    assert log == ["fix (Fixes #1003)", "fix (Fixes #1002)", "fix (Fixes #1001)"]
    checks = [e for e in journal.read() if e["event"] == "check"]
    assert [e["issue"] for e in checks] == [1001, 1002, 1003] and all(e["ok"] for e in checks)
    s = core.state()
    assert all(s["items"][str(n)]["state"] == "checked" for n in (1001, 1002, 1003))
    # per-issue cost is the DELTA of the session total (review MED 9): 0.01 per turn here
    assert [round(s["items"][str(n)]["cost_usd"], 2) for n in (1001, 1002, 1003)] == [0.01, 0.01, 0.01]
    t = s["tasks"]["demo-1001"]
    assert (round(t["cost_usd"], 2), t["issues_done"], round(t["cost_per_issue"], 2)) == (0.03, 3, 0.01), "the page's dollars per issue"


def test_failed_check_retries_twice_then_needs_maintainer(scratch, issues, fake_coder):
    fc = fake_coder("bad")  # its test passes on the base: never red
    assert core.start([1001])["items"]["1001"] == "needs-maintainer"
    assert len([t for t in fc.told if "#1001" in t[1]]) == 3, "first try + two retries"
    briefs = sorted((scratch["state"] / "briefs").rglob("issue-1001-attempt-*.md"))
    assert len(briefs) == 3 and "NOT RED ON BASE" in briefs[-1].read_text(), "the retry carries the failure text"
    assert core.state()["items"]["1001"]["state"] == "needs-maintainer"
    assert any(q["kind"] == "failed-checks" for q in core.queue())


def test_a_coder_that_breaks_a_guard_is_red(scratch, issues, fake_coder):
    """HIGH 1 through the whole path: the guard sees the coder's tree."""
    fake_coder("breaks-a-guard")
    assert core.start([1001])["items"]["1001"] == "needs-maintainer"
    assert "src/bad.py is forbidden" in core.state()["items"]["1001"]["retry_text"]


def test_retry_with_the_failure_can_recover(scratch, issues, fake_coder):
    fc = fake_coder("fix-on-retry")
    assert core.start([1001])["items"]["1001"] == "checked"
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
    assert out == {"issue": "1001", "state": "coding", "attempts": 1}
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
    assert out["state"] == "checked" and "has not passed a check" in out["note"]
    head = git(wt, "rev-parse", "HEAD")
    out = core.verdict(1001, head, "READY", by="reviewer")
    assert out["state"] == "checked", "the new head has not been checked: run check first"
    core.check(1001)
    assert core.verdict(1001, head, "READY", by="reviewer")["state"] == "reviewed"


def _break(wt, msg="break (Fixes #1001)"):
    (wt / "src" / "mod.py").write_text("def base():\n    return 0\n\n\ndef f1001():\n    return 2\n")
    git(wt, "add", ".")
    git(wt, "-c", "user.name=Claude", "-c", "user.email=noreply@anthropic.com", "commit", "-qm", msg)


def test_a_red_check_demotes_checked_and_ready_does_not_bind(scratch, issues, fake_coder):
    """Re-review HIGH N1: after `checked` at A, a breaking commit B whose check is red left the item `checked` at
    sha B, and a reviewer READY for B then bound. Failed before the fix."""
    fake_coder()
    core.start([1001])
    wt = scratch["repo"] / ".worktrees" / "pipeline" / "issues-1001"
    _break(wt)
    results = core.check(1001)
    assert not all(r["ok"] for r in results)
    it = core.state()["items"]["1001"]
    assert it["state"] == "coding" and it["check_ok"] is False, "a red check sends checked back to coding"
    out = core.verdict(1001, it["sha"], "READY", by="reviewer")
    assert out["state"] == "coding" and "has not passed a check" in out["note"]


def test_a_red_check_demotes_reviewed_too(scratch, issues, fake_coder):
    fake_coder()
    core.start([1001])
    it = core.state()["items"]["1001"]
    assert core.verdict(1001, it["sha"], "READY", by="reviewer")["state"] == "reviewed"
    _break(scratch["repo"] / ".worktrees" / "pipeline" / "issues-1001")
    core.check(1001)
    assert core.state()["items"]["1001"]["state"] == "coding"


def test_retry_takes_no_flags_and_reuses_the_start_arguments(scratch, issues, fake_coder, tmp_path):
    """Dogfood 5: the item's record keeps task, base and from_file; `retry <issue>` sends the failure back."""
    fc = fake_coder()
    repo = scratch["repo"]
    git(repo, "checkout", "-qb", "runner-branch")
    (repo / "RUNNER").write_text("here\n")
    git(repo, "add", ".")
    git(repo, "-c", "user.name=Claude", "-c", "user.email=noreply@anthropic.com", "commit", "-qm", "runner (Fixes #1001)")
    git(repo, "checkout", "-q", "integration")
    f = tmp_path / "issue.json"
    f.write_text(json.dumps(dict(issues[1001])))
    core.start([1001], task="boot", base="runner-branch", from_file=str(f))
    it = core.state()["items"]["1001@boot"]
    assert it["start_args"] == {"task": "boot", "milestone": None, "base": "runner-branch", "from_file": str(f), "ids": ["demo.one"]}
    core.verdict(1001, it["sha"], "NOT_READY", by="reviewer", findings="rename f1001")  # a bare number resolves to the one item
    out = core.retry(1001)
    assert out["task"] == "boot" and out["items"]["1001@boot"] == "checked"
    assert len(fc.windows) == 2 and fc.windows[1][1] == scratch["repo"] / ".worktrees" / "pipeline" / "boot"
    brief = sorted((scratch["state"] / "briefs" / "boot").glob("issue-1001-attempt-2.md"))[0].read_text()
    assert "rename f1001" in brief


def test_a_retry_is_measured_from_the_items_first_start(scratch, issues, fake_coder):
    """Live 2026-10-25: a retry that only fixed an unused import in the test file was 'NOT RED ON BASE' because the
    base was the retry's own start. Red-on-base and the changed files are measured from the item's first start."""
    fc = fake_coder()
    real = fc._tell
    calls = {"n": 0}

    def lint_fix_on_retry(window, text):
        calls["n"] += 1
        if calls["n"] == 1:
            return real(window, text)
        test = fc.cwd / "tests" / "test_1001.py"
        test.write_text(test.read_text().replace("from src.mod import f1001", "from src.mod import f1001  # tidy"))
        git(fc.cwd, "add", ".")
        git(fc.cwd, "-c", "user.name=Claude", "-c", "user.email=noreply@anthropic.com", "commit", "-qm", "lint (Fixes #1001)")
        fc.turns += 1

    fc._tell = lint_fix_on_retry
    core.start([1001])
    it = core.state()["items"]["1001"]
    core.verdict(1001, it["sha"], "NOT_READY", by="reviewer", findings="tidy the import")
    assert core.retry(1001)["items"]["1001"] == "checked"
    sinces = [e["sha"] for e in journal.read() if e["event"] == "since" and e["issue"] == 1001]
    assert len(sinces) == 2 and sinces[0] == sinces[1], "the retry keeps the item's first since"


def test_each_window_start_gets_its_own_session_dir(scratch, issues, fake_coder):
    """Re-review MED B: a restarted worker read the OLD session file (40 turns) and never looked idle."""
    fake_coder()
    core.start([1001])
    it = core.state()["items"]["1001"]
    core.verdict(1001, it["sha"], "NOT_READY", by="reviewer", findings="again")
    core.retry(1001)
    dirs = [e["session_dir"] for e in journal.read() if e["event"] == "worker"]
    assert len(dirs) == 2 and dirs[0] != dirs[1] and dirs[1].startswith(str(scratch["state"] / "sessions" / "issues-1001"))


def test_rewriting_own_acceptance_in_the_spec_needs_maintainer(scratch, issues, fake_coder):
    """Dogfood 6: the coder edited the spec's Tests line to fit its work."""
    fc = fake_coder()
    real = fc._tell

    def tell_and_edit_spec(window, text):
        real(window, text)
        spec = fc.cwd / "specs" / "s.md"
        spec.write_text(spec.read_text().replace("Test: tests/test_1.py", "Test: none needed"))
        git(fc.cwd, "add", ".")
        git(fc.cwd, "-c", "user.name=Claude", "-c", "user.email=noreply@anthropic.com", "commit", "-qm", "spec (Fixes #1001)")

    fc._tell = tell_and_edit_spec
    assert core.start([1001])["items"]["1001"] == "needs-maintainer"
    assert "rewrites the item's own acceptance" in core.state()["items"]["1001"]["retry_text"]


def _spec_edit_coder(fake_coder, old, new):
    fc = fake_coder()
    real = fc._tell

    def tell_and_edit_spec(window, text):
        real(window, text)
        spec = fc.cwd / "specs" / "s.md"
        spec.write_text(spec.read_text().replace(old, new))
        git(fc.cwd, "add", ".")
        git(fc.cwd, "-c", "user.name=Claude", "-c", "user.email=noreply@anthropic.com", "commit", "-qm", "spec (Fixes #1001)")

    fc._tell = tell_and_edit_spec


def test_a_tag_only_flip_that_adds_a_named_test_is_allowed(scratch, issues, fake_coder):
    _spec_edit_coder(fake_coder, "[MISSING] — acceptance: f(1) is 1. Test: tests/test_1.py",
                     "[OK] — acceptance: f(1) is 1. Test: tests/test_1.py, tests/test_1001.py")
    got = core.start([1001])["items"]["1001"]
    assert got == "checked", core.state()["items"]["1001"]["retry_text"]


@pytest.mark.parametrize("new", [
    "[OK] — acceptance: f(1) is 1, app-side too. Test: tests/test_1.py, tests/test_1001.py",  # reworded
    "[OK] — acceptance: f(1) is 1. Test: tests/test_1001.py",  # swapped
    "[OK] — acceptance: f(1) is 1."])  # dropped
def test_an_ok_flip_that_rewords_swaps_or_drops_the_named_test_needs_maintainer(scratch, issues, fake_coder, new):
    _spec_edit_coder(fake_coder, "[MISSING] — acceptance: f(1) is 1. Test: tests/test_1.py", new)
    assert core.start([1001])["items"]["1001"] == "needs-maintainer"
    assert "rewrites the item's own acceptance" in core.state()["items"]["1001"]["retry_text"]


def test_brief_requires_the_doc_lookup_first_and_forbids_acceptance_edits(scratch, issues):
    """The name is kept (the spec cites it); the first step is now: do not explore, read only what you edit."""
    text = core.brief(issues[1001], "t")
    assert "Do not explore" in text and "brief miss" in text and "Never push" in text
    assert "Never change your own acceptance" in text and "`pipeline_ask`" in text


def test_tools_unused_is_a_note_not_a_failure(scratch, issues, fake_coder):
    fc = fake_coder()
    fc.tools = {"read": 1}  # a session with no jcodemunch call
    assert core.start([1001])["items"]["1001"] == "checked"
    assert core.state()["items"]["1001"]["notes"] == ["tools unused by the first done: jcodemunch"]


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


def test_reset_zeroes_attempts_but_keeps_the_retry_text(scratch, issues, fake_coder):
    fake_coder("bad")
    core.start([1001])  # three red attempts
    it = core.state()["items"]["1001"]
    assert it["attempts"] == 3 and "NOT RED ON BASE" in it["retry_text"]
    core.reset(1001, "the runner's fault")
    it = core.state()["items"]["1001"]
    assert it["attempts"] == 0 and "NOT RED ON BASE" in it["retry_text"]
    assert "reset" in core.WORKER_FORBIDDEN


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


def test_retry_after_a_rate_limited_stop_takes_the_next_worker(scratch, issues, fake_coder, monkeypatch):
    """One ordered fallback list per role: a 402 on Qwen means the retry runs on the next entry (Sonnet)."""
    fc = fake_coder()
    stopped = dict(cost_usd=0.0, tokens=0, tool_calls={}, idle=False, last_text="", rate_limited=True, model="qwen/x",
                   turns=1, prompts=1, started=True)
    monkeypatch.setattr(core.coder, "wait_idle", lambda *a, **k: stopped)
    assert core.start([1001])["items"]["1001"] == "rate-limited"
    monkeypatch.setattr(core.coder, "wait_idle", fc.wait_idle)
    assert core.retry(1001)["items"]["1001"] == "checked"
    models = [e["model"] for e in journal.read() if e["event"] == "worker"]
    assert models == ["openrouter/qwen/x", "anthropic/claude-sonnet-4-5"]


def test_worker_selection_skips_disabled_entries(scratch, issues, fake_coder):
    """pipeline.worker-roles: the role's list in order, `enabled = false` entries skipped (Qwen is configured but off)."""
    fc = fake_coder()
    scratch["cfg"]["roles"]["coder"] = [{"kind": "pi", "provider": "anthropic", "model": "claude-sonnet-5-5"},
                                        {"kind": "pi", "provider": "openrouter", "model": "qwen/x", "enabled": False}]
    assert [w["model"] for w in core.workers()] == ["claude-sonnet-5-5"]
    core.start([1001])
    name, cwd, cmd, env = fc.windows[0]
    assert cmd[3] == "pi" and "--model" in cmd and cmd[cmd.index("--model") + 1] == "anthropic/claude-sonnet-5-5"
    assert not (cwd / ".claude").exists()


def test_a_journal_at_the_daily_cap_refuses_start_until_raised(scratch, issues, fake_coder):
    """Owner 2026-10-25: a hard daily API cap across all items, read from the profile, summed from the journal."""
    fc = fake_coder()
    scratch["cfg"]["workers"]["daily_cap_usd"] = 1.0
    journal.append("cost", issue=5, key="5", task="old", session="s", usd=0.6, tokens=1, model="m", tools={})
    journal.append("cost", issue=6, key="6", task="old", session="s", usd=0.4, tokens=1, model="m", tools={})
    assert core.spend_today() == 1.0 and core.daily_cap() == 1.0
    with pytest.raises(RuntimeError, match="daily cap"):
        core.start([1001])
    assert fc.windows == [], "nothing started"
    out = core.resume(raise_cap=2.5)
    assert out["daily_cap"] == 2.5 and core.daily_cap() == 2.5
    assert core.start([1001])["items"]["1001"] == "checked"
    s = core.state()
    assert s["daily_cap"] == 2.5 and s["spend_today"] == 1.01, "the page shows today's spend against the cap"


def test_an_item_that_hits_the_daily_cap_mid_run_stops_as_rate_limited(scratch, issues, fake_coder):
    fc = fake_coder()
    scratch["cfg"]["workers"]["daily_cap_usd"] = 0.005  # nothing spent yet, so it starts; the first turn costs 0.01
    assert core.start([1001])["items"]["1001"] == "rate-limited"
    it = core.state()["items"]["1001"]
    assert "daily cap" in it["history"][-1] and fc.stopped == ["coder-issues-1001"], "the window is stopped, not left spending"
    with pytest.raises(RuntimeError, match="daily cap"):
        core.start([1002])  # and nothing new starts today


def test_wait_idle_gets_the_smaller_of_session_cap_and_what_is_left_today(scratch, issues, fake_coder, monkeypatch):
    """#6145: the daily cap is enforced inside the turn (as wait_idle's cap), and its stop queues 'budget'."""
    fc = fake_coder()
    scratch["cfg"]["workers"]["daily_cap_usd"] = 0.5
    caps = []
    real = fc.wait_idle
    monkeypatch.setattr(core.coder, "wait_idle", lambda sd, cap, **kw: (caps.append(cap), real(sd, cap, **kw))[1])
    scratch["cfg"]["workers"]["daily_cap_usd"] = 0.005
    assert core.start([1001])["items"]["1001"] == "rate-limited"
    assert caps and caps[0] == pytest.approx(0.005) and caps[0] < scratch["cfg"]["workers"]["cost_cap_usd"]
    assert [q["kind"] for q in core.state()["queue"].values()] == ["budget"], "every worker is under the same cap: ask for budget"


def test_each_role_has_its_own_mcp_wrapper(scratch):
    a, b = core.coder.mcp_bin("t1", "coder"), core.coder.mcp_bin("t1", "reviewer")
    assert a != b and "role coder" in (a / "pipeline-mcp").read_text().replace("--role", "role") and (b / "pipeline-mcp").exists()


def test_review_runs_a_pi_reviewer_and_binds_its_verdict(scratch, issues, fake_coder, monkeypatch):
    """The smallest Pi reviewer path: a reviewer window, a brief, a wait for `pipeline_verdict`, its cost on the item."""
    fc = fake_coder()
    core.start([1001])
    it = core.state()["items"]["1001"]
    scratch["cfg"]["roles"]["reviewer"] = [{"kind": "pi", "provider": "anthropic", "model": "claude-opus-5-5"}]

    def reviewer_answers(session_dir, cap_usd, after_turns=0, poll=10.0, timeout_s=3600, note=None, token_cap=None):
        core.verdict("1001", it["sha"], "READY", by="reviewer", findings="L1: fine")  # what the pipeline_verdict tool does
        return dict(cost_usd=0.2, tokens=50, tool_calls={"pipeline_verdict": 1}, idle=True, last_text="Verdict recorded.",
                    rate_limited=False, model="claude-opus-5-5", turns=1, prompts=1, started=True)

    monkeypatch.setattr(core.coder, "wait_idle", reviewer_answers)
    out = core.review("1001")
    assert out["state"] == "reviewed" and out["verdict"]["verdict"] == "READY" and out["reviewer_cost_usd"] == 0.2
    assert fc.windows[-1][0] == "reviewer" and "ponytail-reviewer.md" in " ".join(fc.windows[-1][2])
    brief = sorted((scratch["state"] / "briefs" / "issues-1001").glob("review-*.md"))[0].read_text()
    assert "pipeline_verdict" in brief and it["sha"] in brief
    assert round(core.state()["items"]["1001"]["cost_usd"], 2) == 0.21, "the reviewer's cost is inside the item's cap"
    assert fc.stopped[-1] == "reviewer"
    with pytest.raises(RuntimeError, match="needs a green check"):
        core.review("1001")  # reviewed, not checked: nothing to review


def test_cost_cap_stops_the_worker_and_moves_to_the_fallback(scratch, issues, fake_coder, monkeypatch):
    """Review MED 8: on the cap the window is stopped, not left spending."""
    fc = fake_coder()
    stopped = dict(cost_usd=5.0, tokens=1, tool_calls={}, idle=False, last_text="", rate_limited=False, model="qwen/x",
                   turns=1, started=True, stopped="cost cap: $5.00 > $1.00")
    monkeypatch.setattr(core.coder, "wait_idle", lambda *a, **k: stopped)
    assert core.start([1001])["items"]["1001"] == "rate-limited"
    assert fc.stopped == ["coder-issues-1001"]
    assert [q["kind"] for q in core.queue()] == ["fallback"]
    assert any(e["event"] == "worker_gone" for e in journal.read())


def test_brief_carries_spec_lines_files_and_the_test_to_write(scratch, issues):
    """pipeline.batch-session: localisation is model-free; the brief names the files, symbols and the test to write."""
    iss = dict(issues[1001], body="Change `base` in src/mod.py. Test: tests/test_new.py::test_new")
    iss["localised"] = core.localised(iss, "t", "1001")
    text = core.brief(iss, "t")
    assert "- src/mod.py" in text and "`base`: src/mod.py:1:def base" in text
    assert "tests/test_new.py::test_new" in text and "must fail before your change" in text
    assert iss["localised"]["size"] == "small"
    assert any(e["event"] == "localised" and e["files"] == ["src/mod.py"] for e in journal.read())


def test_brief_is_a_stable_prefix_then_the_issue_tail(scratch, issues):
    a, b = core.brief(issues[1001], "t1"), core.brief(issues[1002], "t2")
    head = lambda t: t.split("# Issue #")[0]  # noqa: E731
    assert head(a) == head(b) and "1001" not in head(a) and "t1" not in head(a), "no ids or tasks before the tail"


def test_a_model_names_the_files_only_when_localisation_finds_nothing(scratch, issues, monkeypatch):
    calls = []

    def ask_once(cfg, worker, prompt, session_dir):
        calls.append(worker["model"])
        return {"answer": "src/mod.py\ntests/test_9.py", "cost_usd": 0.001, "tokens": 50, "model": worker["model"]}

    monkeypatch.setattr(core.coder, "ask_once", ask_once)
    core.localised(dict(issues[1001], body="Change `base` in src/mod.py."), "t", "1001")
    assert calls == [], "the body names a file: no model call"
    loc = core.localised(dict(issues[1002], body="Make f(2) return 2."), "t", "1002")
    assert len(calls) == 1 and loc["files"] == ["src/mod.py"] and loc.get("by_model")


def test_a_small_batch_goes_to_the_small_tier_and_a_big_one_to_the_big(scratch, issues, fake_coder):
    scratch["cfg"]["tiers"] = {"openrouter": {"big": "qwen/big", "small": "qwen/small"}, "anthropic": {"big": "b", "small": "s"}}
    fc = fake_coder()
    ISS = __import__("pipeline.tests.conftest", fromlist=["ISSUES"]).ISSUES
    ISS[1001]["body"] += " Change `base` in src/mod.py."
    core.start([1001])
    assert "openrouter/qwen/small" in " ".join(fc.windows[0][2])


def test_approve_checks_records_the_files_and_sends_the_findings(scratch, issues, fake_coder):
    fc = fake_coder()
    real = fc._tell

    def tell_and_touch_a_guard(window, text):
        real(window, text)
        (fc.cwd / "scripts" / "check_no_bad.py").write_text("print('ok, but changed')\n")
        git(fc.cwd, "add", ".")
        git(fc.cwd, "-c", "user.name=Claude", "-c", "user.email=noreply@anthropic.com", "commit", "-qm", "guard (Fixes #1001)")

    fc._tell = tell_and_touch_a_guard
    assert core.start([1001])["items"]["1001"] == "needs-maintainer"
    fc._tell = real
    out = core.approve_checks(1001, "the maintainer approved the guard change; carry on")
    assert out["approved"] == ["scripts/check_no_bad.py"]
    it = core.state()["items"]["1001"]
    assert list(it["approved_checks"]) == ["scripts/check_no_bad.py"] and "approved the guard change" in it["retry_text"]
    with pytest.raises(RuntimeError, match="approve-checks is for a needs-maintainer"):
        core.approve_checks(1001, "again")


def test_batch_done_per_issue_checks_while_the_worker_moves_on(scratch, issues, fake_coder, monkeypatch):
    """Issue 1's checks run on ITS done sha while issue 2's brief is already with the worker; each issue has a done line."""
    import time

    from pipeline import checks
    fc = fake_coder()
    real, seen = checks.run_all, {}

    def run_all(wt, cfg, *a, head="HEAD", **kw):
        n = int(git(wt, "log", "-1", "--format=%s", head).split("#")[1].rstrip(")"))
        if n == 1001:  # the sequential runner never gets past this wait: it tells 1002 only after the check returns
            t0 = time.time()
            while git(wt, "rev-parse", "HEAD") == git(wt, "rev-parse", head) and time.time() - t0 < 30:
                time.sleep(0.05)  # waits for the worker's next commit
            seen["moved_on"] = any("#1002" in t for _, t in fc.told) and git(wt, "rev-parse", "HEAD") != git(wt, "rev-parse", head)
        return real(wt, cfg, *a, head=head, **kw)

    monkeypatch.setattr(checks, "run_all", run_all)
    out = core.start([1001, 1002], milestone="demo")
    assert seen["moved_on"] and [out["items"][n] for n in ("1001", "1002")] == ["checked", "checked"]
    dones = [e for e in journal.read() if e["event"] == "issue_done"]
    assert [e["issue"] for e in dones] == [1001, 1002] and dones[0]["sha"] != dones[1]["sha"]
    s = core.state()["items"]
    assert [i["dones"][0]["sha"] for i in (s["1001"], s["1002"])] == [d["sha"] for d in dones]
    assert s["1001"]["sha"] == dones[0]["sha"], "the check judged the done sha, not the moved head"
    core.done("demo-1001", 1002, "the second acceptance line is left")
    assert core.state()["items"]["1002"]["residue"] == "the second acceptance line is left"


def test_batch_ends_at_the_context_budget_with_a_handoff_note(scratch, issues, fake_coder):
    """Past batch_end_pct of the context a fresh window takes the rest, and its brief points at a note built from the journal."""
    fc = fake_coder()
    fc.context = 900  # 90 % of the 1000-token window once the first issue is in
    out = core.start([1001, 1002], milestone="demo")
    assert list(out["items"].values()) == ["checked", "checked"]
    h = [e for e in journal.read() if e["event"] == "handoff"]
    assert len(h) == 1 and "coder-demo-1001" in fc.stopped
    note = Path(h[0]["note"]).read_text()
    assert "#1001" in note and "src/mod.py" in note
    assert h[0]["note"] in core.brief({**core.ISSUE(1002), "handoff": h[0]["note"]}, "demo")
    assert len([e for e in journal.read() if e["event"] == "worker"]) == 2, "a second window started"


def test_parked_worker_is_woken_for_the_same_kind_within_park_ttl(scratch, issues, fake_coder):
    """A finished milestone batch parks its window; the next issue of that milestone reuses it, a later or other one starts fresh."""
    fc = fake_coder()
    core.start([1001], milestone="demo")
    assert core.state()["workers"]["coder-demo-1001"]["parked"]
    out = core.start([1002], milestone="demo")
    assert out["window"] == "coder-demo-1001" and len([e for e in journal.read() if e["event"] == "worker"]) == 1
    assert [e["event"] for e in journal.read() if e["event"] in ("park", "wake")] == ["park", "wake", "park"]
    scratch["cfg"]["workers"]["park_ttl_minutes"] = 0  # idled past the ttl: stopped, not woken
    time.sleep(1.1)
    core.start([1003], milestone="demo")
    assert "coder-demo-1001" in fc.stopped


def _landed(scratch, monkeypatch, labels=(), residue="", milestone_open=1, comments=()):
    """Issue 1001 coded and checked, its commit pushed to the base branch; a fake GitHub that records the writes."""
    from pipeline import gh
    core.start([1001], milestone="demo")
    if residue:
        core.done("demo-1001", 1001, residue)
    git(Path(core.state()["tasks"]["demo-1001"]["worktree"]), "push", "-q", "origin", "HEAD:integration")
    writes = []
    monkeypatch.setattr(gh, "sh", lambda args, **kw: writes.append(args[1:]) or type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})())

    def read(*a):
        if a[0] == "issue":
            return {"state": "OPEN", "labels": [{"name": n} for n in labels], "milestone": {"title": "demo"},
                    "comments": [{"body": b} for b in comments]}
        return [{"title": "demo", "number": 7, "open_issues": milestone_open, "closed_issues": 0}] if "milestones" in a[1] else []
    monkeypatch.setattr(gh, "read", read)
    return writes


def test_landing_closes_through_the_one_closer_after_a_dry_run_line(scratch, issues, fake_coder, monkeypatch):
    """Dry run writes nothing; --apply journals the dry-run line, then closes with the sha and checks, and the milestone with its last issue."""
    fake_coder()
    writes = _landed(scratch, monkeypatch)
    assert core.close_landed()["closed"] == [1001] and not writes, "the default is a dry run"
    core.DRY_RUN = False
    out = core.close_landed()
    assert out == {"closed": [1001], "residue": [], "milestones": ["demo"]}
    close = next(a for a in writes if a[:2] == ["issue", "close"])
    sha = core.state()["items"]["1001"]["sha"][:9]
    assert sha in close[-1] and "Checks green" in close[-1]
    gw = [e["dry_run"] for e in journal.read() if e["event"] == "gh_write" and e["args"][:2] == ["issue", "close"]]
    assert gw == [True, True, False], "a dry-run line before the real close"
    assert any(a[:3] == ["api", "-X", "PATCH"] for a in writes)
    assert core.close_landed()["closed"] == [], "closed once"


def test_a_residue_leaves_the_issue_open_with_what_is_left(scratch, issues, fake_coder, monkeypatch):
    fake_coder()
    writes = _landed(scratch, monkeypatch, residue="the second acceptance line")
    core.DRY_RUN = False
    out = core.close_landed()
    assert out["residue"] == [1001] and not out["closed"] and not out["milestones"]
    assert any(a[:3] == ["issue", "comment", "1001"] and "second acceptance line" in a[-1] for a in writes)
    assert any(a[:2] == ["issue", "edit"] and "residue" in a for a in writes) and not any(a[:2] == ["issue", "close"] for a in writes)


def test_an_issues_usage_is_its_own_share_of_the_window(scratch):
    """Done lines carry the window's running totals; an issue's usage is the step since the task's last done line, and a new coder window counts from zero."""
    def item(n):
        journal.append("item", issue=n, key=str(n), task="t", title="x", window="w", worktree="/wt", ids=[])
    for n in (1, 2, 3):
        item(n)
    journal.append("worker", window="w", task="t", role="coder", model="m", session_dir="s", cwd="/wt")
    journal.append("issue_done", issue=1, key="1", task="t", sha="a", turns=3, tokens=1000, usd=0.1, fresh=100, cache_read=500, cache_write=0)
    journal.append("issue_done", issue=2, key="2", task="t", sha="b", turns=8, tokens=4000, usd=0.4, fresh=300, cache_read=2500, cache_write=0)
    journal.append("worker", window="r", task="t", role="reviewer", model="m", session_dir="s2", cwd="/wt")  # a reviewer does not reset the coder's count
    journal.append("worker", window="w", task="t", role="coder", model="m", session_dir="s3", cwd="/wt")
    journal.append("issue_done", issue=3, key="3", task="t", sha="c", turns=2, tokens=900, usd=0.09, fresh=90, cache_read=400, cache_write=0)
    u = {k: core.state()["items"][k]["usage"] for k in "123"}
    assert (u["1"]["turns"], u["2"]["turns"], u["3"]["turns"]) == (3, 5, 2)
    assert u["2"]["tokens"] == 3000 and u["2"]["usd"] == pytest.approx(0.3) and u["3"]["cache_read"] == 400


def test_a_milestone_with_unfiled_build_steps_stays_open(scratch, issues, fake_coder, monkeypatch):
    """The closer closes the issue but leaves a milestone open while its spec has a build step with no issue number."""
    fake_coder()
    writes = _landed(scratch, monkeypatch)
    spec = scratch["repo"] / "specs" / "m.md"
    spec.write_text("# M\n\n> Milestone: demo\n\n## Build order\n\n#### Step 1.1 — filed (#1001)\n#### Step 1.2 — not filed yet\n")
    core.DRY_RUN = False
    out = core.close_landed()
    assert out["closed"] == [1001] and out["milestones"] == [] and not any(a[:3] == ["api", "-X", "PATCH"] for a in writes)
    assert core.unfiled_steps("demo") == ["#### Step 1.2 — not filed yet"]


@pytest.mark.parametrize("how", ["comment", "label", "part-of", "clean"])
def test_the_closer_leaves_an_issue_with_residue_or_a_part_of_commit_open(scratch, issues, fake_coder, monkeypatch, how):
    """Live 2026-10-26: four issues with residue in their last comment were closed. Only an explicit Fixes with nothing owed closes."""
    fc = fake_coder()
    fc.keyword = "Part of" if how == "part-of" else "Fixes"
    writes = _landed(scratch, monkeypatch, labels=["needs-your-test"] if how == "label" else (),
                     comments=["Landed; still owed: the second line"] if how == "comment" else ["Landed, all done"])
    core.DRY_RUN = False
    out = core.close_landed()
    assert (out["closed"] == [1001]) == (how == "clean")
    assert any(a[:2] == ["issue", "close"] for a in writes) == (how == "clean")


def test_a_part_of_commit_with_reported_residue_still_posts_the_residue(scratch, issues, fake_coder, monkeypatch):
    fc = fake_coder()
    fc.keyword = "Part of"
    writes = _landed(scratch, monkeypatch, residue="the iPad half")
    core.DRY_RUN = False
    out = core.close_landed()
    assert out["residue"] == [1001] and not out["closed"]
    assert any(a[:2] == ["issue", "comment"] and "iPad half" in a[-1] for a in writes) and any("--add-label" in a for a in writes)


def test_an_issue_over_its_turn_budget_asks_instead_of_retrying(scratch, issues, fake_coder, monkeypatch):
    fc = fake_coder("bad")
    monkeypatch.setitem(core.cfg()["workers"], "issue_turns_max", 0)  # the first red attempt is already over
    assert core.start([1001])["items"]["1001"] == "needs-maintainer"
    assert len([t for t in fc.told if "#1001" in t[1]]) == 1, "no second attempt"
    assert any(q["kind"] == "ask" and "over its budget" in q["text"] for q in core.queue())


def test_review_in_a_batch_diffs_only_that_issues_commit(scratch, issues, fake_coder, monkeypatch):
    fake_coder()
    core.start([1001, 1002, 1003], milestone="demo")
    dones = {e["key"]: e["sha"] for e in journal.read() if e["event"] == "issue_done"}
    scratch["cfg"]["roles"]["reviewer"] = [{"kind": "pi", "provider": "anthropic", "model": "claude-opus-5-5"}]
    monkeypatch.setattr(core.coder, "wait_idle", lambda *a, **k: dict(cost_usd=0.1, tokens=1, tool_calls={}, idle=True, last_text="",
                        rate_limited=False, model="m", turns=1, prompts=1, started=True))
    core.review("1002")
    brief = next(scratch["state"].rglob("review-*.md")).read_text()
    assert f"git diff {dones['1001'][:9]}...{dones['1002'][:9]}" in brief
