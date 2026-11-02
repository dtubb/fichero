"""dev-workflows.tool.triage: `builder triage` changes the repo's GitHub metadata directly, one journal row and one readable
`gh` call per change; a fake gh records every call. The rules are the issues-and-labels spec's: the milestone is the spec,
the label set is closed, needs-spec only inside a spec milestone, the build-order file is read never written."""
from __future__ import annotations

import json
import sys

import pytest

from fichero_builder import __main__ as cli
from fichero_builder import journal, triage

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
    if opt("--milestone"):
        rows = [i for i in rows if i.get("milestone") == opt("--milestone")]
    if opt("--state") == "open":
        rows = [i for i in rows if i["state"] == "open"]
    print(json.dumps([{{"number": i["number"], "title": i["title"], "state": i["state"].upper(), "labels": [{{"name": l}} for l in i["labels"]],
                        "assignees": [{{"login": a}} for a in i.get("assignees", [])],
                        "milestone": {{"title": i["milestone"]}} if i.get("milestone") else None}} for i in rows]))
elif argv[:2] == ["issue", "edit"]:
    for i in db["issues"]:
        if str(i["number"]) == argv[2]:
            if opt("--add-label"): i["labels"] = sorted(set(i["labels"]) | set(opt("--add-label").split(",")))
            if opt("--remove-label"): i["labels"] = [l for l in i["labels"] if l not in opt("--remove-label").split(",")]
            if opt("--milestone"): i["milestone"] = opt("--milestone")
            if opt("--add-assignee"): i["assignees"] = sorted(set(i.get("assignees", [])) | {{opt("--add-assignee")}})
            if opt("--remove-assignee"): i["assignees"] = [a for a in i.get("assignees", []) if a not in opt("--remove-assignee").split(",")]
elif argv[:2] == ["issue", "create"]:
    n = 100 + len(db["issues"])
    db["issues"].append({{"number": n, "title": opt("--title"), "state": "open", "labels": (opt("--label") or "").split(","), "milestone": opt("--milestone")}})
    print("https://github.com/o/r/issues/%d" % n)
elif argv[:2] == ["api", "user"]:
    print("owner-login")
elif argv[0] == "api" and "milestones?" in argv[1]:
    rows = [{{"number": k, "title": t, "state": "closed" if t in db["closed"] else "open",
              "open_issues": sum(1 for i in db["issues"] if i["state"] == "open" and i.get("milestone") == t)}} for k, t in enumerate(db["milestones"], 1)]
    print(json.dumps([r for r in rows if "state=all" in argv[1] or r["state"] == "open"]))
elif argv[0] == "api" and opt("-X") == "POST":
    db["milestones"].append(opt("-f").split("=", 1)[1])
elif argv[0] == "api" and opt("-X") == "PATCH":
    title = db["milestones"][int(argv[argv.index("-X") + 2].rsplit("/", 1)[1]) - 1]
    if opt("-f") == "state=open":
        db["closed"].remove(title)
    else:
        db["closed"].append(title)
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

