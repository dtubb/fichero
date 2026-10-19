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

from fichero_server.recipes.assemble import APPLE_LINES_PIN
from fichero_server.workflows.validation import KRAKEN_READER_PROVIDER

#: job -> the shipped workflow that carries it out, by its stable key: the file the preset ships in, which a
#: rename of its display name never changes (#5497: the names step looked for "2 · Extract Entities" by an id
#: minted from that name, and a project seeded before ids were stable said it "is not in this build").
WORKFLOW_FOR_JOB = {
    "split-pages": "split_pages",
    "find-lines": "detect_regions_kraken",
    "find-the-script": "classify_script",
    "read-a-line": "transcribe_kraken",
    "read-a-page": "transcribe_htr",
    "transcribe-speech": "transcribe_audio",
    "correct": "transcribe_paleography_review",
    "find-names-tag-words": "catalogue_stage_2_extract_entities",
    "find-statements": "catalogue_stage_3_extract_svo",
    # The same rule extractor as the Extract Date tool, one code path (#5514).
    "work-out-dates": "work_out_dates",
    # Each level asked under "Into what" is one run of the Modernización workflow's analyze node, its prompt and
    # its reading level set per run: it reads the page and its transcription and writes a transcription at that
    # level, or a translation (#5660 item 1, the page model's levels #5651, #5653).
    "translate-transliterate-normalise": "paleo_modernizacion",
}
#: What each level's run asks the step's model (#5660 item 1). The reading lands as a transcription at that level.
LEVEL_PROMPTS = {
    "as_written": ("Transcribe this page exactly as written, in its own language: keep the scribe's spelling, "
                   "abbreviations, word division and punctuation; do not expand or modernise anything."),
    "expanded": ("Transcribe this page with every abbreviation expanded into the full word the scribe meant "
                 "(for example dha -> dicha), and the spelling otherwise exactly as written."),
    "regularised": ("Transcribe this page in normalised spelling: expand the abbreviations, regularise u/v, i/j and "
                    "long s and the word division, and keep the period's words and grammar."),
    "modernised": ("Give a modernised reading of this page for a reader who cannot handle the period orthography: "
                   "modern spelling and accents, every abbreviation expanded, the words and their order kept."),
}
_LEVEL_TAIL = (" Use the existing transcription as context where it is given; read the image where it is silent. "
               "Return only the text, line by line.")
#: Kraken finds the lines and the step's vision model (a cloud or MLX pin) reads each one (the line reader).
READ_LINES_WITH_A_MODEL = "read_lines_kraken_vision"
#: Apple Vision as a line finder only, for print and typescript: its lines, none of its text (#5451).
APPLE_LINES_WORKFLOW = "detect_regions_apple_lines"
#: Jobs whose workflow takes the step's model as a run-level provider/model override.
_OVERRIDE_JOBS = frozenset({"read-a-page", "find-the-script", "correct", "find-names-tag-words", "find-statements",
                            "translate-transliterate-normalise"})
#: Jobs carried out by a card that is not a workflow: the check job (`source.check.*`), the page text tied to
#: its lines (a check run of kind `tie-text-to-lines`, #5444: free, on this Mac, with a Kraken reader) and the
#: project's synced folder (`source.sync.*`).
OTHER_CARDS = {"check": "check", "tie-text-to-lines": "check", "export": "export", "publish": "publish",
               # Find the Documents: Fichero's own rules over the text already read (`finddocs.recipe-step`).
               "find-documents-in-a-folder": "find-documents",
               # A diary or register split into its dated entries by the Diary Entries splitter, with the step's
               # model, over the pages that have text (`source.onboard.auto.diary-entries`, #5581).
               "split-into-entries": "entries",
               # Faded pages get a prepared rendition, their contrast raised, before lines; the original is kept
               # (`source.onboard.auto.prepare-damaged-images`, #5580).
               "prepare-the-image": "prepare",
               # A page's regions found by a YOLO layout model (`prep.yolo.regions-card`, #5525).
               "find-regions": "regions",
               # A prototype's questions asked of its documents and entries with the step's text model, the answers
               # landing as their attributes, each citing its words (`structured.extract.step-in-a-recipe`, #5636).
               "extract-to-a-table": "table"}
#: Jobs that need no model.
#: The fixes setup offers as a button for a skipped step (`RecipeStepRow.fixTitle`).
_FIX_BUTTONS = frozenset({"choose-model", "allow-cloud"})
_NO_MODEL_JOBS = frozenset({"export", "publish", "work-out-dates", "find-documents-in-a-folder", "prepare-the-image"})
#: Search: the page's text embedded by the embed job that also follows every correction
#: (`actions/page_text_cache.REEMBED_KIND`, a job named `make-a-vector`), one per page (#5574).
EMBED_JOB = "make-a-vector"
#: Every job Start has a card for (or, for training, offers later). Setup proposes no other job as a step: the
#: rest are listed in the recipe's `by_hand` and in the plan's `skipped`, with the tool that does them by hand
#: (`source.onboard.auto.every-proposed-step-runs`, #5574). A job given a card joins this set.
#: Find where the readers disagree (#5665, `source.disagree.recipe-step`): the lines read again by the readers the
#: step names, or by one reader sampled `samples` times at `temperature`; every reading kept as a reading of the line.
DISAGREE_JOB = "find-where-readers-disagree"
DISAGREE_SAMPLES, DISAGREE_TEMPERATURE = 5, 0.7
START_JOBS = frozenset(WORKFLOW_FOR_JOB) | frozenset(OTHER_CARDS) | {EMBED_JOB, "train-a-model", DISAGREE_JOB}
#: What to use instead, by hand, for a job Start cannot run by itself (the shipped workflow or tool that does it).
BY_HAND_FIX = {
    "link-to-authorities": "link each name to an authority from its Inspector",
    "place-in-a-gazetteer": "run the Extract Geo workflow by hand: it finds the places and puts them on the map",
    "describe-for-the-catalogue": "run the Catalogue Description workflow by hand",
}
_NO_TOOL_YET = "nothing in Fichero does this yet, by hand or by itself"
#: Setup's answers under a purpose (`answers.job_answers`) -> the setting of the step they configure (#5478).
JOB_ANSWER_SETTINGS = {"find-names-tag-words": ("entity_kinds", "kinds"),
                       "place-in-a-gazetteer": ("gazetteer", "gazetteer"),
                       "translate-transliterate-normalise": ("normalise_how_far", "target"),
                       "correct": ("review_lenses", "lenses")}
