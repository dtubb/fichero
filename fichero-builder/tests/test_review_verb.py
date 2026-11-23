"""local.review.*: a review is a step kind. Every test runs on a scratch repo, a scratch state dir and a fake `gh`;
none reads the real git config, the real journal or the real issues."""
from __future__ import annotations

import json
import os
import sys

import subprocess
from pathlib import Path

import pytest

from fichero_builder import review

REPORT = """# Review: widgets

## 1. What exists
The widget store.

## 2. Measured
Ran the tests: 12 passed.

## 3. What is broken
Slow.

## 4. Ranked fixes (each one builder step)

1. **Fast lookup** [1.1]. Index the key. NEW-1. Tests: `test_a.py`.
2. **Honest age** [1.2]. NEW-2 and the existing #42.
3. **Search folds accents** [2.1]. NEW-S1.

## 5. Issues to file

- NEW-1 Lookups scan every row: index the key (`widgets.lookup.indexed`, `widgets.lookup.cheap`).
- NEW-2 A figure says its age (`widgets.age.said`).
- NEW-S1 Search folds accents (`widgets.search.folds`).

## 6. Open questions for the owner

1. Is a day too old?
2. Which unit?

## 7. Existing issues that gained evidence

- #42 the same scan takes 9 s at 5,000 rows.
"""


def test_a_whole_report_passes_and_reads_back():
    assert review.check(REPORT) == []
    p = review.parse(REPORT)
    assert [i["key"] for i in p["issues"]] == ["1", "2", "S1"]
    assert p["issues"][0]["behaviours"] == ["widgets.lookup.indexed", "widgets.lookup.cheap"]
    assert [(f["step"], f["new"], f["old"]) for f in p["fixes"]] == [("1.1", ["1"], []), ("1.2", ["2"], [42]), ("2.1", ["S1"], [])]
    assert len(p["questions"]) == 2 and p["evidence"][0][0] == 42


@pytest.mark.parametrize("cut,needle", [
    ("## 1. What exists\nThe widget store.\n", "What exists"),
    ("## 5. Issues to file", "Issues to file"),
    ("## 2. Measured\nRan the tests: 12 passed.\n", "Measured"),
    ("## 6. Open questions for the owner", "Open questions"),
])
def test_a_report_missing_a_section_is_refused_by_its_name(cut, needle):
    text = REPORT.replace(cut, "") if cut.count("\n") > 1 or not cut.startswith("## 5") and not cut.startswith("## 6") else REPORT.replace(cut, "## Something else")
    assert any(needle in b and "missing" in b for b in review.check(text)), review.check(text)


def test_an_empty_issue_list_a_gap_and_a_fix_with_no_issue_are_refused():
    empty = REPORT.replace("- NEW-1 Lookups", "Lookups").replace("- NEW-2", "A").replace("- NEW-S1", "S")
    assert any("Issues to file list has no" in b for b in review.check(empty))
    gap = REPORT.replace("- NEW-2 A figure", "- NEW-3 A figure").replace("NEW-2 and", "NEW-3 and")
    assert any("1..2" in b or "[1, 3]" in b for b in review.check(gap))
    nofix = REPORT.replace("NEW-S1.", "(no issue).")
    assert review.check(nofix) == ["ranked fix 3 cites no issue (`NEW-n` or `#N`)"]
    ghost = REPORT.replace("NEW-1. Tests", "NEW-1 and NEW-9. Tests")
    assert review.check(ghost) == ["ranked fix 1 cites NEW-9, which the Issues list does not have"]


def test_questions_may_say_none_but_not_be_empty():
    none = REPORT.replace("1. Is a day too old?\n2. Which unit?", "None.")
    assert review.check(none) == [] and review.parse(none)["questions"] == []
    blank = REPORT.replace("1. Is a day too old?\n2. Which unit?\n", "")
    assert any("Open questions" in b for b in review.check(blank))


