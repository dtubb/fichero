"""dev-workflows.tool.milestone: a milestone's issues under the spec's steps, briefs in build order, questions never guesses."""
from __future__ import annotations

import json
import os
import stat
import types
from pathlib import Path

from fichero_builder import __main__ as cli
from fichero_builder import brief_tool, milestone

SPEC = """# A spec

> Milestone: m1
> **Status: APPROVED by the owner**

## Build order

### Stage 1 — first

#### Step 1.1 — the base
- Behaviours: `a.b.one`
- Tests: t/test_one.py
- Size: S

#### Step 1.2 — on top (#8, #10)
- Behaviours: `a.b.two`
- Tests: t/test_two.py
- Depends on: 1.1
- Size: S
"""
ISSUES = [{"number": 7, "title": "m1 Step 1.1: the base", "body": ""},
          {"number": 8, "title": "on top", "body": "Step: 1.2\nmore"},
          {"number": 9, "title": "a stray bug", "body": "no step here"}]


SHEBANG = "/usr/bin/env python3"  # not sys.executable: the M4 gate path has a space, which breaks a shebang

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


def test_enqueue_puts_each_step_brief_in_the_milestones_lane_in_build_order(tmp_path, monkeypatch):
    from fichero_builder import journal, queue

    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    (tmp_path / "spec.md").write_text(SPEC)
    (tmp_path / "harness.toml").write_text('[brief]\nrules = "Rule one."\n[jail]\nworkroot = "/wr"\n')
    gh = _fake_gh(tmp_path)
    assert cli.main(["milestone", "m1", "--spec", str(tmp_path / "spec.md"), "--repo-dir", str(tmp_path), "--out", str(tmp_path / "out"),
                     "--base", "abc1234", "--gh", gh, "--enqueue", "--state", str(tmp_path / "s")]) == 2
    lane = queue.load()[0]
    assert lane["id"] == "m1" and lane["worktree"] == "/wr/wt-m1" and lane["cursor"] == 0
    assert [(s["step"], s["issues"], s["waits"]) for s in lane["steps"]] == [("1.1", [7], []), ("1.2", [8], ["1.1"])]
    assert lane["steps"][1]["brief"].endswith("brief-step-1.2.txt")
    brief = (tmp_path / "out" / "brief-step-1.2.txt").read_text()
    assert "Branch lane-m1" in brief and "step-1.2" not in brief.split("\n")[0] and "abc1234" not in brief.split("\n")[0], \
        "a lane works on its own branch and each step starts from what the last one landed"


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


def _repo(tmp_path):
    import subprocess

    repo = tmp_path / "repo"
    (repo / "pkg" / "readers").mkdir(parents=True)
    (repo / "docs").mkdir()
    (repo / "pkg" / "readers" / "runner.py").write_text("def run_enhancement():\n    pass\n\nclass Other:\n    pass\n")
    (repo / "pkg" / "other.py").write_text("nothing here\n")
    (repo / "docs" / "spec.md").write_text(SPEC.replace("## Build order", "## The design\n\nNew modules live under `pkg/readers/` beside `pkg/readers/runner.py`.\n\n## Build order"))
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    return repo


def test_the_where_list_is_the_spec_the_designs_directory_and_the_files_found_by_the_steps_words_with_their_outlines(tmp_path):
    """Defect 3 made concrete: no index, so grep; the worker gets a map, each file with its outline, and reads less."""
    repo = _repo(tmp_path)
    where = milestone.where_map(repo / "docs" / "spec.md", "1.1", str(repo), "", [{"body": "Where: pkg/readers/runner.py"}])
    assert where == ["docs/spec.md (the spec)", "pkg/readers/ (the directory the spec's design names)",
                     "pkg/readers/runner.py: run_enhancement (1), Other (4)"]
    text = brief_tool.cluster([{"number": 7, "title": "t", "body": "b", "authorAssociation": "OWNER"}], repo=str(repo), branch="b", base="abc", where=where)
    assert "## Where to start (found by the tool; your code tools find the rest)\n- docs/spec.md (the spec)\n" in text