#: Job answers whose empty list says "none of them", never "not answered".
_EMPTY_IS_AN_ANSWER = frozenset({"review_lenses"})
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


def _add_steps(into: list, more: list) -> None:
    """Add a run's step ids to a download's or a place's list, each once, in order: the normalise step runs once per
    level (#5660 item 1), so several runs carry the same step and the list said it twice."""
    for sid in more:
        if sid not in into:
            into.append(sid)


def _kraken_reader_for(pin: dict) -> str | None:
    from fichero_server.recipes.cards import kraken_reader_for

    return kraken_reader_for(pin)


def _override(pin: dict) -> tuple[str, str] | None:
    """(provider, model) a step's pin runs as, for a workflow that takes an override."""
    if set(pin) == {"cloud", "model"}:
        return str(pin["cloud"]), str(pin["model"])
    if "spacy" in pin and set(pin) <= {"spacy", "version"}:  # names: spaCy is the entity tool's local reader
        return "spacy", str(pin["spacy"])
    if pin.get("builtin") == "apple-vision":  # read as the bake-off reads it (`bakeoff._reader_of`, #5668)
        from fichero_server.training.evaluation import APPLE_VISION

        return "apple", APPLE_VISION
    from fichero_server.recipes.cards import mlx_model_for

    model = mlx_model_for(pin)
    return ("omlx", model) if model else None


def _reading_run(job: str, pin: dict) -> dict[str, Any] | None:
    """The shipped workflow and run override that read with `pin` for a `read-a-line` or override job, or None
    when no workflow can: a vision model reads the lines Kraken found; a Kraken reader finds and reads them; the
    other jobs take the model as the run's override. A step's model and each of its `readers` (#5578) go here."""
    if job == "read-a-line" and _override(pin) is not None:
        (name, workflow_id), (provider, model) = _shipped(READ_LINES_WITH_A_MODEL), _override(pin)
    elif job == "read-a-line":
        reader = _kraken_reader_for(pin)
        if reader is None:
            return None
        (name, workflow_id), (provider, model) = _shipped(WORKFLOW_FOR_JOB[job]), (KRAKEN_READER_PROVIDER, reader)
    else:
        override = _override(pin)
        if override is None:
            return None
        (name, workflow_id), (provider, model) = _shipped(WORKFLOW_FOR_JOB[job]), override
    return {"workflow": name, "workflow_id": workflow_id, "provider_override": provider, "model_override": model}


def disagreement_runs(step: dict, recipe: dict) -> tuple[list[tuple[dict[str, Any], bool]], str | None]:
    """The runs of a Find where the readers disagree step (`source.disagree.recipe-step`, #5665), each with whether
    it sends pages off this Mac, or why it has none. With `readers` (pins) in its settings, one run per reader;
    else its model (or, unnamed, the recipe's own line reader) sampled `samples` times (5) at `temperature` (0.7).
    Each run reads the page's lines again with a vision model and keeps its readings beside the others."""
    from fichero_server.recipes.recipe import pin_leaves_this_mac

    settings = dict(step.get("settings") or {})
    pins = [p for p in settings.get("readers") or [] if isinstance(p, dict)]
    temperature = settings.get("temperature", DISAGREE_TEMPERATURE)
    if not pins:
        pin = step.get("model") or next((s.get("model") for s in recipe.get("steps") or []
                                         if s.get("job") == "read-a-line" and isinstance(s.get("model"), dict)), None)
        if not isinstance(pin, dict) or _override(pin) is None:
            return [], ("it samples a vision model, and none is named: choose one for this step, or a vision model "
                        "for the line reader")
        pins = [pin] * max(int(settings.get("samples", DISAGREE_SAMPLES)), 2)
    name, workflow_id = _shipped(READ_LINES_WITH_A_MODEL)
    out = []
    for pin in pins:
        override = _override(pin)
        if override is None:
            return [], f"it reads with a vision model, and {pin} is not one"
        out.append(({"steps": [step.get("id", "?")], "job": DISAGREE_JOB, "card": "workflow", "workflow": name,
                     "workflow_id": workflow_id, "provider_override": override[0], "model_override": override[1],
                     "runs_on": step.get("runs_on") or "this-mac",
                     "tool_config": {"transcribe": {"temperature": temperature}}}, pin_leaves_this_mac(pin)))
    return out, None


