"""Start: the first yes. What a saved recipe would run, on how many pages, and what refuses it.

`source/models-chains-and-projects.md` section 11: `source.project.automatic-after-first-yes`,
`source.recipe.makes-a-workflow`, `source.recipe.holds-no-second-copy`, `source.project.stays-local`,
`source.onboard.estimate-before-start`. A recipe runs only as workflows Fichero already ships,
named, never copied: each step's job maps to one shipped workflow (or, for search, the embed job), and the step's model reaches it
only where that workflow can honestly take it (a provider/model override; for a Kraken reader,
the `kraken` run override that sets the reading node's reader). A step that cannot be mapped is refused by name, never run with another model.

Pure, except `count_pages`: the Start screen, the Inspector, MCP and the command line all read the
same plan from the engine.
"""
from __future__ import annotations

from typing import Any

from fichero_server.workflows.validation import KRAKEN_READER_PROVIDER

#: job -> the shipped workflow that carries it out, by its stable key: the file the preset ships in, which a
#: rename of its display name never changes (#5497: the names step looked for "2 · Extract Entities" by an id
#: minted from that name, and a project seeded before ids were stable said it "is not in this build").
WORKFLOW_FOR_JOB = {
    "split-pages": "split_pages",
    "find-lines": "detect_regions_kraken",
    "read-a-line": "transcribe_kraken",
    "read-a-page": "transcribe_htr",
    "correct": "transcribe_paleography_review",
    "find-names-tag-words": "catalogue_stage_2_extract_entities",
    "find-statements": "catalogue_stage_3_extract_svo",
    # The same rule extractor as the Extract Date tool, one code path (#5514).
    "work-out-dates": "work_out_dates",
}
#: Kraken finds the lines and the step's vision model (a cloud or MLX pin) reads each one (the line reader).
READ_LINES_WITH_A_MODEL = "read_lines_kraken_vision"
#: Jobs whose workflow takes the step's model as a run-level provider/model override.
_OVERRIDE_JOBS = frozenset({"read-a-page", "correct", "find-names-tag-words", "find-statements"})
#: Jobs carried out by a card that is not a workflow: the check job (`source.check.*`), the page text tied to
#: its lines (a check run of kind `tie-text-to-lines`, #5444: free, on this Mac, with a Kraken reader) and the
#: project's synced folder (`source.sync.*`).
OTHER_CARDS = {"check": "check", "tie-text-to-lines": "check", "export": "export", "publish": "publish",
               # Find the Documents: Fichero's own rules over the text already read (`finddocs.recipe-step`).
               "find-documents-in-a-folder": "find-documents"}
#: Jobs that need no model.
#: The fixes setup offers as a button for a skipped step (`RecipeStepRow.fixTitle`).
_FIX_BUTTONS = frozenset({"choose-model", "allow-cloud"})
_NO_MODEL_JOBS = frozenset({"export", "publish", "work-out-dates", "find-documents-in-a-folder"})
#: Search: the page's text embedded by the embed job that also follows every correction
#: (`actions/page_text_cache.REEMBED_KIND`, a job named `make-a-vector`), one per page (#5574).
EMBED_JOB = "make-a-vector"
#: Every job Start has a card for (or, for training, offers later). Setup proposes no other job as a step: the
#: rest are listed in the recipe's `by_hand` and in the plan's `skipped`, with the tool that does them by hand
#: (`source.onboard.auto.every-proposed-step-runs`, #5574). A job given a card joins this set.
START_JOBS = frozenset(WORKFLOW_FOR_JOB) | frozenset(OTHER_CARDS) | {EMBED_JOB, "train-a-model"}
#: What to use instead, by hand, for a job Start cannot run by itself (the shipped workflow or tool that does it).
BY_HAND_FIX = {
    "prepare-the-image": "run the Prepare Images for OCR or Enhance Images workflow on the pages by hand",
    "find-regions": "run the Detect Segments (Apple Vision) workflow by hand",
    "split-into-entries": "run the Diary Entries workflow on the volume by hand",
    "translate-transliterate-normalise": "run the Translate workflow (or Modernización, for Spanish) by hand",
    "link-to-authorities": "link each name to an authority from its Inspector",
    "place-in-a-gazetteer": "run the Extract Geo workflow by hand: it finds the places and puts them on the map",
    "describe-for-the-catalogue": "run the Catalogue Description workflow by hand",
    "extract-to-a-table": "run the Extract Table workflow by hand",
}
_NO_TOOL_YET = "nothing in Fichero does this yet, by hand or by itself"
#: Setup's answers under a purpose (`answers.job_answers`) -> the setting of the step they configure (#5478).
JOB_ANSWER_SETTINGS = {"find-names-tag-words": ("entity_kinds", "kinds"),
                       "place-in-a-gazetteer": ("gazetteer", "gazetteer"),
                       "translate-transliterate-normalise": ("normalise_how_far", "target")}