def test_the_where_list_uses_the_code_map_when_the_repo_is_indexed_and_drops_what_the_tree_lacks(tmp_path):
    repo = _repo(tmp_path)
    (repo / "tests_here").mkdir()
    (repo / "tests_here" / "test_x.py").write_text("def test_x(): pass\n")
    server = tmp_path / "server"
    server.write_text(f"""#!{SHEBANG}
import json, sys
for line in sys.stdin:
    m = json.loads(line)
    if "id" not in m:
        continue
    if m["method"] == "initialize":
        result = {{}}
    else:
        name, args = m["params"]["name"], m["params"]["arguments"]
        data = {{"resolve_repo": {{"indexed": True, "repo": "r"}},
                "get_file_outline": {{"results": [{{"file": "pkg/other.py", "symbols": [{{"name": "helper", "line": 3}}]}},
                                                  {{"file": "pkg/readers/runner.py", "symbols": [{{"name": "run_enhancement", "line": 1}}]}},
                                                  {{"file": "tests_here/test_x.py", "symbols": [{{"name": "test_x", "line": 1}}]}},
                                                  {{"file": "docs/spec.md", "symbols": []}}]}}}}[name]
        result = {{"content": [{{"type": "text", "text": json.dumps(data)}}]}}
    print(json.dumps({{"jsonrpc": "2.0", "id": m["id"], "result": result}}), flush=True)
""")
    server.chmod(0o755)
    issues = [{"body": "Where: pkg/other.py, gone/stale.py\nTests: tests_here/test_x.py, pkg/readers/runner.py"}]
    where = milestone.where_map(repo / "docs" / "spec.md", "1.1", str(repo), str(server), issues)
    assert where[2:] == ["pkg/other.py: helper (3)", "tests_here/test_x.py: test_x (1)", "pkg/readers/runner.py: run_enhancement (1)"], \
        "the outlines come from the code map, in the order named; a named file the tree lacks is dropped"


def test_a_server_that_fails_or_finds_nothing_falls_back_to_grep(tmp_path):
    from fichero_builder import codemap

    repo = _repo(tmp_path)
    bad = tmp_path / "bad"
    bad.write_text("#!/bin/sh\nexit 3\n")
    bad.chmod(0o755)
    assert codemap.outlines(str(bad), str(repo), ["pkg/readers/runner.py"]) is None
    assert codemap.outlines(str(tmp_path / "nowhere"), str(repo), ["pkg/readers/runner.py"]) is None
    assert "pkg/readers/runner.py: run_enhancement (1), Other (4)" in milestone.where_map(
        repo / "docs" / "spec.md", "1.1", str(repo), str(bad), [{"body": "Where: pkg/readers/runner.py"}]), "the outline read by regex instead"


def test_a_step_heading_that_names_an_issue_places_it(tmp_path):
    (tmp_path / "spec.md").write_text(SPEC)
    steps = milestone.build_order(tmp_path / "spec.md")
    p = milestone.plan([{"number": 10, "title": "no step in the title", "body": "none in the body either"}], steps, "m1")
    assert [c["step"] for c in p["clusters"]] == ["1.2"] and not p["questions"]


def test_a_repo_dir_that_is_not_a_checkout_refuses_with_a_row_not_a_traceback(tmp_path, capsys):
    """Real use 2026-11-02: --repo-dir without a harness.toml raised FileNotFoundError."""
    from fichero_builder import journal

    (tmp_path / "spec.md").write_text(SPEC)
    rc = cli.main(["milestone", "m1", "--spec", str(tmp_path / "spec.md"), "--repo-dir", str(tmp_path / "nowhere"), "--out", str(tmp_path / "out"),
                   "--base", "abc1234", "--gh", _fake_gh(tmp_path), "--state", str(tmp_path / "s")])
    assert rc == 1 and "REFUSED" in capsys.readouterr().out
    journal.STATE = tmp_path / "s"
    assert [r for r in journal.read() if r["event"] == "milestone" and r.get("refused") == "rules"]


