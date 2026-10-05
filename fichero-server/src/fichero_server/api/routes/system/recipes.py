"""Recipes: the job registry, checking a recipe, and assembling one from setup's answers.

Spec: `source/models-chains-and-projects.md` (`source.recipe.*`, `source.onboard.*`). Read-only:
nothing here writes to a library. The setup window, the Inspector, the command line and MCP all
read the same answers from the engine (four architecture rules: logic in the engine).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from fichero_server.actions.registry import ActionContext, ChangeSpec, action, registry
from fichero_server.api.auth import action_context
from fichero_server.api.main import get_library_database, get_library_database_for_write
from fichero_server.db import Database

from fichero_server.recipes.assemble import PURPOSE_STEPS, PURPOSES, Answers, assemble


# The recipe store, cards, job registry and check load on first use, not at app start (#3950); the purposes
# (`recipes.assemble`, standard library only) are read at start, for the schema's descriptions.
def read_project_setup(library: Path) -> dict[str, Any]:
    from fichero_server.recipes.project import read_project_setup as read

    return read(library)


def write_project_setup(library: Path, answers: Any, recipe: Any) -> None:
    from fichero_server.recipes.project import write_project_setup as write

    write(library, answers, recipe)


def seed_cards() -> Any:
    from fichero_server.recipes.cards import seed_cards as seed

    return seed()


def all_jobs() -> Any:
    from fichero_server.recipes.jobs import all_jobs as jobs

    return jobs()


def check_recipe(recipe: Any) -> list[str]:
    from fichero_server.recipes.recipe import check_recipe as check

    return check(recipe)

router = APIRouter(prefix="/recipes")


class JobInfo(BaseModel):
    id: str
    name: str = Field(description="the title of its entry in the topic registry")
    # Kept because setup (RecipeStepsView) shows it; it is the topic's text, not a second copy.
    description: str = Field(description="the short sentence and paragraph of its topic (GET /api/topics/{id})")
    topic: str = Field(description="the topic registry id that explains this job (GET /api/topics/{id})")
    layer: str
    takes: list[str]
    gives: list[str]
    compare: str
    settings: list[str]
    since: str


class JobListResponse(BaseModel):
    items: list[JobInfo]
    count: int


@router.get("/jobs", response_model=JobListResponse)
async def list_jobs() -> JobListResponse:
    """Every job a recipe can name, with the plain description setup and the manual show."""
    items = [
        JobInfo(id=j.id, name=j.name, description=j.description, topic=j.topic.id, layer=j.layer,
                takes=sorted(j.takes), gives=sorted(j.gives), compare=j.compare,
                settings=list(j.settings), since=j.since)
        for j in all_jobs()
    ]
    return JobListResponse(items=items, count=len(items))


class AssembleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    purposes: list[str] = Field(default_factory=list, description=(
        f"the ticked purposes, any combination, each one of: {', '.join(PURPOSE_STEPS)}; none is 'not-sure'. "
        "The recipe is the union of their jobs, each once, in step order (source.onboard.purpose-sets-layers)"))
    purpose: Optional[str] = Field(default=None, description="a single purpose, as before 2026-10-05: read as "
                                   "a list of one")
    languages: list[str] = Field(min_length=1, description=(
        "BCP 47 language tags; a language's name is resolved to its tag when exactly one language has it, "
        "and refused in words otherwise (source.onboard.language-stored-as-tag)"))
    scripts: list[str] = Field(min_length=1, description="ISO 15924 script codes (or a script's English name)")
    materials: list[str] = Field(default_factory=list, description=(
        "handwriting, print and/or typescript, any mix; default handwriting. A reading step gets one reader "
        "per kind (source.onboard.material-any-mix)"))
    material: Optional[str] = Field(default=None, description="a single material, as before 2026-10-05")
    jobs: list[str] = Field(default_factory=list, description="jobs ticked on their own, beyond the purposes' "
                            "(GET /api/recipes/jobs)")
    directions: dict[str, str] = Field(default_factory=dict, description=(
        "script code -> ltr, rtl, ttb (columns right to left) or ttb-lr; a script left out takes its own "
        "(source.onboard.direction-chosen)"))
    pages: int = Field(default=0, ge=0, description="roughly how many pages")
    cloud_allowed: bool = False
    mac_memory_gb: Optional[float] = Field(default=None, description="defaults to this machine's memory")
    layers: list[str] = Field(default_factory=list, description="layers added beyond the purposes' "
                              "(source.onboard.add-layer)")


class RecipeCard(BaseModel):
    """The facts on the chosen model's card that setup shows (`source.onboard.proposes-chain`)."""

    id: str = Field(description="<runtime>:<source>@<version>")
    note: str = ""
    licence: str = ""
    open_licence: bool = True
    size_gb: float = 0.0
    memory_gb: float = 0.0
    cer_measured_here: Optional[float] = None
    cer_published: Optional[float] = None
    trainable: bool = False


