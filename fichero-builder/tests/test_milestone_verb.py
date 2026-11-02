"""dev-workflows.tool.milestone: a milestone's issues under the spec's steps, briefs in build order, questions never guesses."""
from __future__ import annotations

import json
import os
import stat
import types

from fichero_builder import __main__ as cli
from fichero_builder import milestone

SPEC = """# A spec

> Milestone: m1
> **Status: APPROVED by the owner**

## Build order

### Stage 1 — first

#### Step 1.1 — the base
- Behaviours: `a.b.one`
- Tests: t/test_one.py
- Size: S

#### Step 1.2 — on top
- Behaviours: `a.b.two`
- Tests: t/test_two.py
- Depends on: 1.1
- Size: S
"""
ISSUES = [{"number": 7, "title": "m1 Step 1.1: the base", "body": ""},
          {"number": 8, "title": "on top", "body": "Step: 1.2\nmore"},
          {"number": 9, "title": "a stray bug", "body": "no step here"}]


def test_steps_come_from_the_guards_parser_and_issues_name_their_step(tmp_path):
    (tmp_path / "spec.md").write_text(SPEC)
    steps = milestone.build_order(tmp_path / "spec.md")
    assert [s["number"] for s in steps] == ["1.1", "1.2"] and steps[1]["depends_on"] == ["1.1"]
    assert milestone.spec_slug(tmp_path / "spec.md") == "m1"
    assert [milestone.step_of(i, "m1") for i in ISSUES] == ["1.1", "1.2", None]
    assert milestone.step_of({"number": 1, "title": "pipeline Step 1.1: x", "body": ""}, "m1") is None, "another spec's step"


def test_plan_orders_clusters_and_asks_instead_of_guessing(tmp_path):
    (tmp_path / "spec.md").write_text(SPEC)
    steps = milestone.build_order(tmp_path / "spec.md")
    p = milestone.plan(ISSUES, steps, "m1")
    assert [(c["step"], c["waits"]) for c in p["clusters"]] == [("1.1", []), ("1.2", ["1.1"])], "1.2 waits on 1.1, which still has an open issue"
    assert any("#9" in q and "no build-order step" in q for q in p["questions"])
    waits = [q for q in p["questions"] if "wait" in q]
    assert len(waits) == 1 and "1.2 (after 1.1)" in waits[0], "one line for every wait, not one per step"
    p2 = milestone.plan([i for i in ISSUES if i["number"] == 8], steps, "m1")
    assert [(c["step"], c["waits"]) for c in p2["clusters"]] == [("1.2", [])] and not p2["questions"], "1.1 landed: 1.2 runs"
    assert "does not have" in milestone.plan([{"number": 1, "title": "m1 Step 9.9: x", "body": ""}], steps, "m1")["questions"][0]


def _fake_gh(tmp_path):
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    (tmp_path / "issues.json").write_text(json.dumps(ISSUES))
    gh = bin_ / "gh"
    gh.write_text(f'''#!/bin/sh
case "$*" in
  "issue list"*) cat {tmp_path}/issues.json ;;
  "repo view"*) echo o/r ;;
  *comments*) echo "[]" ;;
  *issues/7*) echo '[{{"number": 7, "title": "m1 Step 1.1: the base", "body": "do the base", "user": {{"login": "u"}}, "author_association": "OWNER"}}]' ;;
  *issues/8*) echo '[{{"number": 8, "title": "on top", "body": "Step: 1.2", "user": {{"login": "u"}}, "author_association": "OWNER"}}]' ;;
  *) echo "unexpected: $*" >&2; exit 1 ;;
esac
''')
    gh.chmod(gh.stat().st_mode | stat.S_IXUSR)
    return str(gh)


