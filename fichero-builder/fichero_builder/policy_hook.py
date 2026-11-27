"""The policy hook: refuse a forbidden worker action with a reason (dev-workflows.run.policy-hook, #6116).

Plain functions behind `scripts/harness_policy_hook.py` (a Claude Code PreToolUse hook) and a git commit-msg hook.
Rules come from the project's harness.toml [policy]. Fast feedback, not a security boundary: shell text can be
rewritten, so the credential/OS layer (run.land-gate) and the landing guards hold the hard rules. Imports nothing
from the rest of the engine.
ponytail: a second pytest (lock file) and a paid call without a grant are not rules here yet; the lock needs a
PostToolUse release, grants are Step 1.6.
"""

from __future__ import annotations

import fnmatch
import re
import subprocess
import tomllib
from pathlib import Path
from typing import Any

_WRITE_TOOLS = {"Edit", "Write", "NotebookEdit", "MultiEdit"}
_CD = re.compile(r"(?:^|[;&|]\s*|&&\s*)cd\s+(\"[^\"]+\"|'[^']+'|\S+)")
_ARG = r"(\"[^\"]+\"|'[^']+'|[^\s;&|]+)"
# dev-workflows.run.loop-machine-checked: a git verb that throws work away, pointed at another tree
_GIT_AT = re.compile(r"\bgit\s+(?:-c\s+\S+\s+)*(?:-C\s+|--work-tree[=\s]\s*|--git-dir[=\s]\s*)" + _ARG)
_DISCARD = re.compile(r"\b(?:reset\s+(?:\S+\s+)*--hard|checkout\s+(?:\S+\s+)*--(?=\s|$)|clean\s+(?:\S+\s+)*-\w*f|stash)")
_WRITE_TO = re.compile(r"(?:>>?|\btee\s+(?:-a\s+)?)\s*" + _ARG)


def load(root: str | Path) -> dict[str, Any]:
    return tomllib.loads((Path(root) / "harness.toml").read_text()).get("policy", {})


def _inside(p: Path, bases: list[Path]) -> bool:
    p = Path(__import__("os").path.normpath(p))
    return any(p == b or b in p.parents for b in bases)


_COMMIT = re.compile(r"\bgit\s+(?:-c\s+\S+\s+)*commit\b")


def changed_lines(worktree: Path, base: str, generated: list[str]) -> int:
    """Lines added plus deleted between `base` and the working tree (`git diff --numstat`), paths matching a `generated` glob left out."""
    r = subprocess.run(["git", "-C", str(worktree), "diff", "--numstat", base], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"git diff --numstat {base} failed: {r.stderr.strip()[:200]}")
    n = 0
    for row in r.stdout.splitlines():
        add, dele, name = row.split("\t", 2)
        if add != "-" and not any(fnmatch.fnmatch(name, g) for g in generated):  # "-" is a binary file
            n += int(add) + int(dele)
    return n


def _bound_reason(bound: dict[str, Any], worktree: Path, scratch: Path) -> str | None:
    """agent-profiles.worker.small: a `git commit` over the role's bound is refused once with a tell; the next one writes
    the file bound-park in the scratch folder and is refused as parked."""
    try:
        n = changed_lines(worktree, bound["base"], bound.get("generated", []))
    except RuntimeError as e:
        return f"the diff bound cannot be counted: {e}"
    if n <= bound["lines"]:
        return None
    told, park = scratch / "bound-told", scratch / "bound-park"
    msg = f"this step's diff is {n} changed lines (generated files excluded); the bound for your role is {bound['lines']}"
    if not told.exists():
        scratch.mkdir(parents=True, exist_ok=True)
        told.write_text(f"{n}\n")
        return f"{msg}. Cut the step to what its acceptance needs, or write `WAITING: <one line>` and stop; the next commit past the bound parks the step."
    park.write_text(f"{msg}; told once, over it again at {n}\n")
    return f"{msg}: parked with a question. Write `WAITING: the diff is over the bound` and stop."


def check(event: dict[str, Any], cfg: dict[str, Any], *, worktree: Path, scratch: Path, bound: dict[str, Any] | None = None) -> str | None:
    """None to allow; else the reason the worker is shown. `bound` is {lines, base, generated}: the role's diff bound."""
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
        if bound and _COMMIT.search(cmd) and (why := _bound_reason(bound, worktree, scratch)):
            return why
        for m in _CD.finditer(cmd):
            target = Path(m.group(1).strip("\"'")).expanduser()
            if target.is_absolute() and not _inside(target, bases):
                return f"cd {target} goes outside the worktree and scratch path"
        for seg in re.split(r"&&|\|\||[;|]", cmd):
            at = _GIT_AT.search(seg)
            if at and _DISCARD.search(seg) and not _inside(Path(at.group(1).strip("\"'")).expanduser(), bases):
                return f"{at.group(1)} is another tree: reset --hard, checkout --, clean -f and stash run only in the worker's own worktree"
        for m in _WRITE_TO.finditer(cmd):  # ponytail: shell text only; a script that writes is the OS layer's (run.land-gate)
            target = Path(m.group(1).strip("\"'")).expanduser()
            if target.is_absolute() and str(target) != "/dev/null" and not _inside(target, bases):
                return f"a write to {target} is outside the worktree and scratch path"
    return None


DEFAULT_PRODUCT = "Fichero Builder"  # [policy].product


def commit_msg_problems(msg: str, cfg: dict[str, Any]) -> list[str]:
    """Exactly one trailer, `Written-By: <MODEL> using <HARNESS> using <[policy].product>` (agent-profiles.trailer.one-line); no
    `Co-Authored-By`, no `Directed-By`, no second `Written-By`. The same rule for every harness: each runs `git commit`."""
    lines = [ln.rstrip() for ln in msg.splitlines()]
    product = cfg.get("product", DEFAULT_PRODUCT)
    shape = f"Written-By: <MODEL> using <HARNESS> using {product}"
    out = [f"the commit message carries {ln.split(':')[0]}; the one trailer is {shape}"
           for ln in lines if re.match(r"(?i)(co-authored-by|directed-by):", ln)]
    written = [ln for ln in lines if ln.lower().startswith("written-by:")]
    if len(written) != 1:
        out.append(f"the commit message needs exactly one Written-By trailer, `{shape}`; it has {len(written)}")
    elif not re.match(rf"^Written-By: \S.* using \S.* using {re.escape(product)}$", written[0]):
        out.append(f"the Written-By trailer must read `{shape}`; got {written[0]!r}")
    return out


def bound_for(root: str | Path, lines: int, base: str) -> dict[str, Any]:
    """The hook's `bound`: the role's line count, the base ref, and harness.toml's `[check].generated` paths."""
    cfg = tomllib.loads((Path(root) / "harness.toml").read_text())
    return {"lines": lines, "base": base, "generated": cfg.get("check", {}).get("generated", [])}
