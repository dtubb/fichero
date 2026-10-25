"""scripts/close_fixed_issues.py reads which issues a commit says it fixes.

WHY: GitHub only auto-closes `Fixes #N` on main; our commits land on integration, so this script
is what closes them (maintainer, 2026-10-04: "issues just keep growing"). If the reading drifts,
fixed issues stay open forever, or worse, an issue a commit merely MENTIONS gets closed.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "close_fixed_issues.py"
_SPEC = importlib.util.spec_from_file_location("close_fixed_issues", _SCRIPT)
assert _SPEC and _SPEC.loader
_mod = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _mod
_SPEC.loader.exec_module(_mod)


def test_the_closing_keywords_name_the_issues_they_fix():
    message = "fix(x): a thing\n\nFixes #12. Closes #34, resolves #56.\nfixed #7"
    assert _mod.cited(message) == {12, 34, 56, 7}


def test_an_issue_that_is_only_mentioned_is_not_closed():
    # A commit that cites #5409 for context (the usual "(#5409)" subject suffix) did not fix it.
    assert _mod.cited("fix(kg): a model run proposes merges (#5409, #4869)\n\nSee #4868.") == set()


def test_a_keyword_inside_prose_does_not_close():
    # "revert the fix #5222" talks about a fix; it is not a Fixes clause (reviewer, 2026-10-25).
    assert _mod.cited("chore: revert the fix #5222 that broke import\n\nFixes #6000") == {6000}


def test_the_runners_own_commit_form_closes():
    # core.brief tells the coder to write `<what> (Fixes #N)`; the re-review found the clause rule missed it.
    assert _mod.cited("fix (Fixes #1003)") == {1003}
    assert _mod.cited("guard: pins the shape (Part of #6116)") == set()
    assert _mod.cited("x [Closes #12]") == {12}


def test_reopened_compares_instants_not_strings(monkeypatch):
    # git's %cI carries a local offset; GitHub's created_at ends in Z. 10:00-03:00 is 13:00Z.
    events = [{"event": "reopened", "created_at": "2026-10-24T12:30:00Z"}]
    monkeypatch.setattr(_mod, "_run", lambda *a: __import__("json").dumps(events))
    assert _mod.reopened_after(1, "2026-10-24T10:00:00-03:00") is False, "13:00Z commit is after the 12:30Z reopen"
    assert _mod.reopened_after(1, "2026-10-24T09:00:00-03:00") is True


def test_an_issue_reopened_after_the_fixing_commit_stays_open(monkeypatch):
    events = [{"event": "closed", "created_at": "2026-10-20T10:00:00Z"}, {"event": "reopened", "created_at": "2026-10-24T10:00:00Z"}]
    monkeypatch.setattr(_mod, "_run", lambda *a: __import__("json").dumps(events))
    assert _mod.reopened_after(1, "2026-10-22T10:00:00Z") is True, "reopened after the commit: the fix did not hold"
    assert _mod.reopened_after(1, "2026-10-25T10:00:00Z") is False, "reopened before the commit: the commit is the fix"