def _scratch_repo(tmp_path, monkeypatch):
    """A scratch repo with a harness.toml, its own git config and HOME: nothing real is read."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig"))
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", os.devnull)
    (tmp_path / "home").mkdir()
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "harness.toml").write_text(f'[land]\nbranch = "integration"\n[jail]\nworkroot = "{tmp_path / "work"}"\n')
    return repo


def test_check_verb_reads_the_report_in_the_review_worktree_and_exits_1_on_a_fault(tmp_path, monkeypatch, capsys):
    from fichero_builder import __main__ as cli

    repo = _scratch_repo(tmp_path, monkeypatch)
    wt = tmp_path / "work" / "wt-review-widgets"
    wt.mkdir(parents=True)
    (wt / "review-widgets.md").write_text(REPORT)
    assert cli.main(["review", "check", "widgets", "--repo-dir", str(repo)]) == 0 and "ok" in capsys.readouterr().out
    (wt / "review-widgets.md").write_text(REPORT.replace("## 5. Issues to file", "## 5. Notes"))
    assert cli.main(["review", "check", "widgets", "--repo-dir", str(repo)]) == 1
    assert "missing the `## Issues to file` section" in capsys.readouterr().out


def _git(repo, *a):
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=T", "-c", "user.email=t@example.invalid", *a], capture_output=True, text=True, check=True).stdout.strip()


def _git_repo(tmp_path, monkeypatch):
    repo = _scratch_repo(tmp_path, monkeypatch)
    _git(repo, "init", "-q", "-b", "main")
    (repo / "a.txt").write_text("a")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "first")
    _git(repo, "update-ref", "refs/remotes/origin/integration", "HEAD")
    return repo


def test_start_makes_the_worktree_and_branch_excludes_the_report_and_queues_one_step(tmp_path, monkeypatch, capsys):
    from fichero_builder import __main__ as cli
    from fichero_builder import journal, queue

    repo = _git_repo(tmp_path, monkeypatch)
    monkeypatch.setattr(journal, "STATE", tmp_path / "state")
    assert cli.main(["review", "start", "widgets", "--repo-dir", str(repo), "--scope", "the widget store", "--state", str(tmp_path / "state")]) == 0
    wt = tmp_path / "work" / "wt-review-widgets"
    assert _git(wt, "rev-parse", "--abbrev-ref", "HEAD") == "review-widgets"
    assert _git(wt, "rev-parse", "HEAD") == _git(repo, "rev-parse", "origin/integration")
    (wt / "review-widgets.md").write_text("report")
    assert _git(wt, "status", "--short") == "", "the report is excluded from commits"
    lane = queue.load()[0]
    assert lane["id"] == "review-widgets" and lane["worktree"] == str(wt) and [(s["step"], s["issues"]) for s in lane["steps"]] == [("review", [])]
    brief = Path(lane["steps"][0]["brief"]).read_text()
    assert "Scope: the widget store" in brief and "review-widgets.md" in brief and "Ranked fixes" in brief
    assert "/Users/" not in brief.split("# Review", 1)[1].split("COMMON RULES")[1], "the rules text names no home path"
    assert cli.main(["review", "start", "widgets", "--repo-dir", str(repo), "--state", str(tmp_path / "state")]) == 1
    assert "was started" in capsys.readouterr().out
    assert cli.main(["review", "start", "Bad Area", "--repo-dir", str(repo), "--state", str(tmp_path / "state")]) == 1
    assert cli.main(["review", "start", "other", "--repo-dir", str(repo), "--base", "nope", "--state", str(tmp_path / "state")]) == 1
    assert "not a commit" in capsys.readouterr().out


SPEC = """# Widgets

> Milestone: widgets

## Behaviours

