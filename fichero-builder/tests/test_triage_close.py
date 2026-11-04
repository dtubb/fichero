"""dev-workflows.tool.triage --close (manager 2026-11-04): the one close outside a landing, owner-approved, its reason as the comment."""
from __future__ import annotations

import json
import sys

import pytest

from fichero_builder import __main__ as cli
from fichero_builder import journal


@pytest.fixture
def gh(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    log = tmp_path / "gh.log"
    g = tmp_path / "gh"
    g.write_text(f"#!{sys.executable}\nimport json, sys\nopen({str(log)!r}, 'a').write(json.dumps(sys.argv[1:]) + chr(10))\n")
    g.chmod(0o755)
    return g, log


def go(g, *extra):
    return cli.main(["triage", "--gh", str(g), "--state", str(journal.STATE), *extra])


def test_close_is_refused_without_owner_approval_or_a_reason_and_calls_no_gh(gh, capsys):
    g, log = gh
    assert go(g, "--close", "6025", "--reason", "not reproducible") == 1
    assert go(g, "--close", "6025", "--owner-approved") == 1
    assert not log.exists() and "needs --owner-approved" in capsys.readouterr().out


def test_an_approved_close_is_one_gh_call_with_the_reason_as_the_comment_and_one_row(gh):
    g, log = gh
    assert go(g, "--close", "6025", "--reason", "Not reproducible: no traceback since 10-22 (owner)", "--owner-approved") == 0
    (call,) = [json.loads(x) for x in log.read_text().splitlines()]
    assert call[:5] == ["issue", "close", "6025", "--reason", "not planned"] and call[5] == "--comment"
    assert call[6].startswith("Not reproducible: no traceback since 10-22 (owner)") and "owner-approved" in call[6]
    (row,) = [r for r in journal.read() if r["event"] == "triage"]
    assert row["what"] == "close" and row["issue"] == 6025 and row["close_as"] == "not-planned" and row["dry"] is False
    assert go(g, "--close", "6026", "--reason", "a duplicate of #6025", "--as", "duplicate", "--owner-approved", "--dry") == 0
    assert len(log.read_text().splitlines()) == 1, "--dry calls no gh"
