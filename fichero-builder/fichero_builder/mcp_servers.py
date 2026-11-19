"""The MCP servers a worker gets (agent-profiles.mcp.required): jcodemunch and jdocmunch always, then the intersection of what the
role and stack ask (the `tools:` line of the role file and the stack file) and what the project provides (the `tools:` line of its
project file). A stack's `tools:` line replaces the role's whole list. A required server with no wrapper, or an optional one the
project provides with no `[mcp.<name>]` command in harness.toml, is an AdapterRefused; a server asked for and not provided is
returned as missing for the caller to journal.
"""
from __future__ import annotations

import re
import tomllib
from pathlib import Path

from fichero_builder import codemap
from fichero_builder.adapters import AdapterRefused
from fichero_builder.profiles import AGENTS

REQUIRED = tuple(codemap.INDEX_SERVERS)


def _tools(path: Path) -> list[str] | None:
    """The names on a prompt file's `tools:` line; None when the file or the line is absent."""
    m = re.search(r"^tools:[ \t]*(.*)$", path.read_text(), re.M) if path.is_file() else None
    return None if m is None else [t.strip() for t in m.group(1).split(",") if t.strip()]


def wanted(agents: Path, role: str | None, stack: str | None) -> list[str]:
    from_stack = _tools(agents / "stacks" / f"{stack}.md") if stack else None
    if from_stack is not None:
        return from_stack
    return (_tools(agents / "roles" / f"{role}.md") if role else None) or []


def delivered(root, *, role=None, stack=None, project=None, agents_dir=None) -> tuple[dict[str, dict], list[str]]:
    """({server name: its mcp.json entry}, names asked for that the project does not provide)."""
    agents = Path(agents_dir) if agents_dir else AGENTS
    servers: dict[str, dict] = {}
    for name in REQUIRED:
        w = codemap.wrapper(root, name)
        if not w:
            raise AdapterRefused(f"{name} is required for every worker and has no wrapper under the workroot: set [jail].{codemap.INDEX_SERVERS[name][0]} "
                                 "to the install and let the owner side provide it")
        servers[name] = {"type": "stdio", "command": w, "args": [], "env": {}}
    provides = (_tools(agents / "projects" / project / "project.md") if project else None) or []
    commands = tomllib.loads((Path(root) / "harness.toml").read_text()).get("mcp", {})
    missing = []
    for name in wanted(agents, role, stack):
        if name in REQUIRED:
            continue
        if name not in provides:
            missing.append(name)
        elif name not in commands:
            raise AdapterRefused(f"project provides {name} but harness.toml has no [mcp.{name}] command")
        else:
            servers[name] = {"type": "stdio", "command": commands[name]["command"], "args": list(commands[name].get("args", [])), "env": {}}
    return servers, missing
