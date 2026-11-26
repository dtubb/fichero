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
