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


# local.step.stacks-on-a-waiting-step: with [loop].stack_depth = 1 a lane's next step starts on its step waiting for the train

def _stacked_world(tmp_path, monkeypatch):
    from fichero_builder import train
    from test_queue_verb import Fake
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    monkeypatch.setattr(queue, "TRAIN", [train.Cfg(min_steps=5, max_wait_min=1e6)])  # no train runs unless the test runs one
    monkeypatch.setattr(queue, "STACK_DEPTH", [1])
    for n in ("1", "2", "3"):
        (tmp_path / f"b{n}").write_text(f"brief {n}")
        queue.add("ln", "/w/ln", n, str(tmp_path / f"b{n}"), [int(n)])
    fake = Fake()
    fake.procs.train_run = lambda spec, tid, **k: train.Result(id=tid, steps=[x["key"] for x in spec], again=[x["key"] for x in spec])
    fake.heads, fake.chained, fake.rebases, fake.holds, fake.resumes = {}, [], [], [], []
    fake.resume_why = ""

    def chain(lane, step, stage):
        fake.chained.append((step["step"], step.get("stack_base", "")))
        return {"ok": True, "head": fake.heads.get(step["step"], "h" + step["step"]), "why": "", "findings": ""}
    fake.procs.chain = chain
    fake.procs.rebase = lambda lane: fake.rebases.append(lane["id"]) or ""
    fake.procs.stack_hold = lambda lane, step, under: fake.holds.append((step["step"], under)) or ""
    fake.procs.stack_resume = lambda lane, step, under: fake.resumes.append((step["step"], under)) or fake.resume_why
    handles: dict = {}

    def tick(n=1):
        for _ in range(n):
            queue.tick(fake.procs, handles, workers_n=2, push=False, out=lambda s: None)
    return fake, tick, handles


def _st():
    (lane,) = queue.load()
    return lane, {s["step"]: s for s in lane["steps"]}


def test_step_two_starts_on_step_ones_head_while_one_waits_for_the_train_and_is_checked_over_its_own_range(tmp_path, monkeypatch):
    fake, tick, _h = _stacked_world(tmp_path, monkeypatch)
    tick(3)  # 1: sent, done + checked -> train, then 2 stacks on it
    lane, st = _st()
    assert st["1"]["state"] == "train" and lane["cursor"] == 1
    assert st["2"]["stacked_on"] == "1" and st["2"]["stack_base"] == "h1"
    assert any(r.get("state") == "stacked" and r["step"] == "2" for r in journal.read() if r["event"] == "queue")
    tick(2)
    lane, st = _st()
    assert fake.sent[-1] == "brief 2" and not fake.rebases, "sent into the kept session on 1's head: never rebased onto the land branch"
    assert ("2", "h1") in fake.chained, "its checks read the range from 1's head"
    assert st["2"]["state"] == "train" and st["1"]["state"] == "train"
    tick(2)
    lane, st = _st()
    assert lane["cursor"] == 1 and st["3"]["state"] == "queued" and not st["3"].get("stacked_on"), "one step stacks on one; a third waits"
    from fichero_builder import work
    a = types.SimpleNamespace(stack_base="h1")
    assert work.check_since(a, "/e", "integration") == "h1"


def test_when_step_one_goes_back_step_twos_commits_are_kept_under_a_ref_and_rebased_onto_the_fixed_head(tmp_path, monkeypatch):
    fake, tick, handles = _stacked_world(tmp_path, monkeypatch)
    tick(4)  # 2 stacked and sent
    lane, st = _st()
    assert st["2"]["state"] == "sent"
    lanes = queue.load()
    lanes[0]["steps"][0]["train_back"] = {"ok": False, "kind": "red", "why": "the train is red at unit", "findings": "test_x failed"}
    queue.save(lanes)
    tick()
    lane, st = _st()
    assert fake.holds == [("2", "h1")] and "ln" in fake.stops, "the session stops, 2's work is set aside, the tree goes to 1's head"
    assert lane["cursor"] == 0 and st["2"]["state"] == "queued" and st["2"]["stack_held"]["under_head"] == "h1"
    assert any(r.get("state") == "stack-held" for r in journal.read() if r["event"] == "queue")
    fake.heads["1"] = "h1b"
    tick(4)  # 1's fix round, its DONE, its check, back in the train; then 2 resumes on h1b
    lane, st = _st()
    assert "test_x failed" in open(st["1"]["resume_brief"]).read() and len(fake.starts) == 2, "1 got its fix round, in a new session"
    assert fake.resumes == [("2", "h1")] and lane["cursor"] == 1
    assert st["2"]["stacked_on"] == "1" and st["2"]["stack_base"] == "h1b" and "stack_held" not in st["2"]
    assert st["2"].get("resume_brief"), "it was at work: it goes on from the tree"
    tick()
    assert "Continue from the tree" in fake.sent[-1]
    # the jailed tree, with real git
    _git_round_trip(tmp_path, monkeypatch, conflict=False)