BUILD_ORDER = """# Build order

## In order

1. `cat` — the one lane. Spec: x/cataloguing.md
2. `sharing` — next. Spec: x/sharing-two-macs.md

## Parked

- `Next release` — a grab-bag.
"""


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
    state.write_text(json.dumps({"labels": ["spec:sharing-two-macs", "spec:gone-spec", "sharing", "performance", "phase:R1", "priority:P1", "type:bug", "needs-spec", "needs-your-test"],
                                 "issues": [{"number": 7, "title": "a", "state": "open", "labels": ["sharing", "phase:R1", "priority:P1"], "assignees": ["someone"]},
                                            {"number": 8, "title": "b", "state": "open", "labels": ["performance", "needs-spec"]},
                                            {"number": 9, "title": "c", "state": "closed", "labels": ["spec:gone-spec"]},
                                            {"number": 10, "title": "d", "state": "open", "labels": [], "milestone": "orphan-ms"},
                                            {"number": 11, "title": "e", "state": "open", "labels": ["type:bug"]},
                                            {"number": 12, "title": "f", "state": "open", "labels": ["spec:cataloguing"], "milestone": "Bugs - old"},
                                            {"number": 13, "title": "g", "state": "open", "labels": [], "milestone": "cat"},
                                            {"number": 14, "title": "h", "state": "open", "labels": [], "milestone": "Lint - Structural Debt - x"},
                                            {"number": 15, "title": "i", "state": "open", "labels": ["needs-your-test"], "assignees": ["someone", "owner-login"]}],
                                 "milestones": ["sharing", "Bugs - old", "Empty one", "orphan-ms", "cat", "Lint - Structural Debt - x"], "closed": [], "calls": []}))
    (specs / "no-line.md").write_text("# No line\n\n- `n.o` [GAP] (#12) — z\n")
    (specs / "prose-line.md").write_text("# Prose\n> Milestone: sharing. Companion to `x.md` (the other half)\n")
    gh = tmp_path / "gh"
    gh.write_text(FAKE_GH.format(py=sys.executable, state=str(state)))
    gh.chmod(0o755)

    def run(*extra):
        return cli.main(["triage", *extra, "--root", str(root), "--gh", str(gh), "--state", str(tmp_path / "s")])
    run.db = lambda: json.loads(state.read_text())
    run.root = root
    run.gh = str(gh)
    return run


def test_labels_are_the_closed_set_priority_and_phase_kept_spec_labels_never_created(world, capsys):
    """Rule 1 as ruled: the label set is the spec's table (priority:P0-P3 and phase:R0-R6 kept for now). A label outside it is
    reported, its issues get what the table maps it to, and it is never deleted: a delete on the public repo is not undone,
    and the spec says triage refuses an unknown label, not that it removes one. No spec label is created."""
    before = set(world.db()["labels"])
    assert world("--labels") == 0
    d = world.db()
    assert set(d["labels"]) == before, "nothing deleted, nothing created"
    by = {i["number"]: i["labels"] for i in d["issues"]}
    assert "spec:sharing-two-macs" in by[7] and "sharing" in by[7] and "type:bug" in by[8] and "performance" in by[8]
    out = capsys.readouterr().out
    assert "unknown label sharing -> spec:sharing-two-macs" in out and "unknown label performance -> type:bug" in out and "phase:R1" not in out
    calls = d["calls"]
    assert not any(c[:2] in (["label", "create"], ["label", "delete"]) for c in calls)
    rows = [r for r in journal.read() if r["event"] == "triage" and r["what"] == "label-unknown"]
    assert {r["label"] for r in rows} == {"sharing", "performance", "spec:gone-spec"}


def test_dry_changes_nothing_and_prints_the_counts(world, capsys):
    before = world.db()
    assert world("--labels", "--dry") == 0
    after = world.db()
    assert after["labels"] == before["labels"] and after["issues"] == before["issues"]
    assert all(c[:2] in (["label", "list"], ["issue", "list"]) for c in after["calls"]), "reads only"
    assert "labels unknown: 3" in capsys.readouterr().out
    assert all(r.get("dry") for r in journal.read() if r["event"] == "triage")


def test_needs_spec_only_inside_a_spec_milestone_and_only_when_no_spec_cites_the_issue(world):
    """Rule 2 as ruled: #13 sits in `cat` and no spec cites it -> needs-spec; #8 is cited by cataloguing.md -> its needs-spec
    goes; #14 (Lint bucket), #10 (orphan-ms is no spec's milestone), #11 (no milestone) are left alone."""
    assert world("--specs") == 0
    by = {i["number"]: i["labels"] for i in world.db()["issues"]}
    assert "needs-spec" in by[13] and "needs-spec" not in by[8]
    assert by[14] == [] and by[10] == [] and by[11] == ["type:bug"]
    assert not any(lb.startswith("spec:") for lb in by[13]), "no spec label is applied any more"