#: Setup's kinds of names -> the sections the entity extraction finds (`extract_entities_only.entity_types`).
_ENTITY_SECTIONS = {"people": "people", "places": "places", "organisations": "organizations",
                    "organizations": "organizations", "events": "events", "dates": "dates"}


def start_runs(job: str) -> bool:
    """Whether Start can run this job by itself (`source.onboard.auto.every-proposed-step-runs`)."""
    return job in START_JOBS


def by_hand(job: str) -> dict[str, str]:
    """A job Start cannot run by itself, as the recipe's `by_hand` and the plan's `skipped` say it: why, and the fix."""
    from fichero_server.recipes.jobs import get_job

    known = get_job(job)
    name = known.name if known else job
    return {"job": job, "title": name, "why": f"no card runs the job {job!r} yet: Start cannot run “{name}” by itself",
            "fix": BY_HAND_FIX.get(job, _NO_TOOL_YET)}
#: Per-page token assumptions: the same ones the workflow cost estimate prices with (runner.py).
_TOKENS_IN, _TOKENS_OUT = 1200, 300


def _preset(name: str) -> dict | None:
    from fichero_server.workflows.default_workflows import _load_preset_files

    return next((p for p in _load_preset_files() if p.get("name") == name), None)


def _shipped(key: str) -> tuple[str, str]:
    """(display name, stable id) of the shipped workflow under `key`: the id every seed of it mints."""
    from fichero_server.workflows.default_workflows import preset_workflow_id, shipped_preset

    preset = shipped_preset(key)
    if preset is None:
        raise LookupError(f"no shipped workflow under the key {key!r}")
    return preset["name"], preset_workflow_id(preset["name"])


def _kraken_reader_for(pin: dict) -> str | None:
    from fichero_server.recipes.cards import kraken_reader_for

    return kraken_reader_for(pin)


def _override(pin: dict) -> tuple[str, str] | None:
    """(provider, model) a step's pin runs as, for a workflow that takes an override."""
    if set(pin) == {"cloud", "model"}:
        return str(pin["cloud"]), str(pin["model"])
    if "spacy" in pin and set(pin) <= {"spacy", "version"}:  # names: spaCy is the entity tool's local reader
        return "spacy", str(pin["spacy"])
    from fichero_server.recipes.cards import mlx_model_for

    model = mlx_model_for(pin)
    return ("omlx", model) if model else None


def _uses_cloud(step: dict) -> bool:
    return str(step.get("runs_on") or "").startswith("cloud") or "cloud" in (step.get("model") or {})


def _automatic_skip(step: dict, automatic: dict | None) -> tuple[str, str] | None:
    """(why, fix) when What runs by itself (`answers.automatic`) leaves this step to a run by hand (#5478)."""
    if not isinstance(automatic, dict):
        return None
    if not automatic.get("runs", True):
        return ("What runs by itself is “Nothing runs automatically”: new material waits for a run by hand",
                "press Start to run the recipe over it, or choose “New material runs through the ticked steps” "
                "in the project's setup")
    ticked = set(automatic.get("steps") or [])
    if step.get("job") not in ticked and step.get("id") not in ticked:
        return ("it is not ticked under What runs by itself, so it runs only by hand",
                "tick it under What runs by itself in the project's setup, or press Start to run it")
    return None


