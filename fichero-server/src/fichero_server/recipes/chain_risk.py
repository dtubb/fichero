"""What feeds each model step and what it feeds, in one line per step (`designer.how.chain-risk-on-ready`, #6052).

Worked out from the job registry's `takes` and `gives`, never written by hand: an early error carries through the chain, so the earliest model
steps say "check first". Pure."""
from __future__ import annotations

from typing import Any

from fichero_server.recipes.jobs import get_job

#: How many of a recipe's earliest model steps say "check first".
CHECK_FIRST = 2
#: The picture is not something a step "found": a step taking only it has nothing upstream to blame.
_PICTURE = {"page_image", "rendition"}


def _meets(takes: frozenset[str], gives: frozenset[str]) -> set[str]:
    wanted = {alt for t in takes for alt in t.split("|")}
    return (wanted & gives) - _PICTURE


def _list(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def lines(job_ids: list[str]) -> list[dict[str, Any]]:
    """`[{job, line, check_first}]` for each step of the recipe (in order) that needs a model."""
    jobs = [j for j in (get_job(i) for i in job_ids) if j is not None]
    out: list[dict[str, Any]] = []
    for index, job in enumerate(jobs):
        if not job.needs_a_model:
            continue
        before = [j.name for j in jobs[:index] if j.id != job.id and _meets(job.takes, j.gives)]
        after = [j.name for j in jobs[index + 1:] if j.id != job.id and _meets(j.takes, job.gives)]
        parts = []
        if before:
            parts.append(f"{job.name} takes what {_list(before)} found")
        if after:
            parts.append(f"{_list(after)} {'takes' if len(after) == 1 else 'take'} what {job.name} wrote")
        out.append({"job": job.id, "line": "; ".join(parts) + "." if parts else f"{job.name} works from the pages themselves.", "check_first": False})
    for row in out[:CHECK_FIRST]:
        row["check_first"] = True
    return out
