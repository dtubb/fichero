"""dev-workflows run.slice-zero: harness_start refuses unless the wall and the rules file are in place (#6116)."""

from __future__ import annotations

import json
import os
import subprocess

import pytest

from fichero_server.workflows import jail as J
from fichero_server.workflows import start_tool as S

GOOD = """[check]
python = "/usr/bin/python3"
ready = ["true"]
guard_glob = "scripts/check_*.py"
min_guards = 3
contract_guards = ["scripts/check_a.py"]
check_paths = ["scripts/"]
contract_paths = ["src/"]
pytest_config = "pyproject.toml"
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


@pytest.fixture(autouse=True)
def _own_git_config(tmp_path, monkeypatch):
    """prepare() writes the worker's global git config: in a test that file is a scratch one, never the real one (review: a leak)."""
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig-global"))


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
    for ev in ("PostToolUse", "Stop"):  # H3: the handoff hook must be wired, not just written
        assert "harness_handoff_hook.py" in json.dumps(st["hooks"][ev])
    assert json.loads((scratch / "mcp.json").read_text()) == {"mcpServers": {}}
    hook = wt / ".git" / "hooks" / "commit-msg"
    assert hook.is_file() and os.access(hook, os.X_OK) and "--commit-msg" in hook.read_text()
    assert "--strict-mcp-config" in argv and "--settings" in argv and argv[-1] == "do the thing"


def test_trust_folder_marks_only_that_worktree(tmp_path):
    (tmp_path / ".claude.json").write_text('{"x": 1, "projects": {"/a": {"k": 2}}}')
    S.trust_folder("/wt", home=tmp_path)
    cfg = json.loads((tmp_path / ".claude.json").read_text())
    assert cfg["x"] == 1 and cfg["projects"]["/a"] == {"k": 2} and cfg["projects"]["/wt"] == {"hasTrustDialogAccepted": True}


def test_prepare_allows_the_workers_git_to_open_owner_made_trees(tmp_path, monkeypatch):  # 2026-11-01: "dubious ownership"
    import subprocess

    from fichero_server.workflows import start_tool

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig"))  # the explicit global file: the real one is never touched (review: a leak)
    wt = tmp_path / "wt"
    subprocess.run(["git", "init", "-q", str(wt)], check=True)
    (tmp_path / "brief.txt").write_text("go")
    start_tool.prepare(tmp_path, wt, "go", tmp_path / "scratch")
    got = subprocess.run(["git", "config", "--global", "--get-all", "safe.directory"], capture_output=True, text=True).stdout.split()
    assert "*" in got and "safe" in (tmp_path / "gitconfig").read_text()


def test_a_brief_over_100_kb_reaches_the_worker_as_a_short_prompt_naming_its_file(tmp_path):
    """2026-11-02: a 22 KB brief on the tmux command line died with "command too long". The command line carries only a
    short prompt naming the brief file; the worker reads the file. Never the brief's text."""
    brief = tmp_path / "brief.txt"
    brief.write_text("step " * 30000)  # 150 KB
    p = S.brief_prompt(brief)
    assert len(p) < 500 and str(brief.resolve()) in p and "step step" not in p
    wt = tmp_path / "clone"
    subprocess.run(["git", "init", "-q", str(wt)], check=True)
    argv = S.prepare(_root(tmp_path), wt, p, tmp_path / "scratch")
    assert argv[-1] == p and sum(len(x) for x in argv) < 2000, "the whole argv stays short"
    with pytest.raises(FileNotFoundError):
        S.brief_prompt(tmp_path / "missing.txt")


def test_find_claude_falls_back_to_the_worker_home(tmp_path, monkeypatch):
    """#6466: sudo -u gives the worker a PATH without claude; its own ~/.local/bin/claude must be found (a dangling link is not found)."""
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    assert S.find_claude(tmp_path) is None
    link = tmp_path / ".local" / "bin" / "claude"
    link.parent.mkdir(parents=True)
    link.symlink_to(tmp_path / "missing")
    assert S.find_claude(tmp_path) is None
    exe = tmp_path / "claude-real"
    exe.write_text("#!/bin/sh\n")
    exe.chmod(0o755)
    link.unlink()
    link.symlink_to(exe)
    assert S.find_claude(tmp_path) == str(link)


def test_use_worker_home_points_home_at_the_workroot(tmp_path, monkeypatch):
    """#6466: under sudo -u HOME is still the owner's; as the worker user it becomes the workroot, for anyone else it is left alone."""
    class Jail:
        workroot = str(tmp_path)

        def __init__(self, me):
            self.me = me

        def is_self(self):
            return self.me

    monkeypatch.setenv("HOME", "/owner")
    S.use_worker_home(Jail(False))
    assert os.environ["HOME"] == "/owner"
    S.use_worker_home(Jail(True))
    assert os.environ["HOME"] == str(tmp_path)
