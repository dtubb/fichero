"""What a live block carries so its bar is drawn from the list read (`activity.summary.stage-counts`, `.eta-basis`, `.cost-so-far`, #5960):
per Set Up stage its state and pages, the time left with its basis, and the cost so far. Pure over the run's status, never worked out in the app."""
from __future__ import annotations

from typing import Any

#: The states a stage shows as, most telling first (a stage several runs carry reads as its most telling one).
_ORDER = ("failed", "running", "waiting", "partial", "not run", "done")
THIS_RUNS_PACE = "this run's pace"


def _state(states: list[str]) -> str:
    """One of done, partial, running, waiting, skipped, failed, not run: failed, running, waiting, partial, not run, then done."""
    for name in _ORDER:
        if name in states or (name == "failed" and "interrupted" in states) or (name == "not run" and "cancelled" in states):
            return name
    return "done" if all(s in ("done", "completed", "complete", "finished") for s in states) else "waiting"


def stage_counts(status: dict[str, Any]) -> list[dict[str, Any]]:
    """`[{stage, title, state, done, failed, total}]` in Set Up's order: each stage the run ran, or the plan skipped (state `skipped`)."""
    from fichero_server.recipes.stages import STAGES, stage_of

    out = []
    skipped = [s.get("step") for s in status.get("skipped") or []]
    for stage in STAGES:
        runs = [r for r in status.get("steps") or []
                if any((stage_of(j, translation=bool(r.get("translation"))) or None) is stage
                       for j in [*(r.get("steps") or []), r.get("job")] if j)]
        skip = [s for s in skipped if s and stage_of(s) is stage]
        if not runs and not skip:
            continue
        accounts = [r["account"] for r in runs if r.get("account") is not None]
        biggest = max(accounts, key=lambda a: a.pages_total, default=None)
        out.append({"stage": stage.id, "title": stage.title, "state": _state([r["state"] for r in runs]) if runs else "skipped",
                    "done": biggest.pages_done if biggest else 0, "failed": biggest.pages_failed if biggest else 0,
                    "total": biggest.pages_total if biggest else 0})
    return out


def eta(status: dict[str, Any]) -> tuple[float | None, str | None]:
    """(seconds left, its basis) for the running stage: the run account's own pace, so the basis is `this run's pace`; none until a page is done.
    A kind's median per item (the basis for work with no pace of its own yet) is not worked out here."""
    running = next((s for s in status.get("steps") or [] if s.get("state") == "running" and s.get("account") is not None), None)
    left = running["account"].estimate_seconds_left if running else None
    return (left, THIS_RUNS_PACE) if left is not None else (None, None)


def cost_so_far(status: dict[str, Any]) -> float | None:
    """The run's cloud calls in dollars so far, summed over its stages; none when no stage has a priced call (a local run costs nothing to show)."""
    costs = [s["timing"].cost_usd for s in status.get("steps") or [] if s.get("timing") is not None and s["timing"].cost_usd]
    return round(sum(costs), 4) if costs else None
