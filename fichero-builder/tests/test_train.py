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
    assert train.names_for(["a.py"], ("fichero/",), ui) == ["guards", "unit"]
    assert train.names_for(["fichero/A.swift"], ("fichero/",), ui) == ["build", "swift-tests", "guards", "unit"]
    assert train.names_for(["fichero/SegmentX.swift"], ("fichero/",), ui) == ["build", "swift-tests", "ui", "guards", "unit"]


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
    def g(*a):
        return subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@t", *a], capture_output=True, text=True, check=True).stdout
    g("init", "-q"), g("commit", "-q", "--allow-empty", "-m", "x")
    for r in ("refs/train/t1-1", "refs/train/t1-2", "refs/train/t2-1"):
        g("update-ref", r, "HEAD")
    train.drop_refs(tmp_path, "t1")
    assert g("for-each-ref", "--format=%(refname)", "refs/train/").split() == ["refs/train/t2-1"]


def test_the_trains_swift_tests_are_red_only_for_cases_that_pass_on_the_base_which_runs_once_per_sha(tmp_path, monkeypatch):
    """2026-11-26 12:06-13:20, train-20261126-120639: integration's own Swift reds (#7095) made every candidate red; nothing landed
    from 05:41. Judged like red-on-base: the base's failing cases are run once per base sha, kept, and never block."""
    from fichero_builder import journal
    monkeypatch.setattr(journal, "STATE", tmp_path)
    known = ["ModelsWindowLayoutTests.inspectorLines()", "SetupFourStepsTests.continueSavesAndStartSavesFirst()"]
    runs = []
    base_run = lambda: runs.append(1) or {"ok": False, "failing": known}  # noqa: E731
    ok, out = train.against_base(known, "RED", "b" * 40, base_run)
    assert ok and "known reds" in out
    ok, out = train.against_base([*known, "SegmentToolTests.drawsABox()"], "RED", "b" * 40, base_run)
    assert not ok and "failing: SegmentToolTests.drawsABox()" in out and "2 known base reds left out" in out
    assert runs == [1], "the base ran once for its sha"
    ok, out = train.against_base(known, "RED as it was", "c" * 40, lambda: {"ok": False, "not_run": True})
    assert not ok and out == "RED as it was", "a base that could not run judges nothing"


def test_when_the_rest_is_red_on_the_same_cases_as_the_prefix_no_step_is_sent_back():
    """2026-11-26: every prefix and "rest without seg-tools/seg-batch-6" were red at swift-tests on the same cases, and seg-batch-6
    was sent back for reds that were not its own."""
    same = "RED: swift-tests: 5074 tests, 2 failed\nfailing: ModelsWindowLayoutTests.inspectorLines(), ToolbarSymbolsTests.toolbarTogglesAreNative()\n"
    r = train.run_train([{"key": f"l/{h}", "head": h} for h in "abc"], merge=lambda heads: ("+".join(heads), {}),
                        rung=lambda name, cand: (name != "swift-tests", same if name == "swift-tests" else "ok"),
                        rungs_for=lambda heads: ["build", "swift-tests", "unit"], tid="t")
    assert r.back == {} and r.landed == [] and r.again == ["l/a", "l/b", "l/c"] and r.result == "unresolved"
    assert "no step is sent back" in r.bisect[-1]
    assert r.extra_runs <= train.budget(3)


def test_a_swift_red_on_new_cases_searches_the_swift_steps_newest_first_with_only_those_cases_never_by_prefix():
    """2026-11-26, owner: an 88-minute merge (train-20261126-120639: 797 s, then 808, 1107 and 1471 s of whole-suite prefix runs).
    Only the Swift steps are tried, newest first, each alone on the base with only the new cases; the first red one goes back."""
    seen = []
    new = "RED: 1 case(s) fail on the candidate and pass on the base\nfailing: SegmentToolTests.drawsABox()\n"

    def rung(name, cand, only=()):
        seen.append((name, cand, tuple(only)))
        if name != "swift-tests":
            return True, "ok"
        bad = "b" in cand.split("+")
        return (not bad), (new if bad else "green")
    swift = {"b", "d"}
    r = train.run_train([{"key": f"l/{h}", "head": h} for h in "abcd"], merge=lambda heads: ("+".join(heads), {}), rung=rung,
                        rungs_for=lambda heads: ["build", "swift-tests", "unit"], tid="t", touches_swift=lambda h: h in swift)
    assert set(r.back) == {"l/b"} and "this step alone on the land branch fails SegmentToolTests.drawsABox()" in r.back["l/b"]["findings"]
    assert r.landed == ["l/a", "l/c", "l/d"] and r.result == "red"
    searched = [(c, o) for n, c, o in seen if o]
    assert searched == [("d", ("SegmentToolTests.drawsABox()",)), ("b", ("SegmentToolTests.drawsABox()",))], "newest Swift step first, only the new case"
    assert not any(c in ("a", "a+b", "a+b+c") for _n, c, _o in seen), "no prefix run"
    assert r.extra_runs == 3


