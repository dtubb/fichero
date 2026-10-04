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
