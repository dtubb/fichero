"""local.ci.*: hosted CI in the flow; GitHub is a fake (FakeHosted), the clock too."""
from __future__ import annotations

import time

import pytest

from fichero_builder import ci, journal, train


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    (tmp_path / "s").mkdir()
    return tmp_path


class Clock:
    def __init__(self):
        self.t = time.time()

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


def check(name, conclusion="success", cid=1, status="completed", run_id="", seconds=600):
    return {"name": name, "id": cid, "status": status, "conclusion": conclusion, "seconds": seconds, "kind": "actions", "run_id": run_id, "job_id": ""}


class FakeHosted:
    """`plan[sha]`: a list of check lists, one per read; the last repeats. `jobs_of[run_id]`, `logs[(run_id, job)]`."""

    def __init__(self, plan=None, jobs_of=None, logs=None, down=False):
        self.plan, self.jobs_of, self.logs, self.down = plan or {}, jobs_of or {}, logs or {}, down
        self.calls: list = []

    def checks(self, sha):
        self.calls.append(("checks", sha))
        if self.down:
            raise ci.Down("api.github.com: connection refused")
        seq = self.plan.get(sha, [[]])
        return seq.pop(0) if len(seq) > 1 else seq[0]

    def jobs(self, run_id):
        return self.jobs_of.get(run_id, [])

    def failed_log(self, run_id, job_id):
        return self.logs.get((run_id, job_id), "")

    def rerun_failed(self, run_id):
        self.calls.append(("rerun", run_id))

    def push(self, sha, branch):
        self.calls.append(("push", sha, branch))
        return ""

    def delete(self, branch):
        self.calls.append(("delete", branch))
        return ""

    def dispatch(self, ref, inputs=None):
        self.calls.append(("dispatch", ref, inputs))


def green_res(tid="train-1"):
    return train.Result(id=tid, candidate="cand", steps=["a/1", "b/2"], landed=["a/1", "b/2"], result="green")


# --- local.ci.caps-and-fallback ----------------------------------------------------------------------------------------------

def test_ci_with_no_cap_set_is_refused_by_the_rules_check(state):
    from fichero_builder import check_tool
    base = '[land]\nbranch = "integration"\n'
    for table, refused in (('[ci]\ntrain = "report"\n', True), ('[ci]\nnightly = true\n', True),
                           ('[ci]\ntrain = "report"\nxcode_cloud_hours_month = 25\n', False), ("", False)):
        (state / "harness.toml").write_text(base + table)
        hits = [p for p in check_tool.rules_problems(state) if "[ci]" in p]
        assert bool(hits) == refused, (table, hits)
    assert not [p for p in check_tool.rules_problems(state) if "actions_minutes_month" in p], "the Actions cap is optional: the repo is public"


def test_minutes_are_summed_per_month_with_the_macos_multiplier_and_eighty_percent_is_one_alert(state):
    cfg = ci.Cfg(train="report", actions_minutes_month=70, xcode_cloud_hours_month=1.8)
    ci.record([{"id": 1, "name": "engine (1/8)", "status": "completed", "seconds": 541, "os": "ubuntu-latest"},  # 10 min
               {"id": 2, "name": "swift", "status": "completed", "seconds": 300, "os": "macos-26"},  # 5 min x 10
               {"id": 3, "name": "Fichero | Test", "status": "completed", "seconds": 5400, "kind": "xcode"}], "sha1", cfg)
    ci.record([{"id": 1, "name": "engine (1/8)", "status": "completed", "seconds": 541}], "sha1", cfg)  # the same job again: once
    old = {"event": "ci", "state": "job", "job": 9, "minutes": 500, "hours": 9, "ts": "2001-01-01T00:00:00"}
    with journal.path().open("a") as f:
        import json
        f.write(json.dumps(old) + "\n")
    assert ci.month(journal.read()) == {"actions": 60, "xcode": 1.5}, "this month only, macOS ten times"
    said = []
    ci.daily(cfg, said.append)
    ci.daily(cfg, said.append)
    assert len(said) == 2 and "60 of its 70 Actions minutes" in said[0] and "1.5 of its 1.8 Xcode Cloud hours" in said[1], "one alert per cap"
    assert len([r for r in journal.read() if r.get("state") == "month"]) == 1, "one row a day"


