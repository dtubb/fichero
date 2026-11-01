"""dev-workflows.tool.triage: `builder triage` changes the repo's GitHub metadata directly, one journal row and one readable
`gh` call per change; a fake gh records every call."""
from __future__ import annotations

import json
import sys

import pytest

from fichero_builder import __main__ as cli
from fichero_builder import journal

FAKE_GH = """#!{py}
import json, sys
from pathlib import Path
state = Path({state!r})
db = json.loads(state.read_text())
argv = sys.argv[1:]
db["calls"].append(argv)
def opt(name):
    return argv[argv.index(name) + 1] if name in argv else None
if argv[:2] == ["label", "list"]:
    print(json.dumps([{{"name": x}} for x in db["labels"]]))
elif argv[:2] == ["label", "create"]:
    db["labels"].append(argv[2])
elif argv[:2] == ["label", "delete"]:
    db["labels"].remove(argv[2])
    for i in db["issues"]:
        i["labels"] = [l for l in i["labels"] if l != argv[2]]
elif argv[:2] == ["issue", "list"]:
    rows = db["issues"]
    if opt("--label"):
        rows = [i for i in rows if opt("--label") in i["labels"]]
    if opt("--state") == "open":
        rows = [i for i in rows if i["state"] == "open"]
    print(json.dumps([{{"number": i["number"], "title": i["title"], "state": i["state"].upper(), "labels": [{{"name": l}} for l in i["labels"]],
                        "milestone": {{"title": i["milestone"]}} if i.get("milestone") else None}} for i in rows]))
elif argv[:2] == ["issue", "edit"]:
    for i in db["issues"]:
        if str(i["number"]) == argv[2]:
            if opt("--add-label"): i["labels"] = sorted(set(i["labels"]) | set(opt("--add-label").split(",")))
            if opt("--milestone"): i["milestone"] = opt("--milestone")
elif argv[:2] == ["issue", "create"]:
    n = 100 + len(db["issues"])
    db["issues"].append({{"number": n, "title": opt("--title"), "state": "open", "labels": (opt("--label") or "").split(","), "milestone": opt("--milestone")}})
    print("https://github.com/o/r/issues/%d" % n)
elif argv[0] == "api" and "milestones?" in argv[1]:
    print(json.dumps([{{"number": k, "title": t, "open_issues": sum(1 for i in db["issues"] if i["state"] == "open" and i.get("milestone") == t)}} for k, t in enumerate(db["milestones"], 1)]))
elif argv[0] == "api" and opt("-X") == "POST":
    db["milestones"].append(opt("-f").split("=", 1)[1])
elif argv[0] == "api" and opt("-X") == "PATCH":
    db["closed"].append(db["milestones"][int(argv[argv.index("-X") + 2].rsplit("/", 1)[1]) - 1])
else:
    sys.exit("unexpected: " + " ".join(argv))
state.write_text(json.dumps(db))
"""

RULES = '''[check]
engine_repo = "/e"
[triage.labels]
sharing = "spec:sharing-two-macs"
performance = "type:bug"
needs-design = "needs-spec"
'''


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    root = tmp_path / "root"
    specs = root / "docs" / "contributor_manual" / "specs" / "x"
    specs.mkdir(parents=True)
    (root / "harness.toml").write_text(RULES)
    (specs / "sharing-two-macs.md").write_text("# Sharing\n> Milestone: sharing\n- `a.b` [GAP] (#7) — x\n")
    (specs / "cataloguing.md").write_text("# Cat\n> Milestone: cat\n- `c.d` [GAP] (#8, #9) — y\n")
    (root / "docs" / "contributor_manual" / "specs" / "_TEMPLATE.md").write_text("template, never a spec")
    state = tmp_path / "gh.json"
    state.write_text(json.dumps({"labels": ["spec:sharing-two-macs", "spec:gone-spec", "sharing", "performance", "phase:R1", "type:bug", "needs-spec"],
                                 "issues": [{"number": 7, "title": "a", "state": "open", "labels": ["sharing", "phase:R1"]},
                                            {"number": 8, "title": "b", "state": "open", "labels": ["performance"]},
                                            {"number": 9, "title": "c", "state": "closed", "labels": ["spec:gone-spec"]},
                                            {"number": 10, "title": "d", "state": "open", "labels": [], "milestone": "orphan-ms"},
                                            {"number": 11, "title": "e", "state": "open", "labels": ["type:bug"]},
                                            {"number": 12, "title": "f", "state": "open", "labels": ["spec:cataloguing"], "milestone": "Bugs - old"}],
                                 "milestones": ["sharing", "Bugs - old", "Empty one", "orphan-ms"], "closed": [], "calls": []}))
    (specs / "no-line.md").write_text("# No line\n\n- `n.o` [GAP] (#12) — z\n")
    (specs / "prose-line.md").write_text("# Prose\n> Milestone: sharing. Companion to `x.md` (the other half)\n")
    gh = tmp_path / "gh"
    gh.write_text(FAKE_GH.format(py=sys.executable, state=str(state)))
    gh.chmod(0o755)

    def run(*extra):
        return cli.main(["triage", *extra, "--root", str(root), "--gh", str(gh), "--state", str(tmp_path / "s")])
    run.db = lambda: json.loads(state.read_text())
    run.root = root
    return run