def test_a_swift_red_no_single_step_reproduces_sends_none_back():
    r = train.run_train([{"key": f"l/{h}", "head": h} for h in "ab"], merge=lambda heads: ("+".join(heads), {}),
                        rung=lambda name, cand, only=(): (len(cand.split("+")) < 2, "failing: X.y()\n"),
                        rungs_for=lambda heads: ["swift-tests"], tid="t", touches_swift=lambda h: True)
    assert r.back == {} and r.again == ["l/a", "l/b"] and r.result == "unresolved" and "none is sent back" in r.bisect[-1]


def test_a_train_past_its_time_limit_stops_and_every_step_waits_again():
    """Owner 2026-11-26: train-134056 ran 90 min with no result. No run starts past [train].max_run_min."""
    now = [0.0]

    def rung(name, cand, only=()):
        now[0] += 1000
        return name != "swift-tests", "swift-tests failed: no names"
    r = train.run_train([{"key": f"l/{h}", "head": h} for h in "abc"], merge=lambda heads: ("+".join(heads), {}), rung=rung,
                        rungs_for=lambda heads: ["build", "swift-tests", "unit"], tid="t", clock=lambda: now[0], deadline=1800.0)
    assert r.result == "timeout" and r.again == ["l/a", "l/b", "l/c"] and r.back == {} and r.landed == []
    assert [x["name"] for x in r.rungs] == ["build", "swift-tests"] and "time limit" in r.bisect[-1]
    assert train.load({"train": {}}).max_run_min == 30 and train.load({"train": {"max_run_min": 20}}).max_run_min == 20


def test_two_steps_each_green_alone_that_break_a_guard_together_make_the_train_red_at_guards(tmp_path, monkeypatch):
    """local.train.guards-on-candidate: with the same-file rule gone, two steps that share a file check at once; the guards their
    combined diff touches run once on the candidate, and a guard red there and green on the base makes the train red at guards."""
    from fichero_builder import check_tool, journal
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    (tmp_path / "s").mkdir()

    def tree(name, files):
        t = tmp_path / name
        (t / "scripts").mkdir(parents=True)
        (t / "scripts" / "check_pair.py").write_text("import os, sys\nsys.exit(1 if os.path.exists('a.txt') and os.path.exists('b.txt') else 0)\n")
        (t / "scripts" / "check_other.py").write_text("print('ok')\n")
        for f in files:
            (t / f).write_text("x")
        return t
    cfg = check_tool.Config(guard_glob="scripts/check_*.py", guard_inputs={"check_pair": ["a.txt", "b.txt"], "check_other": ["z"]}, guards_by_diff=True)
    cand = check_tool.guards(tree("cand", ["a.txt", "b.txt"]), cfg, ["a.txt", "b.txt"])
    ran_base = []

    def on_base(names):
        ran_base.append(names)
        return check_tool.guards(tree(f"base{len(ran_base)}", []), cfg)
    ok, out = train.guards_against_base(cand, on_base)
    assert not ok and "failing: check_pair" in out and ran_base == [["check_pair"]], "red on the candidate, green on the base"
    ok, out = train.guards_against_base(cand, lambda names: check_tool.guards(tree("baseRed", ["a.txt", "b.txt"]), cfg))
    assert ok and "on the base too" in out, "the land branch's own red never blocks"
    alone = [check_tool.guards(tree(f"alone{f}", [f]), cfg, [f])["ok"] for f in ("a.txt", "b.txt")]
    assert alone == [True, True], "each step alone is green"

    def rung(name, cand_, only=()):
        both = {"a", "b"} <= set(cand_.split("+"))
        return (not both, "failing: check_pair\n") if name == "guards" else (True, "ok")
    r = train.run_train([{"key": f"l/{h}", "head": h} for h in "ab"], merge=lambda heads: ("+".join(heads), {}), rung=rung,
                        rungs_for=lambda heads: train.names_for(["a.py"], ("fichero/",), lambda f: False), tid="t")
    assert r.result in ("red", "unresolved") and any(x["name"] == "guards" and not x["ok"] for x in r.rungs)


