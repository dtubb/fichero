"""The small-worker rule (agent-profiles.worker.small): one step per brief, a brief under 120 lines that names its tests,
and a diff bound per role (`diff_bound: N` in `roles/<role>.md`). Plain module; imports nothing from the rest of the engine."""
from __future__ import annotations

import re

CAP = 120  # lines in a brief


def step_ids(issues: list[dict]) -> list[str]:
    """The distinct `Step: N.M` lines of the issues' bodies, in order."""
    return list(dict.fromkeys(m for i in issues for m in re.findall(r"(?m)^Step:\s*(\S+)", i.get("body") or "")))


def brief_problems(text: str, issues: list[dict], *, need_tests: bool) -> list[str]:
    """Why a brief is refused: more than one step, more than CAP lines, and (for a code project) no named test path."""
    from fichero_builder import brief_tool  # brief_tool.cluster calls this module

    out = []
    if len(steps := step_ids(issues)) > 1:
        out.append(f"the cluster spans {len(steps)} steps ({', '.join(steps)}); a worker gets one step")
    if (n := len(text.splitlines())) > CAP:
        out.append(f"the brief is {n} lines; the cap is {CAP}")
    if need_tests and not any(brief_tool._TEST.search(p) for p, _ in brief_tool._PATH.findall(text)):
        out.append("the brief names no test file by path; a code project's step names its tests")
    return out


def diff_bound(role_text: str) -> int | None:
    """The role file's `diff_bound: N` line, or None."""
    m = re.search(r"(?m)^diff_bound:\s*(\d+)\s*$", role_text)
    return int(m.group(1)) if m else None
