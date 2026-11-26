"""local.ci.*: hosted CI in the flow. A train pushes its candidate to `train/<id>` on the land remote, GitHub Actions (and Xcode Cloud
when its hours allow) run the whole suites there, and the train reads the check runs of that sha: in `report` mode it records them
beside its local result, in `required` mode it lands only on green. Caps, a fallback to the local runners, one re-run of a red, and
a red judged against the train's base. The nightly gates on the frozen sha the same way; TestFlight can come from Xcode Cloud.
The GitHub repo is public: standard Actions minutes are free, so only Xcode Cloud hours must be capped; the Actions cap is optional."""
from __future__ import annotations

import json
import math
import re
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

from fichero_builder import journal

KEYS = {"train", "nightly", "testflight", "required", "wait_min", "start_min", "xcode_workflow", "xcode_cloud_on", "actions_minutes_month",
        "xcode_cloud_hours_month", "macos_multiplier", "testflight_refs", "testflight_wait_min", "local_guards", "remote", "repo", "workflow"}
TEST_STEP = re.compile(r"test|pytest|shard|xcodebuild|guard", re.I)  # a job step that runs tests: a failure before one is set-up
INFRA = ("cancelled", "timed_out", "startup_failure", "stale")  # check conclusions that are the runner's, never the code's


@dataclass
class Cfg:
    train: str = "off"  # off | report | required (local.ci.train-candidate-on-a-branch)
    nightly: bool = False  # local.ci.nightly-gate-on-the-frozen-sha
    testflight: str = "local"  # local | xcode-cloud (local.ci.testflight-from-xcode-cloud)
    required: tuple = ("train-gate",)  # the check names a train lands on, by GitHub's check-run name
    wait_min: float = 45.0
    start_min: float = 10.0
    xcode_workflow: str = ""  # the Xcode Cloud workflow; its check runs are named from it
    xcode_cloud_on: tuple = ("nightly", "release")
    actions_minutes_month: float = 0.0  # optional (a public repo's standard minutes are free); 0 = no cap
    xcode_cloud_hours_month: float = 0.0  # required before train or nightly CI runs
    macos_multiplier: float = 10.0
    testflight_refs: str = "testflight/{version}"  # the ref pushed for the Xcode Cloud archive; {version} is the release version
    testflight_wait_min: float = 60.0
    local_guards: tuple = ()  # guards the nightly keeps in its local verify (history or a local tool)
    remote: str = "origin"
    repo: str = ""  # owner/name for the GitHub API; "" = gh's default for the checkout
    workflow: str = "tests.yml"


def load(rules: dict) -> Cfg:
    """`[ci]` of the rules; a missing table is off; an unknown key or a bad value refuses."""
    c = rules.get("ci", {})
    if unknown := sorted(set(c) - KEYS):
        raise ValueError(f"harness.toml [ci]: unknown keys {unknown}")
    d = Cfg()
    cfg = Cfg(train=str(c.get("train", d.train)), nightly=bool(c.get("nightly", d.nightly)), testflight=str(c.get("testflight", d.testflight)),
              required=tuple(c.get("required", d.required)), wait_min=float(c.get("wait_min", d.wait_min)), start_min=float(c.get("start_min", d.start_min)),
              xcode_workflow=str(c.get("xcode_workflow", d.xcode_workflow)), xcode_cloud_on=tuple(c.get("xcode_cloud_on", d.xcode_cloud_on)),
              actions_minutes_month=float(c.get("actions_minutes_month", 0)), xcode_cloud_hours_month=float(c.get("xcode_cloud_hours_month", 0)),
              macos_multiplier=float(c.get("macos_multiplier", d.macos_multiplier)), testflight_refs=str(c.get("testflight_refs", d.testflight_refs)),
              testflight_wait_min=float(c.get("testflight_wait_min", d.testflight_wait_min)), local_guards=tuple(c.get("local_guards", ())),
              remote=str(c.get("remote", d.remote)), repo=str(c.get("repo", "")), workflow=str(c.get("workflow", d.workflow)))
    if cfg.train not in ("off", "report", "required"):
        raise ValueError("harness.toml [ci].train is off, report or required")
    if cfg.testflight not in ("local", "xcode-cloud"):
        raise ValueError("harness.toml [ci].testflight is local or xcode-cloud")
    return cfg


