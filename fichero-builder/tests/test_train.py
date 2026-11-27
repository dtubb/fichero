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


def test_a_whole_tests_red_searches_the_steps_that_touch_it_with_only_the_failing_cases_and_sends_one_back():
    """local.train.red-goes-to-its-step: never a prefix bisect; the steps touching the failing test, newest first, alone with those cases."""
    seen = []
    red = "RED: 1 case(s) fail on the candidate and pass on the base b\nfailing: pkg/tests/test_x.py::test_a\n"

    def rung(name, cand, only=()):
        seen.append((name, cand, tuple(only)))
        bad = name == "whole-tests" and "b" in cand.split("+")
        return (not bad), (red if bad else "ok")
    touching = {"b", "d"}
    r = train.run_train([{"key": f"l/{h}", "head": h} for h in "abcd"], merge=lambda heads: ("+".join(heads), {}), rung=rung,
                        rungs_for=lambda heads: ["guards", "whole-tests", "unit"], tid="t", touches=lambda n, h, names: h in touching)
    assert set(r.back) == {"l/b"} and "alone on the land branch fails pkg/tests/test_x.py::test_a" in r.back["l/b"]["findings"]
    assert [(c, o) for n, c, o in seen if o] == [("d", ("pkg/tests/test_x.py::test_a",)), ("b", ("pkg/tests/test_x.py::test_a",))]
    assert not any(c in ("a", "a+b", "a+b+c") for _n, c, _o in seen) and r.landed == ["l/a", "l/c", "l/d"]


def test_a_red_only_two_steps_make_together_sends_the_newest_back_naming_the_other():
    r = train.run_train([{"key": f"l/{h}", "head": h} for h in "abc"], merge=lambda heads: ("+".join(heads), {}),
                        rung=lambda name, cand, only=(): (not (name == "guards" and {"a", "c"} <= set(cand.split("+"))),
                                                          "RED: 1 guard(s) red on the candidate and green on the base\nfailing: check_routes\n"),
                        rungs_for=lambda heads: ["guards", "unit"], tid="t", touches=lambda n, h, names: h in ("a", "c"))
    assert set(r.back) == {"l/c"} and "this step and l/a together fail check_routes" in r.back["l/c"]["findings"]
    assert r.landed == ["l/a", "l/b"], "the rest without it is green and lands"


def test_hosted_ci_red_cases_are_searched_on_the_local_runners_among_the_cleared_steps():
    res = train.Result(id="t", candidate="a+b", steps=["l/a", "l/b"], landed=["l/a", "l/b"], result="green")
    out = train.search(res, [{"key": "l/a", "head": "a"}, {"key": "l/b", "head": "b"}], ["pkg/tests/test_x.py::test_a"], merge=lambda hs: ("+".join(hs), {}),
                       rung=lambda n, c, only=(): ("a" not in c.split("+") or not only, "failing: pkg/tests/test_x.py::test_a"), touches=lambda n, h, names: True)
    assert set(out.back) == {"l/a"} and out.landed == ["l/b"]


def test_the_python_rungs_run_while_the_swift_rungs_run_and_the_wall_time_is_the_longest():
    """local.train.rungs-side-by-side: whole-tests, guards, security and perf start with the candidate, beside the build and Swift tests."""
    import threading
    import time as _t
    spans, lock = {}, threading.Lock()
    took = {"build": 0.3, "swift-tests": 0.3, "guards": 0.2, "whole-tests": 0.2, "unit": 0.1, "security": 0.1, "perf": 0.1}

    def rung(name, cand, only=()):
        t0 = _t.time()
        _t.sleep(took[name])
        with lock:
            spans[name] = (t0, _t.time())
        return True, "ok"
    names = ["build", "swift-tests", "guards", "whole-tests", "unit", "security", "perf"]
    t0 = _t.time()
    res = train.run_train([{"key": "l/a", "head": "a"}], merge=lambda hs: ("c", {}), rung=rung, rungs_for=lambda hs: names, tid="t", side_by_side=True)
    wall = _t.time() - t0
    assert res.result == "green" and len(res.rungs) == len(names)
    assert spans["guards"][0] < spans["build"][1], "the guards started while the build ran"
    assert wall < 0.85 * sum(took.values()) and wall >= max(0.6, 0.7) - 0.05, "the longest chain, not the sum"
    red = train.run_train([{"key": "l/a", "head": "a"}], merge=lambda hs: ("c", {}), tid="t", side_by_side=True, rungs_for=lambda hs: names,
                          rung=lambda n, c, only=(): (n not in ("unit", "swift-tests"), f"{n} red"))
    assert "red at swift-tests" in red.back["l/a"]["why"], "both chains red: the one that counts is the first in rung order"
    late = train.run_train([{"key": "l/a", "head": "a"}], merge=lambda hs: ("c", {}), tid="t", side_by_side=True, rungs_for=lambda hs: names,
                           rung=rung, deadline=_t.time() + 0.15)
    assert late.result == "timeout", "the time limit holds over both chains"


