"""Worker prompt assembly (agent-profiles.prompt.assembly, #6623): common + role + stack + project from `agents/`, with the run facts.

Common comes first and carries the `[policy]` reasons and the trailer line; a role, stack or project named with no file is a
ProfileError (a question for a person), never a silent skip. A worktree's own CLAUDE.md and the like are never read here.
"""
from __future__ import annotations

import re
import tomllib
from pathlib import Path

AGENTS = Path(__file__).resolve().parents[1] / "agents"
# a task id, a commit sha, a date: a prompt is project-free and timeless
_PRIVATE = (r"#\d{3,}", r"\b[0-9a-f]{9,40}\b", r"\b20\d\d-\d\d-\d\d\b")


class ProfileError(Exception):
    pass


def trailer(model: str, harness: str) -> str:
    return f"Written-By: {model} using {harness} using Fichero Builder"


def private_text(text: str, boundary: list[str]) -> list[str]:
    """Every match of a `[land].boundary` pattern or a task id, sha or date in `text`."""
    return [m.group(0) for pat in (*boundary, *_PRIVATE) for m in re.finditer(pat, text)]


def _part(agents: Path, rel: str) -> str:
    f = agents / rel
    if not f.is_file():
        raise ProfileError(f"no prompt file {rel} in {agents}: a question for a person, not a fallback")
    return f.read_text().rstrip() + "\n"


def assemble(root, *, worktree, scratch, harness: str, model: str, role: str | None = None, stack: str | None = None,
             project: str | None = None, agents_dir: Path | None = None) -> str:
    agents = Path(agents_dir) if agents_dir else AGENTS
    toml = Path(root) / "harness.toml"
    cfg = tomllib.loads(toml.read_text()) if toml.is_file() else {}
    policy = "\n".join(f"  - `{r['re']}`: {r['reason']}" for r in cfg.get("policy", {}).get("rules", []))
    common = (_part(agents, "common/common.md").replace("{{WORKTREE}}", str(worktree)).replace("{{SCRATCH}}", str(scratch))
              .replace("{{POLICY}}", policy).replace("{{TRAILER}}", trailer(model, harness)))
    rels = (role and f"roles/{role}.md", stack and f"stacks/{stack}.md", project and f"projects/{project}/project.md")
    return "\n".join([common, *[_part(agents, rel) for rel in rels if rel]])