- `widgets.lookup.indexed` [GAP] (→ #NEW-1) — index the key.
- `widgets.lookup.cheap` [GAP] → #NEW-1
- `widgets.age.said` [GAP] → #NEW
  a figure says its age.
- `widgets.search.folds` [GAP] (→ #NEW-S1) — fold accents.

Legend: a bare `#NEW` in prose is legend text, and `→ #NEW-S` too.

## Build order

### Stage 1 — all

#### Step 1.1 — Fast lookup
- Behaviours: `widgets.lookup.indexed`, `widgets.lookup.cheap`
- Tests: tests/test_a.py
- Size: S

#### Step 1.2 — Honest age (#9)
- Behaviours: `widgets.age.said`
- Tests: tests/test_b.py
- Size: S

#### Step 2.1 — Folds
- Behaviours: `widgets.search.folds`
- Tests: tests/test_c.py
- Size: S
"""
ORDER = """# Build order

## In order

1. `Builder` — the harness. Spec: harness/building-fichero-locally.md
2. `other` — another. Spec: x/other.md

## Parked

- `old` — parked.
"""
SPEC_REL = "docs/contributor_manual/specs/harness/widgets.md"


def _fake_gh(tmp_path):
    """Numbers issues from 7000 and records every call as one JSON line; the only issue client the tests use."""
    log = tmp_path / "gh-calls.jsonl"
    counter = tmp_path / "gh-counter"
    counter.write_text("7000")
    gh = tmp_path / "gh"
    gh.write_text(f"""#!{sys.executable}
import json, sys
a = sys.argv[1:]
open({str(log)!r}, "a").write(json.dumps(a) + "\\n")
if a[:2] == ["issue", "create"]:
    n = int(open({str(counter)!r}).read())
    open({str(counter)!r}, "w").write(str(n + 1))
    print(f"https://example.invalid/o/r/issues/{{n}}")
""")
    gh.chmod(0o755)
    return str(gh), log


def _calls(log):
    return [json.loads(x) for x in log.read_text().splitlines()] if log.exists() else []


def _started(tmp_path, monkeypatch, spec=SPEC, report=REPORT):
    from fichero_builder import __main__ as cli
    from fichero_builder import journal

    repo = _scratch_repo(tmp_path, monkeypatch)
    _git(repo, "init", "-q", "-b", "main")
    for rel, text in ((SPEC_REL, spec), ("docs/contributor_manual/specs/build-order.md", ORDER)):
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text)
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "first")
    _git(repo, "update-ref", "refs/remotes/origin/integration", "HEAD")
    monkeypatch.setattr(journal, "STATE", tmp_path / "state")
    assert cli.main(["review", "start", "widgets", "--repo-dir", str(repo), "--state", str(tmp_path / "state")]) == 0
    wt = tmp_path / "work" / "wt-review-widgets"
    (wt / "review-widgets.md").write_text(report)
    return repo, wt


def _approve(repo, tmp_path, gh, *extra):
    from fichero_builder import __main__ as cli

    return cli.main(["review", "approve", "widgets", "--repo-dir", str(repo), "--state", str(tmp_path / "state"), "--gh", gh,
                     "--milestone", "widgets", "--spec", SPEC_REL, "--desc", "the widget store", *extra])


def test_approve_files_the_issues_maps_every_tag_numbers_the_steps_and_commits_two_files(tmp_path, monkeypatch, capsys):
    repo, wt = _started(tmp_path, monkeypatch)
    gh, log = _fake_gh(tmp_path)
    base = _git(wt, "rev-parse", "HEAD")
    assert _approve(repo, tmp_path, gh, "--after", "Builder") == 0, capsys.readouterr().out
    created = [c for c in _calls(log) if c[:2] == ["issue", "create"]]
    assert len(created) == 3 and created[0][created[0].index("--title") + 1] == "[widgets] Lookups scan every row: index the key"
    assert created[0][created[0].index("--milestone") + 1] == "widgets"
    assert json.loads((tmp_path / "state" / "review-widgets-issues.json").read_text())["issues"] == {"1": 7000, "2": 7001, "S1": 7002}
    spec = (wt / SPEC_REL).read_text()
    assert "(→ #7000) — index" in spec and "`widgets.lookup.cheap` [GAP] → #7000" in spec and "[GAP] → #7001\n" in spec, "a bare tag is mapped by behaviour id"
    assert "(→ #7002)" in spec and "`#NEW`" in spec and "`→ #NEW-S`" in spec, "the legend lines stay"
    assert "#### Step 1.1 — Fast lookup (#7000)" in spec and "#### Step 1.2 — Honest age (#9, #7001, #42)" in spec and "#### Step 2.1 — Folds (#7002)" in spec
    order = (wt / "docs/contributor_manual/specs/build-order.md").read_text()
    assert order.index("`Builder`") < order.index("2. `widgets` — the widget store. Spec: harness/widgets.md") < order.index("3. `other`") and "## Parked\n\n- `old`" in order
    assert [c for c in _calls(log) if c[:2] == ["issue", "comment"]][0][2] == "42", "an existing issue that gained evidence is commented"
    assert _git(wt, "diff", "--name-only", base, "HEAD").split() == ["docs/contributor_manual/specs/build-order.md", SPEC_REL]
    body = _git(wt, "log", "-1", "--format=%B")
    assert body.rstrip().endswith("Written-By: Claude Opus 5.5 using Claude Code using Fichero Builder") and "Spec-change: owner 2026-11-21 a review incorporates itself" in body
    assert (tmp_path / "state" / "review-widgets-issue-list.txt").read_text().splitlines()[0] == "#7000 [widgets] Lookups scan every row: index the key"


def test_a_second_approve_files_nothing_new_and_adds_no_commit(tmp_path, monkeypatch):
    repo, wt = _started(tmp_path, monkeypatch)
    gh, log = _fake_gh(tmp_path)
    assert _approve(repo, tmp_path, gh) == 0
    head, n = _git(wt, "rev-parse", "HEAD"), len(_calls(log))
    assert _approve(repo, tmp_path, gh) == 0
    assert _git(wt, "rev-parse", "HEAD") == head and len(_calls(log)) == n, "no issue, no comment, no commit twice"


def test_an_unmappable_bare_tag_or_a_fix_with_no_step_refuses_before_anything_is_filed(tmp_path, monkeypatch, capsys):
    gh, log = _fake_gh(tmp_path)
    repo, wt = _started(tmp_path, monkeypatch, spec=SPEC.replace("`widgets.age.said` [GAP] → #NEW", "`widgets.other` [GAP] → #NEW"))
    assert _approve(repo, tmp_path, gh) == 1
    assert "a bare #NEW on `widgets.other`, which no issue names" in capsys.readouterr().out and _calls(log) == []
    (wt / "review-widgets.md").write_text(REPORT.replace("[2.1]", "[3.1]").replace("**Honest age** [1.2]", "**Honest age**"))
    (wt / SPEC_REL).write_text(SPEC)
    assert _approve(repo, tmp_path, gh) == 1
    out = capsys.readouterr().out
    assert "ranked fix 2 cites no spec step" in out and "Step 3.1, which the spec's Build order lacks" in out and "Step 2.1 has no ranked fix" in out
    assert _calls(log) == []


def test_each_owner_question_is_one_alert_once_and_ask_owner_comments_on_the_first_issue(tmp_path, monkeypatch):
    from fichero_builder import journal, queue

    repo, wt = _started(tmp_path, monkeypatch)
    gh, log = _fake_gh(tmp_path)
    assert _approve(repo, tmp_path, gh) == 0 and _approve(repo, tmp_path, gh) == 0
    alerts = [r for r in journal.read() if r.get("event") == "alert"]
    assert [(r["lane"], r["step"], r["actions"], r["issues"]) for r in alerts] == [
        ("review-widgets", "question-1", ["ask-owner", "park"], [7000]), ("review-widgets", "question-2", ["ask-owner", "park"], [7000])], "once each, not twice"
    assert "Is a day too old?" in alerts[0]["what"]
    rc, msg = queue.answer(alerts[0]["id"], "ask-owner", gh=gh, cwd=str(repo))
    assert rc == 0, msg
    asked = [c for c in _calls(log) if c[:3] == ["issue", "edit", "7000"] or c[:3] == ["issue", "comment", "7000"]]
    assert [c[1] for c in asked] == ["edit", "comment"] and "needs-your-decision" in asked[0] and "Is a day too old?" in asked[1][-1]
    assert queue.answer(alerts[1]["id"], "park", gh=gh)[0] == 0