def test_milestones_follow_the_citing_spec_and_the_spec_label_goes_once_the_issue_sits_there(world, capsys):
    """Rules 3 and 4: the milestone comes from the spec that cites the issue, else from a spec:* label the table left as a
    hint; the label is removed once the issue is in the milestone; a spec-less bug to Next release; empty milestones close;
    a spec-less milestone (not an ops bucket or grab-bag) gets one write-the-spec issue."""
    assert world("--labels", "--specs", "--milestones") == 0
    d = world.db()
    by = {i["number"]: i for i in d["issues"]}
    assert by[7]["milestone"] == "sharing" and "spec:sharing-two-macs" not in by[7]["labels"], "cited by sharing-two-macs.md; the hint label is gone"
    assert by[12]["milestone"] == "cat" and "spec:cataloguing" not in by[12]["labels"], \
        "no-line.md takes no line from a bucket no spec names, so the spec:cataloguing hint places #12; the hint label is gone"
    assert by[8]["milestone"] == "cat" and "cat" in d["milestones"]
    assert by[11]["milestone"] == "Next release", "a bug with no spec goes to Next release"
    assert by[10]["milestone"] == "orphan-ms", "no spec, not a bug: stays where it is"
    assert set(d["closed"]) == {"Empty one", "Bugs - old"}, "only an empty milestone closes (Bugs - old emptied when #12 went to cat)"
    filed = [i for i in d["issues"] if i["title"].startswith("spec: write ")]
    assert [i["title"] for i in filed] == ["spec: write orphan-ms spec"], "no write-the-spec issue for a Lint bucket"
    assert "spec:sharing-two-macs" in d["labels"], "removed from the issue, never deleted from the repo"
    assert world("--labels", "--specs", "--milestones") == 0
    assert sum(1 for i in world.db()["issues"] if i["title"] == "spec: write orphan-ms spec") == 1, "idempotent"
    assert "> Milestone: Bugs - old" not in (world.root / "docs" / "contributor_manual" / "specs" / "x" / "no-line.md").read_text()
    assert not [r for r in journal.read() if r["event"] == "triage" and r["what"] == "spec-milestone-line" and r["milestone"] == "Bugs - old"]


def test_assignees_are_the_owner_on_needs_your_only(world):
    """Rule 6: the gh login is assigned on needs-your-decision / needs-your-test and nothing else; other assignees go."""
    assert world("--assignees") == 0
    by = {i["number"]: i.get("assignees", []) for i in world.db()["issues"]}
    assert by[15] == ["owner-login"] and by[7] == []
    rows = [r for r in journal.read() if r["event"] == "triage" and r["what"] == "assignee"]
    assert {(r["issue"], r["login"], r["set"]) for r in rows} == {(15, "someone", False), (7, "someone", False)}


def test_order_reads_the_build_order_file_and_proposes_a_diff_never_writes(world, capsys):
    """Rule 5: `--order` reads docs/contributor_manual/specs/build-order.md; an open milestone with open issues the file does
    not place is printed as a proposed line; the file is not changed; no file at all is said."""
    assert world("--order") == 0
    assert "no build-order file" in capsys.readouterr().out
    bo = world.root / "docs" / "contributor_manual" / "specs" / "build-order.md"
    bo.write_text(BUILD_ORDER)
    assert world("--order") == 0
    out = capsys.readouterr().out
    proposed = [ln for ln in out.splitlines() if ln.startswith("+ ")]
    assert any("`orphan-ms`" in ln for ln in proposed) and any("`Bugs - old`" in ln for ln in proposed)
    assert not any("`cat`" in ln or "`sharing`" in ln or "`Next release`" in ln for ln in proposed), "placed or parked: not proposed"
    assert bo.read_text() == BUILD_ORDER, "never written"
    assert all(c[:2] in (["api", "repos/{owner}/{repo}/milestones?state=open&per_page=100"],) for c in world.db()["calls"]), "reads only"


