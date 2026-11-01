"""The policy hook: refuse a forbidden worker action with a reason (dev-workflows.run.policy-hook, #6116).

Plain functions behind `scripts/harness_policy_hook.py` (a Claude Code PreToolUse hook) and a git commit-msg hook.
Rules come from the project's harness.toml [policy]. Fast feedback, not a security boundary: shell text can be
rewritten, so the credential/OS layer (run.land-gate) and the landing guards hold the hard rules. Imports nothing
from the rest of the engine.
ponytail: a second pytest (lock file) and a paid call without a grant are not rules here yet; the lock needs a
PostToolUse release, grants are Step 1.6.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any

_WRITE_TOOLS = {"Edit", "Write", "NotebookEdit", "MultiEdit"}
_CD = re.compile(r"(?:^|[;&|]\s*|&&\s*)cd\s+(\"[^\"]+\"|'[^']+'|\S+)")


def load(root: str | Path) -> dict[str, Any]:
    return tomllib.loads((Path(root) / "harness.toml").read_text()).get("policy", {})


def _inside(p: Path, bases: list[Path]) -> bool:
    p = Path(__import__("os").path.normpath(p))
    return any(p == b or b in p.parents for b in bases)


def check(event: dict[str, Any], cfg: dict[str, Any], *, worktree: Path, scratch: Path) -> str | None:
    """None to allow; else the reason the worker is shown."""
    bases = [Path(__import__("os").path.normpath(worktree)), Path(__import__("os").path.normpath(scratch))]
    tool, inp = event.get("tool_name", ""), event.get("tool_input") or {}
    if tool in _WRITE_TOOLS:
        target = Path(inp.get("file_path") or inp.get("notebook_path") or "")
        if not _inside(target, bases):
            return f"{target} is outside the worktree and scratch path; a worker writes only there"
    if tool == "Bash":
        cmd = inp.get("command", "")
        for rule in cfg.get("rules", []):
            if re.search(rule["re"], cmd):
                return rule["reason"]
        for m in _CD.finditer(cmd):
            target = Path(m.group(1).strip("\"'")).expanduser()
            if target.is_absolute() and not _inside(target, bases):
                return f"cd {target} goes outside the worktree and scratch path"
    return None


def commit_msg_problems(msg: str, cfg: dict[str, Any]) -> list[str]:
    return [f"the commit message lacks the trailer {t!r}" for t in cfg.get("required_trailers", []) if t not in msg]
