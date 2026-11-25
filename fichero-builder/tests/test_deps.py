"""local.deps.weekly: `builder deps` over a faked gh. A green grouped or Actions bump is squash-merged; a major or red one is queued
as a step with a brief from the PR and never merged; dry-run changes nothing; main is never touched; the loop runs it weekly."""
from __future__ import annotations

import json
import subprocess
import time
from datetime import datetime

import pytest

from fichero_builder import deps, journal, queue

TOML = '[land]\nbranch = "integration"\n[deps]\nenabled = true\nday = "mon"\nhour = 9\nlane = "deps"\nworktree = "/w/wt-deps"\n'
GREEN = [{"name": "builder", "bucket": "pass"}, {"name": "engine", "bucket": "pass"}]
PRS = [
    {"number": 11, "title": "Bump the python-minor group across 1 directory with 3 updates", "headRefName": "dependabot/uv/python-minor-1a",
     "baseRefName": "integration", "url": "https://github.com/o/r/pull/11", "body": "Updates `httpx` from 0.27.0 to 0.27.2\nUpdates `ruff` from 0.6.1 to 0.6.9"},
    {"number": 12, "title": "Bump actions/checkout from 4 to 5", "headRefName": "dependabot/github_actions/actions/checkout-5",
     "baseRefName": "integration", "url": "https://github.com/o/r/pull/12", "body": "Bumps [actions/checkout](https://github.com/actions/checkout) from 4 to 5."},
    {"number": 13, "title": "Bump the python-minor group with 2 updates", "headRefName": "dependabot/uv/python-minor-2b",
     "baseRefName": "integration", "url": "https://github.com/o/r/pull/13", "body": "Updates `duckdb` from 1.4.1 to 1.4.2\nUpdates `pydantic` from 2.9.0 to 2.10.0"},
    {"number": 14, "title": "Bump fastapi from 0.115.0 to 1.0.0 in /fichero-server", "headRefName": "dependabot/uv/fichero-server/fastapi-1.0.0",
     "baseRefName": "integration", "url": "https://github.com/o/r/pull/14",
     "body": "Bumps [fastapi](https://github.com/fastapi/fastapi) from 0.115.0 to 1.0.0.\n- [Release notes](https://github.com/fastapi/fastapi/releases)"},
    {"number": 15, "title": "Bump the python-minor group with 1 update", "headRefName": "dependabot/uv/python-minor-3c",
     "baseRefName": "integration", "url": "https://github.com/o/r/pull/15", "body": "Updates `numpy` from 2.1.0 to 2.1.3"},
    {"number": 16, "title": "Bump the python-minor group with 1 update", "headRefName": "dependabot/uv/python-minor-4d",
     "baseRefName": "main", "url": "https://github.com/o/r/pull/16", "body": "Updates `rich` from 13.0.0 to 13.1.0"},
]
CHECKS = {"11": GREEN, "12": GREEN, "13": [{"name": "builder", "bucket": "pass"}, {"name": "engine (shard 2)", "bucket": "fail"}],
          "14": GREEN, "15": [{"name": "builder", "bucket": "pending"}], "16": GREEN}


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    (tmp_path / "harness.toml").write_text(TOML)
    return tmp_path


def fake_gh(calls):
    def run(argv, **k):
        calls.append(argv[1:])
        if argv[1:3] == ["pr", "list"]:
            return subprocess.CompletedProcess(argv, 0, json.dumps(PRS), "")
        if argv[1:3] == ["pr", "checks"]:
            return subprocess.CompletedProcess(argv, 0, json.dumps(CHECKS[argv[3]]), "")
        return subprocess.CompletedProcess(argv, 0, "", "")
    return run


def test_green_grouped_and_actions_bumps_merge_major_and_red_ones_queue_a_step_and_nothing_touches_main(root):
    calls, queued, said = [], [], []
    assert deps.main_run(root, run=fake_gh(calls), out=said.append, enqueue=lambda *a: queued.append(a)) == 0
    merges = [c for c in calls if c[:2] == ["pr", "merge"]]
    assert merges == [["pr", "merge", "11", "--squash"], ["pr", "merge", "12", "--squash"]], "only the green grouped and Actions bumps"
    assert ["--author", "app/dependabot", "--base", "integration"] == calls[0][2:6]
    assert ["pr", "checks", "11", "--required", "--json", "name,bucket"] in calls
    assert all("--required" in c for c in calls if c[1] == "checks"), "only the required checks decide"
    assert [(q[0], q[1], q[2]) for q in queued] == [("deps", "/w/wt-deps", "dep-13"), ("deps", "/w/wt-deps", "dep-14")]
    red = (root / "s" / "deps-briefs" / "dep-13.txt").read_text()
    assert "Failing required checks: engine (shard 2)" in red and "- duckdb: 1.4.1 -> 1.4.2" in red and "#13" in red
    major = (root / "s" / "deps-briefs" / "dep-14.txt").read_text()
    assert "- fastapi: 0.115.0 -> 1.0.0 (MAJOR)" in major and "https://github.com/fastapi/fastapi/releases" in major
    states = {r["pr"]: r["state"] for r in journal.read() if r["event"] == "deps"}
    assert states == {11: "merged", 12: "merged", 13: "queued", 14: "queued", 15: "wait", 16: "skip"}


def test_dry_run_prints_what_it_would_do_and_changes_nothing(root):
    calls, queued, said = [], [], []
    assert deps.main_run(root, run=fake_gh(calls), out=said.append, enqueue=lambda *a: queued.append(a), dry=True) == 0
    assert not [c for c in calls if c[:2] == ["pr", "merge"]] and queued == [] and not journal.read()
    assert said[0].startswith("would #11") and ": merge (" in said[0] and any(s.startswith("would #14") and ": queue (major: fastapi" in s for s in said)


def test_a_land_branch_named_main_refuses_the_whole_run(root):
    (root / "harness.toml").write_text(TOML.replace('"integration"', '"main"'))
    calls, said = [], []
    assert deps.main_run(root, run=fake_gh(calls), out=said.append) == 1
    assert calls == [] and "never works on main" in said[0]


def test_the_loop_runs_it_once_on_its_day_after_its_hour_and_not_when_off(root):
    ran = []
    procs = queue.Procs(start=None, alive=None, send=None, rebase=None, row=None, chain=None, landed=None, end_of=None, stop=None,
                        deps=lambda: ran.append(1) or 0, deps_cfg=deps.load(root))
    monday_8, monday_10, tuesday = datetime(2026, 11, 23, 8), datetime(2026, 11, 23, 10), datetime(2026, 11, 24, 10)
    for now in (monday_8, monday_10, monday_10, tuesday):
        procs.now = lambda now=now: now
        queue.deps_when_due(procs, None)
    assert ran == [1], "Monday after 09:00, once"
    assert (root / "s" / queue.DEPS_LAST).read_text().strip() == "2026-11-23"
    assert not deps.load(root.parent / "none").enabled and queue.deps_job(root.parent / "none") is None, "no [deps]: the job is off"
    assert time.localtime(monday_10.timestamp()).tm_wday == 0