def test_first_open_milestone_comes_from_the_build_order_file(world):
    """`builder milestone` with no name: the first milestone under `## In order` that still has open issues, with its spec path."""
    bo = world.root / "docs" / "contributor_manual" / "specs" / "build-order.md"
    bo.write_text(BUILD_ORDER)
    assert triage.first_open(world.root, world.gh) == ("cat", world.root / "docs" / "contributor_manual" / "specs" / "x" / "cataloguing.md")
    db = world.db()
    for i in db["issues"]:
        if i.get("milestone") == "cat":
            i["state"] = "closed"
        if i["number"] == 7:
            i["milestone"] = "sharing"
    (world.root.parent / "gh.json").write_text(json.dumps(db))
    assert triage.first_open(world.root, world.gh)[0] == "sharing"
    bo.unlink()
    with pytest.raises(triage.Refused):
        triage.first_open(world.root, world.gh)


def test_a_milestone_parked_in_the_build_order_file_owes_no_spec_issue(world):
    (world.root / "docs" / "contributor_manual" / "specs" / "build-order.md").write_text("## In order\n\n## Parked\n\n- `orphan-ms` — later.\n")
    assert world("--milestones") == 0
    assert not any(i["title"].startswith("spec: write ") for i in world.db()["issues"])


def test_a_specs_empty_milestone_stays_open_and_a_closed_one_is_reopened_not_made_twice(world):
    """Review of range 2: an empty spec milestone was closed against the rule, and a later issue citing that spec then POSTed a
    duplicate title, which GitHub refuses, so a rerun stopped halfway."""
    db = world.db()
    for i in db["issues"]:
        if i["number"] == 13:
            i["state"] = "closed"
    db["issues"] = [i for i in db["issues"] if i["number"] not in (8, 9)]
    (world.root.parent / "gh.json").write_text(json.dumps(db))
    assert world("--milestones") == 0
    assert "cat" not in world.db()["closed"], "cataloguing.md names it, so it stays though nothing is open in it"
    db = world.db()
    db["closed"].append("sharing")
    for i in db["issues"]:
        if i["number"] == 7:
            i["milestone"] = None
    (world.root.parent / "gh.json").write_text(json.dumps(db))
    assert world("--milestones") == 0
    d = world.db()
    assert "sharing" not in d["closed"] and d["milestones"].count("sharing") == 1, "reopened, not created again"


def test_labels_creates_a_missing_kept_target_and_skips_a_missing_spec_hint(world):
    """Review of range 2: --add-label fails on a label that does not exist; triage still never creates a spec label."""
    db = world.db()
    db["labels"] = [x for x in db["labels"] if x not in ("type:bug", "spec:sharing-two-macs")]
    (world.root.parent / "gh.json").write_text(json.dumps(db))
    assert world("--labels") == 0
    calls = world.db()["calls"]
    made = next(k for k, c in enumerate(calls) if c[:3] == ["label", "create", "type:bug"])
    used = next(k for k, c in enumerate(calls) if c[:2] == ["issue", "edit"] and c[-1] == "type:bug")
    assert made < used
    assert not any(c[:3] == ["label", "create", "spec:sharing-two-macs"] or c[-1] == "spec:sharing-two-macs" for c in calls)


def test_order_does_not_propose_what_the_file_already_lists_under_then(world, capsys):
    bo = world.root / "docs" / "contributor_manual" / "specs" / "build-order.md"
    bo.write_text(BUILD_ORDER.replace("## Parked", "## Then\n\n- `orphan-ms` — unordered.\n\n## Parked"))
    assert world("--order") == 0
    proposed = [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("+ ")]
    assert not any("`orphan-ms`" in ln for ln in proposed) and any("`Bugs - old`" in ln for ln in proposed)


