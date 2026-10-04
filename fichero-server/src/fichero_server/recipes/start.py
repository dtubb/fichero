"""Start: the first yes. What a saved recipe would run, on how many pages, and what refuses it.

`source/models-chains-and-projects.md` section 11: `source.project.automatic-after-first-yes`,
`source.recipe.makes-a-workflow`, `source.recipe.holds-no-second-copy`, `source.project.stays-local`,
`source.onboard.estimate-before-start`. A recipe runs only as workflows Fichero already ships,
named, never copied: each step's job maps to one shipped workflow, and the step's model reaches it
only where that workflow can honestly take it (a provider/model override; for a Kraken reader,
the `kraken` run override that sets the reading node's reader). A step that cannot be mapped is refused by name, never run with another model.

Pure, except `count_pages`: the Start screen, the Inspector, MCP and the command line all read the
same plan from the engine.
"""
from __future__ import annotations

from typing import Any

from fichero_server.workflows.validation import KRAKEN_READER_PROVIDER

#: job -> the shipped workflow that carries it out, by its name in the store.
WORKFLOW_FOR_JOB = {
    "find-lines": "Detect Segments (Kraken)",
    "read-a-line": "Transcribe (Kraken)",
    "read-a-page": "Transcribe HTR",
    "correct": "Paleographer Review",
}
#: Jobs whose workflow takes the step's model as a run-level provider/model override.
_OVERRIDE_JOBS = frozenset({"read-a-page", "correct"})
#: Per-page token assumptions: the same ones the workflow cost estimate prices with (runner.py).
_TOKENS_IN, _TOKENS_OUT = 1200, 300


def _preset(name: str) -> dict | None:
    from fichero_server.workflows.default_workflows import _load_preset_files

    return next((p for p in _load_preset_files() if p.get("name") == name), None)


def _kraken_reader_for(pin: dict) -> str | None:
    from fichero_server.recipes.cards import kraken_reader_for

    return kraken_reader_for(pin)


def _override(pin: dict) -> tuple[str, str] | None:
    """(provider, model) a step's pin runs as, for a workflow that takes an override."""
    if set(pin) == {"cloud", "model"}:
        return str(pin["cloud"]), str(pin["model"])
    if set(pin) == {"hf", "revision"} and str(pin["hf"]).startswith("mlx-community/"):
        return "omlx", str(pin["hf"])
    return None


def _uses_cloud(step: dict) -> bool:
    return str(step.get("runs_on") or "").startswith("cloud") or "cloud" in (step.get("model") or {})


def plan_start(recipe: dict | None, *, stays_local: bool) -> dict[str, Any]:
    """The workflows Start would run, in order, and every reason it cannot start.

    Returns `{"workflows": [...], "offered": [...], "refusals": [...]}`. Each workflow entry names
    the recipe steps it carries out, the shipped workflow (name and id), and the provider/model
    override it runs with. `offered` lists steps that wait to be offered (train), never run at
    Start (`source.recipe.train-never-automatic`). Start may go ahead only when `refusals` is empty.
    """
    from fichero_server.workflows.default_workflows import preset_workflow_id

    from fichero_server.recipes.recipe import check_recipe

    if not recipe:
        return {"workflows": [], "offered": [], "refusals": ["this project has no recipe yet: run setup first"]}
    workflows: list[dict[str, Any]] = []
    offered: list[str] = []
    refusals: list[str] = []
    for step in recipe.get("steps") or []:
        sid, job = step.get("id", "?"), step.get("job", "")
        label = f"step {sid}"
        if step.get("offered_when"):
            offered.append(sid)
            continue
        if step.get("gap") or not step.get("model"):
            refusals.append(f"{label} has no model: {step.get('gap') or 'none is named'}")
            continue
        if stays_local and _uses_cloud(step):
            refusals.append(f"{label} would send pages off this Mac, and this project keeps its pages here")
            continue
        if step.get("when"):
            refusals.append(f"{label} runs only {sorted(step['when'])}; Start cannot honour a condition yet")
            continue
        name = WORKFLOW_FOR_JOB.get(job)
        if name is None:
            refusals.append(f"{label}: no shipped workflow does the job {job!r} yet")
            continue
        pin = step["model"]
        entry: dict[str, Any] = {"steps": [sid], "job": job, "workflow": name,
                                 "workflow_id": preset_workflow_id(name),
                                 "provider_override": None, "model_override": None,
                                 "runs_on": step.get("runs_on") or "this-mac"}
        if job == "find-lines":
            if pin.get("kraken") != "blla":
                refusals.append(f"{label}: {name} finds lines with Kraken's blla only, not {pin}")
                continue
        elif job == "read-a-line":
            reader = _kraken_reader_for(pin)
            if reader is None:
                refusals.append(f"{label}: the reader {pin} is not in the Kraken catalogue this Mac "
                                "can fetch, so no workflow can read with it")
                continue
            entry["provider_override"], entry["model_override"] = KRAKEN_READER_PROVIDER, reader
            # Kraken finds its own lines before reading them: one run carries both steps.
            if workflows and workflows[-1]["job"] == "find-lines":
                entry["steps"] = workflows.pop()["steps"] + entry["steps"]
        elif job in _OVERRIDE_JOBS:
            override = _override(pin)
            if override is None:
                refusals.append(f"{label}: {name} cannot run the model {pin}")
                continue
            entry["provider_override"], entry["model_override"] = override
        workflows.append(entry)
    # A recipe that does not pass the check never starts (`source.recipe.steps-are-jobs`).
    refusals.extend(check_recipe(recipe))
    return {"workflows": workflows, "offered": offered, "refusals": refusals}


def estimate(workflows: list[dict[str, Any]], pages: int) -> dict[str, Any]:
    """What Start would cost, before anything runs (`source.onboard.estimate-before-start`).

    Local runs cost nothing; a cloud run is priced with the workflow estimate's per-page token
    assumptions. An unpriced model is `None`, never a stand-in zero, and makes the total `None`.
    """
    from fichero_server.workflows.model_comparison import estimate_cost

    rows, total = [], 0.0
    for w in workflows:
        cloud = str(w["runs_on"]).startswith("cloud")
        cost = (estimate_cost(w["model_override"] or "", pages * _TOKENS_IN, pages * _TOKENS_OUT,
                              provider=w["provider_override"] or "") if cloud else 0.0)
        rows.append({"workflow": w["workflow"], "steps": w["steps"], "where": w["runs_on"],
                     "pages": pages, "cost_usd": cost})
        total = None if total is None or cost is None else total + cost
    return {"pages": pages, "runs": rows, "total_cost_usd": total}


def count_pages(db) -> int:
    """Units of work in the project: every page, and every file that has no pages (live material only)."""
    return db.unit_of_work_count()
