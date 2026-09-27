"""`check_docs_paths` must give the same verdict on every checkout of the same commit.

It asked the filesystem two questions that belong to the repository:

* which top-level names a path may start with (`ROOT.iterdir()`), so `build/...` citations
  were checked where something had been built and silently skipped everywhere else; and
* whether a gitignored path is present, so `fichero/fichero-api-client/.build` (named by
  AGENTS.md) passed in the main checkout, where Xcode had built it, and failed in every
  fresh worktree — which is how `test_docs_paths_exits_zero` went red on 2026-09-27 with
  nothing in the docs having changed.

A guard whose verdict depends on what was last built on this disk is measuring the disk.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest


_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "check_docs_paths.py"
sys.path.insert(0, str(_SCRIPT.parent))
_SPEC = importlib.util.spec_from_file_location("check_docs_paths_checkout", _SCRIPT)
assert _SPEC and _SPEC.loader
docs_paths = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = docs_paths
_SPEC.loader.exec_module(docs_paths)  # type: ignore[attr-defined]


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    (root / "docs").mkdir(parents=True)
    (root / "pkg").mkdir()
    (root / ".gitignore").write_text("build/\n.build/\n*.pyc\n")
    (root / "pkg" / "Package.swift").write_text("// tracked\n")
    (root / "docs" / "guide.md").write_text(
        "The gate writes `build/report.json`. Never edit `pkg/.build`. "
        "The manifest is `pkg/Package.swift`.\n"
    )
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    monkeypatch.setattr(docs_paths, "ROOT", root)
    monkeypatch.setattr(docs_paths, "ROOT_DOCS", [])
    return root


def test_gitignored_paths_are_reported_when_absent(repo):
    """A fresh worktree: nothing built. Both citations need an allowlist reason."""
    absent = docs_paths.missing()
    assert "build/report.json" in absent
    assert "pkg/.build" in absent


def test_gitignored_paths_are_still_reported_once_built(repo):
    """The same commit after a build must get the SAME verdict. Before the fix the
    main checkout passed on both of these and a fresh worktree failed."""
    (repo / "build").mkdir()
    (repo / "build" / "report.json").write_text("{}")
    (repo / "pkg" / ".build").mkdir()
    absent = docs_paths.missing()
    assert "build/report.json" in absent
    assert "pkg/.build" in absent


def test_a_tracked_path_that_exists_is_not_reported(repo):
    """Over-fire check: the normal case — a doc naming a committed file — stays quiet."""
    assert "pkg/Package.swift" not in docs_paths.missing()


def test_top_level_names_come_from_the_repository_not_the_disk(repo):
    """`build` is a top because .gitignore declares it, whether or not it is on disk;
    a stray untracked directory is not, so `scratch/x` in a doc is not a repo path."""
    (repo / "scratch").mkdir()
    tops = docs_paths.top_level()
    assert "build" in tops and "docs" in tops and "pkg" in tops
    assert "scratch" not in tops


def test_only_plain_gitignore_names_become_tops():
    text = "# comment\nbuild/\n!keep/\n*.pyc\nfoo/bar/\n.build/\n\nagent-work/\n"
    assert docs_paths.ignored_top_level_names(text) == {"build", ".build", "agent-work"}