class StepProblem(BaseModel):
    """Why a step has no model, once, in words a historian reads (`source.onboard.says-no-model`)."""

    kind: str = Field(description="no-model-for-job, no-model-for-script, no-model-for-language, "
                      "no-reader-for-material, licence-not-accepted, cloud-not-allowed or not-enough-memory")
    sentence: str = Field(description="one plain sentence; never a model's id, pin or repository")
    fix: str = Field(description="the fix setup offers as its button: download, choose-cloud, choose-model, "
                     "allow-cloud or accept-licence")
    fixes: list[str] = Field(description="every fix that applies, `fix` first")
    detail: str = Field(description="the rules' own reason, model ids included: for the Inspector and the log")


class StepReader(BaseModel):
    """The reader proposed for one kind of material (`source.onboard.material-any-mix`)."""

    material: str
    model: Optional[dict[str, Any]] = None
    card: Optional[RecipeCard] = None
    runs_on: Optional[str] = None
    reasons: list[str] = Field(default_factory=list)
    gap: Optional[str] = None
    problem: Optional[StepProblem] = None


class RecipeStep(BaseModel):
    id: str
    job: str
    topic: Optional[str] = Field(default=None, description="the topic registry id that explains it (GET /api/topics/{id})")
    title: Optional[str] = Field(default=None, description="its topic's title")
    sentence: Optional[str] = Field(default=None, description="its topic's one sentence")
    model: Optional[dict[str, Any]] = None
    card: Optional[RecipeCard] = None
    uses_cloud: bool = False
    runs_on: Optional[str] = None
    reasons: list[str] = Field(default_factory=list)
    gap: Optional[str] = Field(default=None, description="the rules' raw reason; setup shows `problem` instead")
    problem: Optional[StepProblem] = None
    material: Optional[str] = Field(default=None, description="with several materials: the kind the step's own "
                                    "model reads (the default until an override says which applies where)")
    readers: Optional[list[StepReader]] = Field(default=None, description="with several materials: one reader "
                                                "per kind ticked")
    layer: Optional[str] = None
    offered_when: Optional[dict[str, Any]] = None
    settings: Optional[dict[str, Any]] = None


class AssembledRecipe(BaseModel):
    # Optional so older clients keep decoding; present so a recipe saved from this answer is a
    # whole recipe.yaml that passes the check (`source.recipe.is-a-file`).
    fichero_recipe: Optional[int] = Field(default=None, description="the recipe schema version")
    id: str
    version: Optional[str] = None
    title: str
    suits: Optional[dict[str, Any]] = Field(default=None, description="scripts, languages and material it suits")
    purposes: list[str]
    steps: list[RecipeStep]
    gaps: list[str]
    cloud_options: list[str] = Field(
        default_factory=list,
        description="jobs a cloud model would also fit if pages could leave this Mac; "
        "setup asks the egress question only when this is not empty",
    )
    problems: list[str] = Field(description="what the recipe check finds (empty when it can run)")


