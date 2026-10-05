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
    "split-pages": "Split Pages",
    "find-lines": "Detect Segments (Kraken)",
    "read-a-line": "Transcribe (Kraken)",
    "read-a-page": "Transcribe HTR",
    "correct": "Paleographer Review",
    "find-names-tag-words": "2 · Extract Entities",
    "find-statements": "3 · Extract SVO → Claims",
}
#: Kraken finds the lines and the step's vision model (a cloud or MLX pin) reads each one (the line reader).
READ_LINES_WITH_A_MODEL = "Read Lines (Kraken lines, vision model)"
#: Jobs whose workflow takes the step's model as a run-level provider/model override.
_OVERRIDE_JOBS = frozenset({"read-a-page", "correct", "find-names-tag-words", "find-statements"})
#: Jobs carried out by a card that is not a workflow: the check job (`source.check.*`) and the project's
#: synced folder (`source.sync.*`).
OTHER_CARDS = {"check": "check", "export": "export", "publish": "publish"}
#: Jobs that need no model.
_NO_MODEL_JOBS = frozenset({"export", "publish"})
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
    if "spacy" in pin and set(pin) <= {"spacy", "version"}:  # names: spaCy is the entity tool's local reader
        return "spacy", str(pin["spacy"])
    if set(pin) == {"hf", "revision"} and str(pin["hf"]).startswith("mlx-community/"):
        return "omlx", str(pin["hf"])
    return None


def _uses_cloud(step: dict) -> bool:
    return str(step.get("runs_on") or "").startswith("cloud") or "cloud" in (step.get("model") or {})