def test_the_train_row_says_the_swift_selection_the_base_runs_seconds_and_a_reds_tail():
    """2026-11-26: a 1651 s swift-tests row had no selection, no base time and no failure lines. The rung's own notes (`rung.last`)
    go in its row, and a red keeps its last lines."""
    def rung(name, cand, only=()):
        rung.last = {"selection": "whole: no [check].swift_test_target", "base_seconds": 12.0} if name == "swift-tests" else {}
        return (name != "swift-tests", "failing: FicheroTests/A/t()\n" if name == "swift-tests" else "ok")
    r = train.run_train([{"key": "l/a", "head": "a"}], merge=lambda heads: ("+".join(heads), {}), rung=rung,
                        rungs_for=lambda heads: ["build", "swift-tests"], tid="t")
    sw = next(x for x in r.rungs if x["name"] == "swift-tests")
    assert sw["selection"].startswith("whole: no [check].swift_test_target") and sw["base_seconds"] == 12.0 and "FicheroTests/A/t()" in sw["tail"]
    assert "selection" not in r.rungs[0] and "tail" not in r.rungs[0]


def test_the_base_runs_only_the_suites_of_the_failing_cases():
    assert train.suites_of(["-[FicheroTests.SegmentToolTests testDraw]", "FicheroTests/CanvasTests/lasso()", "Other/x()"], "FicheroTests") == [
        "FicheroTests/CanvasTests", "FicheroTests/Other", "FicheroTests/SegmentToolTests"]
    assert train.suites_of(["a failure with no name"], "FicheroTests") is None


def test_the_train_runs_the_owed_whole_dirs_once_and_is_red_only_for_cases_green_on_its_base(tmp_path, monkeypatch):
    """local.train.whole-tests-against-base: the rung is in the train when its steps owe dirs; a red is judged on the base, kept per sha."""
    from fichero_builder import journal
    monkeypatch.setattr(journal, "STATE", tmp_path)
    assert train.names_for(["pkg/a.py"], (), lambda f: False, ("pkg/tests",)) == ["guards", "whole-tests", "unit"]
    assert "whole-tests" not in train.names_for(["pkg/a.py"], (), lambda f: False)
    runs = []

    def base():
        runs.append(1)
        return {"ok": False, "failing": ["pkg/tests/test_x.py::test_old"]}
    out = "FAILED pkg/tests/test_x.py::test_old\nFAILED pkg/tests/test_x.py::test_new"
    ok, said = train.against_base(["pkg/tests/test_x.py::test_old", "pkg/tests/test_x.py::test_new"], out, "b1", base, ("pkg/tests",), label="whole-tests")
    assert not ok and "failing: pkg/tests/test_x.py::test_new" in said and "test_old" not in said.split("\n")[1]
    ok, said = train.against_base(["pkg/tests/test_x.py::test_old"], out, "b1", base, ("pkg/tests",), label="whole-tests")
    assert ok and said.startswith("whole-tests: green against the base") and runs == [1], "the base ran once for that sha and selection"
    assert (tmp_path / "whole-tests-base-b1-" f"{__import__('hashlib').sha256(b'pkg/tests').hexdigest()[:12]}.json").is_file()
    calls = []
    res = train.run_train([{"key": "a/1", "head": "h1"}, {"key": "b/2", "head": "h2"}], merge=lambda hs: ("c", {}),
                          rung=lambda n, c, only=(): calls.append(n) or (True, "ok"), rungs_for=lambda hs: ["whole-tests", "unit"], tid="t")
    assert calls == ["whole-tests", "unit"] and res.result == "green", "once for the train, never per step"
