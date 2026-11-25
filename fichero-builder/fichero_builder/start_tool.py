"""Start path for a worker (dev-workflows run.slice-zero item 3, #6116): refuse unless the wall and rules file hold,
then write the generated settings (policy hook, empty strict MCP) and the clone's commit-msg hook.

Stdlib + workflows.check_tool/jail only. `scripts/harness_start.py` is the only caller that opens a pane.
"""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import subprocess
import stat
import sys
from pathlib import Path

from fichero_builder import adapters, check_tool, client, journal, mcp_servers, profiles
from fichero_builder.jail import Jail

_HOOK = client.scripts_dir() / "harness_policy_hook.py"  # the checkout's scripts folder; the functions below take [harness].scripts_dir from their root
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
    return " ".join(shlex.quote(str(x)) for x in (sys.executable, client.script(root, "harness_policy_hook.py", _HOOK), "--root", root, "--worktree", worktree, "--scratch", scratch))


def find_claude(*homes) -> str | None:
    """claude on PATH, else <home>/.local/bin/claude for each home given (sudo -u keeps HOME as the owner's, so the caller
    passes the workroot too, #6466); a dangling link is skipped."""
    import shutil
    found = shutil.which("claude")
    if found:
        return found
    for h in homes or (Path.home(),):
        cand = Path(h) / ".local" / "bin" / "claude"
        if cand.is_file() and os.access(cand, os.X_OK):
            return str(cand)
    return None


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


# Reads the prompt file in the pane's own shell: the text is never on tmux's line (claude's own argv still holds it). Every value reaches the shell as a
# positional argument (harness_start shell-quotes each argv word), so a brief or model string is never parsed as shell.
_READ_PROMPT = 'export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=safe.directory GIT_CONFIG_VALUE_0="*"; f=$1; b=$2; shift 2; exec "$@" --append-system-prompt "$(cat "$f")" "$b"'


def prepare(root, worktree, brief: str, scratch, model: str = "sonnet", claude_bin: str = "claude", *, role: str | None = None,
            stack: str | None = None, project: str | None = None) -> list[str]:
    """Write settings.json, mcp.json under `scratch` and the commit-msg hook in the clone; return claude's argv, whose
    --append-system-prompt is the assembled common + role + stack + project (profiles.assemble)."""
    root, worktree, scratch = Path(root), Path(worktree), Path(scratch)
    scratch.mkdir(parents=True, exist_ok=True)
    hook = {"type": "command", "command": _hook_cmd(root, worktree, scratch)}
    handoff = {"hooks": [{"type": "command", "command": " ".join(shlex.quote(str(x)) for x in (sys.executable, client.script(root, "harness_handoff_hook.py", _HANDOFF)))}]}
    settings = {"skipDangerousModePermissionPrompt": True, "hooks": {
        "PreToolUse": [{"matcher": "Bash|Edit|Write|MultiEdit|NotebookEdit", "hooks": [hook]}],
        "PostToolUse": [handoff], "Stop": [handoff]}}
    (scratch / "settings.json").write_text(json.dumps(settings, indent=1))
    # the worker's git must open owner-made trees (the engine repo, the ladder's scratch worktrees) or every call there dies with
    # "dubious ownership" (first real check, 2026-11-01): _READ_PROMPT exports safe.directory=* into the worker's own environment.
    # The worker commits as Claude, never as the jail user (a host name leaked, 2026-11-02): the name and email go in THIS
    # worktree's config, never --global (#6854: a global write made two starts at once race on one file and rewrote every user's identity).
    wt = ["git", "-C", str(worktree)]
    if subprocess.run([*wt, "config", "--get", "extensions.worktreeConfig"], capture_output=True, text=True).stdout.strip() != "true":
        # the one write to the repo's shared config file, once per repo, under a lock named for that repo (two starts in two repos never meet)
        common = subprocess.run([*wt, "rev-parse", "--path-format=absolute", "--git-common-dir"], capture_output=True, text=True, check=True).stdout.strip()
        with journal.Lock("git-config-" + hashlib.sha1(common.encode(), usedforsecurity=False).hexdigest()[:12], what=f"worktreeConfig of {common}"):
            subprocess.run([*wt, "config", "extensions.worktreeConfig", "true"], check=True)
    for k, v in (("user.name", AUTHOR["GIT_AUTHOR_NAME"]), ("user.email", AUTHOR["GIT_AUTHOR_EMAIL"])):
        subprocess.run([*wt, "config", "--worktree", k, v], check=True)  # this worktree's own config.worktree file: no lock
    adapters.require_lane_capable(adapters.ClaudeCode())
    servers, missing = mcp_servers.delivered(root, role=role, stack=stack, project=project)
    for name in missing:
        journal.append("mcp-missing", server=name, role=role, stack=stack, project=project)
    (scratch / "mcp.json").write_text(json.dumps({"mcpServers": servers}))  # with --strict-mcp-config: this file is all the worker gets
    # a linked worktree's .git is a file: ask git where hooks live (the clone's shared hooks dir)
    hooks = subprocess.run(["git", "-C", str(worktree), "rev-parse", "--path-format=absolute", "--git-path", "hooks"],
                           capture_output=True, text=True, check=True).stdout.strip()
    cm = Path(hooks) / "commit-msg"
    cm.parent.mkdir(parents=True, exist_ok=True)
    cm.write_text(f'#!/bin/sh\nexec {shlex.quote(sys.executable)} {shlex.quote(str(client.script(root, "harness_policy_hook.py", _HOOK)))} --root {shlex.quote(str(root))} --commit-msg "$1"\n')
    cm.chmod(cm.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    (scratch / "prompt.md").write_text(profiles.assemble(root, worktree=worktree, scratch=scratch, harness=adapters.ClaudeCode.harness, model=model,
                               role=role, stack=stack, project=project, servers=list(servers)))  # a file, never the text on tmux's line
    claude = [claude_bin, "--dangerously-skip-permissions", "--model", model, "--settings", str(scratch / "settings.json"),
              "--setting-sources", "", "--strict-mcp-config", f"--mcp-config={scratch / 'mcp.json'}"]  # =form: --mcp-config is variadic and would swallow the brief
    if "PYTEST_ADDOPTS" in os.environ:  # #6869: set by queue.real_procs.start for the lane; a window in a running tmux server gets the server's environment, not ours
        claude = ["env", *(f"{k}={os.environ[k]}" for k in ("TMPDIR", "PYTEST_ADDOPTS") if k in os.environ), *claude]
    return ["sh", "-c", _READ_PROMPT, "sh", str(scratch / "prompt.md"), brief, *claude]  # the brief stays the first user message
