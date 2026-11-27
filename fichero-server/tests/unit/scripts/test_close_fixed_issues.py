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


def test_a_last_comment_that_says_what_is_left_keeps_the_issue_open(monkeypatch):
    # Live 2026-10-26: #6129 #6133-#6135 were closed with residue in their last comment.
    for text in ("Residue: the iPad half", "remaining: the docs", "this is still missing", "not yet wired", "needs your test",
                 "what is left: the docs", "left to do", "not done", "a follow-up is filed", "TODO", "to do: iPad"):
        assert _mod.owes_more(text), text
    assert not _mod.owes_more("Done and verified.") and not _mod.owes_more("")
    monkeypatch.setattr(_mod, "_run", lambda *a: __import__("json").dumps({"comments": [{"body": "old"}, {"body": "Residue: x"}]}))
    assert _mod.owes_more(_mod.last_comment(1))


def _fake_gh(monkeypatch, issue: dict, releases: list, in_tag: set):
    import json as _json
    calls = []

    def run(*a):
        calls.append(a)
        if a[:3] == ("gh", "issue", "view") and "comments" in a:
            return _json.dumps({"comments": []})
        if a[:3] == ("gh", "issue", "view"):
            return _json.dumps(issue)
        if a[:2] == ("gh", "api"):
            return "[]"
        if a[:3] == ("gh", "release", "list"):
            return _json.dumps(releases)
        if a[:2] == ("git", "show"):
            return "MARKETING_VERSION = 2026.11.28\nCURRENT_PROJECT_VERSION = 412\n"
        if a[:2] == ("git", "log"):
            return "abc123\x1ffix: the thing\x1f2026-11-27T10:00:00Z\x1fFixes #7\x1e"
        return ""
    monkeypatch.setattr(_mod, "_run", run)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)

    def sub(argv, **k):
        calls.append(tuple(argv))
        return __import__("types").SimpleNamespace(returncode=0 if argv[-1] in in_tag else 1, stdout="added", stderr="")
    monkeypatch.setattr(_mod.subprocess, "run", sub)
    monkeypatch.setattr(sys, "argv", ["close_fixed_issues.py", "--range", "a..b", "--apply"])
    assert _mod.main() == 0
    return calls


def test_a_closed_owner_bug_gets_owner_verify_and_names_the_first_release_that_carries_the_fix(monkeypatch):
    issue = {"state": "OPEN", "labels": [{"name": "type:bug"}], "author": {"login": "dtubb"}, "title": "Back does nothing",
             "url": "https://github.com/o/r/issues/7"}
    rels = [{"tagName": "v2026.11.29", "isPrerelease": True, "createdAt": "2026-11-29T04:00:00Z"},
            {"tagName": "v2026.11.28", "isPrerelease": True, "createdAt": "2026-11-28T04:00:00Z"}]
    calls = _fake_gh(monkeypatch, issue, rels, {"v2026.11.28", "v2026.11.29"})
    assert ("gh", "issue", "edit", "7", "--add-label", "owner-verify") in calls
    assert ("gh", "issue", "comment", "7", "--body", "In dev release 2026.11.28 (build 412) — please check and reopen if not fixed.") in calls
    assert [c[:3] for c in calls].index(("gh", "issue", "close")) < [c[:3] for c in calls].index(("gh", "issue", "edit"))
    add = next(c for c in calls if "review" in c)
    assert add[add.index("review"):add.index("review") + 3] == ("review", "add", "bug-7")
    assert add[add.index("--build") + 1] == "dev release 2026.11.28 (build 412)" and add[add.index("--issue") + 1] == "https://github.com/o/r/issues/7"


def test_an_owner_bug_with_no_release_yet_says_the_next_nightly_and_others_get_no_label(monkeypatch):
    issue = {"state": "OPEN", "labels": [{"name": "type:bug"}], "author": {"login": "dtubb"}}
    calls = _fake_gh(monkeypatch, issue, [], set())
    assert ("gh", "issue", "comment", "7", "--body", "In the next nightly — please check and reopen if not fixed.") in calls
    for other in ({"state": "OPEN", "labels": [{"name": "type:bug"}], "author": {"login": "someone"}},
                  {"state": "OPEN", "labels": [{"name": "type:feature"}], "author": {"login": "dtubb"}}):
        calls = _fake_gh(monkeypatch, other, [], set())
        assert not [c for c in calls if c[:3] in (("gh", "issue", "edit"), ("gh", "issue", "comment")) or "review" in c]
