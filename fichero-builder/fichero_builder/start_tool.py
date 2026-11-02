"""Start path for a worker (dev-workflows run.slice-zero item 3, #6116): refuse unless the wall and rules file hold,
then write the generated settings (policy hook, empty strict MCP) and the clone's commit-msg hook.

Stdlib + workflows.check_tool/jail only. `scripts/harness_start.py` is the only caller that opens a pane.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import stat
import sys
from pathlib import Path

from fichero_builder import check_tool, codemap
from fichero_builder.jail import Jail

_HOOK = Path(__file__).resolve().parents[2] / "scripts" / "harness_policy_hook.py"  # <repo>/scripts; the first live run found parents[4] after the move
_HANDOFF = _HOOK.with_name("harness_handoff_hook.py")


def refusals(root, jail: Jail | None) -> list[str]:
    """Every reason NOT to start; empty = go. Runs the probe live (it is cheap and proves the wall now, not at set-up)."""
    out: list[str] = check_tool.rules_problems(root)
    if jail is None:
        return out or ["harness.toml has no [jail]: a worker never starts unjailed"]
    if not jail.is_self():
        out.append(f"must run as the worker user {jail.user!r} (start it through sudo -u from the owner's side)")
    c = check_tool.load(root) if not out else None
    if c and c.python and not os.access(c.python, os.X_OK):
        out.append(f"[check].python {c.python!r} must be a program the worker user can run")
    if out:
        return out
    return jail.probe()


def _hook_cmd(root, worktree, scratch) -> str:
    return " ".join(shlex.quote(str(x)) for x in (sys.executable, _HOOK, "--root", root, "--worktree", worktree, "--scratch", scratch))


def trust_folder(worktree, home=None) -> None:
    """Mark `worktree` trusted in the worker's own ~/.claude.json (else claude waits on a trust prompt nobody answers)."""
    f = Path(home or Path.home()) / ".claude.json"
    cfg = json.loads(f.read_text()) if f.is_file() else {}
    cfg.setdefault("projects", {}).setdefault(str(worktree), {})["hasTrustDialogAccepted"] = True
    f.write_text(json.dumps(cfg, indent=1))


def brief_prompt(brief) -> str:
    """What the command line carries: a short prompt naming the brief file, never its text (a 22 KB brief made tmux refuse
    "command too long", 2026-11-02). The worker reads the file itself; a missing file raises FileNotFoundError."""
    path = Path(brief).resolve(strict=True)
    return f"Your brief is the file {path}. Read all of it with the Read tool first (in parts if it is long), then follow it."


AUTHOR = {f"GIT_{r}_{f}": v for r in ("AUTHOR", "COMMITTER") for f, v in (("NAME", "Claude"), ("EMAIL", "noreply@anthropic.com"))}


def prepare(root, worktree, brief: str, scratch, model: str = "sonnet", claude_bin: str = "claude") -> list[str]:
    """Write settings.json, mcp.json under `scratch` and the commit-msg hook in the clone; return claude's argv."""
    root, worktree, scratch = Path(root), Path(worktree), Path(scratch)
    scratch.mkdir(parents=True, exist_ok=True)
    hook = {"type": "command", "command": _hook_cmd(root, worktree, scratch)}
    handoff = {"hooks": [{"type": "command", "command": " ".join(shlex.quote(str(x)) for x in (sys.executable, _HANDOFF))}]}
    settings = {"skipDangerousModePermissionPrompt": True, "hooks": {
        "PreToolUse": [{"matcher": "Bash|Edit|Write|MultiEdit|NotebookEdit", "hooks": [hook]}],
        "PostToolUse": [handoff], "Stop": [handoff]}}
    (scratch / "settings.json").write_text(json.dumps(settings, indent=1))
    # the worker's git must open owner-made trees (the engine repo, the ladder's scratch worktrees) or every call there dies
    # with "dubious ownership" (first real check, 2026-11-01); the worker user is the jail, so the wide allow is its own risk only
    if "*" not in subprocess.run(["git", "config", "--global", "--get-all", "safe.directory"], capture_output=True, text=True).stdout.split():
        subprocess.run(["git", "config", "--global", "--add", "safe.directory", "*"], check=True)
    # the worker commits as Claude, never as the jail user (a host name leaked, check_agent_commits_authored_as_claude, 2026-11-02)
    for k, v in (("user.name", AUTHOR["GIT_AUTHOR_NAME"]), ("user.email", AUTHOR["GIT_AUTHOR_EMAIL"])):
        subprocess.run(["git", "config", "--global", k, v], check=True)
    (scratch / "mcp.json").write_text(json.dumps(codemap.mcp_config(root)))  # with --strict-mcp-config: this file is all the worker gets
    # a linked worktree's .git is a file: ask git where hooks live (the clone's shared hooks dir)
    hooks = subprocess.run(["git", "-C", str(worktree), "rev-parse", "--path-format=absolute", "--git-path", "hooks"],
                           capture_output=True, text=True, check=True).stdout.strip()
    cm = Path(hooks) / "commit-msg"
    cm.parent.mkdir(parents=True, exist_ok=True)
    cm.write_text(f'#!/bin/sh\nexec {shlex.quote(sys.executable)} {shlex.quote(str(_HOOK))} --root {shlex.quote(str(root))} --commit-msg "$1"\n')
    cm.chmod(cm.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return [claude_bin, "--dangerously-skip-permissions", "--model", model, "--settings", str(scratch / "settings.json"),
            "--strict-mcp-config", f"--mcp-config={scratch / 'mcp.json'}", brief]  # =form: --mcp-config is variadic and would swallow the brief