def _with_readers(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The runs and, as runs of their own steps, each kind's reader they carry: their models are checked too."""
    return runs + [{**run, **reader} for run in runs for reader in (run.get("readers") or {}).values()
                   if reader["model_override"] != run.get("model_override")]


def _uses_cloud(step: dict) -> bool:
    from fichero_server.recipes.recipe import pin_leaves_this_mac

    return str(step.get("runs_on") or "").startswith("cloud") or pin_leaves_this_mac(step.get("model"))


def provider_without_key(step: dict) -> str | None:
    """The name of the cloud provider a step's pin needs a key for, when none is configured; else None (#5364)."""
    pin = step.get("model") or {}
    if "cloud" not in pin:
        return None
    from fichero_server.llm import get_api_key
    from fichero_server.llm.providers import get_provider_info

    info = get_provider_info(str(pin["cloud"]).strip().lower())
    if info is None or info.is_local or info.is_builtin or not info.api_key_env or get_api_key(info.type.value):
        return None
    return info.name


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
               automatic: dict | None = None, job_answers: dict | None = None,
               db: Any = None) -> dict[str, Any]:
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
    (`JOB_ANSWER_SETTINGS`) where the recipe does not already set it (#5478). With the project's `db`, a model
    already downloading does not refuse Start: its download is marked `downloading` (with its progress), `waiting`
    says so in words, and the run's steps on it wait for it to land (#5660, #5583).
    """
    from fichero_server.recipes.recipe import check_recipe

    if not recipe:
        return {"runs": [], "workflows": [], "skipped": [], "offered": [], "waiting": [], "fallbacks": [],
                "refusals": ["this project has no recipe yet: run setup first"]}
    runs: list[dict[str, Any]] = []
    skipped: list[dict[str, str | None]] = []
    offered: list[str] = []
    #: Steps that run their next candidate because the first cannot (a missing key), each saying which and why.
    fallbacks: list[dict[str, Any]] = []
    #: Steps kept in the recipe with no model (`source.onboard.no-model-step-kept`): skipped, never refusing Start.
    needs_a_model: list[dict[str, Any]] = []

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
        if job == DISAGREE_JOB:
            sampled, why = disagreement_runs(step, recipe)
            if why:
                skip(sid, f"{label}: {why}", "choose-model")
            elif stays_local and any(leaves for _run, leaves in sampled):
                skip(sid, f"{label} would send pages off this Mac, and this project keeps its pages here",
                     "allow-cloud")
            else:
                runs.extend(run for run, _leaves in sampled)
            continue
        if job not in _NO_MODEL_JOBS and (step.get("gap") or not step.get("model")):
            # Said as setup says it: the problem's sentence, naming the nearest readers, never the refused
            # cards' ids (`source.onboard.nothing-fits-names-nearest`, #5593).
            said = (step.get("problem") or {}).get("sentence") or step.get("gap") or "none is named"
            skip(sid, f"{label} has no model: {said}", "choose-model")
            needs_a_model.append(step)
            continue
        if stays_local and _uses_cloud(step):
            skip(sid, f"{label} would send pages off this Mac, and this project keeps its pages here", "allow-cloud")
            continue
        if (keyless := provider_without_key(step)) is not None:
            # The next LOCAL candidate in the step's chain takes its place, and the plan says so
            # (`source.recipe.candidates-fallback-chain`); with none, the step waits and no other model is used
            # (`source.recipe.missing-key-never-substitutes`).
            rest = list(step.get("chain") or [])
            runnable = [c for c in rest if not (stays_local and _uses_cloud(c))
                        and provider_without_key({"model": c.get("model")}) is None]
            # Only a local model runs on its own; any other provider sends pages somewhere new (the same provider has
            # the same missing key), so it is offered and never used without the person's press.
            nxt = next((c for c in runnable if not _uses_cloud(c)), None)
            offer = next(iter(runnable), None) if nxt is None else None
            if offer is not None:
                fallbacks.append({"step": sid, "from": keyless, "to": offer["id"], "used": False,
                                  "why": f"Needs a key for {keyless}: {offer['id']} would send pages to another "
                                         "provider, so it is offered, not used until you choose it"})
            if nxt is not None:
                fallbacks.append({"step": sid, "from": keyless, "to": nxt["id"], "used": True,
                                  "why": f"Needs a key for {keyless}: {nxt['id']} runs instead"})
                step = {**step, "model": nxt["model"], "runs_on": nxt.get("runs_on", "this-mac"),
                        "chain": rest[rest.index(nxt) + 1:]}
            else:
                # Not a `_FIX_BUTTONS` token: the app has no Add Key button yet (`RecipeSetupStore` maps allow-cloud
                # and choose-model only), so `skip` folds this into the why and `fix` is None. When the app grows
                # the button, add "add-key" to `_FIX_BUTTONS` and pass it here.
                skip(sid, f"{label}: Needs a key for {keyless}", "Add Key… in Settings")
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
        given = (job_answers or {}).get(answer) if answer else None
        # An empty list is an answer where it turns things off (every review lens off, #5723); elsewhere it is none.
        if (answer and setting not in settings and given not in (None, "")
                and (given != [] or answer in _EMPTY_IS_AN_ANSWER)):
            settings[setting] = given
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
            elif job == "split-into-entries":
                override = _override(pin)
                if override is None:
                    skip(sid, f"{label}: the entries are split by a text model, and {pin} is not one", "choose-model")
                    continue
                entry.update(provider=override[0], model=override[1])
            elif job == "extract-to-a-table":
                override = _override(pin)
                if override is None:
                    skip(sid, f"{label}: the table is filled by a text model, and {pin} is not one", "choose-model")
                    continue
                if not settings.get("prototype"):
                    skip(sid, f"{label} names no kind of document (`prototype`) whose fields it fills",
                         "choose the kind of document in the step's settings")
                    continue
                entry.update(provider=override[0], model=override[1], prototype=str(settings["prototype"]))
            elif job == "find-regions":
                # Kraken's bundled segmenter is the open default (prep.regions.open-default); a YOLO layout model is a choice.
                if pin.get("kraken") == "blla":
                    entry.update(provider="kraken", model="blla")
                elif pin.get("yolo"):
                    entry.update(provider="yolo", model=str(pin["yolo"]))
                else:
                    skip(sid, f"{label}: regions are found by Kraken's segmenter or a YOLO layout model, and this "
                              "step's model is neither", "choose-model")
                    continue
            elif job == "find-documents-in-a-folder":
                # The project's setting: None leaves every proposal for the person.
                entry.update(accept_above=settings.get("accept_above"))
            elif job == "prepare-the-image":
                pass  # Fichero's own measure and contrast, on this Mac: nothing to configure
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
        elif job == "find-lines" and pin == APPLE_LINES_PIN:
            # Print and typescript: Apple finds the lines and keeps no text (`source.recipe.apple-finds-lines-on-print`).
            entry["workflow"], entry["workflow_id"] = _shipped(APPLE_LINES_WORKFLOW)
        elif job == "find-lines":
            if pin.get("kraken") != "blla":
                skip(sid, f"{label}: {name} finds lines with Kraken's blla only, not {pin}", "choose-model")
                continue
        elif job == "read-a-line" or job in _OVERRIDE_JOBS:
            reading = _reading_run(job, pin)
            if reading is None:
                skip(sid, f"{label}: the reader {pin} is not in the Kraken catalogue this Mac can fetch, so no "
                          "workflow can read with it" if job == "read-a-line" else
                          f"{label}: {name} cannot run the model {pin}", "choose-model")
                continue
            entry.update(reading)
            if job == "read-a-line" and step.get("granularity") in ("lines", "region", "page"):
                # How the bake-off measured this reader is how it reads (#5722).
                entry["tool_config"] = {"transcribe": {"read_granularity": step["granularity"]}}
            if step.get("readers"):
                # One reader per kind of page (#5578). A kind whose reader cannot run here, or would send pages
                # off a Mac that keeps them, is read by the step's own reader.
                entry["readers"] = {r["material"]: run for r in step["readers"]
                                    if r.get("material") and r.get("model") and not (stays_local and _uses_cloud(r))
                                    and (run := _reading_run(job, r["model"])) is not None}
            # Kraken finds its own lines before reading them: one run carries both steps.
            if (job == "read-a-line" and runs and runs[-1]["job"] == "find-lines"
                    and runs[-1]["workflow_id"] == _shipped(WORKFLOW_FOR_JOB["find-lines"])[1]):
                entry["steps"] = runs.pop()["steps"] + entry["steps"]
        if job == "translate-transliterate-normalise":
            # One run per level asked under "Into what" (a list; a project saved with one value reads as one), each
            # writing its reading level; a translation is a reading of kind translation (#5660 item 1).
            from fichero_server.recipes.answers import TRANSLATION_PREFIX, normalise_levels

            asked, _ = normalise_levels(settings.get("target") or ["regularised"])
            for target in asked:
                if target.startswith(TRANSLATION_PREFIX):
                    from fichero_server.recipes.names import language_name

                    language = target[len(TRANSLATION_PREFIX):]
                    config = {"reading_kind": "translation", "reading_level": None,
                              "prompt": f"Translate this page into {language_name(language)}." + _LEVEL_TAIL}
                elif target in LEVEL_PROMPTS:
                    config = {"reading_kind": "transcription", "reading_level": target,
                              "prompt": LEVEL_PROMPTS[target] + _LEVEL_TAIL}
                else:
                    skip(sid, f"{label}: Fichero has no level {target!r} to write", None)
                    continue
                runs.append({**entry, "tool_config": {"analyze": config}})
            continue
        if job == "find-names-tag-words" and settings.get("kinds"):
            # Setup's kinds of names reach the entity extraction as its sections (#5478).
            sections = [_ENTITY_SECTIONS[k] for k in settings["kinds"] if k in _ENTITY_SECTIONS]
            if not sections:
                skip(sid, f"{label}: {name} finds people, places, organisations, events and dates, and none of "
                          f"{sorted(settings['kinds'])} is among them",
                     "tick a kind of name it finds under the purpose in the project's setup")
                continue
            entry["tool_config"] = {"extract_entities_only": {"entity_types": ",".join(dict.fromkeys(sections))}}
        if job == "correct" and settings.get("lenses") is not None:
            # The review's lenses turned on or off in setup (#5723), in the profiles' order.
            from fichero_server.recipes.review_profiles import lens_ids

            lenses = [lens for lens in lens_ids() if lens in settings["lenses"]]
            if not lenses:
                skip(sid, f"{label}: every lens of the review is turned off, so it has nothing to look for",
                     "turn a lens on under the purpose in the project's setup")
                continue
            entry["lenses"] = lenses
        runs.append(entry)
    for item in recipe.get("by_hand") or []:
        if only is None or item.get("job") in only:
            skip(item.get("job", "?"), item.get("why", ""), item.get("fix", ""))
    # Each card declares what it takes and gives, so a run knows which steps a failure stops (#5498).
    jobs_of = {s.get("id"): s.get("job", "") for s in recipe.get("steps") or []}
    for run in runs:
        run["takes"], run["gives"] = card_inputs([jobs_of.get(sid, "") for sid in run["steps"]])
    # A step with no model stays in the recipe, skipped with its fix; what does not need it runs, and what does
    # waits for it (`source.onboard.no-model-step-kept`, #5668): Organise's Split into entries with no text model on
    # this Mac no longer refuses Read and Names.
    runs = _without_what_waits(runs, needs_a_model, recipe, skip)
    kept_ids = {s.get("id") for s in needs_a_model}
    no_model_said = {f"step {i} ({s.get('id', '?')}): "
                     f"{(s.get('problem') or {}).get('sentence') or s.get('gap') or 'no model is chosen for it'}"
                     for i, s in enumerate(recipe.get("steps") or [], start=1)
                     if s.get("id") in kept_ids and "model" in s and s["model"] is None}
    # A recipe that does not pass the check never starts (`source.recipe.steps-are-jobs`).
    refusals = [r for r in check_recipe(recipe) if r not in no_model_said]
    every = _with_readers(runs)  # each step's readers per kind are fetched and checked like its own model (#5578)
    downloads = runtime_to_set_up(every) + missing_models(every) + local_models_to_download(every)
    if db is not None:
        mark_downloads_under_way(db, downloads)
    # A model that is not here never refuses Start: Start fetches it itself and its steps wait for it (#5664,
    # ruled 2026-10-11: Set Up never downloads). Only a model that cannot be fetched at all refuses, below.
    waiting = [_downloading(d) for d in downloads if d.get("downloading")]
    cannot = local_models_this_mac_cannot_serve(every)
    elsewhere = places_elsewhere(every, stays_local=stays_local)
    for entry in elsewhere:  # the refusal of a model this Mac cannot run says what other place, if any, is offered
        head = f"steps {', '.join(entry['steps'])} cannot run on this Mac"
        cannot = [f"{r} {entry['said']}" if r.startswith(head) else r for r in cannot]
    refusals += cannot
    if not runs and not refusals:
        nothing = isinstance(automatic, dict) and not automatic.get("runs", True)
        refusals.append("What runs by itself is “Nothing runs automatically”: new material waits for a run by hand"
                        if nothing else "nothing in this recipe can run yet: every step is skipped (see why)")
    return {"runs": runs, "workflows": [r for r in runs if r["card"] == "workflow"], "skipped": skipped,
            "offered": offered, "refusals": refusals, "downloads": downloads, "elsewhere": elsewhere,
            "waiting": waiting, "start_downloads": start_downloads(downloads), "fallbacks": fallbacks}


def place_runs(runs: list[dict[str, Any]], pages: int, *, cloud_allowed: bool, bound_cluster: str | None = None,
               pages_per_second: float | None = None) -> list[dict[str, Any]]:
    """Each read run says where it runs (`place`, `target`, `why`) and what a run that size costs (`sizing`), for
    its step row (`source.recipe.placement-by-scale`, #5589). With no measured rate the sizing says a pilot measures
    it. `bound_cluster` is the project's cluster (`answers.cluster`, `runs-on-binds-to-a-target`), its id. ponytail:
    only a run with one Kraken reader goes there (the runner sends it as a read-at-scale run); a vision reader's
    cluster build, and one reader per material, stay here and say so."""
    from fichero_server.recipes.placement import place_step
    from fichero_server.remote_read.sizing import size_run

    for run in runs:
        if run.get("job") != "read-a-line":
            continue
        sendable = run.get("provider_override") == KRAKEN_READER_PROVIDER and not run.get("readers")
        run.update(place_step(pages, pages_may_leave=cloud_allowed, bound_cluster=bound_cluster if sendable else None))
        unsent = bound_cluster and not sendable and run["place"] == "this-mac"
        if unsent and run["why"].endswith("set up for this project"):
            run["why"] = (f"{pages:,} pages would suit the cluster {bound_cluster}, but only a single Kraken reader is "
                          "sent there yet, not a vision reader or one reader per material")
        try:
            run["sizing"] = size_run(pages, pages_per_second=pages_per_second or 0)
        except ValueError:
            run["sizing"] = "measured by a 1,000-page pilot"
    return runs


def _size_words(size_mb: int | None) -> str:
    if not size_mb:
        return "size not stated"
    return f"{size_mb} MB" if size_mb < 1000 else f"{size_mb / 1000:.1f} GB"


def start_downloads(downloads: list[dict[str, Any]]) -> dict[str, Any] | None:
    """What pressing Start will fetch before its steps run, for Ready to say in one line (#5664): each model by the
    name a person reads, its size, and the total. None when nothing needs fetching. A download already under way
    is not in it (`waiting` says that one)."""
    fetch = [d for d in downloads if not d.get("downloading")]
    if not fetch:
        return None
    items = [{"name": d.get("name") or d["model"], "size_mb": d.get("size_mb"), "steps": list(d["steps"])}
             for d in fetch]
    named = [f"{i['name']} ({_size_words(i['size_mb'])})" for i in items]
    listed = named[0] if len(named) == 1 else ", ".join(named[:-1]) + " and " + named[-1]
    total = sum(i["size_mb"] or 0 for i in items)
    unknown = any(not i["size_mb"] for i in items)
    sentence = f"Start downloads {listed}"
    if len(items) > 1 and total:
        sentence += f": {'at least ' if unknown else ''}{_size_words(total)} in all"
    return {"items": items, "total_mb": total, "total_known": not unknown, "sentence": sentence + "."}


def queue_downloads(db: Any, plan: dict[str, Any], *, started_by: str) -> list[str]:
    """Start fetches every model its plan needs that is not here and not already downloading, through the one
    download path (`model.download`'s `enqueue_download`, a `download-model` job on the network lane, resumable,
    in Activity). Each download is then marked under way, so the run's steps on it wait for it to land
    (`runner.enqueue`'s `awaited`). ValueError, in words, for a model that cannot be fetched at all. Returns the
    jobs queued."""
    from fichero_server.llm.local_models import enqueue_download

    queued = []
    for download in plan.get("downloads") or []:
        if download.get("downloading"):
            continue
        try:
            job_id = enqueue_download(db, download["runtime"], download["model"], started_by=started_by)
        except ValueError as exc:
            raise ValueError(f"steps {', '.join(download['steps'])} need {download.get('name') or download['model']}, "
                             f"which cannot be downloaded: {exc}") from exc
        download.update(downloading=True, job_id=job_id, progress=None)
        queued.append(job_id)
    return queued


#: A download-model job still under way: waiting for the network lane, fetching, or paused.
_UNDER_WAY = frozenset({"waiting", "running", "paused"})


def mark_downloads_under_way(db: Any, downloads: list[dict[str, Any]]) -> None:
    """Mark each download the project's queue is already fetching (a `download-model` job not yet ended):
    `downloading`, its `job_id`, and its `progress` as the job last said it ("Downloading Qwen2.5-VL 7B: 1.2 GB of
    5.6 GB"), or None (#5660). The job's subject is `<runtime>:<model>`, as `enqueue_download` names it."""
    from fichero_server.execution import jobs
    from fichero_server.llm.local_models import DOWNLOAD_KIND

    by_subject = {f"{d['runtime']}:{d['model']}": d for d in downloads}
    if not by_subject:
        return
    for row in sorted(jobs.jobs_on_subjects(db, list(by_subject)), key=lambda r: str(r["created_at"])):
        if row["kind"] != DOWNLOAD_KIND or row["state"] not in _UNDER_WAY:
            continue
        download = by_subject[row["subject"]]
        download.update(downloading=True, job_id=row["id"], progress=row["reason"] or None)


def _downloading(download: dict[str, Any]) -> str:
    """The plan's words for a download under way: its steps wait for it and run when it lands (#5660)."""
    steps = ", ".join(download["steps"])
    name = download.get("name") or download["model"]
    progress = download.get("progress")
    return (f"steps {steps} wait for {name}, which is downloading"
            + (f" ({progress})" if progress else "") + ": they run when it lands")


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


def _without_what_waits(runs: list[dict[str, Any]], needs_a_model: list[dict[str, Any]], recipe: dict[str, Any],
                        skip: Any) -> list[dict[str, Any]]:
    """The runs that do not need what a step with no model would have made; each that does is skipped, saying it
    waits for that step (`source.onboard.no-model-step-kept`). A take is met when the material starts with it or
    another run gives it. ponytail: one pass, so a run that waits on a run skipped here is not caught; add a loop
    if a recipe ever chains two such waits."""
    from fichero_server.recipes.jobs import get_job, starts_with

    missing: dict[str, str] = {}
    for step in needs_a_model:
        for kind in getattr(get_job(step.get("job", "")), "gives", ()):
            missing.setdefault(kind, str(step.get("id")))
    if not missing:
        return runs
    material = (recipe.get("suits") or {}).get("material")
    have = set(starts_with([material] if isinstance(material, str) else material))
    for run in runs:
        have |= set(run.get("gives") or ())
    kept = []
    for run in runs:
        waits = sorted({missing[k] for take in run.get("takes") or [] if not have & set(take.split("|"))
                        for k in take.split("|") if k in missing})
        if waits:
            for sid in run["steps"]:
                skip(sid, f"step {sid} waits for {', '.join(waits)}, which has no model yet", "choose-model")
            continue
        kept.append(run)
    return kept


def missing_models(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The downloadable models the plan's steps are pinned to that are not on this Mac
    (`source.recipe.missing-model-offered`): spaCy pipelines, Kraken readers (a catalogue or Zenodo reader;
    a reader trained here is never a download) and YOLO layout models, each offered as a `download-model` job."""
    from fichero_server.llm import kraken_runtime
    from fichero_server.llm.local_models import SPACY_MODELS, spacy_pipeline_available

    out: dict[str, dict[str, Any]] = {}
    for run in runs:
        name = run.get("model_override") or (run.get("model") if run.get("card") == "regions" else None)
        runtime = run.get("provider_override") or (run.get("provider") if run.get("card") == "regions" else None)
        if not name:
            continue
        if runtime == "yolo":
            from fichero_server.llm.yolo_runtime import YOLO_MODELS, is_installed

            if name not in YOLO_MODELS or is_installed(name):
                continue
            label = f"the layout model {YOLO_MODELS[name][2].split(',')[0]}"
            size_mb = YOLO_MODELS[name][3] // 1_000_000 or None
        elif runtime == "spacy":
            if spacy_pipeline_available(name):
                continue
            size_mb = SPACY_MODELS.get(name, {}).get("disk_mb")
            label = f"the spaCy pipeline {name}"
        elif runtime == "kraken":
            spec = kraken_runtime.recognition_spec(name)
            if not spec or "trained" in spec or _kraken_reader_here(name):
                continue
            record = _repository_record(spec.get("doi"))
            size_bytes = spec.get("size_bytes") or record.get("size_bytes")
            size_mb = (int(size_bytes) // 1_000_000 or None) if size_bytes else spec.get("size_mb")
            label = f"the Kraken reader {spec.get('display_name') or _seed_name(spec.get('doi')) or record.get('summary') or name}"
        else:
            continue
        entry = out.setdefault(name, {"runtime": runtime, "model": name, "name": label, "steps": [],
                                      "size_mb": size_mb, "action": "model.download",
                                      "params": {"runtime": runtime, "model": name}})
        _add_steps(entry["steps"], run["steps"])
    return list(out.values())


def _kraken_reader_here(name: str) -> bool:
    """Whether the Kraken reader `name` is downloaded to this Mac."""
    from fichero_server.llm import kraken_runtime

    return bool(kraken_runtime.recognition_model_path(name))


def _seed_name(doi: Any) -> str | None:
    """A shipped reader's own name for this Zenodo DOI (its card's `note`, as setup's rows show it)."""
    from fichero_server.recipes.cards import all_seed_cards

    card = next((c for c in all_seed_cards() if doi and c.pin.get("zenodo") == doi), None)
    return card.note.split(",")[0].strip().rstrip(".") if card is not None and card.note else None  # its short name


def _repository_record(doi: Any) -> dict[str, Any]:
    """A Zenodo reader's record as the kept repository listing has it (its title, `summary`, and size); empty
    without one. Never the network."""
    from fichero_server.recipes.discovery import repository_record

    return (repository_record(str(doi)) if doi else None) or {}


#: Jobs whose local model reads the page image; the others send it text alone.
_TEXT_ONLY_JOBS = frozenset({"find-names-tag-words", "find-statements", "split-into-entries", "extract-to-a-table"})


def _capability(run: dict[str, Any]) -> str:
    return "text" if run["job"] in _TEXT_ONLY_JOBS else "vision"


def _local_model(run: dict[str, Any]) -> str | None:
    """The model a run asks this Mac's local model server (`omlx`) for, or None for any other run."""
    provider = run.get("provider_override") or run.get("provider")
    model = run.get("model_override") or run.get("model")
    return model if provider == "omlx" and model else None


def runtime_to_set_up(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """This Mac's local model runtime (MLX), as a download Start fetches first, when a run is served by the local
    model server and the runtime is not set up (#5664: Start fetches what its steps need; seen 2026-10-11, every
    step on Qwen2.5-VL failing "MLX runtime is not provisioned"). None in the app, where MLX ships inside it."""
    from fichero_server.llm.local_models import MLX_RUNTIME, MLX_RUNTIME_NAME
    from fichero_server.llm.mlx_runtime import bundled_versions, get_mlx_runtime

    steps: list[str] = []
    for run in runs:
        if _local_model(run) is not None:
            _add_steps(steps, run["steps"])
    if not steps or bundled_versions() is not None or get_mlx_runtime().is_provisioned():
        return []
    return [{"runtime": MLX_RUNTIME, "model": "mlx", "name": MLX_RUNTIME_NAME, "steps": steps, "size_mb": None,
             "action": "model.download", "params": {"runtime": MLX_RUNTIME, "model": "mlx"}, "instead": []}]


def local_models_to_download(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The catalogue MLX models the plan's runs are pinned to that are not installed, each offered as a download
    (`runtime` mlx, its name and size, the steps it serves) and, in `instead`, the installed models this Mac can
    serve for every one of those steps, each by its card, to use in one press (`use_instead`,
    `source.onboard.auto.installed-model-first`, #5583)."""
    from fichero_server.llm import local_model_choice

    store = local_model_choice._store()
    out: dict[str, dict[str, Any]] = {}
    for run in runs:
        model = _local_model(run)
        if model is None:
            continue
        problem = local_model_choice.local_model_problem(model, _capability(run), store=store)
        if problem is None or problem.kind != "not-installed":
            continue
        model_id = store.canonical_id(model)
        spec = store.spec(model_id)
        instead = _installed_instead(run, store)
        entry = out.get(model_id)
        if entry is None:
            out[model_id] = {"runtime": "mlx", "model": model_id, "name": spec.display_name,
                             # A size the Hub did not state is unknown (None), never 0 MB (#5593).
                             "steps": list(run["steps"]), "size_mb": spec.download_size_bytes // 1_000_000 or None,
                             "action": "model.download", "params": {"runtime": "mlx", "model": model_id},
                             "instead": instead}
        else:
            _add_steps(entry["steps"], run["steps"])
            fits = {i["card"] for i in instead}
            entry["instead"] = [i for i in entry["instead"] if i["card"] in fits]
    return list(out.values())


def _installed_instead(run: dict[str, Any], store: Any) -> list[dict[str, str]]:
    """The installed models' cards that name this run's job and that this Mac's server can serve for it."""
    from fichero_server.llm.local_model_choice import local_model_problem
    from fichero_server.recipes.cards import mlx_model_for
    from fichero_server.recipes.discovery import known_cards

    out: dict[str, dict[str, str]] = {}
    for card in known_cards():
        repo = mlx_model_for(card.pin) if card.installed and run["job"] in card.jobs else None
        if repo is None or local_model_problem(repo, _capability(run), store=store) is not None:
            continue
        model_id = store.canonical_id(repo)
        # A licence that is not open is named, so the press that chooses it says what it accepts.
        out.setdefault(model_id, {"card": card.id, "model": model_id, "name": store.spec(model_id).display_name,
                                  "licence": "" if card.open_licence else (card.licence or "not open")})
    return list(out.values())


def use_instead(recipe: dict[str, Any] | None, downloads: list[dict[str, Any]], model: str, card: Any, *,
                now: str) -> dict[str, Any]:
    """The recipe with the installed model `card` set, as a project-scope override (the one way a person's choice
    of model is kept, as Use This keeps a bake-off's), on every step pinned to the download `model` the plan
    offers it instead of (`source.onboard.auto.installed-model-first`, #5583). The press is the person's
    deliberate choice, a licence that is not open included. ValueError, in words, when the plan offers no such
    choice."""
    import copy

    from fichero_server.llm import local_model_choice
    from fichero_server.recipes.bakeoff import apply_project_overrides
    from fichero_server.recipes.cards import mlx_model_for

    if not recipe:
        raise ValueError("this project has no recipe yet: run setup first")
    offer = next((d for d in downloads if d.get("runtime") == "mlx" and d["model"] == model), None)
    if offer is None:
        raise ValueError(f"{model} is not a model this project's Start waits to download")
    chosen = next((i for i in offer.get("instead") or [] if i["card"] == card.id), None)
    if chosen is None:
        raise ValueError(f"{card.note or card.id} is not an installed model offered instead of {offer['name']}")
    store = local_model_choice._store()
    out = copy.deepcopy(recipe)
    because = (f"chosen by you: the installed {chosen['name']}, rather than downloading {offer['name']} "
               f"({offer['size_mb']} MB)")
    for step in out.get("steps") or []:
        repo = mlx_model_for(step.get("model") or {})
        if step.get("id") not in offer["steps"] or not repo or store.canonical_id(repo) != model:
            continue
        _keep_choice(out, step["id"], card, because, now)
    return apply_project_overrides(out, [card])


def _keep_choice(recipe: dict[str, Any], sid: str, card: Any, because: str, now: str) -> None:
    """Keep the person's choice of `card` for step `sid` as its project-scope override, replacing any earlier one:
    the one way a chosen reader is kept (Use This, use-instead, a found candidate). Changes `recipe` in place."""
    override = {"step": sid, "scope": "project", "folder_id": None, "model": dict(card.pin), "card": card.id,
                "runs_on": card.runs_on, "because": because, "at": now}
    recipe["overrides"] = [o for o in recipe.get("overrides") or []
                           if (o.get("step"), o.get("scope"), o.get("folder_id")) != (sid, "project", None)]
    recipe["overrides"].append(override)


def use_candidate(recipe: dict[str, Any] | None, step_id: str, card: Any, *, now: str) -> dict[str, Any]:
    """The recipe with any found candidate `card` set as step `step_id`'s reader, kept as a project-scope override
    by the path use-instead and Use This take (#5612, `source.find.app-card-actions`). The press is the person's
    deliberate choice: the rules' refusals (a licence, a script its card does not state) do not stop it, but a card
    that does not do the step's job does. ValueError, in words."""
    import copy

    from fichero_server.recipes.bakeoff import apply_project_overrides

    if not recipe:
        raise ValueError("this project has no recipe yet: run setup first")
    out = copy.deepcopy(recipe)
    step = next((s for s in out.get("steps") or [] if s.get("id") == step_id), None)
    if step is None:
        raise ValueError(f"this project's recipe has no step {step_id!r}")
    if step.get("job") not in card.jobs:
        raise ValueError(f"{card.note.strip().rstrip('.') or card.id} does not do the step {step_id!r} "
                         f"({step.get('job')}): it does {', '.join(sorted(card.jobs)) or 'no job'}")
    because = f"chosen by you from the models found ({card.offered_because or card.source})"
    _keep_choice(out, step_id, card, because, now)
    return apply_project_overrides(out, [card])


def local_models_this_mac_cannot_serve(runs: list[dict[str, Any]]) -> list[str]:
    """A refusal for each run whose own local model (`omlx`) this Mac's local model server cannot
    serve -- not in the catalogue, not installed, or its card says this Mac's memory cannot run it
    -- with the reason and the fix, BEFORE Start (#5496, #5520). The step's model is the one the
    run asks the server for, which switches to it; it is never served another in its place. One that is only
    not installed is not refused here: the plan offers its download and any installed model instead (#5583)."""
    from fichero_server.llm.local_model_choice import local_model_problem

    out = []
    for run in runs:
        model = _local_model(run)
        if model is None:
            continue
        problem = local_model_problem(model, _capability(run))
        # A catalogue model that is only not installed yet is a download offer (`local_models_to_download`).
        if problem is not None and problem.kind != "not-installed":
            out.append(f"steps {', '.join(run['steps'])} cannot run on this Mac: {problem}")
    return out


def places_elsewhere(runs: list[dict[str, Any]], *, stays_local: bool) -> list[dict[str, Any]]:
    """For each local model this Mac cannot run (its card says this Mac's memory cannot), the other places that
    run the same model and cost nothing, each offered in `instead` to choose in one press (`use_place_instead`),
    never used without it (`ai.where.fallback-free-and-asked`, #5592). A place is one of the person's provider
    rows, enabled, off this Mac, that lists the model by the same id; it is free when it is the person's own machine,
    or when the price list says its input and output cost nothing. A paid place, or one whose price is not known, is never offered; a project that
    keeps its pages on this Mac is offered no other place. `said` is the sentence its refusal adds."""
    from fichero_server.llm import local_model_choice

    store = local_model_choice._store()
    out: dict[str, dict[str, Any]] = {}
    for run in runs:
        model = _local_model(run)
        if model is None:
            continue
        problem = local_model_choice.local_model_problem(model, _capability(run), store=store)
        if problem is None or problem.kind != "cannot-run":
            continue
        model_id = store.canonical_id(model)
        if model_id in out:
            _add_steps(out[model_id]["steps"], run["steps"])
            continue
        spec = store.spec(model_id)
        free, paid = ([], []) if stays_local else _places_running({model, model_id, spec.repo_id})
        if stays_local:
            said = "This project keeps its pages on this Mac, so no other place is offered."
        elif free:
            said = (f"Or run it free at {' or '.join(p['provider_name'] for p in free)} instead, "
                    "if you choose to (Set Up… › Ready).")
        elif paid:
            said = (f"{' and '.join(paid)} {'runs' if len(paid) == 1 else 'run'} it, but not free: a step moves to "
                    "another place only when that place is free, and only when you choose it.")
        else:
            said = "No other place you have set up runs it free."
        out[model_id] = {"runtime": "mlx", "model": model_id, "name": spec.display_name, "steps": list(run["steps"]),
                         "why": str(problem), "said": said, "instead": free}
    return list(out.values())


def _places_running(ids: set[str]) -> tuple[list[dict[str, Any]], list[str]]:
    """(the free places, the names of the paid or unpriced ones) among the person's enabled provider rows off this
    Mac that list the model by one of `ids`. The person's own machine (`own_machine`) is free; any other place is
    free only by the price list's word (input and output cost 0), never a guess: a row's own stated cost, or no
    price at all, is not free."""
    from fichero_server.db.app import get_app_db
    from fichero_server.llm import LLMConfig, usage
    from fichero_server.llm.places import OWN_MACHINE, THIS_MAC, place_of

    app_db = get_app_db()
    free, paid = [], []
    for row in app_db.list_providers():
        ptype = row.provider_type.value
        place = place_of(LLMConfig(provider=ptype, model="", api_base=row.api_base))
        if not row.enabled or place == THIS_MAC:
            continue
        listed = next((m for m in app_db.list_models(row.id) if m.enabled and m.model_id in ids), None)
        if listed is None:
            continue
        price = usage._registry_entry(listed.model_id, ptype) or {}
        # The person's own machine costs nothing (ruled 2026-10-08); a company's place is free only at $0 listed.
        if place == OWN_MACHINE or (price.get("input_cost_per_token") == 0
                                    and price.get("output_cost_per_token") == 0):
            free.append({"model": listed.model_id, "name": listed.name or listed.model_id, "provider": row.id, "provider_name": row.name, "provider_type": ptype, "place": place,
                         "free": True})
        else:
            paid.append(row.name)
    return free, paid


def use_place_instead(recipe: dict[str, Any] | None, elsewhere: list[dict[str, Any]], model: str, provider: str, *,
                      now: str) -> dict[str, Any]:
    """The recipe with the free place `provider` (a provider row id) set, as a project-scope override, on every step
    pinned to the model this Mac cannot run that the plan offers it for (`ai.where.fallback-free-and-asked`, #5592):
    the same model, at that place. The press is the person's choice; nothing moves a step to another place without
    it. ValueError, in words, when the plan offers no such place."""
    import copy

    from fichero_server.llm import local_model_choice
    from fichero_server.recipes.assemble import Card
    from fichero_server.recipes.bakeoff import apply_project_overrides
    from fichero_server.recipes.cards import mlx_model_for

    if not recipe:
        raise ValueError("this project has no recipe yet: run setup first")
    offer = next((e for e in elsewhere if e["model"] == model), None)
    if offer is None:
        raise ValueError(f"{model} is not a model this project's Start finds this Mac cannot run")
    chosen = next((i for i in offer["instead"] if i["provider"] == provider), None)
    if chosen is None:
        raise ValueError(f"that place is not one offered free for {offer['name']}: a step moves to another place "
                         "only when that place is free")
    store = local_model_choice._store()
    out = copy.deepcopy(recipe)
    because = (f"chosen by you: {offer['name']} at {chosen['provider_name']}, free, because this Mac cannot run it "
               f"({offer['why']})")
    cards = []
    for step in out.get("steps") or []:
        repo = mlx_model_for(step.get("model") or {})
        if step.get("id") not in offer["steps"] or not repo or store.canonical_id(repo) != model:
            continue
        was = step.get("card") or {}
        card = Card(id=f"cloud:{chosen['provider_type']}/{chosen['model']}@{provider}",
                    pin={"cloud": chosen["provider_type"], "model": chosen["model"]}, jobs=frozenset({step["job"]}),
                    scripts=None, languages=None, material=frozenset(), runs_on=f"cloud:{chosen['provider_type']}",
                    open_licence=bool(was.get("open_licence", True)), licence=str(was.get("licence") or ""),
                    note=f"{offer['name']} at {chosen['provider_name']} (free)")
        cards.append(card)
        sid = step["id"]
        override = {"step": sid, "scope": "project", "folder_id": None, "model": dict(card.pin), "card": card.id,
                    "runs_on": card.runs_on, "place": chosen["place"], "provider": provider, "free": True,
                    "because": because, "at": now}
        out["overrides"] = [o for o in out.get("overrides") or []
                            if (o.get("step"), o.get("scope"), o.get("folder_id")) != (sid, "project", None)]
        out["overrides"].append(override)
    return apply_project_overrides(out, cards)


def estimate(workflows: list[dict[str, Any]], pages: int) -> dict[str, Any]:
    """What Start would cost, before anything runs (`source.onboard.estimate-before-start`).

    Local runs cost nothing; a cloud run is priced with the workflow estimate's per-page token
    assumptions. An unpriced model is `None`, never a stand-in zero, and makes the total `None`.
    """
    from fichero_server.recipes.review_profiles import REVIEW_PRESET, lens_ids, review_passes

    rows, total = [], 0.0
    for w in workflows:
        runs_on = str(w["runs_on"])
        review = w.get("job") == "correct"
        # The review makes a call a page for each pass it runs, one a lens on (#5723); any other run, one.
        calls = review_passes(REVIEW_PRESET, w.get("lenses")) if review else 1
        cost = _priced(w, pages * calls)
        basis = "unpriced" if cost is None else "free on this Mac" if not runs_on.startswith("cloud") else "the model's listed rate"
        # ponytail: a lens a pass, as the paleographer review runs them; each lens's page costs one call.
        per_lens = _priced(w, 1) if review else None
        lenses = [{"lens": lens, "on": w.get("lenses") is None or lens in w["lenses"], "cost_per_page_usd": per_lens}
                  for lens in lens_ids()] if review else []
        rows.append({"workflow": w["workflow"], "steps": w["steps"], "where": w["runs_on"],
                     "pages": pages, "cost_usd": cost, "basis": basis, "memory": _local_memory(w),
                     "calls_per_page": calls, "lenses": lenses})
        total = None if total is None or cost is None else total + cost
    return {"pages": pages, "runs": rows, "total_cost_usd": total}


def _priced(run: dict[str, Any], calls: int) -> float | None:
    """What `calls` model calls of `run` cost. Only this Mac is free by its own word; a cloud call is priced by the
    model's listed rate; any other place (a cluster, a person's other machine) is unpriced, never $0 (#5590)."""
    from fichero_server.workflows.model_comparison import estimate_cost

    runs_on = str(run["runs_on"])
    if runs_on.startswith("cloud"):
        return estimate_cost(run["model_override"] or "", calls * _TOKENS_IN, calls * _TOKENS_OUT,
                             provider=run["provider_override"] or "")
    return 0.0 if runs_on in ("this-mac", "") else None


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
