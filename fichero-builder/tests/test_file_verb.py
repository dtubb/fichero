"""dev-workflows.tool.file: `builder file` creates a milestone and one issue, edits (never duplicates) on a second run,
and writes nothing on --dry-run. A fake `gh` keeps state in a JSON file."""
from __future__ import annotations

import json
import sys

import pytest

from fichero_builder import __main__ as cli
from fichero_builder import journal

FAKE_GH = """#!{py}
import json, sys
from pathlib import Path
state = Path({state!r})
db = json.loads(state.read_text()) if state.exists() else {{"milestones": [], "issues": [], "labels": [], "calls": []}}
argv = sys.argv[1:]
db["calls"].append(argv)
def opt(name):
    return argv[argv.index(name) + 1] if name in argv else None
if argv[0] == "api" and "-X" in argv:
    db["milestones"].append({{"title": opt("-f").split("=", 1)[1]}})
elif argv[0] == "api":
    print(json.dumps(db["milestones"]))
elif argv[:2] == ["issue", "list"]:
    print(json.dumps([i for i in db["issues"] if i["milestone"] == opt("--milestone")]))
elif argv[:2] == ["issue", "create"]:
    db["issues"].append({{"number": 7 + len(db["issues"]), "title": opt("--title"), "body": opt("--body"), "milestone": opt("--milestone")}})
    print("https://github.com/o/r/issues/%d" % (6 + len(db["issues"])))
elif argv[:2] == ["issue", "edit"]:
    for i in db["issues"]:
        if str(i["number"]) == argv[2]:
            i["body"] = opt("--body")
elif argv[:2] == ["label", "list"]:
    print(json.dumps([{{"name": x}} for x in db["labels"]]))
elif argv[:2] == ["label", "create"]:
    db["labels"].append(argv[2])
state.write_text(json.dumps(db))
"""


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    state = tmp_path / "gh.json"
    gh = tmp_path / "gh"
    gh.write_text(FAKE_GH.format(py=sys.executable, state=str(state)))
    gh.chmod(0o755)
    body = tmp_path / "body.md"
    body.write_text("Write the spec.\n")

    def run(*extra):
        return cli.main(["file", "--milestone", "Builder app", "--title", "Write the spec", "--body-file", str(body),
                         "--label", "needs-spec", "--gh", str(gh), "--state", str(tmp_path / "s"), *extra])

    def db():
        return json.loads(state.read_text()) if state.exists() else {"milestones": [], "issues": [], "labels": [], "calls": []}
    return run, db, body


def test_a_second_run_edits_the_issue_and_a_dry_run_writes_nothing(env):
    run, db, body = env
    assert run("--dry-run") == 0
    assert db()["milestones"] == [] and db()["issues"] == []  # nothing written, only reads
    assert not any(c[:2] in (["issue", "create"], ["label", "create"]) or "-X" in c for c in db()["calls"])
    assert run() == 0
    assert [m["title"] for m in db()["milestones"]] == ["Builder app"] and len(db()["issues"]) == 1
    assert db()["labels"] == ["needs-spec"]
    body.write_text("Changed.\n")
    assert run() == 0
    assert len(db()["issues"]) == 1 and db()["issues"][0]["body"] == "Changed.\n"
    assert len(db()["milestones"]) == 1


def test_an_empty_body_is_refused(env, capsys):
    run, db, body = env
    body.write_text("  \n")
    assert run() == 1
    assert "REFUSED" in capsys.readouterr().err and db()["issues"] == []
