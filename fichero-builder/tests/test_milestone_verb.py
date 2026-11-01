"""dev-workflows.tool.milestone: a milestone's issues under the spec's steps, briefs in build order, questions never guesses."""
from __future__ import annotations

import json
import os
import stat

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
    assert [c["step"] for c in p["clusters"]] == ["1.1"], "1.2 waits on 1.1, which still has an open issue"
    assert any("#9" in q and "no build-order step" in q for q in p["questions"])
    assert any("Step 1.2 waits on Step 1.1" in q for q in p["questions"])
    p2 = milestone.plan([i for i in ISSUES if i["number"] == 8], steps, "m1")
    assert [c["step"] for c in p2["clusters"]] == ["1.2"] and not p2["questions"], "1.1 landed: 1.2 runs"
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
    assert rc == 2 and "Step 1.1: #7 ->" in out and err.count("QUESTION:") == 2
    brief = (tmp_path / "out" / "brief-step-1.1.txt").read_text()
    assert "Branch step-1.1" in brief and "base abc1234" in brief and "Rule one." in brief and "do the base" in brief
    assert not (tmp_path / "out" / "brief-step-1.2.txt").exists()
    assert os.listdir(tmp_path / "out") == ["brief-step-1.1.txt"]