def test_a_second_train_stops_at_its_next_run_once_its_base_train_failed():
    """local.train.second-train-on-the-first: no waiting for the second train's whole ladder after the first went red."""
    failed, calls = [""], []

    def rung(name, cand, only=()):
        calls.append(name)
        failed[0] = "its base train-1 did not land (red)"  # the first train's result arrives while this rung runs
        return True, "ok"
    train.CANCEL["t2"] = lambda: failed[0]
    try:
        res = train.run_train([{"key": "l/a", "head": "a"}], merge=lambda hs: ("c", {}), rung=rung, rungs_for=lambda hs: ["guards", "unit"], tid="t2")
    finally:
        train.CANCEL.pop("t2", None)
    assert calls == ["guards"] and res.result == "cancelled" and res.again == ["l/a"] and "did not land" in res.bisect[-1]


TAIL_161601 = ("✔ Suite RecipeSetupFlowTests passed after 89.838 seconds.\n"
               "✘ Test run with 1006 tests in 155 suites failed after 89.839 seconds with 4 issues.\n\n"
               "Test session results, code coverage, and logs:\n\t/Volumes/Fichero Development/fichero-gate/results/test.xcresult\n")


def test_a_swift_red_with_no_suite_read_from_its_names_never_runs_the_base(tmp_path, monkeypatch):
    """train-20261126-161601: selection and base_selection both "296 suite(s)", base 864.8 s, then the time limit. Without suites read
    from the failing names, the base is never run: the red stands with `no case names`, and failures=N is on the row."""
    from fichero_builder import journal
    monkeypatch.setattr(journal, "STATE", tmp_path)
    ran = []
    base = lambda suites: ran.append(suites) or {"ok": True}  # noqa: E731
    for r, target, why in (({"ok": False, "failing": [], "failures": 5}, "FicheroTests", "no case names"),
                           ({"ok": False, "failing": ["Test \"the way chosen\" failed"], "failures": 5}, "FicheroTests", "names no suite"),
                           ({"ok": False, "failing": ["FicheroTests/A/b()"], "failures": 5}, "", "no [check].swift_test_target")):
        ok, said, facts = train.swift_judge(r, TAIL_161601, "b1", target, base)
        assert not ok and why in said and "see tail" in said and "1006 tests in 155 suites" in said and facts == {"failures": 5}
    assert ran == [], "the base never re-ran the candidate's selection"
    ok, said, facts = train.swift_judge({"ok": False, "failing": ["FicheroTests/SegmentToolTests/draw()"], "failures": 1}, TAIL_161601, "b1",
                                        "FicheroTests", lambda s: ran.append(s) or {"ok": False, "failing": []})
    assert ran == [["FicheroTests/SegmentToolTests"]] and facts["base_selection"] == "1 suite(s)" and facts["failures"] == 1


def test_a_swift_red_with_no_case_names_searches_the_swift_steps_alone_on_their_own_suites():
    seen = []

    def rung(name, cand, only=()):
        seen.append((name, cand, tuple(only)))
        bad = name == "swift-tests" and "b" in cand.split("+")
        return (not bad), ("swift-tests: no case names, see tail: the base is not run\n" + TAIL_161601 if bad else "ok")
    r = train.run_train([{"key": f"l/{h}", "head": h} for h in "abc"], merge=lambda hs: ("+".join(hs), {}), rung=rung,
                        rungs_for=lambda hs: ["build", "swift-tests"], tid="t", touches_swift=lambda h: h in ("b", "c"))
    assert set(r.back) == {"l/b"} and "no case names were read" in r.back["l/b"]["findings"]
    assert [c for n, c, _o in seen if n == "swift-tests"][1:3] == ["c", "b"], "the Swift steps alone, newest first, never a prefix"
    assert not any(c in ("a", "a+b") for _n, c, _o in seen)


FIX_192626 = (__import__("pathlib").Path(__file__).parent / "fixtures" / "swift-train-20261126-192626-tail.log").read_text()