@pytest.mark.parametrize("why", ["cap", "down", "not-started"])
def test_at_the_cap_or_with_ci_down_the_train_runs_its_whole_suites_locally_with_a_fallback_row(state, why):
    cfg = ci.Cfg(train="required", xcode_cloud_hours_month=25, actions_minutes_month=10 if why == "cap" else 0)
    if why == "cap":
        ci.record([{"id": 1, "name": "x", "status": "completed", "seconds": 900}], "old", cfg)
    h = FakeHosted(down=why == "down")
    clock, ran = Clock(), []
    res = ci.land_on_checks(green_res(), cfg, h, "base", lambda m: None, run_local=lambda c: ran.append(c) or (True, "ok"), clock=clock, sleep=clock.sleep)
    assert ran == ["cand"], "the whole suites ran on the local runners"
    assert res.result == "green" and res.landed == ["a/1", "b/2"], "it never waits and lands on what it ran"
    (row,) = [r for r in journal.read() if r.get("state") == "ci-fallback"]
    assert {"cap": "Actions cap", "down": "could not be reached", "not-started": "start_min"}[why] in row["detail"]
    assert ci.local_rungs(cfg, ["build", "swift-tests", "unit"]) == ["build", "swift-tests"], "with CI required the whole suites are CI's"
    assert ci.local_rungs(ci.Cfg(train="report"), ["build", "unit"]) == ["build", "unit"]


# --- local.ci.train-candidate-on-a-branch ------------------------------------------------------------------------------------

def _train(order, fail=None):
    def merge(heads):
        order.append("merge")
        return "cand", {}

    def rung(name, cand, only=()):
        order.append(f"rung {name}")
        if fail == "raise":
            raise RuntimeError("the runner fell over")
        return True, "ok"
    return lambda on_candidate: train.run_train([{"key": "a/1", "head": "h1"}], merge=merge, rung=rung, rungs_for=lambda hs: ["build", "unit"],
                                                tid="train-1", on_candidate=on_candidate)


@pytest.mark.parametrize("end", ["green", "raise"])
def test_a_train_pushes_its_candidate_to_a_train_branch_first_and_deletes_it_however_it_ends(state, end):
    h, order = FakeHosted(), []
    h.push = lambda sha, b: order.append(f"push {sha} {b}") or ""
    h.delete = lambda b: order.append(f"delete {b}") or ""
    cfg = ci.Cfg(train="report", xcode_cloud_hours_month=25)
    if end == "raise":
        with pytest.raises(RuntimeError):
            ci.with_train(cfg, h, "train-1", _train(order, "raise"))
    else:
        assert ci.with_train(cfg, h, "train-1", _train(order)).result == "green"
    assert order[:3] == ["merge", "push cand train/train-1", "rung build"], "pushed before any local rung"
    assert "delete train/train-1" in order and order.index("delete train/train-1") > order.index("rung build")
    assert any(r.get("state") == "deleted" for r in journal.read())


def test_with_ci_off_no_branch_is_pushed(state):
    h, order = FakeHosted(), []
    assert ci.with_train(ci.Cfg(), h, "train-1", _train(order)).result == "green"
    assert not [c for c in h.calls if c[0] in ("push", "delete")] and order == ["merge", "rung build", "rung unit"]


def test_the_workflow_runs_on_train_branches_and_train_gate_is_green_when_each_tier_is_green_or_skipped():
    import json
    import os
    import re
    import subprocess
    import sys
    from pathlib import Path
    yaml = pytest.importorskip("yaml")
    wf = yaml.safe_load((Path(__file__).resolve().parents[2] / ".github" / "workflows" / "tests.yml").read_text())
    on = wf.get("on") or wf[True]
    assert "train/**" in on["push"]["branches"]
    assert "github.ref" in wf["concurrency"]["group"], "one run a branch: a newer push cancels the older"
    tiers = [k for k, v in wf["jobs"].items() if v.get("needs") == "changes"]
    assert set(tiers) >= {"engine", "builder", "swift", "contracts"}
    for k in tiers:
        assert "needs.changes.outputs." in wf["jobs"][k]["if"], f"{k} runs only when the diff touches it"
        assert "refs/heads/train/" in str(wf["jobs"][k]["continue-on-error"]), f"{k}: a train's red is red"
    gate = wf["jobs"]["train-gate"]
    assert set(gate["needs"]) == set(tiers) and gate["if"] == "always()"
    code = re.search(r'python3 -c "(.*)"', gate["steps"][0]["run"]).group(1)

    def run(results):
        env = {**os.environ, "NEEDS": json.dumps({k: {"result": r} for k, r in results.items()})}
        return subprocess.run([sys.executable, "-c", code], env=env, capture_output=True).returncode
    assert run({"engine": "success", "swift": "skipped", "builder": "success"}) == 0
    assert run({"engine": "success", "swift": "failure"}) == 1
    assert run({"engine": "cancelled"}) == 1, "a tier that did not finish never passes the gate"