def test_labels_are_consolidated_by_the_rules_table_and_the_mapping_is_printed(world, capsys):
    assert world("--labels") == 0
    d = world.db()
    assert set(d["labels"]) == {"spec:sharing-two-macs", "spec:cataloguing", "spec:no-line", "spec:prose-line", "type:bug", "needs-spec"}, "spec labels follow the files; the rest is gone"
    by = {i["number"]: i["labels"] for i in d["issues"]}
    assert by[7] == ["spec:sharing-two-macs"] and by[8] == ["type:bug"] and by[9] == [] and by[10] == []
    out = capsys.readouterr().out
    assert "sharing -> spec:sharing-two-macs" in out and "phase:R1 -> (nothing)" in out and "performance -> type:bug" in out
    rows = [r for r in journal.read() if r["event"] == "triage"]
    assert {(r["what"], r["label"]) for r in rows} >= {("label-create", "spec:cataloguing"), ("label-delete", "spec:gone-spec"), ("label-delete", "phase:R1"), ("relabel", "spec:sharing-two-macs")}
    creates = [k for k, c in enumerate(d["calls"]) if c[:2] == ["label", "create"]]
    calls = d["calls"]
    for old, new in (("sharing", "spec:sharing-two-macs"), ("performance", "type:bug")):
        move = next(k for k, c in enumerate(calls) if c[:2] == ["issue", "edit"] and c[-1] == new)
        delete = next(k for k, c in enumerate(calls) if c[:2] == ["label", "delete"] and c[2] == old)
        assert move < delete, "an issue is relabelled before its old label is deleted"
    assert creates


def test_dry_changes_nothing_and_prints_the_counts(world, capsys):
    before = world.db()
    assert world("--labels", "--dry") == 0
    after = world.db()
    assert after["labels"] == before["labels"] and after["issues"] == before["issues"]
    assert all(c[:2] in (["label", "list"], ["issue", "list"]) for c in after["calls"]), "reads only"
    assert "labels deleted: 4" in capsys.readouterr().out
    assert all(r.get("dry") for r in journal.read() if r["event"] == "triage")


def test_the_spec_label_comes_from_the_spec_that_cites_the_issue_else_needs_spec(world):
    assert world("--specs") == 0
    by = {i["number"]: i["labels"] for i in world.db()["issues"]}
    assert "spec:sharing-two-macs" in by[7] and "spec:cataloguing" in by[8] and "needs-spec" in by[10]
    assert by[9] == ["spec:gone-spec"], "a closed issue is left alone"


def test_milestones_follow_the_spec_and_empty_ones_close_and_a_spec_less_one_gets_a_write_the_spec_issue(world, capsys):
    """Rules 3 and 4."""
    assert world("--labels", "--specs", "--milestones") == 0
    d = world.db()
    by = {i["number"]: i for i in d["issues"]}
    assert by[7]["milestone"] == "sharing", "the spec's milestone"
    assert by[12]["milestone"] == "cat" and "cat" in d["milestones"], "moved to the spec's milestone, created on the repo first"
    assert by[11]["milestone"] == "Next release", "a bug with no spec goes to Next release"
    assert by[10]["milestone"] == "orphan-ms", "no spec, not a bug: stays where it is, keeps needs-spec for the owner"
    assert set(d["closed"]) == {"Empty one", "Bugs - old"}, "empty after the moves; sharing and orphan-ms have open issues"
    filed = [i for i in d["issues"] if i["title"] == "spec: write orphan-ms spec"]
    assert len(filed) == 1 and filed[0]["labels"] == ["needs-spec"] and filed[0]["milestone"] == "orphan-ms"
    assert world("--labels", "--specs", "--milestones") == 0
    assert sum(1 for i in world.db()["issues"] if i["title"] == "spec: write orphan-ms spec") == 1, "idempotent"
    assert set(world.db()["milestones"]) == {"sharing", "Bugs - old", "Empty one", "orphan-ms", "cat", "Next release"}, \
        "the prose after the title on prose-line.md made no milestone"
    assert "> Milestone: Bugs - old" in (world.root / "docs" / "contributor_manual" / "specs" / "x" / "no-line.md").read_text(), \
        "a spec with no line gets the milestone most of its cited issues carry (#12 was in Bugs - old)"
    assert [r for r in journal.read() if r["event"] == "triage" and r["what"] == "spec-milestone-line"]
