"""dev-workflows.tool.steps: `builder steps --spec FILE` files one issue per build-order step of an APPROVED spec under its
milestone, updates (never duplicates) on a second run, refuses a PROPOSED spec, and journals every write. A fake `gh`
script keeps issues in a JSON file and logs every call."""
from __future__ import annotations

import json
import shlex
import sys

import pytest

from fichero_builder import __main__ as cli
from fichero_builder import journal

SPEC = """# Thing — Design Spec

> Milestone: thing
> Manual: TBD

> **Status: {status} by the owner 2026-11-01.**

## Build order

### Stage 1 — first

#### Step 1.1 — the model (#99)
- Behaviours: `thing.model`
- Tests: tests/test_model.py
- Size: S

#### Step 1.2 — the route
- Behaviours: `thing.route`, `thing.error`
- Tests: tests/test_route.py
- Depends on: 1.1
- Size: M

### Stage 2 — second

#### Step 2.1 — the view
- Behaviours: `thing.view`
- Tests: tests/test_view.py
- Depends on: 1.1, 1.2
- Size: M

## Test matrix
"""

FAKE_GH = """import json, sys
from pathlib import Path
state = Path({state!r})
db = json.loads(state.read_text()) if state.exists() else {{"issues": [], "calls": []}}
argv = sys.argv[1:]
db["calls"].append(argv)
def opt(name):
    return argv[argv.index(name) + 1] if name in argv else None
db.setdefault("labels", ["type:feature"])  # the kind label exists already; no spec label is ever made
if argv[:2] == ["issue", "list"]:
    print(json.dumps([i for i in db["issues"] if i["milestone"] == opt("--milestone")]))
elif argv[:2] == ["issue", "create"]:
    n = 100 + len(db["issues"])
    db["issues"].append({{"number": n, "title": opt("--title"), "body": opt("--body"), "milestone": opt("--milestone"),
                         "labels": (opt("--label") or "").split(",") if opt("--label") else []}})
    print("https://github.com/o/r/issues/%d" % n)
elif argv[:2] == ["issue", "edit"]:
    for i in db["issues"]:
        if str(i["number"]) == argv[2]:
            if opt("--body"): i["body"] = opt("--body")
            if opt("--add-label"): i["labels"] = sorted(set(i.get("labels", [])) | set(opt("--add-label").split(",")))
elif argv[:2] == ["label", "list"]:
    print(json.dumps([{{"name": x}} for x in db["labels"]]))
elif argv[:2] == ["label", "create"]:
    db["labels"].append(argv[2])
state.write_text(json.dumps(db))
"""


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    state = tmp_path / "gh.json"
    gh = tmp_path / "gh"
    # A shebang cannot hold an interpreter path with a space (the gate disk's): an sh wrapper runs the script instead.
    gh.with_suffix(".py").write_text(FAKE_GH.format(state=str(state)))
    gh.write_text(f"#!/bin/sh\nexec {shlex.quote(sys.executable)} {shlex.quote(str(gh.with_suffix('.py')))} \"$@\"\n")
    gh.chmod(0o755)
    spec = tmp_path / "spec.md"
    spec.write_text(SPEC.format(status="APPROVED"))

    def run(*extra, spec_path=spec):
        return cli.main(["steps", "--spec", str(spec_path), "--gh", str(gh), "--state", str(tmp_path / "s"), *extra])

    def db():
        return json.loads(state.read_text()) if state.exists() else {"issues": [], "calls": []}
    run.db, run.spec = db, spec
    return run


def writes(db, verb):
    return [c for c in db["calls"] if c[:2] == ["issue", verb]]


def test_one_issue_per_step_with_the_body_and_depends_on_links(env):
    assert env() == 0
    d = env.db()
    assert [i["title"] for i in d["issues"]] == ["thing Step 1.1: the model", "thing Step 1.2: the route", "thing Step 2.1: the view"]
    assert all(i["milestone"] == "thing" for i in d["issues"])
    b1, b2, b3 = (i["body"] for i in d["issues"])
    assert "Step: 1.1" in b1 and "Behaviours: `thing.model`" in b1 and "Tests: tests/test_model.py" in b1 and "Size: S" in b1
    assert "Depends on" not in b1
    assert "Depends on: #100" in b2 and "`thing.route`, `thing.error`" in b2
    assert "Depends on: #100, #101" in b3 and "Step: 2.1" in b3