def test_a_conflict_in_that_rebase_is_step_twos_fix_round(tmp_path, monkeypatch):
    from fichero_builder import work
    fake, tick, handles = _stacked_world(tmp_path, monkeypatch)
    tick(4)
    lanes = queue.load()
    lanes[0]["steps"][0]["train_back"] = {"ok": False, "kind": "red", "why": "red", "findings": "f"}
    queue.save(lanes)
    fake.heads["1"] = "h1b"
    fake.resume_why = "2 could not be put back on h1b: conflict in a.txt" + work.REBASE_CONFLICT + "CHERRY-PICK IT YOURSELF"
    tick(6)
    lane, st = _st()
    assert lane["cursor"] == 1 and st["2"]["conflict_rounds"] == 1
    assert "CHERRY-PICK IT YOURSELF" in fake.sent[-1] and st["2"]["state"] == "sent"
    assert any(r.get("state") == "stack-conflict" for r in journal.read() if r["event"] == "queue")
    text = _git_round_trip(tmp_path, monkeypatch, conflict=True)
    assert work.REBASE_CONFLICT in text and "a.txt" in text and "stack/ln/2" in text


def _git_round_trip(tmp_path, monkeypatch, conflict: bool) -> str:
    """work.stack_hold then work.stack_resume in a real tree: the wip commit, the ref, the reset, the cherry-pick back."""
    import subprocess

    from fichero_builder import work
    wt = tmp_path / "wt"
    wt.mkdir()

    def g(*a):
        return subprocess.run(["git", "-C", str(wt), *a], capture_output=True, text=True, check=True).stdout.strip()
    g("init", "-q", "-b", "lane-ln")
    g("config", "user.email", "w@x"), g("config", "user.name", "w"), g("config", "commit.gpgsign", "false")
    (wt / "a.txt").write_text("one\n")
    g("add", "-A"), g("commit", "-q", "-m", "step 1")
    h1 = g("rev-parse", "HEAD")
    (wt / "b.txt").write_text("two\n")
    g("add", "-A"), g("commit", "-q", "-m", "step 2 part")
    (wt / "a.txt").write_text("one\nmine\n" if conflict else "one\n")
    (wt / "c.txt").write_text("not committed\n")
    monkeypatch.setattr(work, "as_worker", lambda a, script: subprocess.run(["sh", "-c", script], capture_output=True, text=True))
    monkeypatch.setattr(work, "jail_git", lambda: "git")
    a = types.SimpleNamespace(worktree=str(wt), name="ln")
    assert work.stack_hold(a, "2", h1) == ""
    assert g("rev-parse", "HEAD") == h1 and g("status", "--porcelain") == "", "the tree is at 1's head, clean"
    assert g("log", "--format=%s", f"{h1}..refs/heads/stack/ln/2").splitlines() == ["wip: 2", "step 2 part"]
    (wt / "a.txt").write_text("one\nfixed\n" if conflict else "one\nfix\n")
    g("add", "-A"), g("commit", "-q", "-m", "step 1 fix")
    why = work.stack_resume(a, "2", h1)
    if conflict:
        assert g("status", "--porcelain") == "" and g("log", "-1", "--format=%s") == "step 1 fix", "aborted: the tree is 1's fixed head"
        assert g("rev-parse", "--verify", "refs/heads/stack/ln/2"), "the kept commits stay for the worker"
        return why
    assert why == ""
    assert g("log", "-2", "--format=%s").splitlines() == ["step 2 part", "step 1 fix"], "2's commits on 1's fixed head"
    assert (wt / "c.txt").read_text() == "not committed\n" and "c.txt" in g("status", "--porcelain"), "the wip is uncommitted again"
    assert subprocess.run(["git", "-C", str(wt), "rev-parse", "--verify", "-q", "refs/heads/stack/ln/2"], capture_output=True).returncode, "the ref is gone"
    return why


def test_when_step_one_is_cleared_it_lands_alone_and_step_two_goes_on_from_its_landed_head(tmp_path, monkeypatch):
    fake, tick, handles = _stacked_world(tmp_path, monkeypatch)
    tick(4)
    lanes = queue.load()
    lanes[0]["steps"][0].update(state="done", train_cleared="train-x")  # the train cleared 1 alone
    queue.save(lanes)
    tick()
    assert fake.holds == [("2", "h1")] and queue.load()[0]["cursor"] == 0
    tick(2)
    lane, st = _st()
    assert fake.landed_calls[0][0] == "h1" and st["1"]["state"] == "landed"
    assert fake.resumes == [("2", "h1")] and lane["cursor"] == 1 and "stacked_on" not in st["2"]
    tick()
    lane, st = _st()
    assert fake.starts[-1][1] == "2" and "Continue from the tree" in open(st["2"]["resume_brief"]).read(), "a new session goes on from the tree"


