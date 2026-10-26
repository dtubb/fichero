"""The pipeline as data (pipeline.pipeline-as-data): the profile's [[steps]] name each step of an item, what it reads
and writes, where an exit code sends it, and its caps. `validate` runs when a profile loads, so a broken pipeline
refuses before anything starts; `route` is the whole of the runner's routing: no model call decides where an item goes.
Ideas from Microsoft Conductor (steps, routes on outcome, explicit inputs/outputs, iteration caps), not its code."""
from __future__ import annotations

KINDS = ("script", "model", "manual")  # manual: the maintainer or the manager lands it


def validate(steps: list[dict]) -> list[str]:
    """→ the problems; empty means the pipeline can run."""
    errs, names = [], [s.get("name") for s in steps]
    if not steps:
        return ["no steps declared"]
    if len(set(names)) != len(names):
        errs.append("step names repeat")
    have = {"issue"}  # what exists before the first step
    for i, s in enumerate(steps):
        n = s.get("name", f"#{i}")
        if s.get("kind") not in KINDS:
            errs.append(f"{n}: kind must be one of {', '.join(KINDS)}")
        if s.get("kind") == "script" and not s.get("timeout_s"):
            errs.append(f"{n}: a script step needs timeout_s")
        for need in s.get("in", []):
            if need not in have:
                errs.append(f"{n}: reads {need}, which no earlier step writes")
        have |= set(s.get("out", []))
        for edge in ("on_ok", "on_fail"):
            to = s.get(edge)
            if to is None:
                if edge == "on_ok":
                    errs.append(f"{n}: on_ok is required")
            elif to != "end" and to not in names:
                errs.append(f"{n}: {edge} names {to}, which is not a step")
            elif to != "end" and names.index(to) <= i and not steps[names.index(to)].get("max_iter"):
                errs.append(f"{n}: {edge} loops back to {to}, which has no max_iter")
    reach, todo = set(), names[:1]
    while todo:
        cur = todo.pop()
        if cur != "end" and cur not in reach and cur in names:
            reach.add(cur)
            todo += [steps[names.index(cur)].get(e) for e in ("on_ok", "on_fail") if steps[names.index(cur)].get(e)]
    errs += [f"{n}: unreachable from {names[0]}" for n in names if n not in reach]
    return errs


def route(steps: list[dict], name: str, exit_code: int) -> str:
    """The next step (or "end") after `name` finished with `exit_code`: 0 → on_ok, else on_fail (default: stop at the
    step itself, so a failure with no declared route is never silently skipped past)."""
    s = next(x for x in steps if x["name"] == name)
    return s["on_ok"] if exit_code == 0 else s.get("on_fail", name)