def plan_start(recipe: dict | None, *, stays_local: bool, only: set[str] | None = None,
               automatic: dict | None = None, job_answers: dict | None = None) -> dict[str, Any]:
    """What Start would run, in order, what it skips and why, and what refuses it outright.

    Returns `{"runs": [...], "workflows": [...], "skipped": [...], "offered": [...], "refusals": [...]}`.
    `runs` are the cards Start runs in order: a shipped workflow (name, id, provider/model override), a
    check run (its layer and checker), the embed job (search), or the project's synced folder (its folder and
    formats); `workflows` is the workflow runs among them. A step that cannot run is SKIPPED with its reason and
    its fix, and the others still run (`source.recipe.step-skipped-says-why`); so is each job the recipe lists
    `by_hand` (one Start has no card for, #5574). `offered` lists steps that wait to be offered
    (train), never run at Start (`source.recipe.train-never-automatic`). Start may go ahead only when
    `refusals` is empty: a recipe that fails the recipe check, or one with nothing to run. `only` limits
    the plan to those step ids: the jobs a layer added later proposes for the material already there
    (`source.onboard.add-layer`); the whole recipe is still checked. `automatic` is setup's What runs by itself
    (`answers.automatic`), given for a run new material starts by itself (an import after Start), never for Start:
    with Nothing runs automatically every step is skipped, else every step not ticked (#5478). `job_answers` are
    setup's answers under a purpose (`answers.job_answers`): each reaches the step it configures as its setting
    (`JOB_ANSWER_SETTINGS`) where the recipe does not already set it (#5478).
    """
    from fichero_server.recipes.recipe import check_recipe

    if not recipe:
        return {"runs": [], "workflows": [], "skipped": [], "offered": [],
                "refusals": ["this project has no recipe yet: run setup first"]}
    runs: list[dict[str, Any]] = []
    skipped: list[dict[str, str | None]] = []
    offered: list[str] = []

    def skip(sid: str, why: str, fix: str | None = None) -> None:
        # `fix`: the button setup offers for it, in the words of a step problem's `fix` (choose-model,
        # allow-cloud); None when nothing the person can do in setup fixes it (#5573).
        if fix and fix not in _FIX_BUTTONS:
            # a fix setup has no button for (do it by hand, choose a reader) is said with the why (#5574)
            why, fix = f"{why}; {fix}", None
        skipped.append({"step": sid, "why": why, "fix": fix})

    for step in recipe.get("steps") or []:
        sid, job = step.get("id", "?"), step.get("job", "")
        label = f"step {sid}"
        if only is not None and sid not in only:
            continue
        if step.get("offered_when"):
            offered.append(sid)
            continue
        if not start_runs(job):
            gone = by_hand(job)
            skip(sid, f"{label}: {gone['why']}", gone["fix"])
            continue
        if job not in _NO_MODEL_JOBS and (step.get("gap") or not step.get("model")):
            skip(sid, f"{label} has no model: {step.get('gap') or 'none is named'}", "choose-model")
            continue
        if stays_local and _uses_cloud(step):
            skip(sid, f"{label} would send pages off this Mac, and this project keeps its pages here", "allow-cloud")
            continue
        if step.get("when"):
            skip(sid, f"{label} runs only {sorted(step['when'])}; Start cannot honour a condition yet",
                 "remove the condition from the step, or run it by hand")
            continue
        held = _automatic_skip(step, automatic)
        if held is not None:
            skip(sid, f"{label}: {held[0]}", held[1])
            continue
        pin = step.get("model") or {}
        settings = dict(step.get("settings") or {})
        answer, setting = JOB_ANSWER_SETTINGS.get(job, (None, None))
        if answer and setting not in settings and (job_answers or {}).get(answer) not in (None, "", []):
            settings[setting] = job_answers[answer]
        runs_on = step.get("runs_on") or "this-mac"
        if job == EMBED_JOB:
            from fichero_server.db.embeddings import search_embedder

            engine, named = search_embedder(), str(pin.get("hf") or pin)
            if named.lower() != engine.lower():
                skip(sid, f"{label}: this library's search embeds with {engine}, and the step names {named}, whose "
                          "vectors could not be searched beside them",
                     f"choose {engine} for this step: propose the recipe again in the project's setup")
                continue
            runs.append({"steps": [sid], "job": job, "card": "embed", "runs_on": runs_on, "model": engine})
            continue
        if job in OTHER_CARDS:
            entry: dict[str, Any] = {"steps": [sid], "job": job, "card": OTHER_CARDS[job], "runs_on": runs_on}
            if job == "tie-text-to-lines":
                reader = _kraken_reader_for(pin)
                if reader is None:
                    skip(sid, f"{label}: the page text is tied to its lines by a Kraken reader's rough read, "
                              f"and {pin} is not one this Mac can fetch", "choose-model")
                    continue
                entry.update(check="tie-text-to-lines", layer="readings", provider=KRAKEN_READER_PROVIDER,
                             model=reader, prompt=None)
            elif job == "check":
                override = _override(pin)
                if override is None:
                    skip(sid, f"{label}: the check job cannot run the model {pin}", "choose-model")
                    continue
                entry.update(layer=settings.get("layer", "readings"), provider=override[0], model=override[1],
                             prompt=step.get("prompt"))
            elif job == "find-documents-in-a-folder":
                # The project's setting: None leaves every proposal for the person.
                entry.update(accept_above=settings.get("accept_above"))
            elif job == "publish":
                if not settings.get("where"):
                    skip(sid, f"{label} names no folder (`where`) to publish the site into",
                         "name the folder to publish the site into")
                    continue
                entry.update(folder=settings["where"])
            else:
                entry.update(folder=settings.get("folder"), formats=list(settings.get("formats") or []))
            runs.append(entry)
            continue
        name, workflow_id = _shipped(WORKFLOW_FOR_JOB[job])
        entry = {"steps": [sid], "job": job, "card": "workflow", "workflow": name,
                 "workflow_id": workflow_id, "provider_override": None, "model_override": None,
                 "runs_on": runs_on}
        if job == "split-pages":
            if pin.get("builtin") != "page-splitter":
                skip(sid, f"{label}: {name} cuts pages with the built-in page splitter only, not {pin}",
                     "choose-model")
                continue
        elif job == "work-out-dates":
            # The rule extractor reads one calendar per run; a recipe asking for a
            # Julian/Gregorian switch is skipped and says so, never run as Gregorian.
            calendars = set(settings.get("calendars") or [])
            if calendars - {"gregorian"}:
                skip(sid, f"{label}: {name} reads Gregorian dates only; it cannot use "
                          f"{sorted(calendars)} or switch calendars yet",
                     "keep only the Gregorian calendar for this step, or work out the other dates by hand")
                continue
        elif job == "find-lines":
            if pin.get("kraken") != "blla":
                skip(sid, f"{label}: {name} finds lines with Kraken's blla only, not {pin}", "choose-model")
                continue
        elif job == "read-a-line" and _override(pin) is not None:
            # A vision model reads the lines Kraken found: the step's own model, as the run's override.
            entry["workflow"], entry["workflow_id"] = _shipped(READ_LINES_WITH_A_MODEL)
            entry["provider_override"], entry["model_override"] = _override(pin)
            if runs and runs[-1]["job"] == "find-lines":
                entry["steps"] = runs.pop()["steps"] + entry["steps"]
        elif job == "read-a-line":
            reader = _kraken_reader_for(pin)
            if reader is None:
                skip(sid, f"{label}: the reader {pin} is not in the Kraken catalogue this Mac "
                          "can fetch, so no workflow can read with it", "choose-model")
                continue
            entry["provider_override"], entry["model_override"] = KRAKEN_READER_PROVIDER, reader
            # Kraken finds its own lines before reading them: one run carries both steps.
            if runs and runs[-1]["job"] == "find-lines":
                entry["steps"] = runs.pop()["steps"] + entry["steps"]
        elif job in _OVERRIDE_JOBS:
            override = _override(pin)
            if override is None:
                skip(sid, f"{label}: {name} cannot run the model {pin}", "choose-model")
                continue
            entry["provider_override"], entry["model_override"] = override
        if job == "find-names-tag-words" and settings.get("kinds"):
            # Setup's kinds of names reach the entity extraction as its sections (#5478).
            sections = [_ENTITY_SECTIONS[k] for k in settings["kinds"] if k in _ENTITY_SECTIONS]
            if not sections:
                skip(sid, f"{label}: {name} finds people, places, organisations, events and dates, and none of "
                          f"{sorted(settings['kinds'])} is among them",
                     "tick a kind of name it finds under the purpose in the project's setup")
                continue
            entry["tool_config"] = {"extract_entities_only": {"entity_types": ",".join(dict.fromkeys(sections))}}
        runs.append(entry)
    for item in recipe.get("by_hand") or []:
        if only is None or item.get("job") in only:
            skip(item.get("job", "?"), item.get("why", ""), item.get("fix", ""))
    # Each card declares what it takes and gives, so a run knows which steps a failure stops (#5498).
    jobs_of = {s.get("id"): s.get("job", "") for s in recipe.get("steps") or []}
    for run in runs:
        run["takes"], run["gives"] = card_inputs([jobs_of.get(sid, "") for sid in run["steps"]])
    # A recipe that does not pass the check never starts (`source.recipe.steps-are-jobs`).
    refusals = check_recipe(recipe)
    downloads = missing_models(runs)
    refusals += [f"steps {', '.join(d['steps'])} need the {d['runtime']} model {d['model']} ({d['size_mb']} MB), "
                 f"which is not on this Mac: download it first" for d in downloads]
    refusals += local_models_this_mac_cannot_serve(runs)
    if not runs and not refusals:
        nothing = isinstance(automatic, dict) and not automatic.get("runs", True)
        refusals.append("What runs by itself is “Nothing runs automatically”: new material waits for a run by hand"
                        if nothing else "nothing in this recipe can run yet: every step is skipped (see why)")
    return {"runs": runs, "workflows": [r for r in runs if r["card"] == "workflow"], "skipped": skipped,
            "offered": offered, "refusals": refusals, "downloads": downloads}