def test_a_head_holding_another_lanes_unlanded_commits_is_refused_before_its_check(tmp_path, monkeypatch):
    """2026-11-27 05:14: told of a train conflict, kg-readable 2.3's worker merged the training lane's branch; the rebase after it
    flattened ~25 training commits into the step. Commits whose patch-id is one of another lane's unlanded step's are found."""
    import subprocess as sp

    from fichero_builder import journal, queue, work
    r = tmp_path / "r"
    r.mkdir()
    g = lambda *a: sp.run(["git", "-C", str(r), "-c", "user.name=t", "-c", "user.email=t@t", *a], check=True, capture_output=True, text=True).stdout.strip()  # noqa: E731
    (r / "base.txt").write_text("0\n")
    g("init", "-q", "-b", "integration"), g("add", "."), g("commit", "-qm", "base")
    base = g("rev-parse", "HEAD")
    g("checkout", "-qb", "training", base)
    for n in ("cycle", "start_sheet"):
        (r / f"{n}.py").write_text(n), g("add", "."), g("commit", "-qm", f"feat(training): {n}")
    training = g("rev-parse", "HEAD")
    g("checkout", "-qb", "kg", base)
    (r / "kg.py").write_text("kg"), g("add", "."), g("commit", "-qm", "feat(kg): place")
    clean = g("rev-parse", "HEAD")
    g("merge", "-q", "--no-edit", "training")
    g("rebase", "-q", "integration")  # the flattening: the training commits are now the step's own, new shas, same patches
    flat = g("rev-parse", "HEAD")
    others = [("training/1b", training)]
    assert work.foreign_commits(str(r), base, clean, others) == []
    hits = work.foreign_commits(str(r), base, flat, others)
    assert sorted(c.split(" ", 1)[1] for _k, c in hits) == ["feat(training): cycle", "feat(training): start_sheet"] and {k for k, _c in hits} == {"training/1b"}
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    (tmp_path / "s").mkdir()
    (tmp_path / "b").write_text("b")
    queue.add("kg", "/w/kg", "2.3", str(tmp_path / "b"), [1])
    queue.add("training", "/w/t", "1b", str(tmp_path / "b"), [2])
    lanes = queue.load()
    lanes[1]["steps"][0].update(state="train", head=training)
    queue.save(lanes)
    assert queue.other_heads("kg") == [("training/1b", training)] and queue.other_heads("training") == []


@pytest.mark.parametrize("merged", [True, False])
def test_a_lane_branch_left_from_an_old_batch_is_deleted_and_the_tree_made_when_it_is_merged_else_the_add_fails_as_before(tmp_path, monkeypatch, merged):
    """2026-11-27 11:17: runner-reliability's new tree could not be made: "a branch named 'lane-runner-reliability' already exists",
    a branch from 11-16 that origin/integration held in full; the manager deleted it by hand."""
    import types

    from fichero_builder import journal, work
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    (tmp_path / "pin").mkdir()
    (tmp_path / "pin" / "harness.toml").write_text('[land]\nbranch = "integration"\n')
    monkeypatch.setattr(work, "_jail", lambda a: types.SimpleNamespace(workroot=str(tmp_path / "wr")))
    monkeypatch.setattr(work, "jail_git", lambda: "git")
    adds, ran = [0], []

    def as_worker(a, script):
        ran.append(script)
        if "worktree add" in script:
            adds[0] += 1
            if adds[0] == 1:
                return types.SimpleNamespace(returncode=128, stdout="", stderr="fatal: a branch named 'lane-rr' already exists")
            return types.SimpleNamespace(returncode=0, stdout="", stderr="")
        if "merge-base --is-ancestor" in script:
            return types.SimpleNamespace(returncode=0 if merged else 1, stdout="", stderr="")
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")
    monkeypatch.setattr(work, "as_worker", as_worker)
    a = types.SimpleNamespace(worktree=str(tmp_path / "wt-rr"), pinned=str(tmp_path / "pin"), name="rr")
    why = work.ensure_worktree(a, "lane-rr")
    if merged:
        assert why == "" and adds[0] == 2 and any("branch -D lane-rr" in s for s in ran)
        assert [r["state"] for r in journal.read() if r.get("event") == "cleanup"] == ["merged-branch-deleted"]
    else:
        assert "already exists" in why and adds[0] == 1 and not any("branch -D" in s for s in ran)
