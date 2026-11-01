"""dev-workflows run.slice-zero: harness_start refuses unless the wall and the rules file are in place (#6116)."""

from __future__ import annotations

import json
import os
import subprocess

from fichero_server.workflows import jail as J
from fichero_server.workflows import start_tool as S

GOOD = """[check]
python = "/usr/bin/python3"
ready = ["true"]
guard_glob = "scripts/check_*.py"
min_guards = 3
contract_guards = ["scripts/check_a.py"]
[policy]
required_trailers = ["Co-Authored-By: "]
[jail]
user = "%s"
workroot = "%s"
deny_read = ["/nonexistent-secret"]
[land]
branch = "main"
boundary = ["zzz"]
"""


def _me():
    return subprocess.run(["id", "-un"], capture_output=True, text=True).stdout.strip()


def _root(tmp_path, body=None):
    (tmp_path / "harness.toml").write_text(body or GOOD % (_me(), tmp_path))
    return tmp_path


def _jail(tmp_path):
    return J.Jail(user=_me(), workroot=str(tmp_path), deny_read=("/nonexistent-secret",), floor=())


def test_a_complete_rules_file_as_the_worker_user_passes(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", "/usr/bin:/bin")  # the owner's gh login is not the stand-in worker's
    root = _root(tmp_path)
    assert S.refusals(root, _jail(tmp_path)) == []


def test_no_jail_table_refuses(tmp_path):
    root = _root(tmp_path, GOOD.split("[jail]")[0])
    assert any("[jail]" in r for r in S.refusals(root, None))


def test_not_the_worker_user_refuses(tmp_path):
    root = _root(tmp_path)
    j = J.Jail(user="root" if _me() != "root" else "nobody", workroot=str(tmp_path), deny_read=("/x",), floor=())
    assert any("must run as" in r for r in S.refusals(root, j))


def test_empty_deny_read_and_missing_rungs_refuse(tmp_path):
    root = _root(tmp_path, GOOD.replace('deny_read = ["/nonexistent-secret"]', "deny_read = []").replace('python = "/usr/bin/python3"\n', ""))
    out = " ".join(S.refusals(root, J.Jail(user=_me(), workroot=str(tmp_path), floor=())))
    assert "deny_read" in out and "[check].python" in out


def test_a_leaking_probe_refuses(tmp_path):
    root = _root(tmp_path)
    secret = tmp_path / "secret"
    secret.write_text("x")
    j = J.Jail(user=_me(), workroot=str(tmp_path), deny_read=(str(secret),), floor=())  # same uid can read it = leak
    assert any("readable" in r for r in S.refusals(root, j))


def test_prepare_writes_hooked_settings_empty_mcp_and_the_commit_msg_hook(tmp_path):
    root = _root(tmp_path)
    wt = tmp_path / "clone"
    subprocess.run(["git", "init", "-q", str(wt)], check=True)
    argv = S.prepare(root, wt, "do the thing", tmp_path / "scratch")
    scratch = tmp_path / "scratch"
    st = json.loads((scratch / "settings.json").read_text())
    cmds = json.dumps(st["hooks"]["PreToolUse"])
    assert "harness_policy_hook.py" in cmds and str(wt) in cmds
    assert json.loads((scratch / "mcp.json").read_text()) == {"mcpServers": {}}
    hook = wt / ".git" / "hooks" / "commit-msg"
    assert hook.is_file() and os.access(hook, os.X_OK) and "--commit-msg" in hook.read_text()
    assert "--strict-mcp-config" in argv and "--settings" in argv and argv[-1] == "do the thing"


def test_trust_folder_marks_only_that_worktree(tmp_path):
    (tmp_path / ".claude.json").write_text('{"x": 1, "projects": {"/a": {"k": 2}}}')
    S.trust_folder("/wt", home=tmp_path)
    cfg = json.loads((tmp_path / ".claude.json").read_text())
    assert cfg["x"] == 1 and cfg["projects"]["/a"] == {"k": 2} and cfg["projects"]["/wt"] == {"hasTrustDialogAccepted": True}