def test_the_where_list_names_only_what_the_step_its_behaviours_and_its_issues_name_plus_importers(tmp_path):
    """Real use 2026-11-02: image-enhancement Step 1.1's map listed LICENSE, agent-work/ drafts, openapi.json and harness
    modules found by the step's words. Now: the files the step's section, its behaviour lines and the issues' Where/Test lines
    name, plus the Python files importing them; never agent-work/ or LICENSE."""
    repo = _repo(tmp_path)
    (repo / "t").mkdir()
    (repo / "t" / "test_one.py").write_text("from pkg.readers import runner\n\ndef test_one():\n    pass\n")
    (repo / "pkg" / "uses.py").write_text("from pkg.readers.runner import run_enhancement\n")
    (repo / "pkg" / "named_by_issue.py").write_text("def where():\n    pass\n")
    (repo / "agent-work").mkdir()
    (repo / "agent-work" / "draft.py").write_text("from pkg.readers import runner\n")
    (repo / "LICENSE").write_text("MIT\n")
    (repo / "pkg" / "enhancement_noise.py").write_text("ENHANCEMENT = 1\n")  # the step's word, named by nothing
    spec = (repo / "docs" / "spec.md")
    spec.write_text(spec.read_text() + "\n## Behaviours\n\n- `a.b.one` [GAP] — the base. Test: `pkg/readers/runner.py`, LICENSE\n")
    import subprocess
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    issues = [{"number": 7, "body": "Where: pkg/named_by_issue.py and agent-work/draft.py\nOther prose naming pkg/other.py\nTest: t/test_new.py"}]
    where = milestone.where_map(spec, "1.1", str(repo), "", issues)
    files = [w.split(":")[0] for w in where[1:] if " (the directory" not in w and " goes;" not in w]
    assert where[0] == "docs/spec.md (the spec)"
    assert set(files) == {"t/test_one.py", "pkg/readers/runner.py", "pkg/named_by_issue.py", "pkg/uses.py"}, files
    assert "pkg/readers/runner.py: run_enhancement (1), Other (4)" in where, "each file with its outline"
    assert "t/ (where t/test_new.py goes; it does not exist yet)" in where, "a test the step writes: its directory"
    assert not any("agent-work" in w or "LICENSE" in w or "enhancement_noise" in w or "pkg/other.py" in w for w in where)


def test_the_queue_takes_the_first_ordered_milestone_no_lane_holds_with_its_step_briefs(tmp_path, monkeypatch):
    """The real feed of `builder queue run`: build-order.md's `## In order`, skipping held milestones and lines with no spec."""
    from fichero_builder import journal, queue

    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    specs = tmp_path / "docs" / "contributor_manual" / "specs" / "h"
    specs.mkdir(parents=True)
    (specs / "m1.md").write_text(SPEC)
    (tmp_path / "harness.toml").write_text('[jail]\nworkroot = "/wr"\n[brief]\nrules = "Rule one."\n')
    (specs.parent / "build-order.md").write_text("## In order\n\n1. `m0` — held. Spec: h/m1.md\n2. `no-spec` — none.\n3. `m1` — next. Spec: h/m1.md\n")
    gh = _fake_gh(tmp_path)
    lane, worktree, steps = queue.next_in_order(tmp_path, {"m0"}, gh=gh)
    assert (lane, worktree) == ("m1", "/wr/wt-m1")
    assert [(s["step"], s["issues"], s["waits"]) for s in steps] == [("1.1", [7], []), ("1.2", [8], ["1.1"])]
    assert all(Path(s["brief"]).is_file() and "Rule one." in Path(s["brief"]).read_text() for s in steps)
    assert queue.next_in_order(tmp_path, {"m0", "m1"}, gh=gh) is None, "the order is done"


def test_list_issues_runs_gh_in_the_repo_so_a_launchd_cwd_still_resolves_the_remote(tmp_path, monkeypatch):
    """#6497: the console's LaunchAgent runs in the state dir, where gh says 'not a git repository'; gh runs in the repo given."""
    seen = {}
    monkeypatch.setattr(milestone.subprocess, "run", lambda argv, **k: seen.update(k) or type("R", (), {"returncode": 0, "stdout": "[]", "stderr": ""})())
    assert milestone.list_issues("m1", gh="gh", cwd=str(tmp_path)) == [] and seen["cwd"] == str(tmp_path)