def test_a_whole_plan_swift_red_is_judged_on_the_bases_failing_suites_and_searched_never_bisected(tmp_path, monkeypatch):
    """train-20261126-192626: the whole plan (5075 tests, failures=59) was red; xcodebuild listed `Suite.case()`, no suite was read,
    the base never ran (base_selection None), and the prefix bisect ran a second whole plan to the time limit."""
    from fichero_builder import check_tool, journal
    monkeypatch.setattr(journal, "STATE", tmp_path)
    names = check_tool.failing_cases(FIX_192626)
    assert "PaneMenuEntriesShapeTests.testCloseIsOnePath()" in names and len(names) > 20
    suites = train.suites_of(names, "FicheroTests")
    assert suites and "FicheroTests/PaneMenuEntriesShapeTests" in suites and len(suites) < len(names)
    ran = []
    known = [n for n in names if not n.startswith("PaneMenuEntriesShapeTests")]  # every red but one is the base's own

    def base(s):
        ran.append(s)
        return {"ok": False, "failing": known}
    ok, said, facts = train.swift_judge({"ok": False, "failing": names, "failures": 59}, FIX_192626, "b1", "FicheroTests", base)
    assert ran == [suites] and facts["base_selection"] == f"{len(suites)} suite(s)" and facts["failures"] == 59
    assert not ok and said.startswith("RED: 1 case(s)") and "failing: PaneMenuEntriesShapeTests.testCloseIsOnePath()" in said
    assert train.swift_judge({"ok": False, "failing": names}, FIX_192626, "b1", "FicheroTests", base)[0] is False and len(ran) == 1, "the base's run is kept"
    seen = []

    def rung(name, cand, only=()):
        seen.append((name, cand))
        return (name != "swift-tests" or "b" not in cand.split("+")), "NOT RUN: the runner could not run the tests (not a test failure)"
    r = train.run_train([{"key": f"l/{h}", "head": h} for h in "abc"], merge=lambda hs: ("+".join(hs), {}), rung=rung,
                        rungs_for=lambda hs: ["build", "swift-tests"], tid="t", touches_swift=lambda h: True)
    assert not any(c in ("a", "a+b") for _n, c in seen), "never a prefix bisect on Swift, whatever the red says"
    assert set(r.back) == {"l/b"}, "the Swift step that fails alone goes back"


def test_an_openapi_change_selects_the_suites_naming_its_changed_types_not_the_whole_plan(tmp_path):
    import json as _json
    import subprocess as sp
    from fichero_builder import check_tool
    g = lambda *a: sp.run(["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@t", *a], check=True, capture_output=True, text=True).stdout.strip()  # noqa: E731
    api = tmp_path / "fichero/fichero-api-client/Sources/FicheroAPIClient/openapi.json"
    api.parent.mkdir(parents=True)
    doc = {"paths": {"/a": {"get": {"operationId": "listThings", "responses": {}}}}, "components": {"schemas": {"Thing": {"type": "object"}, "Other": {"type": "string"}}}}
    api.write_text(_json.dumps(doc))
    tests = tmp_path / "fichero/FicheroTests"
    tests.mkdir(parents=True)
    (tests / "ThingTests.swift").write_text("struct ThingTests { func a() { _ = Components.Schemas.Thing() } }\n")
    (tests / "OtherTests.swift").write_text("struct OtherTests { func a() { _ = Components.Schemas.Other.self } }\n")
    g("init", "-q"), g("add", "."), g("commit", "-qm", "base")
    base = g("rev-parse", "HEAD")
    doc["components"]["schemas"]["Thing"]["required"] = ["id"]
    api.write_text(_json.dumps(doc))
    g("commit", "-qam", "contract")
    files = ["fichero/fichero-api-client/Sources/FicheroAPIClient/openapi.json"]
    types = check_tool.contract_types(str(tmp_path), base, g("rev-parse", "HEAD"), files)
    assert types == {"Thing"}
    cfg = check_tool.Config(swift_test_target="FicheroTests", swift_test_dir="fichero/FicheroTests", build_paths=("fichero/",))
    assert check_tool.swift_affected(tmp_path, files, cfg, types) == ["FicheroTests/ThingTests"]
    assert check_tool.swift_affected(tmp_path, files, cfg) is None, "unmapped (no types read): the whole plan, as before"
    gen = [*files, "fichero/fichero-api-client/Sources/FicheroAPIClient/openapi-generator-config.yaml"]
    assert check_tool.swift_affected(tmp_path, gen, cfg, types) is None, "the generator's own config: the whole plan"
    assert "openapi-generator-config.yaml" in check_tool.swift_whole_why(gen, cfg, True)


def test_a_swift_run_the_runner_could_not_run_is_tried_once_on_another_runner():
    from fichero_builder import check_tool
    assert check_tool.other_runner(check_tool.Config(build_remote="imac:/g1", remotes=("imac:/g1", "air:/g"))) == "air:/g"
    assert check_tool.other_runner(check_tool.Config(build_remote="imac:/g1")) == "imac:/g1", "no other: the same one, once more"