def _this_machine_memory_gb() -> float:
    try:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1e9
    except (ValueError, OSError):
        return 8.0


class PurposeJob(BaseModel):
    id: str = Field(description="the job's registry id")
    title: str = Field(description="its topic's title")


class PurposeInfo(BaseModel):
    id: str
    title: str
    description: str
    runs_by_itself: bool = Field(description="true: its layers run after Start; false: tools are offered")
    jobs: list[PurposeJob] = Field(default_factory=list, description=(
        "the jobs it proposes, in step order, by their topic titles (source.onboard.purposes-show-their-jobs)"))


class PurposeListResponse(BaseModel):
    items: list[PurposeInfo]
    count: int


@router.get("/purposes", response_model=PurposeListResponse)
async def list_purposes() -> PurposeListResponse:
    """The purposes setup offers as checkboxes, in order, each with its label, whether it runs by
    itself and the jobs it proposes (`source.onboard.purpose-first`)."""
    from fichero_server.recipes.jobs import get_job

    items = [
        PurposeInfo(id=pid, title=title, description=desc, runs_by_itself=bool(PURPOSE_STEPS[pid]),
                    jobs=[PurposeJob(id=j, title=get_job(j).name) for j in PURPOSE_STEPS[pid]])
        for pid, (title, desc) in PURPOSES.items()
    ]
    return PurposeListResponse(items=items, count=len(items))


class NamedCode(BaseModel):
    code: str
    name: str


class NamedCodeList(BaseModel):
    items: list[NamedCode]
    count: int


class LanguageMatch(BaseModel):
    """A language or dialect: its BCP 47 tag and its Glottolog code, two systems kept apart."""

    code: Optional[str] = Field(default=None, description="BCP 47 tag; a dialect carries its language's; none when only Glottolog knows it")
    name: str
    glottocode: Optional[str] = Field(default=None, description="Glottolog 5.3 code, where Glottolog has one")
    level: str = Field(description="language or dialect")
    language: Optional[str] = Field(default=None, description="for a dialect, the language it belongs to")


class LanguageMatchList(BaseModel):
    items: list[LanguageMatch]
    count: int


@router.get("/languages", response_model=LanguageMatchList)
async def search_languages(q: str = "", limit: int = 20) -> LanguageMatchList:
    """Search ISO 639-3 and Glottolog languages and dialects by name, tag or glottocode
    (`source.onboard.widget-and-search`)."""
    from fichero_server.recipes.names import search_languages as find

    items = [LanguageMatch(**row) for row in find(q, max(1, min(limit, 100)))]
    return LanguageMatchList(items=items, count=len(items))


class Figure(BaseModel):
    """One number and where it came from: measured here, an estimate, or unknown."""

    value: Optional[float] = None
    basis: str = Field(description="measured, estimate or unknown")
    source: str = Field(alias="from", description="what the figure rests on")

    model_config = ConfigDict(populate_by_name=True)


class RouteStep(BaseModel):
    step: str
    pages: Optional[int] = None
    cost_usd: Optional[Figure] = None
    time_seconds: Optional[Figure] = None


class Route(BaseModel):
    id: str
    title: str
    pages: int
    cost_usd: Optional[Figure] = None
    time_seconds: Optional[Figure] = None
    steps: list[RouteStep] = []
    accuracy_cer: Figure
    leaves_this_mac: bool


class RoutesResponse(BaseModel):
    pages: int
    routes: list[Route]