def test_the_verb_writes_one_brief_per_cluster_and_prints_the_questions(tmp_path, capsys):
    (tmp_path / "spec.md").write_text(SPEC)
    (tmp_path / "harness.toml").write_text('[brief]\nrules = "Rule one."\n')
    gh = _fake_gh(tmp_path)
    rc = cli.main(["milestone", "m1", "--spec", str(tmp_path / "spec.md"), "--repo-dir", str(tmp_path), "--out", str(tmp_path / "out"),
                   "--base", "abc1234", "--gh", gh])
    out, err = capsys.readouterr()
    assert rc == 2 and "Step 1.1: #7 ->" in out and "Step 1.2: #8 ->" in out and err.count("QUESTION:") == 2
    brief = (tmp_path / "out" / "brief-step-1.1.txt").read_text()
    assert "Branch step-1.1" in brief and "base abc1234" in brief and "Rule one." in brief and "do the base" in brief
    assert sorted(os.listdir(tmp_path / "out")) == ["brief-step-1.1.txt", "brief-step-1.2.txt"], "a waiting step's brief is written too (the queue runs it after)"


def test_enqueue_queues_one_item_per_step_brief_with_its_waits_as_depends_on(tmp_path, monkeypatch):
    from fichero_builder import journal, queue

    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    (tmp_path / "spec.md").write_text(SPEC)
    (tmp_path / "harness.toml").write_text('[brief]\nrules = "Rule one."\n[jail]\nworkroot = "/wr"\n')
    gh = _fake_gh(tmp_path)
    assert cli.main(["milestone", "m1", "--spec", str(tmp_path / "spec.md"), "--repo-dir", str(tmp_path), "--out", str(tmp_path / "out"),
                     "--base", "abc1234", "--gh", gh, "--enqueue", "--state", str(tmp_path / "s")]) == 2
    items = {i["id"]: i for i in queue.load()}
    assert items["step-1.1"]["depends_on"] == [] and items["step-1.1"]["issues"] == [7] and items["step-1.1"]["worktree"] == "/wr/wt-step-1.1"
    assert items["step-1.2"]["depends_on"] == ["step-1.1"] and items["step-1.2"]["brief"].endswith("brief-step-1.2.txt") and items["step-1.2"]["base"] == "abc1234"


def test_the_step_label_is_read_first_and_the_title_shape_only_for_an_issue_with_no_step_label():
    """Item 8: `step:N.M` is the key; the title shape and the body line are the fallback for unlabelled issues."""
    labelled = {"number": 9, "title": "a plain title", "body": "", "labels": [{"name": "spec:m1"}, {"name": "step:2.1"}]}
    assert milestone.step_of(labelled, "m1") == "2.1"
    mislabelled_title = {"number": 10, "title": "m1 Step 1.1: old shape", "body": "", "labels": [{"name": "step:1.2"}]}
    assert milestone.step_of(mislabelled_title, "m1") == "1.2", "the label wins over the title"
    assert milestone.step_of({"number": 11, "title": "m1 Step 1.1: x", "body": "", "labels": []}, "m1") == "1.1"


def test_list_issues_asks_gh_for_the_labels(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(milestone.subprocess, "run", lambda argv, **kw: (seen.append(argv), types.SimpleNamespace(returncode=0, stdout="[]", stderr=""))[1])
    assert milestone.list_issues("m1", gh="gh") == []
    assert "number,title,body,labels" in seen[0]


def test_no_name_takes_the_first_ordered_milestone_with_open_issues_and_its_spec(tmp_path, capsys):
    """Rule 5 (issues-and-labels): `builder milestone` with no name reads specs/build-order.md: the first milestone under
    `## In order` that still has open issues, and the spec that line names; no file is a refusal."""
    specs = tmp_path / "docs" / "contributor_manual" / "specs" / "h"
    specs.mkdir(parents=True)
    (specs / "m1.md").write_text(SPEC)
    (tmp_path / "harness.toml").write_text('[brief]\nrules = "Rule one."\n')
    gh = _fake_gh(tmp_path)
    rc = cli.main(["milestone", "--repo-dir", str(tmp_path), "--out", str(tmp_path / "out"), "--base", "abc1234", "--gh", gh])
    assert rc == 1 and "no build-order file" in capsys.readouterr().out
    (specs.parent / "build-order.md").write_text("# Order\n\n## In order\n\n1. `m1` — first. Spec: h/m1.md\n")
    rc = cli.main(["milestone", "--repo-dir", str(tmp_path), "--out", str(tmp_path / "out"), "--base", "abc1234", "--gh", gh])
    out, _ = capsys.readouterr()
    assert rc == 2 and "milestone m1 (first in build-order.md)" in out and "Step 1.1: #7 ->" in out
