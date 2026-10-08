"""Recipes: the job registry, checking a recipe, and assembling one from setup's answers.

Spec: `source/models-chains-and-projects.md` (`source.recipe.*`, `source.onboard.*`). Read-only:
nothing here writes to a library. The setup window, the Inspector, the command line and MCP all
read the same answers from the engine (four architecture rules: logic in the engine).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from fichero_server.actions.registry import ActionContext, ChangeSpec, action, registry
from fichero_server.api.auth import action_context
from fichero_server.api.main import get_library_database, get_library_database_for_write
from fichero_server.db import Database
from fichero_server.db.embeddings import search_embedder

from fichero_server.recipes.assemble import PURPOSE_STEPS, PURPOSES, Answers, assemble
from fichero_server.recipes.run_view import RecipeRunStep, RecipeRunSummary, SkippedStep


# The recipe store, cards, job registry and check load on first use, not at app start (#3950); the purposes
# (`recipes.assemble`, standard library only) are read at start, for the schema's descriptions.
def read_project_setup(library: Path) -> dict[str, Any]:
    from fichero_server.recipes.project import read_project_setup as read

    return read(library)


def write_project_setup(library: Path, answers: Any, recipe: Any) -> None:
    from fichero_server.recipes.project import write_project_setup as write

    write(library, answers, recipe)


def known_cards(answers: Any = None, *, include_not_built: bool = False) -> Any:
    """The cards the rules choose from: the shipped seed, installed models' and the cached Kraken
    repository's (#5519, `recipes.discovery`); never the network."""
    from fichero_server.recipes.discovery import known_cards as known

    return known(answers, include_not_built=include_not_built)


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
    loose_pages: Optional[bool] = Field(default=None, description=(
        "the material is loose pages (a box or bundle not yet sorted into documents): a recipe that reads them "
        "then finds the documents among them, accepting by itself only the clearest; unset, it is on when the open "
        "project holds a folder of loose page images (finddocs.recipe-step)"))
    job_answers: dict[str, Any] = Field(default_factory=dict, description=(
        "the answers under a purpose (entity_kinds, gazetteer, normalise_how_far): each becomes the setting of the "
        "step it configures (source.onboard.auto.job-answers-read)"))


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
    source: Literal["shipped", "installed", "kraken-repository", "hugging-face"] = Field(
        default="shipped", description="where the card came from: the shipped seed, an installed model's own "
        "metadata, Kraken's model repository or a Hugging Face search (GET /api/recipes/candidates)")


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


class ByHandJob(BaseModel):
    """A job the answers bring that Start cannot run by itself: never a step, said with why and the fix."""

    job: str
    title: str
    why: str
    fix: str = Field(description="what does it by hand instead, in words")


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
    by_hand: list[ByHandJob] = Field(default_factory=list, description=(
        "jobs the answers bring that Start cannot run by itself, so never steps; each with why and the tool that "
        "does it by hand (source.onboard.auto.every-proposed-step-runs)"))
    cloud_options: list[str] = Field(
        default_factory=list,
        description="jobs a cloud model would also fit if pages could leave this Mac; "
        "setup asks the egress question only when this is not empty",
    )
    problems: list[str] = Field(description="what the recipe check finds (empty when it can run)")
    overrides: Optional[list[dict[str, Any]]] = Field(default=None, description=(
        "the open project's saved overrides (Use This, for the project or a folder), kept so a recipe proposed "
        "again and saved keeps them; a project-scope one has already set its step's reader"))


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


