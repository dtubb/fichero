"""The Activity window's Recipes view (`activity.window.recipes`, decision 37, #6588; the owner 2026-11-15: "much more granular
information … so we can see what recipes worked").

Each recipe (a workflow, by name) with its runs under it and each run's steps under that, with rates that compare: pages
done and failed, failed %, seconds a page (the median of its pages' own times), cost a page, and each step's model and place.
All read from what is kept: the run records and each run's job tree (`jobs.tree`: its steps, their pages, their calls'
usage). Nothing recorded anew.
"""

from __future__ import annotations

import statistics
from datetime import timedelta
from typing import TYPE_CHECKING, Any, Optional

from fichero_server.core.timeutil import ensure_utc, utc_now

if TYPE_CHECKING:
    from fichero_server.db import Database

#: How many of the newest runs the view reads.
RUNS_READ = 200


def _page_seconds(step: dict[str, Any]) -> list[float]:
    """The seconds of each page a step did (its done leaf rows), for the median."""
    return [float(c["seconds"]) for c in step.get("children") or []
            if c.get("state") == "done" and isinstance(c.get("seconds"), (int, float)) and not c.get("children")]


def _model_of(step: dict[str, Any]) -> Optional[str]:
    """The model a step ran: its own, else the first of its pages'."""
    if step.get("model"):
        return step["model"]
    return next((c["model"] for c in step.get("children") or [] if c.get("model")), None)


def _place_of(step: dict[str, Any]) -> Optional[str]:
    """Where its calls went, the place most of them did; None when it made none."""
    places = step.get("places") or {}
    return max(places, key=places.get) if places else None


#: The kind of a recipe run's own job: its step runs hang under it.
RECIPE_RUN_KIND = "run-a-recipe"


def project_recipe_name(db: "Database") -> str:
    """The project's recipe reads as the project (owner 2026-11-16: "the recipe is the project"): its package's name."""
    from pathlib import Path

    folder = Path(str(getattr(db, "path", "") or "")).parent
    return folder.stem or "This project's recipe"


def recipe_of_run(db: "Database", run_id: str, cache: dict[str, str] | None = None) -> str:
    """The recipe a workflow run belongs to: the project's recipe when the run is a step of a recipe run, else the
    workflow it ran, by name. The graph by recipe and the Recipes view group by this one answer."""
    if cache is not None and run_id in cache:
        return cache[run_id]
    from fichero_server.db import activity_records as records
    from fichero_server.execution import jobs as job_queue

    if job_queue.parent_kind(db, run_id) == RECIPE_RUN_KIND:
        name = project_recipe_name(db)
    else:
        row = db.execute_fetchone(f"SELECT workflow_name, workflow_id FROM {records.RUNS} WHERE id = ?", [run_id])
        name = (row[0] or row[1]) if row else None
        name = name or "Workflow"
    if cache is not None:
        cache[run_id] = name
    return name


def _rate(numerator: float, denominator: int) -> Optional[float]:
    return round(numerator / denominator, 4) if denominator else None


def _median(values: list[float]) -> Optional[float]:
    return round(statistics.median(values), 1) if values else None


def step_row(step: dict[str, Any]) -> dict[str, Any]:
    pages = _page_seconds(step)
    done, failed = int(step.get("done") or 0), int(step.get("failed") or 0)
    cost = step.get("cost_usd")
    return {"id": step["id"], "name": step.get("display_name") or step.get("name") or "Step", "model": _model_of(step),
            "place": _place_of(step), "state": step.get("state"), "pages_done": done, "pages_failed": failed,
            "seconds": step.get("seconds"), "seconds_per_page": _median(pages), "tokens": int(step.get("tokens") or 0),
            "cost_usd": cost, "cost_per_page": _rate(cost, done) if cost is not None else None}


def run_row(run: dict[str, Any], tree: Optional[dict[str, Any]]) -> dict[str, Any]:
    steps = [step_row(s) for s in (tree or {}).get("children") or []]
    pages: list[float] = []
    for step in (tree or {}).get("children") or []:
        pages += _page_seconds(step)
    done = int((tree or {}).get("done") or 0)
    failed = int((tree or {}).get("failed") or 0)
    cost = (tree or {}).get("cost_usd")
    return {"id": run["id"], "status": run["status"], "started_at": run["started_at"], "ended_at": run["completed_at"],
            "scope": run.get("scope"), "pages_done": done, "pages_failed": failed,
            "failed_pct": _rate(100.0 * failed, done + failed), "seconds": (tree or {}).get("seconds"),
            "seconds_per_page": _median(pages), "cost_usd": cost, "cost_per_page": _rate(cost, done) if cost is not None else None,
            "steps": steps, "_pages": pages}


def recipes(db: "Database", *, days: int = 30) -> list[dict[str, Any]]:
    """Every recipe run in the last `days`, by recipe (newest run first), each with its runs and their steps, and the
    recipe's rates over its runs. A recipe with runs of no pages still lists them (a run that failed before any page)."""
    from fichero_server.db import activity_records as records
    from fichero_server.execution import jobs as job_queue

    job_queue._ensure(db)
    since = (utc_now() - timedelta(days=days)).replace(tzinfo=None)
    try:
        rows = records.runs_started_since(db, since, RUNS_READ)
    except Exception:  # noqa: BLE001 -- a project with no run records yet lists none
        return []
    by_recipe: dict[str, dict[str, Any]] = {}
    for thread_id, workflow_id, name, status, started, completed in rows:
        run = {"id": thread_id, "status": status, "started_at": ensure_utc(started).isoformat() if started else None,
               "completed_at": ensure_utc(completed).isoformat() if completed else None}
        tree = job_queue.tree(db, thread_id)
        key = name or workflow_id or "Workflow"
        recipe = by_recipe.setdefault(key, {"id": workflow_id or key, "name": key, "runs": []})
        recipe["runs"].append(run_row(run, tree))
    out = []
    for recipe in by_recipe.values():
        runs = recipe["runs"]
        done = sum(r["pages_done"] for r in runs)
        failed = sum(r["pages_failed"] for r in runs)
        pages = [p for r in runs for p in r.pop("_pages")]
        costs = [r["cost_usd"] for r in runs if r["cost_usd"] is not None]
        out.append({**recipe, "run_count": len(runs), "pages_done": done, "pages_failed": failed,
                    "failed_pct": _rate(100.0 * failed, done + failed), "seconds_per_page": _median(pages),
                    "cost_usd": round(sum(costs), 4) if costs else None,
                    "cost_per_page": _rate(sum(costs), done) if costs else None,
                    "last_run": runs[0]["started_at"] if runs else None})
    return out
