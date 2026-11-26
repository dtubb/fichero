"""local.train.*: the merge train over fakes: one pass for many steps, a bisect that lands the green ones, a conflict that drops one."""
from __future__ import annotations

import subprocess

import pytest

from fichero_builder import train


class World:
    """merge/rung fakes: a candidate is the heads in it joined by `+`; a `bad` head makes the `swift-tests` rung red while it is in the candidate."""

    def __init__(self, bad=(), conflict=()):
        self.bad, self.conflict = set(bad), set(conflict)
        self.runs = []

    def merge(self, heads):
        kept = [h for h in heads if h not in self.conflict]
        return "+".join(kept), {h: f"conflict in {h}.txt" for h in heads if h in self.conflict}

    def rung(self, name, cand):
        self.runs.append((name, cand))
        hit = [h for h in cand.split("+") if h in self.bad and name == "swift-tests"]
        return (not hit), (f"{name} failed: {hit[0]}" if hit else "ok")

    def go(self, heads, names=("build", "swift-tests", "unit")):
        steps = [{"key": f"l/{h}", "head": h} for h in heads]
        return train.run_train(steps, merge=self.merge, rung=self.rung, rungs_for=lambda hs: list(names), tid="t1")


def test_four_green_steps_land_together_after_one_run_of_each_rung():
    w = World()
    r = w.go(["a", "b", "c", "d"])
    assert r.result == "green" and r.landed == ["l/a", "l/b", "l/c", "l/d"] and not r.back and r.extra_runs == 0
    assert [n for n, _ in w.runs] == ["build", "swift-tests", "unit"], "each rung once for the four steps"
    assert [x["name"] for x in r.rungs] == ["build", "swift-tests", "unit"]


def test_a_red_train_of_four_lands_three_and_sends_back_the_culprit_within_three_extra_runs():
    for culprit in "abcd":
        r = World(bad={culprit}).go(["a", "b", "c", "d"])
        assert set(r.back) == {f"l/{culprit}"} and r.back[f"l/{culprit}"]["kind"] == "red"
        assert f"swift-tests failed: {culprit}" in r.back[f"l/{culprit}"]["findings"]
        assert r.landed == [f"l/{h}" for h in "abcd" if h != culprit] and r.result == "red"
        assert r.extra_runs <= 3 == train.budget(4), (culprit, r.bisect)
    w = World(bad={"c"})  # the first pass stops at the red rung; the bisect re-runs only it over prefixes, then it and the rungs after it over the rest
    w.go(["a", "b", "c", "d"])
    assert [n for n, _ in w.runs] == ["build", "swift-tests", "swift-tests", "swift-tests", "swift-tests", "unit"]


@pytest.mark.parametrize("n", [1, 2, 3, 5, 8])
def test_the_extra_runs_never_pass_ceil_log2_n_plus_one(n):
    heads = [chr(97 + i) for i in range(n)]
    for culprit in heads:
        r = World(bad={culprit}).go(heads)
        assert r.extra_runs <= train.budget(n) and set(r.back) == {f"l/{culprit}"} and len(r.landed) == n - 1


def test_two_culprits_land_nothing_unjudged():
    r = World(bad={"b", "d"}).go(["a", "b", "c", "d"])
    assert set(r.back) == {"l/b"} and r.landed == [] and r.again == ["l/a", "l/c", "l/d"] and r.result == "unresolved"
    assert r.extra_runs <= train.budget(4)


def test_a_merge_conflict_drops_one_step_and_the_train_goes_on():
    w = World(conflict={"b"})
    r = w.go(["a", "b", "c"])
    assert r.back["l/b"]["kind"] == "conflict" and "conflict in b.txt" in r.back["l/b"]["findings"]
    assert r.landed == ["l/a", "l/c"] and r.candidate == "a+c" and r.result == "conflict"
    assert all("b" not in c.split("+") for _, c in w.runs)


def test_every_step_conflicting_ends_the_train_with_no_run():
    w = World(conflict={"a"})
    r = w.go(["a"])
    assert set(r.back) == {"l/a"} and not w.runs and not r.landed


def test_the_cfg_and_when_a_train_is_due():
    cfg = train.load({})
    assert (cfg.enabled, cfg.min_steps, cfg.max_wait_min) == (True, 4, 45)
    assert not train.due([], 1e6, cfg)
    assert train.due([0, 1, 2, 3], 10, cfg), "four wait"
    assert not train.due([0, 1000], 2000, cfg), "two, the oldest 33 min"
    assert train.due([0, 1000], 2700, cfg), "max_wait: a train of 2"
    assert train.load({"train": {"enabled": False}}).enabled is False
    with pytest.raises(ValueError, match="unknown keys"):
        train.load({"train": {"min_step": 2}})
    with pytest.raises(ValueError):
        train.load({"train": {"min_steps": 0}})