def _assemble(answers: dict[str, Any], library: Optional[Path] = None) -> dict[str, Any]:
    """The rules' recipe for setup's answers (as sent to `/assemble`, or as saved on the project).
    A language or script given as a word is resolved to its tag first, or refused (ValueError, in
    words): the rules only ever see tags (`source.onboard.language-stored-as-tag`).

    For a project with a saved recipe, its overrides come with the recipe and each project-scope one
    sets its step's reader (`bakeoff.apply_project_overrides`, the path Use This takes), so proposing
    the recipe again never undoes a reader the person chose; folder overrides stay overrides."""
    if answers.get("loose_pages") is None and library is not None:
        # Default on for a project that holds a folder of loose page images (§7b, "Everything automatic after
        # Start": a box is organised as a stage of the run); an answer of False turns it off.
        answers = {**answers, "loose_pages": _holds_loose_pages(library)}
    a = _answers(answers)
    recipe = assemble(a, known_cards(a))
    saved = (read_project_setup(library)["recipe"] or {}) if library is not None else {}
    if saved.get("overrides"):
        from fichero_server.recipes.bakeoff import apply_project_overrides

        recipe["overrides"] = list(saved["overrides"])
        apply_project_overrides(recipe, known_cards(a, include_not_built=True))
    return recipe


def _holds_loose_pages(library: Path) -> bool:
    """Whether the project holds a folder (or a root) with two or more photographs of pages lying loose in it."""
    from collections import Counter

    from fichero_server.db.manager import db_manager
    from fichero_server.models import Document

    db = db_manager.get_database(str(library))
    folders = {d.id for d in db.query(Document, doc_type="folder") if not d.deleted_at}
    loose = Counter(d.parent_id for d in db.query(Document, doc_type="file")
                    if not d.deleted_at and str(getattr(d.file_type, "value", d.file_type)) == "image"
                    and (d.parent_id is None or d.parent_id in folders))
    return any(n >= 2 for n in loose.values())


def _optional_library(request: Request) -> Optional[Path]:
    """The open project's folder when the caller names one (the project's own client), else None (setup
    before a project exists); a named project is opened through the same checks as every library route."""
    from fichero_server.api.library_header import optional_library_path

    path = optional_library_path(request)
    return _library(get_library_database(request, path)) if path else None


def _answers(answers: dict[str, Any]) -> Answers:
    """Setup's answers as the rules read them (the one place they are turned into `Answers`)."""
    a = normalise_answers(answers, strict=True)
    return Answers(
        purposes=tuple(a["purposes"]), languages=frozenset(a.get("languages") or ()),
        scripts=frozenset(a.get("scripts") or ()), materials=tuple(a["materials"]),
        jobs=tuple(a.get("jobs") or ()),
        pages=a.get("pages") or 0, cloud_allowed=bool(a.get("cloud_allowed")),
        mac_memory_gb=a.get("mac_memory_gb") or _this_machine_memory_gb(),
        layers=frozenset(a.get("layers") or ()), loose_pages=bool(a.get("loose_pages")),
        job_answers=dict(a.get("job_answers") or {}),
        search_embedder=search_embedder(),
    )


