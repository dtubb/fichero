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


def _iso(value: Any) -> Optional[str]:
    return ensure_utc(value).isoformat() if value else None


def run_as_step(run: dict[str, Any], name: str) -> dict[str, Any]:
    """A workflow run that is one step of a recipe run, as a step row: its workflow's name, the model and place of its
    first step that has one, and its own pages, time, tokens and cost."""
    steps = run["steps"]
    return {"id": run["id"], "name": name, "model": next((s["model"] for s in steps if s["model"]), None),
            "place": next((s["place"] for s in steps if s["place"]), None), "state": run["status"],
            "pages_done": run["pages_done"], "pages_failed": run["pages_failed"], "seconds": run["seconds"],
            "seconds_per_page": run["seconds_per_page"], "tokens": sum(s["tokens"] for s in steps),
            "cost_usd": run["cost_usd"], "cost_per_page": run["cost_per_page"], "_started": run["started_at"]}


def _recipe_run(db: "Database", job_id: str) -> dict[str, Any]:
    """A recipe run's own row, from its job: its state and times; its steps are filled in by `recipes`."""
    row = db.execute_fetchone("SELECT state, created_at, started_at, finished_at FROM jobs WHERE id = ?", [job_id])
    state, created, started, finished = row if row else ("done", None, None, None)
    return {"id": job_id, "status": state, "started_at": _iso(started or created), "ended_at": _iso(finished),
            "scope": None, "steps": [], "_pages": []}


def _close_recipe_run(run: dict[str, Any]) -> dict[str, Any]:
    """A recipe run's rates over its steps, the steps in the order they ran."""
    run["steps"].sort(key=lambda s: s.pop("_started") or "")
    done = sum(s["pages_done"] for s in run["steps"])
    failed = sum(s["pages_failed"] for s in run["steps"])
    costs = [s["cost_usd"] for s in run["steps"] if s["cost_usd"] is not None]
    seconds = [s["seconds"] for s in run["steps"] if s["seconds"] is not None]
    run.update({"pages_done": done, "pages_failed": failed, "failed_pct": _rate(100.0 * failed, done + failed),
                "seconds": round(sum(seconds), 1) if seconds else None, "seconds_per_page": _median(run["_pages"]),
                "cost_usd": round(sum(costs), 4) if costs else None,
                "cost_per_page": _rate(sum(costs), done) if costs else None})
    return run


def recipes(db: "Database", *, days: int = 30) -> list[dict[str, Any]]:
    """Every recipe run in the last `days`, by recipe (newest run first), each with its runs and their steps, and the
    recipe's rates over its runs. A recipe with runs of no pages still lists them (a run that failed before any page).

    A recipe run's step runs are its steps (owner 2026-11-16: "they're steps and should be in order; the recipe is the
    project"): each workflow run whose job hangs under a `run-a-recipe` job is one step row of that recipe run, in the
    order they ran, and the recipe runs list under the project's recipe. A workflow run on its own is its own recipe."""
    from fichero_server.db import activity_records as records
    from fichero_server.execution import jobs as job_queue

    job_queue._ensure(db)
    since = (utc_now() - timedelta(days=days)).replace(tzinfo=None)
    try:
        rows = records.runs_started_since(db, since, RUNS_READ)
    except Exception:  # noqa: BLE001 -- a project with no run records yet lists none
        return []
    by_recipe: dict[str, dict[str, Any]] = {}
    recipe_runs: dict[str, dict[str, Any]] = {}
    for thread_id, workflow_id, name, status, started, completed in rows:
        run = {"id": thread_id, "status": status, "started_at": _iso(started), "completed_at": _iso(completed)}
        tree = job_queue.tree(db, thread_id)
        parent = db.execute_fetchone("SELECT p.id, p.kind FROM jobs c JOIN jobs p ON p.id = c.parent_id WHERE c.id = ?",
                                     [thread_id])
        if parent and parent[1] == RECIPE_RUN_KIND:
            key = project_recipe_name(db)
            recipe = by_recipe.setdefault(key, {"id": f"recipe:{key}", "name": key, "runs": []})
            if parent[0] not in recipe_runs:
                recipe_runs[parent[0]] = _recipe_run(db, parent[0])
                recipe["runs"].append(recipe_runs[parent[0]])
            as_run = run_row(run, tree)
            recipe_runs[parent[0]]["_pages"] += as_run.pop("_pages")
            recipe_runs[parent[0]]["steps"].append(run_as_step(as_run, name or workflow_id or "Step"))
            continue
        key = name or workflow_id or "Workflow"
        recipe = by_recipe.setdefault(key, {"id": workflow_id or key, "name": key, "runs": []})
        recipe["runs"].append(run_row(run, tree))
    for run in recipe_runs.values():
        _close_recipe_run(run)
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