def test_a_second_run_updates_by_title_and_files_nothing_new(env):
    env()
    assert env() == 0
    d = env.db()
    assert len(d["issues"]) == 3 and len(writes(d, "create")) == 3 and len(writes(d, "edit")) == 3
    assert "Depends on: #100" in d["issues"][1]["body"]
    acts = [(r["action"], r["step"]) for r in journal.read() if r["event"] == "steps"]
    assert acts == [("create", "1.1"), ("create", "1.2"), ("create", "2.1"), ("update", "1.1"), ("update", "1.2"), ("update", "2.1")]
    assert all(r["issue"] >= 100 and r["title"] for r in journal.read() if r["event"] == "steps")


def test_a_proposed_spec_is_refused_and_nothing_is_written(env, capsys):
    env.spec.write_text(SPEC.format(status="PROPOSED"))
    assert env() == 1
    assert "PROPOSED" in capsys.readouterr().err
    assert env.db()["issues"] == [] and journal.read() == []


def test_dry_run_prints_the_plan_and_writes_nothing(env, capsys):
    assert env("--dry-run") == 0
    out = capsys.readouterr().out
    assert out.count("would create") == 3 and "thing Step 1.2: the route" in out
    d = env.db()
    assert writes(d, "create") == [] and writes(d, "edit") == [] and journal.read() == []


def test_a_spec_with_no_milestone_line_is_refused(env, capsys):
    env.spec.write_text(SPEC.format(status="APPROVED").replace("> Milestone: thing\n", ""))
    assert env() == 1 and "Milestone" in capsys.readouterr().err


def test_find_lists_the_milestone_and_compares_exact_titles_and_a_hung_gh_is_refused(tmp_path, monkeypatch):
    from fichero_builder import steps

    seen = []
    monkeypatch.setattr(steps, "_gh", lambda gh, *args: (seen.append(args), json.dumps([{"number": 5, "title": "m Step 1.1: a b"}]))[1])
    assert steps.find("gh", "m", "m Step 1.1: a b") == 5 and steps.find("gh", "m", "m Step 1.1: a") is None
    assert "--search" not in seen[0] and seen[0][seen[0].index("--limit") + 1] == "1000"

    import subprocess
    monkeypatch.undo()
    monkeypatch.setattr(steps.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(subprocess.TimeoutExpired("gh", 120)))
    with pytest.raises(steps.Refused, match="timed out"):
        steps._gh("gh", "issue", "list")


def test_every_step_issue_carries_the_step_label_and_type_feature_never_a_spec_label(env):
    """The step key is (milestone, `step:N.M`): each issue gets `step:N.M` and `type:feature`, no `spec:*` (the milestone is
    the spec); a missing step label is created (list first), an existing one never re-created; create comes before the
    issue write that applies it."""
    assert env() == 0
    d = env.db()
    assert [sorted(i["labels"]) for i in d["issues"]] == [["step:1.1", "type:feature"], ["step:1.2", "type:feature"], ["step:2.1", "type:feature"]]
    creates = [c[2] for c in d["calls"] if c[:2] == ["label", "create"]]
    assert creates == ["step:1.1", "step:1.2", "step:2.1"], "each step label once, no spec label"
    lists = [k for k, c in enumerate(d["calls"]) if c[:2] == ["label", "list"]]
    first_create = next(k for k, c in enumerate(d["calls"]) if c[:2] == ["label", "create"])
    first_issue = next(k for k, c in enumerate(d["calls"]) if c[:2] == ["issue", "create"])
    assert lists and lists[0] < first_create < first_issue
    assert env() == 0  # the second run applies the same labels to the found issues and creates no label
    d = env.db()
    assert [c[2] for c in d["calls"] if c[:2] == ["label", "create"]] == creates
    assert all(c[:2] != ["issue", "edit"] or "--add-label" in c for c in d["calls"][len(d["calls"]) // 2:])