def plan_start(recipe: dict | None, *, stays_local: bool, only: set[str] | None = None) -> dict[str, Any]:
    """What Start would run, in order, what it skips and why, and what refuses it outright.

    Returns `{"runs": [...], "workflows": [...], "skipped": [...], "offered": [...], "refusals": [...]}`.
    `runs` are the cards Start runs in order: a shipped workflow (name, id, provider/model override), a
    check run (its layer and checker), or the project's synced folder (its folder and formats); `workflows`
    is the workflow runs among them. A step that cannot run is SKIPPED with its reason, and the others
    still run (`source.recipe.step-skipped-says-why`). `offered` lists steps that wait to be offered
    (train), never run at Start (`source.recipe.train-never-automatic`). Start may go ahead only when
    `refusals` is empty: a recipe that fails the recipe check, or one with nothing to run. `only` limits
    the plan to those step ids: the jobs a layer added later proposes for the material already there
    (`source.onboard.add-layer`); the whole recipe is still checked.
    """
    from fichero_server.workflows.default_workflows import preset_workflow_id

    from fichero_server.recipes.recipe import check_recipe

    if not recipe:
        return {"runs": [], "workflows": [], "skipped": [], "offered": [],
                "refusals": ["this project has no recipe yet: run setup first"]}
    runs: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    offered: list[str] = []

    def skip(sid: str, why: str) -> None:
        skipped.append({"step": sid, "why": why})

    for step in recipe.get("steps") or []:
        sid, job = step.get("id", "?"), step.get("job", "")
        label = f"step {sid}"
        if only is not None and sid not in only:
            continue
        if step.get("offered_when"):
            offered.append(sid)
            continue
        if job not in _NO_MODEL_JOBS and (step.get("gap") or not step.get("model")):
            skip(sid, f"{label} has no model: {step.get('gap') or 'none is named'}")
            continue
        if stays_local and _uses_cloud(step):
            skip(sid, f"{label} would send pages off this Mac, and this project keeps its pages here")
            continue
        if step.get("when"):
            skip(sid, f"{label} runs only {sorted(step['when'])}; Start cannot honour a condition yet")
            continue
        pin = step.get("model") or {}
        settings = step.get("settings") or {}
        runs_on = step.get("runs_on") or "this-mac"
        if job in OTHER_CARDS:
            entry: dict[str, Any] = {"steps": [sid], "job": job, "card": OTHER_CARDS[job], "runs_on": runs_on}
            if job == "check":
                override = _override(pin)
                if override is None:
                    skip(sid, f"{label}: the check job cannot run the model {pin}")
                    continue
                entry.update(layer=settings.get("layer", "readings"), provider=override[0], model=override[1],
                             prompt=step.get("prompt"))
            elif job == "publish":
                if not settings.get("where"):
                    skip(sid, f"{label} names no folder (`where`) to publish the site into")
                    continue
                entry.update(folder=settings["where"])
            else:
                entry.update(folder=settings.get("folder"), formats=list(settings.get("formats") or []))
            runs.append(entry)
            continue
        name = WORKFLOW_FOR_JOB.get(job)
        if name is None:
            skip(sid, f"{label}: no card runs the job {job!r} yet")
            continue
        entry = {"steps": [sid], "job": job, "card": "workflow", "workflow": name,
                 "workflow_id": preset_workflow_id(name), "provider_override": None, "model_override": None,
                 "runs_on": runs_on}
        if job == "split-pages":
            if pin.get("builtin") != "page-splitter":
                skip(sid, f"{label}: {name} cuts pages with the built-in page splitter only, not {pin}")
                continue
        elif job == "find-lines":
            if pin.get("kraken") != "blla":
                skip(sid, f"{label}: {name} finds lines with Kraken's blla only, not {pin}")
                continue
        elif job == "read-a-line" and _override(pin) is not None:
            # A vision model reads the lines Kraken found: the step's own model, as the run's override.
            entry["workflow"], entry["workflow_id"] = READ_LINES_WITH_A_MODEL, preset_workflow_id(READ_LINES_WITH_A_MODEL)
            entry["provider_override"], entry["model_override"] = _override(pin)
            if runs and runs[-1]["job"] == "find-lines":
                entry["steps"] = runs.pop()["steps"] + entry["steps"]
        elif job == "read-a-line":
            reader = _kraken_reader_for(pin)
            if reader is None:
                skip(sid, f"{label}: the reader {pin} is not in the Kraken catalogue this Mac "
                          "can fetch, so no workflow can read with it")
                continue
            entry["provider_override"], entry["model_override"] = KRAKEN_READER_PROVIDER, reader
            # Kraken finds its own lines before reading them: one run carries both steps.
            if runs and runs[-1]["job"] == "find-lines":
                entry["steps"] = runs.pop()["steps"] + entry["steps"]
        elif job in _OVERRIDE_JOBS:
            override = _override(pin)
            if override is None:
                skip(sid, f"{label}: {name} cannot run the model {pin}")
                continue
            entry["provider_override"], entry["model_override"] = override
        runs.append(entry)
    # A recipe that does not pass the check never starts (`source.recipe.steps-are-jobs`).
    refusals = check_recipe(recipe)
    downloads = missing_models(runs)
    refusals += [f"steps {', '.join(d['steps'])} need the {d['runtime']} model {d['model']} ({d['size_mb']} MB), "
                 f"which is not on this Mac: download it first" for d in downloads]
    if not runs and not refusals:
        refusals.append("nothing in this recipe can run yet: every step is skipped (see why)")
    return {"runs": runs, "workflows": [r for r in runs if r["card"] == "workflow"], "skipped": skipped,
            "offered": offered, "refusals": refusals, "downloads": downloads}


def missing_models(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The downloadable models the plan's steps are pinned to that are not on this Mac
    (`source.recipe.missing-model-offered`): today spaCy pipelines, each offered as a `download-model` job."""
    from fichero_server.llm.local_models import SPACY_MODELS, spacy_pipeline_available

    out: dict[str, dict[str, Any]] = {}
    for run in runs:
        name = run.get("model_override")
        if run.get("provider_override") != "spacy" or not name or spacy_pipeline_available(name):
            continue
        entry = out.setdefault(name, {"runtime": "spacy", "model": name, "steps": [],
                                      "size_mb": SPACY_MODELS.get(name, {}).get("disk_mb"),
                                      "action": "model.download", "params": {"runtime": "spacy", "model": name}})
        entry["steps"] += run["steps"]
    return list(out.values())


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