def xcode_on(cfg: Cfg, where: str) -> bool:
    return bool(cfg.xcode_workflow) and where in cfg.xcode_cloud_on


def required_names(cfg: Cfg, where: str = "train") -> tuple:
    return tuple(cfg.required) + ((cfg.xcode_workflow,) if xcode_on(cfg, where) else ())


# --- caps (local.ci.caps-and-fallback) -----------------------------------------------------------------------------------------

def problems(cfg: Cfg, rows: list[dict], now: float | None = None) -> list[str]:
    """What the rules check refuses: train or nightly CI with no Xcode Cloud hours cap (as a metered provider with no weekly cap is),
    and `required` before seven days of `report` rows earned it."""
    out = []
    for what, on in (("train", cfg.train != "off"), ("nightly", cfg.nightly)):
        if on and cfg.xcode_cloud_hours_month <= 0:
            out.append(f"harness.toml [ci].{what} is on and [ci].xcode_cloud_hours_month is not set: Xcode Cloud hours are capped before CI runs")
    if cfg.train == "required" and (why := required_unearned(cfg, rows, now)):
        out.append(f"harness.toml [ci].train = \"required\" is refused: {why}; run `report` until `builder rung-stats --flow` shows it")
    return out


def required_unearned(cfg: Cfg, rows: list[dict], now: float | None = None) -> str:
    """'' when the last seven days of `report` train rows show CI's 90th percentile under wait_min and at most one train in twenty
    where CI disagreed with the local result; else why not."""
    now = time.time() if now is None else now
    rep = [r for r in rows if r.get("event") == "train" and (r.get("ci") or {}).get("mode") == "report" and _ts(r) >= now - 7 * 86400]
    if not rep or now - min(_ts(r) for r in rep) < 6.5 * 86400:
        return "fewer than seven days of report rows"
    mins = sorted(r["ci"].get("minutes", 0) for r in rep)
    p90 = mins[min(len(mins) - 1, math.ceil(0.9 * len(mins)) - 1)]
    if p90 >= cfg.wait_min:
        return f"CI's 90th percentile is {p90:.0f} min, not under [ci].wait_min = {cfg.wait_min:g}"
    bad = sum(1 for r in rep if r["ci"].get("agreed") is False)
    if bad * 20 > len(rep):
        return f"CI disagreed with the local result on {bad} of {len(rep)} trains (more than one in twenty)"
    return ""


def _ts(r: dict) -> float:
    try:
        return datetime.strptime(r["ts"][:19], "%Y-%m-%dT%H:%M:%S").timestamp()
    except (KeyError, ValueError, TypeError):
        return 0.0


def billed(job: dict, cfg: Cfg) -> float:
    """One job's billed minutes: GitHub rounds each job up to the minute; a macOS job counts `macos_multiplier` times."""
    m = math.ceil(max(0.0, float(job.get("seconds", 0))) / 60)
    return m * (cfg.macos_multiplier if str(job.get("os", "")).startswith("macos") else 1)


def record(jobs: list[dict], sha: str, cfg: Cfg, seen: set | None = None) -> None:
    """One `ci` row `job` per completed job the builder started (by id, once): its billed minutes, or an Xcode Cloud build's hours."""
    have = seen if seen is not None else {r.get("job") for r in journal.read() if r.get("event") == "ci" and r.get("state") == "job"}
    for j in jobs:
        if j.get("id") in have or j.get("status") != "completed":
            continue
        have.add(j.get("id"))
        xc = j.get("kind") == "xcode"
        journal.append("ci", state="job", job=j.get("id"), sha=sha, name=j.get("name", ""), kind="xcode" if xc else "actions",
                       minutes=0 if xc else billed(j, cfg), hours=round(float(j.get("seconds", 0)) / 3600, 3) if xc else 0)


def month(rows: list[dict], now: float | None = None) -> dict:
    """{"actions": billed minutes, "xcode": hours} of this calendar month's `ci` job rows."""
    key = time.strftime("%Y-%m", time.localtime(time.time() if now is None else now))
    got = [r for r in rows if r.get("event") == "ci" and r.get("state") == "job" and str(r.get("ts", ""))[:7] == key]
    return {"actions": sum(float(r.get("minutes", 0)) for r in got), "xcode": sum(float(r.get("hours", 0)) for r in got)}