@router.get("/routes", response_model=RoutesResponse, response_model_by_alias=True)
async def routes_for_volume(
    teacher: str,
    local_reader: str,
    pages: Optional[int] = None,
    sample_pages: int = 300,
    db: Database = Depends(get_library_database),
) -> RoutesResponse:
    """What can we do with this many pages? The cloud, this-Mac and distil routes side by side,
    each figure marked measured, estimate or unknown (`source.onboard.routes-for-the-volume`).
    `pages` defaults to the project's own count."""
    from fichero_server.recipes.routes import routes_for_volume as plan
    from fichero_server.recipes.start import count_pages

    n = pages if pages is not None else count_pages(db)
    if n < 0 or sample_pages < 1:
        raise HTTPException(status_code=422, detail="pages must be 0 or more and sample_pages at least 1")
    return RoutesResponse(pages=n, routes=[Route(**r) for r in plan(
        db, n, teacher=teacher, local_reader=local_reader, sample_pages=sample_pages)])


def _app_database():
    from fichero_server.api.routes.ai.providers import get_app_database

    return get_app_database()


class ScriptFacts(BaseModel):
    script: str
    direction: Optional[str] = None
    direction_from: str
    may_be_vertical: bool
    font: Optional[str] = None
    font_from: str


class MacFacts(BaseModel):
    chip: Optional[str] = None
    memory_gb: Optional[int] = None
    source: str = Field(alias="from")

    model_config = ConfigDict(populate_by_name=True)


class PlaceToRun(BaseModel):
    id: str
    title: str
    source: str = Field(alias="from")

    model_config = ConfigDict(populate_by_name=True)


class DerivedFacts(BaseModel):
    scripts: list[ScriptFacts]
    mac: MacFacts
    keys: list[str] = Field(description="providers with a readable key: names only, never a key")
    targets: list[PlaceToRun]


@router.get("/derived", response_model=DerivedFacts, response_model_by_alias=True)
async def derived_facts(scripts: str = "", app_db=Depends(_app_database)) -> DerivedFacts:
    """What setup works out instead of asking, each fact saying where it came from
    (`source.onboard.derives-not-asks`): per script its direction, whether it may be vertical
    and its bundled font; this Mac's chip and memory; which providers have a key; where work
    can run."""
    from fichero_server.api.routes.ai.hpc import _load_clusters
    from fichero_server.recipes import derived

    codes = [c.strip() for c in scripts.split(",") if c.strip()]
    unknown = derived.unknown_scripts(codes)
    if unknown:
        raise HTTPException(status_code=422, detail=f"not ISO 15924 script codes: {', '.join(unknown)}")
    keys = derived._providers_with_keys()
    clusters = sorted(c.get("name") or cid for cid, c in _load_clusters(app_db).items())
    return DerivedFacts(
        scripts=[ScriptFacts(**derived.script_facts(c)) for c in codes],
        mac=MacFacts(**derived.this_mac()), keys=keys,
        targets=[PlaceToRun(**t) for t in derived.targets(keys, clusters)],
    )


@router.get("/scripts", response_model=NamedCodeList)
async def search_scripts(q: str = "", limit: int = 20) -> NamedCodeList:
    """Search ISO 15924 scripts by name or code (`source.onboard.widget-and-search`)."""
    from fichero_server.recipes.names import search_scripts as find

    items = [NamedCode(**row) for row in find(q, max(1, min(limit, 100)))]
    return NamedCodeList(items=items, count=len(items))


def normalise_answers(answers: Any, *, strict: bool) -> Any:
    from fichero_server.recipes.answers import normalise

    return normalise(answers, strict=strict)


def _assemble(answers: dict[str, Any]) -> dict[str, Any]:
    """The rules' recipe for setup's answers (as sent to `/assemble`, or as saved on the project).
    A language or script given as a word is resolved to its tag first, or refused (ValueError, in
    words): the rules only ever see tags (`source.onboard.language-stored-as-tag`)."""
    a = normalise_answers(answers, strict=True)
    return assemble(Answers(
        purposes=tuple(a["purposes"]), languages=frozenset(a.get("languages") or ()),
        scripts=frozenset(a.get("scripts") or ()), materials=tuple(a["materials"]),
        jobs=tuple(a.get("jobs") or ()),
        pages=a.get("pages") or 0, cloud_allowed=bool(a.get("cloud_allowed")),
        mac_memory_gb=a.get("mac_memory_gb") or _this_machine_memory_gb(),
        layers=frozenset(a.get("layers") or ()),
    ), list(seed_cards()))