def card_inputs(step_jobs: list[str]) -> tuple[list[str], list[str]]:
    """(takes, gives) of a card that carries these jobs in order, in the job registry's kinds
    (`recipes/jobs.py`; a take may name kinds joined by "|", any one of which meets it). A take a step of
    the same card meets (Kraken's lines, read in the same run) is not the card's: only what it needs from
    the steps before it."""
    from fichero_server.recipes.jobs import get_job

    takes: list[str] = []
    gives: set[str] = set()
    for job_id in step_jobs:
        job = get_job(job_id)
        if job is None:
            continue
        takes += [k for k in sorted(job.takes) if gives.isdisjoint(k.split("|")) and k not in takes]
        gives |= job.gives
    return takes, sorted(gives)


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


#: Jobs whose local model reads the page image; the others send it text alone.
_TEXT_ONLY_JOBS = frozenset({"find-names-tag-words", "find-statements"})


def local_models_this_mac_cannot_serve(runs: list[dict[str, Any]]) -> list[str]:
    """A refusal for each run whose own local model (`omlx`) this Mac's local model server cannot
    serve -- not in the catalogue, not installed, or its card says this Mac's memory cannot run it
    -- with the reason and the fix, BEFORE Start (#5496, #5520). The step's model is the one the
    run asks the server for, which switches to it; it is never served another in its place."""
    from fichero_server.llm.local_model_choice import local_model_problem

    out = []
    for run in runs:
        provider = run.get("provider_override") or run.get("provider")
        model = run.get("model_override") or run.get("model")
        if provider != "omlx" or not model:
            continue
        problem = local_model_problem(model, "text" if run["job"] in _TEXT_ONLY_JOBS else "vision")
        if problem is not None:
            out.append(f"steps {', '.join(run['steps'])} cannot run on this Mac: {problem}")
    return out


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
                     "pages": pages, "cost_usd": cost, "memory": _local_memory(w)})
        total = None if total is None or cost is None else total + cost
    return {"pages": pages, "runs": rows, "total_cost_usd": total}


def _local_memory(run: dict[str, Any]) -> str | None:
    """A run on this Mac's model server, in words: the model's need, pages at once, the peak (#5537,
    rule 8). None for any other run, or a model the catalogue does not size."""
    if run.get("provider_override") != "omlx" or not run.get("model_override"):
        return None
    from fichero_server.llm.local_inference import local_read_plan
    from fichero_server.llm.local_model_choice import model_to_serve
    from fichero_server.llm.mlx_model_store import get_mlx_model_store

    try:
        return local_read_plan(get_mlx_model_store().spec(model_to_serve(run["model_override"])))
    except KeyError:
        return None


def count_pages(db) -> int:
    """Units of work in the project: every page, every file that has no pages, and every page a split cut from a
    photograph (live material only): the pages a started recipe runs over (`done.pages_for`), so the estimate
    and the run count the same thing (#5498)."""
    from fichero_server.recipes.done import material

    return material(db)["pages"]