def daily(cfg: Cfg, alert: Callable[[str], None], now: float | None = None) -> dict:
    """One `ci` row `month` a day with the month's sums, and one alert per cap per month at 80% of it. Returns the sums."""
    now = time.time() if now is None else now
    rows = journal.read()
    used = month(rows, now)
    day, mon = time.strftime("%Y-%m-%d", time.localtime(now)), time.strftime("%Y-%m", time.localtime(now))
    if not any(r.get("event") == "ci" and r.get("state") == "month" and r.get("day") == day for r in rows):
        journal.append("ci", state="month", day=day, actions_minutes=used["actions"], xcode_hours=round(used["xcode"], 2))
    for cap, val, unit in (("actions_minutes_month", used["actions"], "Actions minutes"), ("xcode_cloud_hours_month", used["xcode"], "Xcode Cloud hours")):
        limit = getattr(cfg, cap)
        if limit > 0 and val >= 0.8 * limit and not any(r.get("event") == "ci" and r.get("state") == "eighty" and r.get("cap") == cap and r.get("month") == mon for r in rows):
            journal.append("ci", state="eighty", cap=cap, month=mon, used=val, limit=limit)
            alert(f"hosted CI has used {val:g} of its {limit:g} {unit} this month (80%): at the cap the train runs its whole suites locally")
    return used


def at_cap(cfg: Cfg, now: float | None = None) -> str:
    used = month(journal.read(), now)
    if cfg.actions_minutes_month > 0 and used["actions"] >= cfg.actions_minutes_month:
        return f"at the Actions cap ({used['actions']:g} of {cfg.actions_minutes_month:g} minutes this month)"
    if cfg.xcode_cloud_hours_month > 0 and used["xcode"] >= cfg.xcode_cloud_hours_month:
        return f"at the Xcode Cloud cap ({used['xcode']:.1f} of {cfg.xcode_cloud_hours_month:g} hours this month)"
    return ""


# --- GitHub (the manager's gh, never a worker's) -------------------------------------------------------------------------------

class Down(Exception):
    """The API could not be reached or refused."""


class Hosted:
    """The check runs of a sha and what the builder does to them, through `gh`. `run(argv) -> (rc, stdout)`; tests replace the class."""

    def __init__(self, cfg: Cfg, cwd: str, run: Callable[[list[str]], tuple] | None = None):
        self.cfg, self.cwd = cfg, cwd
        self.run = run or (lambda argv: (lambda r: (r.returncode, r.stdout + (r.stderr if r.returncode else "")))(
            subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=120)))

    def _api(self, path: str) -> dict:
        rc, out = self.run(["gh", "api", f"repos/{self.cfg.repo or '{owner}/{repo}'}/{path}"])
        if rc:
            raise Down(out.strip()[-300:])
        return json.loads(out or "{}")

    def checks(self, sha: str) -> list[dict]:
        """[{name, id, status, conclusion, seconds, kind, os, run_id, job_id}] of the sha's check runs."""
        out = []
        for c in self._api(f"commits/{sha}/check-runs?per_page=100").get("check_runs", []):
            app = (c.get("app") or {}).get("slug", "")
            m = re.search(r"/runs/(\d+)/job/(\d+)", c.get("details_url") or "")
            out.append({"name": c["name"], "id": c["id"], "status": c.get("status", ""), "conclusion": c.get("conclusion") or "",
                        "seconds": _secs(c.get("started_at"), c.get("completed_at")), "kind": "actions" if app == "github-actions" else "xcode",
                        "run_id": m.group(1) if m else "", "job_id": m.group(2) if m else ""})
        return out

    def jobs(self, run_id: str) -> list[dict]:
        """The run's jobs: {id, name, conclusion, os, seconds, steps: [{name, conclusion}]}."""
        return [{"id": j["id"], "name": j["name"], "conclusion": j.get("conclusion") or "", "status": j.get("status", ""),
                 "os": next((lb for lb in j.get("labels", []) if lb.startswith(("macos", "ubuntu"))), ""),
                 "seconds": _secs(j.get("started_at"), j.get("completed_at")), "kind": "actions",
                 "steps": [{"name": s["name"], "conclusion": s.get("conclusion") or ""} for s in j.get("steps", [])]}
                for j in self._api(f"actions/runs/{run_id}/jobs?per_page=100").get("jobs", [])]

    def failed_log(self, run_id: str, job_id) -> str:
        rc, out = self.run(["gh", "run", "view", str(run_id), "--job", str(job_id), "--log-failed"])
        return out if rc == 0 else ""

    def rerun_failed(self, run_id: str) -> None:
        rc, out = self.run(["gh", "run", "rerun", str(run_id), "--failed"])
        if rc:
            raise Down(out.strip()[-300:])

    def dispatch(self, ref: str, inputs: dict | None = None) -> None:
        rc, out = self.run(["gh", "workflow", "run", self.cfg.workflow, "--ref", ref, *(a for k, v in (inputs or {}).items() for a in ("-f", f"{k}={v}"))])
        if rc:
            raise Down(out.strip()[-300:])

    def push(self, sha: str, branch: str) -> str:
        rc, out = self.run(["git", "push", "-q", "--force", self.cfg.remote, f"{sha}:refs/heads/{branch}"])
        return "" if rc == 0 else out.strip()[-300:]

    def delete(self, branch: str) -> str:
        rc, out = self.run(["git", "push", "-q", self.cfg.remote, "--delete", branch])
        return "" if rc == 0 else out.strip()[-300:]