# --- local.ci.train-lands-on-green-checks ------------------------------------------------------------------------------------

def test_in_report_mode_the_train_lands_on_its_local_rungs_and_records_each_check_and_its_agreement(state):
    cfg = ci.Cfg(train="report", xcode_cloud_hours_month=25)
    h = FakeHosted({"cand": [[check("train-gate", "failure", seconds=1500)]], "base": [[check("train-gate", "success", cid=7)]]})
    clock = Clock()
    res = ci.land_on_checks(green_res(), cfg, h, "base", lambda m: None, clock=clock, sleep=clock.sleep)
    assert res.result == "green" and res.landed == ["a/1", "b/2"], "report mode: the local result stands"
    assert res.ci["mode"] == "report" and res.ci["checks"] == [{"name": "train-gate", "conclusion": "failure", "minutes": 25.0}]
    assert res.ci["agreed"] is False, "CI red, the local train green: they disagree"
    h2 = FakeHosted({"cand": [[check("train-gate", "success")]]})
    assert ci.land_on_checks(green_res(), cfg, h2, "base", lambda m: None, clock=clock, sleep=clock.sleep).ci["agreed"] is True


@pytest.mark.parametrize("ci_says", ["red", "missing"])
def test_in_required_mode_a_green_local_train_with_a_red_or_missing_check_does_not_land(state, ci_says):
    cfg = ci.Cfg(train="required", xcode_cloud_hours_month=25)
    cand = [[check("train-gate", "failure")]] if ci_says == "red" else [[check("engine (1/8)", status="in_progress", conclusion="")]]
    h = FakeHosted({"cand": cand, "base": [[check("train-gate", "success", cid=7)]]})
    clock, said = Clock(), []
    res = ci.land_on_checks(green_res(), cfg, h, "base", said.append, clock=clock, sleep=clock.sleep)
    assert res.landed == [] and set(res.again) == {"a/1", "b/2"}
    assert res.result == ("red" if ci_says == "red" else "timeout")
    if ci_says == "missing":
        assert clock() - time.time() >= cfg.wait_min * 60 - 60, "it waited [ci].wait_min, never longer, and the train timed out"
    h3 = FakeHosted({"cand": [[check("train-gate", "success")]]})
    assert ci.land_on_checks(green_res(), cfg, h3, "base", said.append, clock=clock, sleep=clock.sleep).landed == ["a/1", "b/2"]


def test_required_is_refused_until_seven_days_of_report_rows_meet_the_time_and_agreement_bars():
    now = time.time()

    def rows(n, days, minutes=20.0, bad=0):
        return [{"event": "train", "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now - days * 86400 * i / max(1, n - 1))),
                 "ci": {"mode": "report", "minutes": minutes, "agreed": i >= bad}} for i in range(n)]
    cfg = ci.Cfg(train="required", xcode_cloud_hours_month=25)
    assert ci.problems(cfg, rows(20, 6.9, bad=1), now) == [], "seven days, under wait_min, one disagreement in twenty"
    assert "seven days" in ci.problems(cfg, rows(20, 3), now)[0]
    assert "90th percentile" in ci.problems(cfg, rows(20, 6.9, minutes=50), now)[0]
    assert "disagreed" in ci.problems(cfg, rows(20, 6.9, bad=2), now)[0]
    assert ci.problems(ci.Cfg(train="report", xcode_cloud_hours_month=25), [], now) == [], "report needs no rows"


# --- local.ci.red-is-retried-once-and-judged-against-base --------------------------------------------------------------------

