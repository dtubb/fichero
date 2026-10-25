"""pipeline.issues-and-milestones-kept-current: one write function, dry run by default, journaled."""
from __future__ import annotations

import re
from pathlib import Path

from pipeline import ROOT, gh, journal


def test_every_write_goes_through_one_function_and_dry_run_writes_nothing(scratch, monkeypatch):
    ran = []
    monkeypatch.setattr(gh, "sh", lambda args, **kw: ran.append(args))
    out = gh.write("issue", "close", "1")
    assert out.startswith("DRY RUN") and ran == []
    assert journal.read()[-1]["event"] == "gh_write" and journal.read()[-1]["dry_run"] is True
    # no other module runs `gh` itself
    for p in (ROOT / "pipeline").glob("*.py"):
        if p.name != "gh.py":
            assert not re.search(r'["\']gh["\']', p.read_text()), f"{p.name} calls gh directly"


def test_reads_are_cached(monkeypatch):
    calls = []

    class R:
        returncode, stdout, stderr = 0, '{"a": 1}', ""

    monkeypatch.setattr(gh, "sh", lambda args, **kw: calls.append(args) or R())
    gh.cache_clear()
    assert gh.read("issue", "view", "1", "--json", "a") == {"a": 1}
    assert gh.read("issue", "view", "1", "--json", "a") == {"a": 1}
    assert len(calls) == 1
    gh.cache_clear()
    gh.read("issue", "view", "1", "--json", "a")
    assert len(calls) == 2


def test_slim_issue_shape():
    d = gh._slim({"number": 1, "labels": [{"name": "b"}, {"name": "a"}], "milestone": {"title": "m"}, "author": {"login": "x"}})
    assert d["labels"] == ["a", "b"] and d["milestone"] == "m" and d["author"] == "x"
    assert Path(__file__).exists()