def _secs(a, b) -> float:
    try:
        f = "%Y-%m-%dT%H:%M:%SZ"
        return max(0.0, (datetime.strptime(b, f) - datetime.strptime(a, f)).total_seconds())
    except (TypeError, ValueError):
        return 0.0


# --- waiting, re-running and judging (local.ci.train-lands-on-green-checks, local.ci.red-is-retried-once-and-judged-against-base) --

@dataclass
class Verdict:
    ok: bool = False
    checks: list = field(default_factory=list)  # [{name, conclusion, minutes}] of each required check
    cases: list = field(default_factory=list)  # failing cases red on the candidate and green on its base: for the step search
    flaky: list = field(default_factory=list)
    fallback: str = ""  # why CI was not used: the train ran its whole suites locally
    timeout: bool = False
    minutes: float = 0.0


def wait(h: Hosted, sha: str, names: tuple, cfg: Cfg, clock=time.time, sleep=time.sleep, poll_s: float = 30.0, newer: dict | None = None) -> tuple[dict, str]:
    """({name: check} of the newest check per required name once all completed; "" or "not-started" / "timeout"). Down raises.
    `newer` {name: id}: only a check run after that one counts (a re-run makes a new check run; the old one stays completed)."""
    t0 = clock()
    while True:
        got, every = {}, h.checks(sha)
        for c in every:
            if c["name"] in names and c["id"] > (newer or {}).get(c["name"], -1) and (c["name"] not in got or c["id"] > got[c["name"]]["id"]):
                got[c["name"]] = c
        if got and all(n in got and got[n]["status"] == "completed" for n in names):
            return got, ""
        if not every and clock() - t0 >= cfg.start_min * 60:  # no run of any job started: CI is not there
            return got, "not-started"
        if clock() - t0 >= cfg.wait_min * 60:
            return got, "timeout"
        sleep(poll_s)


def _failed(h: Hosted, check: dict) -> tuple[bool, list[str], list[dict]]:
    """(infra, the failing cases, the run's failed jobs) of a failed check: infra = no runner, a cancel, a timeout, or a set-up step."""
    if check["conclusion"] in INFRA:
        return True, [], []
    jobs = [j for j in h.jobs(check["run_id"]) if j["conclusion"] not in ("success", "skipped", "")] if check.get("run_id") else []
    if any(j["conclusion"] in INFRA for j in jobs):
        return True, [], jobs
    cases, infra = [], bool(jobs)
    for j in jobs:
        steps = j.get("steps", [])
        first_bad = next((i for i, s in enumerate(steps) if s["conclusion"] == "failure"), None)
        first_test = next((i for i, s in enumerate(steps) if TEST_STEP.search(s["name"])), None)
        if first_bad is not None and (first_test is None or first_bad < first_test):
            continue  # this job failed setting up
        infra = False
        cases += failing(h.failed_log(check["run_id"], j["id"]))
    return infra, sorted(set(cases)), jobs