@router.post("/assemble", response_model=AssembledRecipe)
async def assemble_recipe(
    request: AssembleRequest, library: Optional[Path] = Depends(_optional_library),
) -> AssembledRecipe:
    """The recipe the rules give for these answers, each choice with its reasons and each gap named
    once as a structured problem (`source.onboard.deterministic-recipe`, `source.onboard.says-no-model`).
    For an open project with a saved recipe, its overrides are kept and a project-scope one (Use This)
    sets its step's reader. Proposes; writes nothing. Refused with 422, in words, for a language,
    script, purpose, material, job or direction Fichero does not know."""
    try:
        recipe = _assemble(request.model_dump(), library)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    problems = [] if recipe["gaps"] else check_recipe(recipe)
    return AssembledRecipe(
        fichero_recipe=recipe["fichero_recipe"], version=recipe["version"], suits=recipe["suits"],
        id=recipe["id"], title=recipe["title"], purposes=recipe["purposes"],
        steps=[RecipeStep(**s) for s in recipe["steps"]], gaps=recipe["gaps"], by_hand=recipe.get("by_hand") or [],
        cloud_options=recipe["cloud_options"], problems=problems, overrides=recipe.get("overrides"),
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
# Finding models beyond the shipped cards (#5519): the candidates the rules see, and where they came from.
# =============================================================================

CardSource = Literal["shipped", "installed", "kraken-repository", "hugging-face"]


class CandidateSource(BaseModel):
    source: CardSource
    state: Literal["read", "searched", "cached", "not-searched", "offline", "failed"] = Field(description=(
        "read: on this Mac; searched: fetched now; cached: from the last fetch; not-searched: online was not "
        "asked; offline: this engine works offline (local-only); failed: the fetch failed (detail says why)"))
    count: int
    detail: str


class ModelCandidate(BaseModel):
    """One reader candidate as a card: where it came from, why it is offered, what it states, and what
    the rules make of it for the project's scripts, languages and material."""

    id: str = Field(description="<runtime>:<source>@<version>")
    name: str
    source: CardSource
    offered_because: str = Field(description="why discovery offers it, in words")
    pin: dict[str, Any]
    jobs: list[str]
    scripts: Optional[list[str]] = Field(default=None, description="ISO 15924 codes its card states; null: unstated")
    languages: Optional[list[str]] = Field(default=None, description="BCP 47 tags its card states; null: unstated")
    licence: str = ""
    open_licence: bool
    size_gb: float
    memory_gb: float
    cer_published: Optional[float] = Field(default=None, description="a published CER the rules rank on (only "
                                            "where the record names the project's languages)")
    cer_measured_here: Optional[float] = None
    measured: str = Field(description="what is measured on this project, or that it is unmeasured until a "
                          "bake-off measures it")
    in_recipe_rules: bool = Field(description="false for a Hugging Face result: Fichero cannot download a Hub "
                                  "model outside its catalogue yet, so the rules do not choose it")
    rule_rank: Optional[int] = Field(default=None, description="its place by the rules' fixed order among the "
                                     "candidates they keep; null when refused or not in the rules")
    refused: Optional[str] = Field(default=None, description="the rules' first reason it cannot do the job here")


class ModelCandidateList(BaseModel):
    job: str
    items: list[ModelCandidate]
    count: int
    sources: list[CandidateSource]


@router.get("/candidates", response_model=ModelCandidateList)
async def model_candidates(
    scripts: str, languages: str = "", material: str = "handwriting", job: str = "read-a-line",
    online: bool = False, cloud_allowed: bool = False, mac_memory_gb: Optional[float] = None,
) -> ModelCandidateList:
    """Every reader candidate for these scripts and languages (comma-separated codes or names), from the
    shipped cards, the models installed on this Mac, Kraken's model repository and Hugging Face, each as a
    card saying where it came from and why it is offered, ranked by the rules' fixed order (#5519,
    `source.find.by-need`). The network is reached only with `online=true`, and never when this engine works
    offline; otherwise the repository is read from its last fetch and the Hub is not searched. Refused
    (422), in words, for an unknown script, language, material or job."""
    from fichero_server.recipes.assemble import MATERIALS, READING_JOBS, _rank_key, _refusal
    from fichero_server.recipes.discovery import discover
    from fichero_server.recipes.names import resolve_language, resolve_script

    if job not in READING_JOBS:
        raise HTTPException(status_code=422, detail=f"discovery finds readers: job must be one of "
                                                    f"{', '.join(sorted(READING_JOBS))}")
    if material not in MATERIALS:
        raise HTTPException(status_code=422, detail=f"material must be one of {', '.join(MATERIALS)}")
    try:
        script_codes = frozenset(resolve_script(s) for s in scripts.split(",") if s.strip())
        tags = frozenset(resolve_language(t) for t in languages.split(",") if t.strip())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not script_codes:
        raise HTTPException(status_code=422, detail="name at least one script")
    a = Answers(purposes=("transcribe",), languages=tags, scripts=script_codes, materials=(material,),
                cloud_allowed=cloud_allowed, mac_memory_gb=mac_memory_gb or _this_machine_memory_gb())
    cards, sources = await discover(a, online=online)
    cards = [c for c in cards if job in c.jobs]
    in_rules = [c for c in cards if c.source != "hugging-face"]
    kept = sorted((c for c in in_rules if _refusal(job, c, a, material) is None),
                  key=lambda c: _rank_key(c, material))
    rank = {c.id: i for i, c in enumerate(kept, 1)}

    def measured(c: Any) -> str:
        if c.cer_measured_here is not None:
            return f"CER {c.cer_measured_here * 100:.1f}% on your pages"
        return "unmeasured on your pages until a bake-off measures it"

    items = [ModelCandidate(
        id=c.id, name=c.note.strip().rstrip(".") or c.id, source=c.source,
        offered_because=c.offered_because or "a card that ships with Fichero", pin=dict(c.pin),
        jobs=sorted(c.jobs), scripts=sorted(c.scripts) if c.scripts is not None else None,
        languages=sorted(c.languages) if c.languages is not None else None, licence=c.licence,
        open_licence=c.open_licence, size_gb=c.size_gb, memory_gb=c.memory_gb, cer_published=c.cer_published,
        cer_measured_here=c.cer_measured_here, measured=measured(c), in_recipe_rules=c.source != "hugging-face",
        rule_rank=rank.get(c.id),
        refused=None if c.source == "hugging-face" or c.id in rank else (_refusal(job, c, a, material) or (None, None))[1],
    ) for c in sorted(cards, key=lambda c: (rank.get(c.id, len(rank) + 1), c.source == "hugging-face", c.id))]
    return ModelCandidateList(job=job, items=items, count=len(items),
                              sources=[CandidateSource(**s) for s in sources])


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
    memory: Optional[str] = Field(default=None, description=(
        "a run on this Mac's model server: the model's memory need, how many pages at once it reads on this Mac, "
        "and the peak that comes to (#5537); null for any other run"))


class StartEstimate(BaseModel):
    pages: int = Field(description="pages, files with no pages, and pages cut from photographs, in the project: "
                       "the pages a started recipe runs over")
    counted: Optional[str] = Field(default=None, description=(
        "what `pages` counts, in words: '4 photographs + 1 PDF page = 5 pages', what the project holds that is "
        "not a page (the PDF a page came from, folders), and photographs that share a file name"))
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
    card: str = Field(description="workflow, check, embed (search: the embed job for each page), export or publish")
    runs_on: str
    workflow: Optional[str] = None
    workflow_id: Optional[str] = None
    provider_override: Optional[str] = None
    model_override: Optional[str] = None
    layer: Optional[str] = None
    check: Optional[str] = Field(default=None, description=(
        "a check card's kind of check (CheckRunRequest.check): 'tie-text-to-lines' ties the page reading to "
        "the page's lines with a Kraken reader (#5444); none: the checker model reads each proposal"))
    provider: Optional[str] = None
    model: Optional[str] = None
    prompt: Optional[str] = None
    folder: Optional[str] = None
    formats: Optional[list[str]] = None
    done: Optional[int] = Field(default=None, description="pages that already have this card's output; none: it "
                                "cannot tell (`source.recipe.done-is-not-redone`)")
    of: Optional[int] = Field(default=None, description="the pages (or, for a split, photographs) it runs over")
    note: Optional[str] = Field(default=None, description="'already done on N of M pages', in words")
    last_run: Optional[str] = Field(default=None, description=(
        "'failed' or 'not run' when the project's last finished run did not do this step; Start runs it again "
        "(no redo needed). Null when it was done, or never ran"))
    last_why: Optional[str] = Field(default=None, description="why the last run did not do it, in words")
    takes: list[str] = Field(default_factory=list, description=(
        "the kinds of thing it needs from the steps before it (the job registry's; 'a|b': either); it waits "
        "only when every earlier step that gives one failed"))
    gives: list[str] = Field(default_factory=list, description="the kinds of thing it gives the steps after it")
    tool_config: Optional[dict[str, dict[str, Any]]] = Field(default=None, description=(
        "settings from setup's answers this run gives its workflow's tools, by tool (which kinds of names)"))


class StartInstead(BaseModel):
    """An installed model the plan offers instead of a download (#5583)."""

    card: str = Field(description="its card id, to send to use-instead")
    model: str = Field(description="its id in this Mac's model store")
    name: str = Field(description="its name, as people read it")


class StartDownload(BaseModel):
    """A model a step needs that is not on this Mac, and the action that downloads it."""

    runtime: str
    model: str
    steps: list[str]
    size_mb: Optional[int] = None
    action: str = Field(description="the action to invoke to download it (a download-model job on the network lane)")
    params: dict[str, Any]
    name: Optional[str] = Field(default=None, description="the model's name, as people read it (MLX models)")
    instead: list[StartInstead] = Field(default_factory=list, description=(
        "installed models this Mac can serve for the same steps, each usable instead in one press "
        "(POST /api/recipes/project/start/use-instead; source.onboard.auto.installed-model-first)"))


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
    from fichero_server.recipes import runner
    from fichero_server.recipes.done import annotate, material
    from fichero_server.recipes.layers import addable_now, explain
    from fichero_server.recipes.project import read_proposed, read_start
    from fichero_server.recipes.start import estimate, plan_start

    library = _library(db)
    setup = read_project_setup(library)
    started, proposal = read_start(library), read_proposed(library)
    # A project keeps its pages on this Mac unless setup's answer said otherwise.
    stays_local = not (setup["answers"] or {}).get("cloud_allowed", False)
    # Steps the last run did not finish stay in the plan, to run again (#5498).
    unfinished = runner.unfinished_steps(db) if started else {}
    # Before the first yes Start runs the whole recipe, the added layer with it; after it, only what an
    # added layer proposes for the material already there, and what did not finish.
    only = set(proposal["steps"]) | set(unfinished) if started and proposal else None
    plan = plan_start(setup["recipe"], stays_local=stays_local, only=only,
                      job_answers=(setup["answers"] or {}).get("job_answers"))
    pages = material(db)
    plan["estimate"] = estimate(plan["workflows"], pages["pages"])
    plan["estimate"]["counted"] = pages["sentence"]
    plan["started"] = started
    plan["proposed"] = explain(setup["recipe"], proposal)
    plan["addable"] = addable_now(setup["answers"] or {})
    annotate(db, plan, unfinished)
    return plan


def _as_started(db: Database, plan: dict[str, Any]) -> dict[str, Any]:
    """The plan as Start started it (#5498): its runs, workflows and skipped steps are the queued run's, so the
    response's `started.workflows` and `runs` name the same thing, never the plan for next time."""
    from fichero_server.recipes import runner
    from fichero_server.recipes.done import annotate
    from fichero_server.recipes.start import estimate

    job_id = (plan.get("started") or {}).get("job_id")
    if not job_id:
        return plan
    started = runner.started_plan(db, job_id)
    plan["runs"], plan["skipped"] = started["runs"], started["skipped"]
    plan["workflows"] = [r for r in plan["runs"] if r["card"] == "workflow"]
    counted = plan["estimate"].get("counted")
    plan["estimate"] = {**estimate(plan["workflows"], plan["estimate"]["pages"]), "counted": counted}
    return annotate(db, plan)


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
    Refused with 422 while the plan has refusals (a recipe that fails the check, or nothing to run).
    The response is the plan as started: its `runs` and `workflows` are the run's, as `started.workflows` is."""
    try:
        registry.invoke(db, "project.start", {"redo": request.redo if request else []}, ctx)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return StartPlan(**_as_started(db, _start_plan(db)))


class UseInsteadRequest(BaseModel):
    """Use an installed model instead of downloading the one the plan waits for (#5583)."""

    model_config = ConfigDict(extra="forbid")
    model: str = Field(description="the download the plan waits for, as its `downloads` names it (`model`)")
    card: str = Field(description="the installed model's card id, as that download's `instead` names it")


@router.post("/project/start/use-instead", response_model=ProjectSetup)
async def use_installed_instead(
    request: UseInsteadRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> ProjectSetup:
    """Use the installed model instead: every step pinned to the model Start waits to download is set to the
    installed one the plan offers (`downloads[].instead`), kept as a project-scope override on the recipe (as Use
    This keeps a bake-off's choice), through `project.save_setup` (audited, undoable)
    (`source.onboard.auto.installed-model-first`). Refused (422) for a model the plan does not wait for, or a card
    it does not offer instead."""
    from fichero_server.core.timeutil import utc_now_iso
    from fichero_server.recipes.start import use_instead

    library = _library(db)
    card = next((c for c in known_cards(include_not_built=True) if c.id == request.card), None)
    if card is None:
        raise HTTPException(status_code=422, detail="that model is not one Fichero has a card for")
    setup = read_project_setup(library)
    try:
        recipe = use_instead(setup["recipe"], _start_plan(db)["downloads"], request.model, card,
                             now=utc_now_iso(timespec="seconds"))
        result = registry.invoke(db, "project.save_setup", {"answers": setup["answers"], "recipe": recipe}, ctx)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ProjectSetup(**result.result)


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


class RecipeRunStatus(BaseModel):
    job_id: str
    state: str
    reason: Optional[str] = None
    documents: Optional[list[str]] = Field(default=None, description="the pages an import brought; none: all")
    steps: list[RecipeRunStep]
    skipped: list[SkippedStep]
    refusals: list[str] = Field(default_factory=list, description=(
        "why an import's run could not run at all (the plan's refusals then); empty for a run that ran (#5575)"))
    started_by: Optional[str] = Field(default=None, description="who or what started it: the person, or 'import'")
    waiting_for: Optional[str] = Field(default=None, description=(
        "what the run waits for now, in words: another recipe run, or what the running stage's pages wait for "
        "(memory, a model loading); null when nothing waits (#5576)"))
    estimate_seconds_left: Optional[float] = Field(default=None, description=(
        "the running stage's time left at its own pace so far; null until it has done a page"))


class RecipeRuns(BaseModel):
    items: list[RecipeRunStatus]


@router.get("/project/runs", response_model=RecipeRuns)
async def recipe_runs(db: Database = Depends(get_library_database)) -> RecipeRuns:
    """The project's recipe runs, newest first: Start's, and one for each import after it. Each stage that is a
    workflow run carries its run account (pages done, failed and left, time left, what it waits for; #5576)."""
    from fichero_server.recipes import runner
    from fichero_server.recipes.run_view import with_accounts

    return RecipeRuns(items=[RecipeRunStatus(**await with_accounts(db, r)) for r in runner.runs(db)])


@router.get("/project/runs/{job_id}", response_model=RecipeRunStatus)
async def recipe_run_status(job_id: str, db: Database = Depends(get_library_database)) -> RecipeRunStatus:
    """A started recipe's run: each card's state and its own job (a workflow stage with its run account), the
    steps it skipped with why and their fixes, and what it waits for now (#5576)."""
    from fichero_server.recipes import runner
    from fichero_server.recipes.run_view import with_accounts

    try:
        return RecipeRunStatus(**await with_accounts(db, runner.status(db, job_id)))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/project/runs/{job_id}/summary", response_model=RecipeRunSummary)
async def recipe_run_summary(job_id: str, db: Database = Depends(get_library_database)) -> RecipeRunSummary:
    """What a recipe run made, over the pages it ran on (`source.onboard.auto.results-summary`, #5577): pages
    with a reading, names by kind and dates (the document knowledge graph's grouping), statements, each stage's
    failed pages with the offer to read them again (its run account's), and the skipped steps with their fixes.
    While the run goes on, the figures are what is there so far (`finished` false)."""
    from fichero_server.recipes import run_view

    try:
        return await run_view.summary(db, job_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# =============================================================================
# The bake-off, slice 1: the readers (#4951, `source.try.bakeoff-is-the-same-tool`). The evaluation job run on
# the project's corrected sample pages; one comparison code path (`recipes/bakeoff.py`).
# =============================================================================


class BakeoffStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    page_ids: list[str] = Field(default_factory=list, description="the sample pages; none: every page with a pass a "
                                "person made")


class BakeoffPage(BaseModel):
    document_id: str
    name: str
    lines: int = Field(description="its corrected lines: the lines of the newest pass a person made")


class BakeoffLeftOut(BaseModel):
    document_id: str
    why: str


class BakeoffPageScore(BaseModel):
    document_id: str
    name: str
    lines: int
    cer: Optional[float] = Field(default=None, description="none for a page the reader did not read")
    read: bool = Field(default=True, description="false when the reader returned nothing, or far too little "
                       "against the reference, for this page: not read, never scored as 100% CER (#5531)")
    why: Optional[str] = Field(default=None, description="why the page was not read: the reader's error or what "
                               "it said, else 'returned no text'")


class BakeoffRow(BaseModel):
    """One candidate reader in the bake-off table."""

    rank: int = Field(description="its place in the fixed order: accuracy in one-point bands, then local, cheaper, "
                      "faster, lower carbon, trainable, smaller, the card id")
    card: str = Field(description="its model card id: for Use This, never shown")
    name: str = Field(default="", description="the reader by its card's own name (the card's note, as a recipe step "
                      "names its model): what the table shows, never the card id")
    role: Literal["rule rank", "baseline for print"]
    rule_rank: Optional[int] = Field(default=None, description="its place by the rules before measurement")
    reader: Optional[Literal["kraken", "vision", "tesseract"]] = None
    model: Optional[str] = Field(default=None, description="the model id the evaluation reads with")
    runs_on: str
    local: bool
    cer: Optional[float] = Field(default=None, description="its character error rate over the sample pages it read, "
                                 "under `policy`; none unless it was measured")
    policy: Optional[str] = None
    scores: dict[str, Optional[float]] = Field(default_factory=dict, description="CER under every named policy")
    per_page: list[BakeoffPageScore] = Field(default_factory=list)
    measured: bool = Field(default=False, description="it read enough of the pages to be compared (#5531); only a "
                           "measured reader can win or be used")
    pages_read: Optional[int] = Field(default=None, description="the sample pages it read (its CER is over these)")
    pages_total: Optional[int] = Field(default=None, description="the sample pages it was given")
    pages_per_hour: Optional[float] = Field(default=None, description="measured on this Mac in this run")
    seconds: Optional[float] = None
    cost_usd: Figure = Field(description="for the whole volume, before anything runs")
    carbon_g_per_page: Optional[float] = None
    trainable: bool
    size_gb: float
    why: Optional[str] = Field(default=None, description="why it has no score (not on this Mac, not in this build, "
                               "remote, still running, or 'not measured: read N of M pages (why)')")


class BakeoffResult(BaseModel):
    id: str
    job_id: str = Field(description="the evaluation job in Activity")
    step: str
    started_at: str
    state: str = Field(description="the job's state: waiting, running, done, failed, cancelled, or cleared")
    reason: Optional[str] = None
    pages: list[BakeoffPage]
    left_out: list[BakeoffLeftOut]
    lines: int
    rows: list[BakeoffRow]
    winner: Optional[str] = Field(default=None, description="the first measured row's card, only when at least two "
                                  "readers were measured")
    no_winner_why: Optional[str] = Field(default=None, description="when the job has finished with no winner, why, in "
                                         "words: only one reader could be compared, or no reader read these pages")


class BakeoffReadiness(BaseModel):
    """Whether the project holds enough corrected lines for a bake-off now: the same count and constants as
    the refusal of a start (`bakeoff.readiness`), so setup can say it before anything is pressed."""

    ready: bool
    lines: int = Field(description="corrected lines on the sample pages (each page's newest pass a person made or "
                             "marked ground truth, else the lines a person corrected)")
    pages: int = Field(description="pages with such lines")
    min_lines: int
    min_pages: int
    more_lines: int = Field(description="how many more corrected lines are needed; 0 when there are enough")
    more_pages: int = Field(description="how many more pages with corrected lines are needed; 0 when there are enough")
    unmarked_import_pages: int = Field(default=0, description="pages of imported transcriptions not marked as ground "
                                                              "truth (#5513): marking them is how they count")
    sentence: Optional[str] = Field(default=None, description="when not ready, what to correct, in words")


class BakeoffList(BaseModel):
    items: list[BakeoffResult]
    readiness: BakeoffReadiness


class BakeoffUseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    card: str = Field(description="the candidate's card id")
    scope: Literal["project", "folder"] = "project"
    folder_id: Optional[str] = Field(default=None, description="the folder, when the scope is a folder")


def _bakeoff() -> Any:
    from fichero_server.recipes import bakeoff  # loaded on first use (#3950)

    return bakeoff


@router.post("/project/bakeoffs", response_model=BakeoffResult, response_model_by_alias=True)
async def start_bakeoff(
    request: Optional[BakeoffStartRequest] = None,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> BakeoffResult:
    """Compare the readers on the project's corrected sample pages: the top three by rule rank (and Tesseract
    for print, when it has the language), each scored by the evaluation job (`evaluation.run`, audited) on
    the same pages. Refused (422) in words, with nothing run, below 100 corrected lines on two pages (saying
    how many more), for a project not set up, or when no candidate can be scored on this Mac."""
    from fichero_server.core.timeutil import utc_now_iso
    from fichero_server.recipes.start import count_pages

    library = _library(db)
    setup = read_project_setup(library)
    if not setup["answers"]:
        raise HTTPException(status_code=422, detail="this project has not been set up: run setup first")
    bakeoff = _bakeoff()
    try:
        a = _answers(setup["answers"])
        record = bakeoff.start(
            db, library, a, known_cards(a, include_not_built=True), page_ids=request.page_ids if request else None,
            volume=a.pages or count_pages(db), now=utc_now_iso(timespec="seconds"),
            run_evaluation=lambda params: registry.invoke(db, "evaluation.run", params, ctx).result["job_id"])
        return BakeoffResult(**bakeoff.result(db, library, record["id"]))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/project/bakeoffs", response_model=BakeoffList, response_model_by_alias=True)
async def list_bakeoffs(db: Database = Depends(get_library_database)) -> BakeoffList:
    """Every bake-off kept in the project, newest first, each with its table (`source.try.kept-and-rerunnable`),
    and whether the project has enough corrected lines to run one now (`readiness`, counted as a start is)."""
    bakeoff, library = _bakeoff(), _library(db)
    pages, _ = bakeoff.ground_truth(db, None)
    return BakeoffList(items=[BakeoffResult(**bakeoff.result(db, library, r["id"]))
                              for r in bakeoff.list_records(library)],
                       readiness=BakeoffReadiness(**bakeoff.readiness(pages, bakeoff.unmarked_import_pages(db))))


@router.get("/project/bakeoffs/{bakeoff_id}", response_model=BakeoffResult, response_model_by_alias=True)
async def bakeoff_result(bakeoff_id: str, db: Database = Depends(get_library_database)) -> BakeoffResult:
    """A bake-off's pages, its job's state and its table, ranked by the fixed order; the scores are read from
    each model's card, so the table outlives the job row."""
    try:
        return BakeoffResult(**_bakeoff().result(db, _library(db), bakeoff_id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/project/bakeoffs/{bakeoff_id}/use", response_model=ProjectSetup)
async def use_bakeoff_choice(
    bakeoff_id: str,
    request: BakeoffUseRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> ProjectSetup:
    """Use This: make a scored candidate the reading step's reader for the project or one folder, kept as an
    override on the recipe (for the project, the step's model too), through `project.save_setup` (audited,
    undoable). Refused (422) for a candidate not scored in this bake-off, a folder that is not one, or a
    project with no recipe."""
    from fichero_server.core.timeutil import utc_now_iso
    from fichero_server.models import DocType, Document

    bakeoff, library = _bakeoff(), _library(db)
    try:
        table = bakeoff.result(db, library, bakeoff_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    card = next((c for c in known_cards(include_not_built=True) if c.id == request.card), None)
    if card is None:
        raise HTTPException(status_code=422, detail="that reader is not one Fichero has a card for")
    if request.scope == "folder":
        folder = db.get(Document, request.folder_id) if request.folder_id else None
        if folder is None or folder.doc_type != DocType.folder:
            raise HTTPException(status_code=422, detail=f"{request.folder_id} is not a folder in this project")
    setup = read_project_setup(library)
    try:
        recipe = bakeoff.use_this(setup["recipe"], table, card, scope=request.scope, folder_id=request.folder_id,
                                  now=utc_now_iso(timespec="seconds"))
        result = registry.invoke(db, "project.save_setup", {"answers": setup["answers"], "recipe": recipe}, ctx)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ProjectSetup(**result.result)
