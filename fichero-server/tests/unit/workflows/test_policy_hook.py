"""The policy hook refuses forbidden worker actions with a reason (dev-workflows.run.policy-hook, #6116).

Plain functions behind a Claude Code PreToolUse hook script and a git commit-msg hook; the rules are the
project's harness.toml [policy], not code. The hook is fast feedback, not the security boundary (run.land-gate)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from fichero_server.workflows import policy_hook as ph

ROOT = Path(__file__).resolve().parents[4]


@pytest.fixture
def cfg():
    return ph.load(ROOT)


def _bash(cmd):
    return {"tool_name": "Bash", "tool_input": {"command": cmd}}


@pytest.mark.parametrize("cmd,word", [
    ("git stash", "stash"),
    ("git push origin HEAD:main", "push"),
    ("git push origin integration", "push"),
    ("xcodebuild test -scheme X", "xcodebuild"),
    ("pkill -f pytest", "pkill"),
    ("killall Fichero", "killall"),
    ("ls /tmp/x && rm -rf /tmp/x", "rm"),
    ("cd /Users/someone/else && ls", "outside"),
    ("git -C /Users/Shared/fichero-worker/root reset --hard origin/integration", "own worktree"),
    ("git -C /w/other-lane checkout -- src/a.py", "own worktree"),
    ("git --work-tree=/w/other-lane clean -fd", "own worktree"),
    ("git -C /w/other-lane clean -df && ls", "own worktree"),
    ("echo x > /Users/Shared/fichero-worker/root/harness.toml", "outside"),
    ("python gen.py | tee -a /w/other-lane/out.txt", "outside"),
])
def test_each_forbidden_command_is_refused_with_a_reason(cfg, tmp_path, cmd, word):
    reason = ph.check(_bash(cmd), cfg, worktree=tmp_path / "wt", scratch=tmp_path / "scratch")
    assert reason and word in reason


@pytest.mark.parametrize("cmd", ["git status", "git commit -m x", "python -m pytest -q tests/x.py", "rm -rf build",
                                 "cd . && ls", "git reset --hard HEAD~1", "git checkout -- src/a.py", "git clean -fd",
                                 "git -C /w/other-lane log --oneline -3", "pytest -q 2>&1 > /dev/null", "echo x > out.txt"])
def test_ordinary_commands_pass(cfg, tmp_path, cmd):
    assert ph.check(_bash(cmd), cfg, worktree=tmp_path / "wt", scratch=tmp_path / "scratch") is None


def test_a_write_outside_the_worktree_and_scratch_is_refused(cfg, tmp_path):
    wt, scratch = tmp_path / "wt", tmp_path / "scratch"
    ev = lambda p: {"tool_name": "Edit", "tool_input": {"file_path": str(p)}}  # noqa: E731
    assert ph.check(ev(wt / "a.py"), cfg, worktree=wt, scratch=scratch) is None
    assert ph.check(ev(scratch / "n.txt"), cfg, worktree=wt, scratch=scratch) is None
    assert "outside" in ph.check(ev(tmp_path / "other" / "a.py"), cfg, worktree=wt, scratch=scratch)
    assert "outside" in ph.check(ev(wt / ".." / "x"), cfg, worktree=wt, scratch=scratch)


def test_commit_msg_needs_the_trailers(cfg):
    ok = "fix: x\n\nDirected-By: the maintainer\nCo-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>\n"
    assert ph.commit_msg_problems(ok, cfg) == []
    assert any("Directed-By" in p for p in ph.commit_msg_problems("fix: x\n", cfg))


def test_the_hook_script_speaks_claude_code_exit_2(tmp_path):
    script = ROOT / "scripts" / "harness_policy_hook.py"
    run = lambda cmd: subprocess.run(  # noqa: E731
        [sys.executable, str(script), "--worktree", str(tmp_path), "--scratch", str(tmp_path / "s"), "--root", str(ROOT)],
        input=json.dumps(_bash(cmd)), capture_output=True, text=True)
    bad = run("git stash")
    assert bad.returncode == 2 and "stash" in bad.stderr
    assert run("git status").returncode == 0