def judge(h: Hosted, sha: str, base: str, cfg: Cfg, alert: Callable[[str], None], *, where: str = "train", push_base: Callable[[], str] | None = None,
          clock=time.time, sleep=time.sleep) -> Verdict:
    """The required checks of `sha`, sorted before they count: an infrastructure failure is re-run once (twice: not run, one alert,
    a fallback); a test failure is re-run once (green then: a `flaky` row); red twice: judged against `base`'s newest completed run
    of the same check (started once by `push_base` when there is none), and the candidate is red only for cases green there."""
    v = Verdict()
    names = required_names(cfg, where)
    if why := at_cap(cfg, clock()):
        v.fallback = why
        return v
    try:
        got, end = wait(h, sha, names, cfg, clock, sleep)
        if end == "not-started":
            v.fallback = f"no CI run started within [ci].start_min = {cfg.start_min:g} min"
            return v
        if end == "timeout":
            v.timeout, v.checks = True, [_row(c) for c in got.values()]
            return v
        record([j for c in got.values() if c.get("run_id") for j in h.jobs(c["run_id"])] or list(got.values()), sha, cfg)
        reds: dict = {}
        for name, c in got.items():
            if c["conclusion"] == "success":
                continue
            infra, cases, _jobs = _failed(h, c)
            if c.get("run_id"):
                h.rerun_failed(c["run_id"])
            again, end2 = wait(h, sha, (name,), cfg, clock, sleep, newer={name: c["id"]})
            c2 = again.get(name, c) if not end2 else c
            got[name] = c2
            if c2["conclusion"] == "success":
                if cases:
                    v.flaky.append({"check": name, "cases": cases})
                    journal.append("ci", state="flaky", sha=sha, check=name, job=c.get("job_id", ""), cases=cases,
                                   detail=f"{name}: {len(cases)} case(s) red once and green on the re-run: filed, never hidden")
                continue
            infra2, cases2, _ = _failed(h, c2)
            if infra and infra2:
                alert(f"hosted CI check {name} at {sha[:9]} failed on its infrastructure twice: it is not run, never red")
                v.fallback = f"{name} failed on its infrastructure twice"
                return v
            reds[name] = cases2 or cases
        v.checks = [_row(c) for c in got.values()]
        v.minutes = round(sum(c.get("seconds", 0) for c in got.values()) / 60, 1)
        if not reds:
            v.ok = True
            return v
        base_got = _base_checks(h, base, tuple(reds), cfg, push_base, clock, sleep)
        for name, cases in reds.items():
            b = base_got.get(name)
            if b is None:  # the base could not run: the red stands, every case goes to the step search
                v.cases += cases or [f"{name} (no cases named)"]
                continue
            base_cases = set() if b["conclusion"] == "success" else set(_failed(h, b)[1])
            if b["conclusion"] != "success" and not cases:
                continue  # red on the base too, and nothing more is named: the base's
            v.cases += [x for x in cases if x not in base_cases] if cases else [f"{name} (no cases named)"]
        v.ok = not v.cases
        return v
    except Down as e:
        v.fallback = f"the GitHub API could not be reached: {e}"
        return v


def _base_checks(h: Hosted, base: str, names: tuple, cfg: Cfg, push_base, clock, sleep) -> dict:
    have = {}
    for c in h.checks(base):
        if c["name"] in names and c["status"] == "completed" and (c["name"] not in have or c["id"] > have[c["name"]]["id"]):
            have[c["name"]] = c
    if len(have) == len(names) or push_base is None:
        return have
    if push_base():  # the push failed: what there is
        return have
    got, end = wait(h, base, names, cfg, clock, sleep)
    return {**got, **have} if not end else have


def _row(c: dict) -> dict:
    return {"name": c["name"], "conclusion": c.get("conclusion") or c.get("status", ""), "minutes": round(c.get("seconds", 0) / 60, 1)}


# --- the train (local.ci.train-candidate-on-a-branch) --------------------------------------------------------------------------

def branch(tid: str) -> str:
    return f"train/{tid}"


