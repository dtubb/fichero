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

from fichero_server.workflows import check_tool
from fichero_server.workflows.jail import Jail

_HOOK = Path(__file__).resolve().parents[4] / "scripts" / "harness_policy_hook.py"


def refusals(root, jail: Jail | None) -> list[str]:
    """Every reason NOT to start; empty = go. Runs the probe live (it is cheap and proves the wall now, not at set-up)."""
    if jail is None:
        return ["harness.toml has no [jail]: a worker never starts unjailed"]
    out: list[str] = []
    if not jail.is_self():
        out.append(f"must run as the worker user {jail.user!r} (start it through sudo -u from the owner's side)")
    if not jail.deny_read:
        out.append("[jail].deny_read is empty: the probe needs paths to prove unreadable")
    try:
        c = check_tool.load(root)
    except ValueError as e:
        return [*out, str(e)]
    for name, val in (("python", c.python), ("ready", c.ready), ("guard_glob", c.guard_glob), ("min_guards", c.min_guards),
                      ("contract_guards", c.contract_guards)):
        if not val:
            out.append(f"harness.toml [check].{name} is not declared")
    if c.python and not (Path(c.python).is_absolute() and os.access(c.python, os.X_OK)):
        out.append(f"[check].python {c.python!r} must be an absolute path the worker user can run (no PATH lookup, no shim)")
    if out:
        return out
    return jail.probe()


def _hook_cmd(root, worktree, scratch) -> str:
    return " ".join(shlex.quote(str(x)) for x in (sys.executable, _HOOK, "--root", root, "--worktree", worktree, "--scratch", scratch))


def prepare(root, worktree, brief: str, scratch, model: str = "sonnet", claude_bin: str = "claude") -> list[str]:
    """Write settings.json, mcp.json under `scratch` and the commit-msg hook in the clone; return claude's argv."""
    root, worktree, scratch = Path(root), Path(worktree), Path(scratch)
    scratch.mkdir(parents=True, exist_ok=True)
    hook = {"type": "command", "command": _hook_cmd(root, worktree, scratch)}
    settings = {"hooks": {"PreToolUse": [{"matcher": "Bash|Edit|Write|MultiEdit|NotebookEdit", "hooks": [hook]}]}}
    (scratch / "settings.json").write_text(json.dumps(settings, indent=1))
    (scratch / "mcp.json").write_text(json.dumps({"mcpServers": {}}))
    # a linked worktree's .git is a file: ask git where hooks live (the clone's shared hooks dir)
    hooks = subprocess.run(["git", "-C", str(worktree), "rev-parse", "--path-format=absolute", "--git-path", "hooks"],
                           capture_output=True, text=True, check=True).stdout.strip()
    cm = Path(hooks) / "commit-msg"
    cm.parent.mkdir(parents=True, exist_ok=True)
    cm.write_text(f'#!/bin/sh\nexec {shlex.quote(sys.executable)} {shlex.quote(str(_HOOK))} --root {shlex.quote(str(root))} --commit-msg "$1"\n')
    cm.chmod(cm.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return [claude_bin, "--dangerously-skip-permissions", "--model", model, "--settings", str(scratch / "settings.json"),
            "--strict-mcp-config", f"--mcp-config={scratch / 'mcp.json'}", brief]  # =form: --mcp-config is variadic and would swallow the brief
