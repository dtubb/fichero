"""scripts/check_spec_acceptance.py (dev-workflows.run.presubmit-lints, lint 6): a behaviour's acceptance text changes only with a
`Spec-change:` trailer naming the ruling; its tag, issue numbers, test paths and appended notes are free. Offline: a scratch git repo."""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "check_spec_acceptance.py"
_SPEC = importlib.util.spec_from_file_location("check_spec_acceptance", _SCRIPT)
assert _SPEC and _SPEC.loader
_mod = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _mod
_SPEC.loader.exec_module(_mod)  # type: ignore[attr-defined]

SPECS = "/".join(["docs", "contributor_manual", "specs"])  # built, so the spec-citation guards do not read it as a citation
BASE = ("- `x.undo` [GAP] (#1; owner 2026-11-01: a cap change slipped past undo) — a cap change is undoable, one step back.\n"
        "- `x.other` [GAP] (#2) — another thing.\n")


def _git(root, *a):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-C", str(root), *a], check=True, capture_output=True, text=True).stdout


def _repo(tmp_path):
    (tmp_path / SPECS).mkdir(parents=True)
    (tmp_path / SPECS / "x.md").write_text(BASE)
    _git(tmp_path, "init", "-q", "-b", "main"), _git(tmp_path, "add", "."), _git(tmp_path, "commit", "-qm", "base")
    _git(tmp_path, "update-ref", "refs/remotes/origin/integration", "HEAD")
    return tmp_path


def _batch(root, text, msg="batch"):
    (root / SPECS / "x.md").write_text(text)
    _git(root, "commit", "-qam", msg)
    return _mod.check(root)


def test_a_tag_an_issue_test_paths_and_appended_notes_are_free(tmp_path):
    root = _repo(tmp_path)
    head = BASE.replace("[GAP] (#1;", "[PARTIAL] (#1, #6346;").replace("one step back.", "one step back. Built: the route "
           "(test `tests/t.py::test_u`). not built: the menu. Built 2026-11-05: the CLI. Was: undoable by hand.")
    assert _batch(root, head) == []


def test_a_rewritten_or_deleted_acceptance_line_fails_and_a_spec_change_trailer_lets_it_through(tmp_path):
    root = _repo(tmp_path)
    fails = _batch(root, BASE.replace("is undoable, one step back", "is NOT on the undo stack").replace("- `x.other` [GAP] (#2) — another thing.\n", ""))
    rel = f"{SPECS}/x.md"
    assert any(f.startswith(f"{rel}:1: `x.undo`'s acceptance text changed") for f in fails), fails
    assert f"{rel}: behaviour `x.other` was deleted: restore it, or add a `Spec-change:` trailer naming the ruling" in fails
    (root / "note").write_text("x")
    _git(root, "add", "."), _git(root, "commit", "-qm", "the ruling\n\nSpec-change: x.undo is not on the undo stack (manager 2026-11-05)")
    assert _mod.check(root) == [], "a Spec-change trailer naming the ruling lets it through"


def test_a_spec_change_trailer_with_no_ruling_named_is_not_enough(tmp_path):
    root = _repo(tmp_path)
    assert _batch(root, BASE.replace("one step back", "two steps back"), "edit\n\nSpec-change: two steps now") != []
