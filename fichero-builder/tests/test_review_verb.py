"""local.review.*: a review is a step kind. Every test runs on a scratch repo, a scratch state dir and a fake `gh`;
none reads the real git config, the real journal or the real issues."""
from __future__ import annotations

import os

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