TEST_JOB = {"id": 11, "name": "engine (3/8)", "conclusion": "failure", "status": "completed", "os": "ubuntu-latest", "seconds": 600, "kind": "actions",
            "steps": [{"name": "Install the engine", "conclusion": "success"}, {"name": "Unit tests", "conclusion": "failure"}]}
LOG = "engine (3/8)\tUnit tests\t2026-11-26T10:00:00Z FAILED tests/unit/test_x.py::test_a - assert 1 == 2\n"


def _judge(plan, jobs=None, logs=None, cfg=None):
    cfg = cfg or ci.Cfg(train="required", xcode_cloud_hours_month=25)
    h = FakeHosted(plan, jobs or {}, logs or {})
    clock, said = Clock(), []
    v = ci.judge(h, "cand", "base", cfg, said.append, push_base=lambda: h.push("base", "train/train-1-base"), clock=clock, sleep=clock.sleep)
    return v, h, said


def test_an_infrastructure_failure_is_rerun_once_and_a_second_one_is_not_run_never_red(state):
    v, h, said = _judge({"cand": [[check("train-gate", "startup_failure", cid=1, run_id="r1")],
                                  [check("train-gate", "startup_failure", cid=2, run_id="r1")]]})
    assert [c for c in h.calls if c[0] == "rerun"] == [("rerun", "r1")], "its failed jobs re-run once"
    assert not v.ok and not v.cases and "infrastructure twice" in v.fallback, "not run: caps-and-fallback decides, never a red"
    assert len(said) == 1
    v2, h2, _ = _judge({"cand": [[check("train-gate", "cancelled", cid=1, run_id="r1")], [check("train-gate", "success", cid=2, run_id="r1")]]})
    assert v2.ok and not v2.flaky, "green on its re-run: nothing to file, a cancel names no case"


def test_a_case_green_on_the_rerun_is_green_with_a_flaky_row(state):
    v, h, _ = _judge({"cand": [[check("train-gate", "failure", cid=1, run_id="r1")], [check("train-gate", "success", cid=2, run_id="r1")]]},
                     {"r1": [TEST_JOB]}, {("r1", 11): LOG})
    assert v.ok and v.flaky == [{"check": "train-gate", "cases": ["tests/unit/test_x.py::test_a"]}]
    (row,) = [r for r in journal.read() if r.get("state") == "flaky"]
    assert row["cases"] == ["tests/unit/test_x.py::test_a"] and row["check"] == "train-gate"


def test_a_case_red_twice_and_red_on_the_base_run_sends_no_step_back(state):
    red = [check("train-gate", "failure", cid=1, run_id="r1")]
    v, h, _ = _judge({"cand": [red, [check("train-gate", "failure", cid=2, run_id="r1")]], "base": [[check("train-gate", "failure", cid=5, run_id="r9")]]},
                     {"r1": [TEST_JOB], "r9": [TEST_JOB]}, {("r1", 11): LOG, ("r9", 11): LOG})
    assert v.ok and not v.cases, "the case is the base's own red"
    assert not [c for c in h.calls if c[0] == "push"], "the base had a completed run: none started"


def test_a_case_red_twice_and_green_on_the_base_goes_to_the_step_search(state):
    plan = {"cand": [[check("train-gate", "failure", cid=1, run_id="r1")], [check("train-gate", "failure", cid=2, run_id="r1")]],
            "base": [[], [check("train-gate", "success", cid=5)]]}
    v, h, _ = _judge(plan, {"r1": [TEST_JOB]}, {("r1", 11): LOG})
    assert not v.ok and v.cases == ["tests/unit/test_x.py::test_a"]
    assert ("push", "base", "train/train-1-base") in h.calls, "no base run: one started once"
    searched = []
    plan2 = {"cand": [[check("train-gate", "failure", cid=1, run_id="r1")], [check("train-gate", "failure", cid=2, run_id="r1")]],
             "base": [[check("train-gate", "success", cid=5)]]}
    h2, clock = FakeHosted(plan2, {"r1": [TEST_JOB]}, {("r1", 11): LOG}), Clock()
    res = ci.land_on_checks(green_res(), ci.Cfg(train="required", xcode_cloud_hours_month=25), h2, "base", lambda m: None,
                            search=lambda r, cases: searched.append(cases) or green_res(), clock=clock, sleep=clock.sleep)
    assert searched == [["tests/unit/test_x.py::test_a"]] and res.result == "green"