def test_an_issue_its_current_milestones_spec_cites_stays_put_though_another_spec_cites_it_too(world):
    """Precedence (lead ruling 2026-11-02): the dry run moved 58 recipe-designer issues to source-model only because a spec
    earlier by path also cited them. An issue stays where its current milestone's spec cites it; else the first citing spec."""
    specs = world.root / "docs" / "contributor_manual" / "specs" / "x"
    (specs / "aa-first.md").write_text("# First by path\n> Milestone: sharing\n- `e.f` [GAP] (#13, #10) — w\n")
    (specs / "cataloguing.md").write_text("# Cat\n> Milestone: cat\n- `c.d` [GAP] (#8, #9, #13, #10) — y\n")
    assert world("--milestones") == 0
    by = {i["number"]: i for i in world.db()["issues"]}
    assert by[13]["milestone"] == "cat", "cat's spec cites #13: it stays in cat"
    assert by[10]["milestone"] == "sharing", "orphan-ms has no citing spec: the first citing spec by path wins"


def test_a_parked_line_may_name_a_pattern_and_the_milestones_it_matches_owe_no_spec_and_are_not_proposed(world, capsys):
    """Ops buckets are parked by pattern (`UX - *`): fnmatch over the milestone title, for --milestones and --order alike."""
    bo = world.root / "docs" / "contributor_manual" / "specs" / "build-order.md"
    bo.write_text(BUILD_ORDER.replace("- `Next release` — a grab-bag.", "- `Next release` — a grab-bag.\n- `orphan-*`, `Bugs - *` — buckets."))
    assert world("--milestones") == 0
    assert not any(i["title"].startswith("spec: write ") for i in world.db()["issues"]), "orphan-ms matches `orphan-*`"
    capsys.readouterr()
    assert world("--order") == 0
    proposed = [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("+ ")]
    assert not any("`orphan-ms`" in ln or "`Bugs - old`" in ln for ln in proposed), "parked by pattern: not proposed"


def test_a_spec_line_is_written_only_for_a_milestone_whose_spec_names_the_file_or_the_files_stem(world, capsys):
    """Lead ruling 2026-11-02: the dry run guessed kg-interactions.md -> historical-text-normalization from its cited issues'
    milestones. A guess is written only when that milestone's own spec names the file, or it is the file's stem; build-notes
    files are notes: no line, and their citations place no issue."""
    specs = world.root / "docs" / "contributor_manual" / "specs" / "x"
    (specs / "no-line.md").write_text("# No line\n\n- `n.o` [GAP] (#12) — z\n")       # #12 sits in `Bugs - old`: no spec names it
    (specs / "guess-cat.md").write_text("# Guess\n\n- `g.c` [GAP] (#13) — c\n")       # #13 sits in `cat`, whose spec names this file
    (specs / "unnamed.md").write_text("# Unnamed\n\n- `u.n` [GAP] (#13) — c\n")        # also `cat`, but cataloguing.md does not name it
    (specs / "cataloguing.md").write_text("# Cat\n> Milestone: cat\n- `c.d` [GAP] (#8, #9) — y. Notes: guess-cat.md\n")
    (specs / "orphan-ms.md").write_text("# Its stem\n\n- `o.m` [GAP] (#10) — o\n")    # #10 sits in `orphan-ms`: the stem
    (specs / "build-notes-x.md").write_text("# Notes\n\n- `b.n` [GAP] (#11) — n\n")    # notes: no line, its citation moves nothing
    assert world("--milestones") == 0
    assert "> Milestone:" not in (specs / "no-line.md").read_text(), "a bucket no spec names is not written"
    assert "> Milestone: cat" in (specs / "guess-cat.md").read_text()
    assert "> Milestone:" not in (specs / "unnamed.md").read_text(), "a spec milestone whose spec does not name the file: not written"
    assert "> Milestone: orphan-ms" in (specs / "orphan-ms.md").read_text()
    assert "> Milestone:" not in (specs / "build-notes-x.md").read_text()
    assert {i["number"]: i for i in world.db()["issues"]}[11]["milestone"] == "Next release", "a notes file's citation places nothing"
    assert "no-line.md" in capsys.readouterr().out