def with_train(cfg: Cfg, h: Hosted | None, tid: str, run: Callable[[Callable[[str], None]], object]):
    """`run(on_candidate)` runs the train; with CI on, `on_candidate(sha)` pushes the candidate to `train/<tid>` before the local rungs
    start, and the branch (and its `-base` one) is deleted when the train ends, however it ends. Returns run's result."""
    if cfg.train == "off" or h is None:
        return run(lambda sha: None)
    pushed: list = []

    def on_candidate(sha: str) -> None:
        if at_cap(cfg):
            return  # at the cap no CI run starts; the train falls back when it reads the checks
        if err := h.push(sha, branch(tid)):
            journal.append("ci", state="push-failed", train=tid, detail=err)
            return
        pushed.append(branch(tid))
        journal.append("ci", state="pushed", train=tid, sha=sha, branch=branch(tid))
    try:
        return run(on_candidate)
    finally:
        for b in (branch(tid), branch(tid) + "-base"):
            if b in pushed or b.endswith("-base"):
                err = h.delete(b)
                if b in pushed:
                    journal.append("ci", state="deleted", train=tid, branch=b, detail=err)


def land_on_checks(res, cfg: Cfg, h: Hosted | None, base: str, alert: Callable[[str], None], run_local: Callable[[str], tuple] | None = None,
                   search: Callable[[list], object] | None = None, clock=time.time, sleep=time.sleep):
    """local.ci.train-lands-on-green-checks: the train's Result after its local rungs, with `res.ci` set. `report`: the result stands,
    with each check, its minutes and whether it agreed. `required`: a green local train lands only when every required check is green
    at its candidate; a timeout ends it `timeout`; a fallback runs the whole suites locally (`run_local(candidate)`) and that decides;
    a red goes to `search(cases)` (local.train.red-goes-to-its-step), or every step waits again."""
    if cfg.train == "off" or h is None or not res.candidate or res.result not in ("green", "conflict", "red", "unresolved"):
        return res
    local_green = res.result in ("green", "conflict")
    if cfg.train == "report" or not local_green:
        v = judge(h, res.candidate, base, cfg, alert, push_base=lambda: h.push(base, branch(res.id) + "-base"), clock=clock, sleep=sleep)
        res.ci = {"mode": cfg.train, "checks": v.checks, "minutes": v.minutes, "fallback": v.fallback,
                  "agreed": None if v.fallback or v.timeout else v.ok == local_green, "flaky": v.flaky}
        return res
    v = judge(h, res.candidate, base, cfg, alert, push_base=lambda: h.push(base, branch(res.id) + "-base"), clock=clock, sleep=sleep)
    res.ci = {"mode": "required", "checks": v.checks, "minutes": v.minutes, "fallback": v.fallback, "flaky": v.flaky, "cases": v.cases}
    if v.fallback:
        journal.append("ci", state="ci-fallback", train=res.id, detail=v.fallback + ": the whole suites run on the local runners")
        ok, out = run_local(res.candidate) if run_local else (True, "")
        if ok:
            return res
        res.ci["local"] = out[-500:]
        v.cases = failing(out) or ["the local whole suites (see the train row)"]
    elif v.timeout:
        res.again, res.landed, res.result = list(res.landed), [], "timeout"
        res.bisect.append(f"stopped: no required check completed within [ci].wait_min = {cfg.wait_min:g} min")
        return res
    elif v.ok:
        return res
    if search is not None:
        return search(v.cases)
    res.again, res.landed, res.result = list(res.landed), [], "red"
    res.bisect.append("hosted CI is red on cases green on the base: " + ", ".join(v.cases)[:300])
    alert(f"the merge train {res.id} is red on hosted CI: {', '.join(v.cases)[:200]}; its steps wait again")
    return res


def failing(out: str) -> list[str]:
    """The failing cases a job log names: pytest's `FAILED|ERROR path::case` summary lines and XCTest's (check_tool.failing_cases)."""
    from fichero_builder import check_tool
    return sorted(set(check_tool.failing_cases(out)) | set(re.findall(r"\b(?:FAILED|ERROR) (\S+::\S+)", out)))


def local_rungs(cfg: Cfg, names: list[str]) -> list[str]:
    """In `required` mode the whole Python suites (`unit`) are CI's; the train runs them here only on a fallback."""
    return [n for n in names if n != "unit"] if cfg.train == "required" else names