def test_the_rungs_follow_what_the_steps_changed():
    def ui(files):
        return any("Segment" in f for f in files)
    assert train.names_for(["a.py"], ("fichero/",), ui) == ["unit"]
    assert train.names_for(["fichero/A.swift"], ("fichero/",), ui) == ["build", "swift-tests", "unit"]
    assert train.names_for(["fichero/SegmentX.swift"], ("fichero/",), ui) == ["build", "swift-tests", "ui", "unit"]


def git(cwd, *a):
    return subprocess.run(["git", "-C", str(cwd), "-c", "user.name=t", "-c", "user.email=t@x", *a], capture_output=True, text=True, check=True).stdout.strip()


def test_git_merge_merges_in_order_and_names_a_conflicting_head(tmp_path):
    repo = tmp_path / "r"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "integration")
    (repo / "f.txt").write_text("base\n")
    git(repo, "add", "."), git(repo, "commit", "-qm", "base")
    base = git(repo, "rev-parse", "HEAD")
    heads = []
    for name, fname, body in (("a", "a.txt", "a\n"), ("b", "f.txt", "b\n"), ("c", "f.txt", "c\n")):
        git(repo, "checkout", "-q", "-b", name, base)
        (repo / fname).write_text(body)
        git(repo, "add", "."), git(repo, "commit", "-qm", name)
        heads.append(git(repo, "rev-parse", "HEAD"))
    git(repo, "checkout", "-q", "integration")
    cand, conflicts = train.git_merge(repo, base, heads, "refs/train/t-1")
    assert list(conflicts) == [heads[2]] and "f.txt" in conflicts[heads[2]], "c conflicts with b on f.txt"
    assert git(repo, "rev-parse", "refs/train/t-1") == cand
    assert git(repo, "show", f"{cand}:a.txt") == "a" and git(repo, "show", f"{cand}:f.txt") == "b"
    assert git(repo, "worktree", "list").count("\n") == 0, "the throwaway worktree is gone"


def test_the_ladder_skips_the_rungs_the_train_runs_once(monkeypatch):
    from fichero_builder import check_tool
    ran = []
    rungs = [(n, (lambda n=n: ran.append(n) or {"ok": True})) for n in ("ready", "build", "ui", "unit")]
    monkeypatch.setattr(check_tool, "ACTIVITY", lambda **k: None)
    check_tool.SKIP_RUNGS[0] = ("build", "ui")
    try:
        out = check_tool.ladder(rungs)
    finally:
        check_tool.SKIP_RUNGS[0] = ()
    assert out["ok"] and ran == ["ready", "unit"]
    skipped = {r["name"]: r for r in out["rungs"]}
    assert skipped["build"]["skipped"] and "merge train" in skipped["build"]["stdout_tail"] and skipped["ui"]["skipped"]
    ran.clear()
    assert check_tool.ladder(rungs)["ok"] and ran == ["ready", "build", "ui", "unit"], "off by default: a hand `builder check` runs everything"


def test_the_unit_rung_can_run_the_whole_tier(tmp_path, monkeypatch):
    from fichero_builder import check_tool
    (tmp_path / "pkg" / "tests").mkdir(parents=True)
    got = {}
    monkeypatch.setattr(check_tool, "green_runs", lambda root, files, whole, cfg, t: got.update(files=files) or {"ok": True, "runs": [], "stdout_tail": ""})
    monkeypatch.setattr(check_tool, "_lines", lambda *a, **k: [])
    cfg = check_tool.Config(always_tests=("pkg/tests/test_a.py",))
    r = check_tool.unit(tmp_path, [], cfg, everything=True)
    assert r["ok"] and got["files"] == ["pkg/tests"] and "the whole suite: the merge train" in r["stdout_tail"]


def test_the_train_table_is_a_known_rules_table():
    from fichero_builder import check_tool
    assert "train" in check_tool.KNOWN_TABLES


def test_drop_refs_deletes_the_train_candidate_refs_and_only_those(tmp_path):
    import subprocess
    g = lambda *a: subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@t", *a], capture_output=True, text=True, check=True).stdout
    g("init", "-q"), g("commit", "-q", "--allow-empty", "-m", "x")
    for r in ("refs/train/t1-1", "refs/train/t1-2", "refs/train/t2-1"):
        g("update-ref", r, "HEAD")
    train.drop_refs(tmp_path, "t1")
    assert g("for-each-ref", "--format=%(refname)", "refs/train/").split() == ["refs/train/t2-1"]
