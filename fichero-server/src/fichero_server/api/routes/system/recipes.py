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
from fichero_server.recipes.project import read_project_setup, write_project_setup

from fichero_server.recipes.assemble import PURPOSE_STEPS, PURPOSES, Answers, assemble
from fichero_server.recipes.cards import seed_cards
from fichero_server.recipes.jobs import all_jobs
from fichero_server.recipes.recipe import check_recipe

router = APIRouter(prefix="/recipes")


class JobInfo(BaseModel):
    id: str
    name: str
    description: str
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
        JobInfo(id=j.id, name=j.name, description=j.description, layer=j.layer,
                takes=sorted(j.takes), gives=sorted(j.gives), compare=j.compare,
                settings=list(j.settings), since=j.since)
        for j in all_jobs()
    ]
    return JobListResponse(items=items, count=len(items))


class AssembleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    purpose: str = Field(description=f"one of: {', '.join(PURPOSE_STEPS)}")
    languages: list[str] = Field(min_length=1, description="BCP 47 language tags")
    scripts: list[str] = Field(min_length=1, description="ISO 15924 script codes")
    material: str = "handwriting"
    pages: int = Field(default=0, ge=0, description="roughly how many pages")
    cloud_allowed: bool = False
    mac_memory_gb: Optional[float] = Field(default=None, description="defaults to this machine's memory")


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


class RecipeStep(BaseModel):
    id: str
    job: str
    model: Optional[dict[str, Any]] = None
    card: Optional[RecipeCard] = None
    uses_cloud: bool = False
    runs_on: Optional[str] = None
    reasons: list[str] = Field(default_factory=list)
    gap: Optional[str] = None
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


class PurposeInfo(BaseModel):
    id: str
    title: str
    description: str
    runs_by_itself: bool = Field(description="true: its layers run after Start; false: tools are offered")


class PurposeListResponse(BaseModel):
    items: list[PurposeInfo]
    count: int


@router.get("/purposes", response_model=PurposeListResponse)
async def list_purposes() -> PurposeListResponse:
    """The purposes setup offers, in order, each with its label and whether it runs by itself
    (`source.onboard.purpose-first`)."""
    items = [
        PurposeInfo(id=pid, title=title, description=desc, runs_by_itself=bool(PURPOSE_STEPS[pid]))
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


@router.post("/assemble", response_model=AssembledRecipe)
async def assemble_recipe(request: AssembleRequest) -> AssembledRecipe:
    """The recipe the rules give for these answers, each choice with its reasons and each gap named
    (`source.onboard.deterministic-recipe`). Proposes; writes nothing."""
    answers = Answers(
        purpose=request.purpose, languages=frozenset(request.languages),
        scripts=frozenset(request.scripts), material=request.material, pages=request.pages,
        cloud_allowed=request.cloud_allowed,
        mac_memory_gb=request.mac_memory_gb or _this_machine_memory_gb(),
    )
    recipe = assemble(answers, list(seed_cards()))
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
    Refused with 422 when either holds code or credentials."""
    try:
        result = registry.invoke(db, "project.save_setup", request.model_dump(mode="json"), ctx)
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


class StartPlan(BaseModel):
    """What pressing Start would run, on how many pages, and every reason it cannot yet."""

    started: Optional[StartRecord] = Field(default=None, description="the first yes, once given")
    workflows: list[StartWorkflow]
    offered: list[str] = Field(description="steps offered later (training), never run at Start")
    refusals: list[str] = Field(description="Start is refused while this is not empty")
    estimate: StartEstimate


def _start_plan(db: Database) -> dict[str, Any]:
    from fichero_server.recipes.project import read_start
    from fichero_server.recipes.start import count_pages, estimate, plan_start

    library = _library(db)
    setup = read_project_setup(library)
    # A project keeps its pages on this Mac unless setup's answer said otherwise.
    stays_local = not (setup["answers"] or {}).get("cloud_allowed", False)
    plan = plan_start(setup["recipe"], stays_local=stays_local)
    plan["estimate"] = estimate(plan["workflows"], count_pages(db))
    plan["started"] = read_start(library)
    return plan


@router.get("/project/start", response_model=StartPlan)
async def get_start_plan(db: Database = Depends(get_library_database)) -> StartPlan:
    """What Start would run on this project, with the estimate, before anything runs
    (`source.onboard.estimate-before-start`)."""
    return StartPlan(**_start_plan(db))


class StartParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    withdraw: bool = Field(default=False, description="take the first yes back (undo)")


@router.post("/project/start", response_model=StartPlan)
async def start_project(
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> StartPlan:
    """The first yes: record that the person pressed Start, on which recipe version (audited,
    undoable). Refused with 422, naming each step, while the plan has refusals."""
    try:
        registry.invoke(db, "project.start", {}, ctx)
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
        recipe = read_project_setup(library)["recipe"] or {}
        record = {
            "started_at": utc_now_iso(timespec="seconds"),
            "recipe_id": recipe.get("id"),
            "recipe_version": recipe.get("version"),
            "workflows": [w["workflow"] for w in plan["workflows"]],
            "pages": plan["estimate"]["pages"],
        }
    write_start(library, record)
    return {"started": record}, ChangeSpec(domains=["project"], target_ids=[], before={"started": before},
                                           after={"started": record}, emit_type="project.started")