@router.post("/assemble", response_model=AssembledRecipe)
async def assemble_recipe(request: AssembleRequest) -> AssembledRecipe:
    """The recipe the rules give for these answers, each choice with its reasons and each gap named
    once as a structured problem (`source.onboard.deterministic-recipe`, `source.onboard.says-no-model`).
    Proposes; writes nothing. Refused with 422, in words, for a language, script, purpose, material,
    job or direction Fichero does not know."""
    try:
        recipe = _assemble(request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    problems = [] if recipe["gaps"] else check_recipe(recipe)
    return AssembledRecipe(
        fichero_recipe=recipe["fichero_recipe"], version=recipe["version"], suits=recipe["suits"],
        id=recipe["id"], title=recipe["title"], purposes=recipe["purposes"],
        steps=[RecipeStep(**s) for s in recipe["steps"]], gaps=recipe["gaps"],
        cloud_options=recipe["cloud_options"], problems=problems,
    )


class CheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recipe: dict[str, Any]


class CheckResponse(BaseModel):
    problems: list[str]


@router.post("/check", response_model=CheckResponse)
async def check(request: CheckRequest) -> CheckResponse:
    """Every reason a recipe cannot run as it stands, step by step (`source.recipe.*`)."""
    return CheckResponse(problems=check_recipe(request.recipe))


# =============================================================================
# A project's saved setup (#4951): the answers and the recipe, as files in the project folder.
# =============================================================================


class ProjectSetup(BaseModel):
    """Setup's answers and the project's recipe; each null when the project has none
    (`source.project.has-settings`). Saving is not Start: nothing runs."""

    model_config = ConfigDict(extra="forbid")
    answers: Optional[dict[str, Any]] = None
    recipe: Optional[dict[str, Any]] = None


def _library(db: Database) -> Path:
    return Path(db.path).parent


@router.get("/project", response_model=ProjectSetup)
async def get_project_setup(db: Database = Depends(get_library_database)) -> ProjectSetup:
    """The open project's saved setup answers and recipe."""
    return ProjectSetup(**read_project_setup(_library(db)))


@router.put("/project", response_model=ProjectSetup)
async def save_project_setup(
    request: ProjectSetup,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> ProjectSetup:
    """Save the project's setup answers and recipe (audited, undoable). A null part is removed.
    The answers are saved in today's shape: `purposes` and `materials` as lists, languages as tags
    and scripts as codes (a word is resolved to its tag, or refused), and one direction per script.
    Refused with 422 when either holds code or credentials, or an answer Fichero does not know."""
    try:
        params = request.model_dump(mode="json")
        params["answers"] = normalise_answers(params["answers"], strict=True)
        result = registry.invoke(db, "project.save_setup", params, ctx)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ProjectSetup(**result.result)


def _invert_save_setup(before: dict | None, after: dict | None, ctx: ActionContext):
    return ("project.save_setup", before or {"answers": None, "recipe": None})


@action("project.save_setup", ProjectSetup, domains=["project"], undoable=True,
        invert=_invert_save_setup)
def _action_save_setup(db: Database, params: ProjectSetup, ctx: ActionContext) -> tuple[dict, ChangeSpec]:
    library = _library(db)
    before = read_project_setup(library)
    write_project_setup(library, params.answers, params.recipe)
    after = read_project_setup(library)
    return after, ChangeSpec(domains=["project"], target_ids=[], before=before, after=after,
                             emit_type="project.setup_saved")


# =============================================================================
# Start: the project's first yes (#4951). `source.project.automatic-after-first-yes`.
# =============================================================================


class StartWorkflow(BaseModel):
    """One shipped workflow Start runs, the recipe steps it carries out, and its model."""

    steps: list[str]
    job: str
    workflow: str = Field(description="the shipped workflow's name in the store")
    workflow_id: str
    provider_override: Optional[str] = None
    model_override: Optional[str] = None
    runs_on: str


class StartEstimateRun(BaseModel):
    workflow: str
    steps: list[str]
    where: str
    pages: int
    cost_usd: Optional[float] = Field(description="0 on this Mac; null when the model has no price")


class StartEstimate(BaseModel):
    pages: int = Field(description="pages, and files with no pages, in the project")
    runs: list[StartEstimateRun]
    total_cost_usd: Optional[float] = None


class StartRecord(BaseModel):
    started_at: str
    recipe_id: Optional[str] = None
    recipe_version: Optional[str] = None
    workflows: list[str]
    pages: int
    job_id: Optional[str] = Field(default=None, description="the recipe run Start queued (`run-a-recipe`)")


class StartRun(BaseModel):
    """One card Start runs, in order: a shipped workflow, a check run, or the project's synced folder."""

    steps: list[str]
    job: str
    card: str = Field(description="workflow, check or export")
    runs_on: str
    workflow: Optional[str] = None
    workflow_id: Optional[str] = None
    provider_override: Optional[str] = None
    model_override: Optional[str] = None
    layer: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    prompt: Optional[str] = None
    folder: Optional[str] = None
    formats: Optional[list[str]] = None
    done: Optional[int] = Field(default=None, description="pages that already have this card's output; none: it "
                                "cannot tell (`source.recipe.done-is-not-redone`)")
    of: Optional[int] = Field(default=None, description="the pages (or, for a split, photographs) it runs over")
    note: Optional[str] = Field(default=None, description="'already done on N of M pages', in words")


class SkippedStep(BaseModel):
    step: str
    why: str


class StartDownload(BaseModel):
    """A model a step needs that is not on this Mac, and the action that downloads it."""

    runtime: str
    model: str
    steps: list[str]
    size_mb: Optional[int] = None
    action: str = Field(description="the action to invoke to download it (a download-model job on the network lane)")
    params: dict[str, Any]


class ProposedStep(BaseModel):
    step: str
    job: Optional[str] = None
    layer: Optional[str] = None
    topic: Optional[str] = Field(default=None, description="the topic registry id that explains it (GET /api/topics/{id})")
    title: str
    explanation: str = Field(description="its topic's text: what it does and why")


class ProposedJobs(BaseModel):
    """What an added layer proposes for the material already in the project; nothing runs before Start."""

    layers: list[str]
    steps: list[ProposedStep]
    proposed_at: Optional[str] = None


class StartPlan(BaseModel):
    """What pressing Start would run, on how many pages, and every reason it cannot yet."""

    started: Optional[StartRecord] = Field(default=None, description="the first yes, once given")
    runs: list[StartRun] = Field(description="what Start runs, in order")
    workflows: list[StartWorkflow]
    skipped: list[SkippedStep] = Field(description="steps Start skips, each with why; the others still run")
    offered: list[str] = Field(description="steps offered later (training), never run at Start")
    refusals: list[str] = Field(description="Start is refused while this is not empty")
    downloads: list[StartDownload] = Field(default_factory=list, description=(
        "models the steps are pinned to that are not on this Mac, each offered as a download "
        "(source.recipe.missing-model-offered)"))
    estimate: StartEstimate
    proposed: Optional[ProposedJobs] = Field(default=None, description=(
        "jobs proposed for the material already in the project by a layer added later; once the project has "
        "started, the plan is these alone (source.onboard.add-layer)"))
    addable: list[str] = Field(default_factory=list, description=(
        "layers this project can add now: the addable ones less those it has and those its purpose brings "
        "(source.onboard.add-layer)"))


def _start_plan(db: Database) -> dict[str, Any]:
    from fichero_server.recipes.layers import addable_now, explain
    from fichero_server.recipes.project import read_proposed, read_start
    from fichero_server.recipes.start import count_pages, estimate, plan_start

    library = _library(db)
    setup = read_project_setup(library)
    started, proposal = read_start(library), read_proposed(library)
    # A project keeps its pages on this Mac unless setup's answer said otherwise.
    stays_local = not (setup["answers"] or {}).get("cloud_allowed", False)
    # Before the first yes Start runs the whole recipe, the added layer with it; after it, only what an
    # added layer proposes for the material already there.
    only = set(proposal["steps"]) if started and proposal else None
    plan = plan_start(setup["recipe"], stays_local=stays_local, only=only)
    plan["estimate"] = estimate(plan["workflows"], count_pages(db))
    plan["started"] = started
    plan["proposed"] = explain(setup["recipe"], proposal)
    plan["addable"] = addable_now(setup["answers"] or {})
    from fichero_server.recipes.done import annotate

    annotate(db, plan)
    return plan


@router.get("/project/start", response_model=StartPlan)
async def get_start_plan(db: Database = Depends(get_library_database)) -> StartPlan:
    """What Start would run on this project, with the estimate, before anything runs
    (`source.onboard.estimate-before-start`)."""
    return StartPlan(**_start_plan(db))


class StartParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    withdraw: bool = Field(default=False, description="take the first yes back (undo)")
    redo: list[str] = Field(default_factory=list, description="step ids to run again on pages that already have "
                            "their output (`source.recipe.done-is-not-redone`)")


class StartRequest(BaseModel):
    """What the person asks of Start, beyond the yes."""

    model_config = ConfigDict(extra="forbid")
    redo: list[str] = Field(default_factory=list, description="step ids to run again on pages that already have "
                            "their output; the others run only on pages that do not")


@router.post("/project/start", response_model=StartPlan)
async def start_project(
    request: Optional[StartRequest] = None,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> StartPlan:
    """The first yes: record that the person pressed Start, on which recipe version (audited,
    undoable), and run the recipe over the project's material as one `run-a-recipe` job
    (`source.recipe.start-runs-the-steps`): its runnable steps in order, the skipped ones named with why.
    Refused with 422 while the plan has refusals (a recipe that fails the check, or nothing to run)."""
    try:
        registry.invoke(db, "project.start", {"redo": request.redo if request else []}, ctx)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return StartPlan(**_start_plan(db))


def _invert_start(before: dict | None, after: dict | None, ctx: ActionContext):
    return ("project.start", {"withdraw": True})


@action("project.start", StartParams, domains=["project"], undoable=True, invert=_invert_start)
def _action_start(db: Database, params: StartParams, ctx: ActionContext) -> tuple[dict, ChangeSpec]:
    from fichero_server.core.timeutil import utc_now_iso
    from fichero_server.recipes.project import read_start, write_start

    library = _library(db)
    before = read_start(library)
    if params.withdraw:
        record = None
    else:
        plan = _start_plan(db)
        if plan["refusals"]:
            raise ValueError("Start is refused: " + "; ".join(plan["refusals"]))
        from fichero_server.recipes import runner

        recipe = read_project_setup(library)["recipe"] or {}
        runner.register_job_kinds()
        record = {
            "started_at": utc_now_iso(timespec="seconds"),
            "recipe_id": recipe.get("id"),
            "recipe_version": recipe.get("version"),
            "workflows": [w["workflow"] for w in plan["workflows"]],
            "pages": plan["estimate"]["pages"],
            "job_id": runner.enqueue(db, plan, documents=None, started_by=ctx.actor or "owner", redo=params.redo),
        }
        # Start runs what an added layer proposed (source.onboard.add-layer): the proposal is done with.
        from fichero_server.recipes.project import write_proposed

        write_proposed(library, None)
    write_start(library, record)
    return {"started": record}, ChangeSpec(domains=["project"], target_ids=[], before={"started": before},
                                           after={"started": record}, emit_type="project.started")


# =============================================================================
# Adding a layer (or a language) later (#5470). `source.onboard.add-layer`.
# =============================================================================


class LayerChangeRequest(BaseModel):
    """Layers and languages to add to the project (or, with `remove`, to take out)."""

    model_config = ConfigDict(extra="forbid")
    layers: list[str] = Field(default_factory=list, description="layers to add, e.g. entities, graph, places, vectors")
    languages: list[str] = Field(default_factory=list, description="BCP 47 language tags to add")
    remove: bool = Field(default=False, description="take these out; a layer removed before Start withdraws its "
                         "proposed jobs")


class LayerChangeParams(LayerChangeRequest):
    restore: Optional[dict[str, Any]] = Field(default=None, description="undo: the answers, recipe and proposal "
                                              "to put back")


@router.post("/project/layers", response_model=StartPlan)
async def change_project_layers(
    request: LayerChangeRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> StartPlan:
    """Add a layer (or a language) to the project's recipe (audited, undoable). The layer's steps join the
    recipe and are proposed for the material already in the project: the Start plan returned shows those
    jobs with the estimate, each explained by its topic, and nothing runs until the person presses Start.
    `remove` takes a layer out again and withdraws its proposed jobs. Refused with 422, in words, for a
    project not set up, an unknown layer, or one it already has."""
    try:
        registry.invoke(db, "project.add_layer", request.model_dump(mode="json"), ctx)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return StartPlan(**_start_plan(db))


def _invert_add_layer(before: dict | None, after: dict | None, ctx: ActionContext):
    return ("project.add_layer", {"restore": before or {}})


@action("project.add_layer", LayerChangeParams, domains=["project"], undoable=True, invert=_invert_add_layer)
def _action_add_layer(db: Database, params: LayerChangeParams, ctx: ActionContext) -> tuple[dict, ChangeSpec]:
    from fichero_server.core.timeutil import utc_now_iso
    from fichero_server.recipes.layers import change
    from fichero_server.recipes.project import read_proposed, write_proposed

    library = _library(db)
    before = {**read_project_setup(library), "proposed": read_proposed(library)}
    if params.restore is not None:
        after = {"answers": params.restore.get("answers"), "recipe": params.restore.get("recipe"),
                 "proposed": params.restore.get("proposed")}
    else:
        after = change(before, before["proposed"], layers=params.layers, languages=params.languages,
                       remove=params.remove, assemble=_assemble, now=utc_now_iso(timespec="seconds"))
    write_project_setup(library, after["answers"], after["recipe"])
    write_proposed(library, after["proposed"])
    return after, ChangeSpec(domains=["project"], target_ids=[], before=before, after=after,
                             emit_type="project.layer_added")


class RecipeRunStep(BaseModel):
    steps: list[str]
    card: str
    state: str = Field(description="waiting, running, done, failed or not run")
    child_id: Optional[str] = Field(default=None, description="the step's own job: a workflow run or a check run")
    why: Optional[str] = None


class RecipeRunStatus(BaseModel):
    job_id: str
    state: str
    reason: Optional[str] = None
    documents: Optional[list[str]] = Field(default=None, description="the pages an import brought; none: all")
    steps: list[RecipeRunStep]
    skipped: list[SkippedStep]


class RecipeRuns(BaseModel):
    items: list[RecipeRunStatus]


@router.get("/project/runs", response_model=RecipeRuns)
async def recipe_runs(db: Database = Depends(get_library_database)) -> RecipeRuns:
    """The project's recipe runs, newest first: Start's, and one for each import after it."""
    from fichero_server.recipes import runner

    return RecipeRuns(items=[RecipeRunStatus(**r) for r in runner.runs(db)])


@router.get("/project/runs/{job_id}", response_model=RecipeRunStatus)
async def recipe_run_status(job_id: str, db: Database = Depends(get_library_database)) -> RecipeRunStatus:
    """A started recipe's run: each card's state and its own job, and the steps it skipped, with why."""
    from fichero_server.recipes import runner

    try:
        return RecipeRunStatus(**runner.status(db, job_id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
