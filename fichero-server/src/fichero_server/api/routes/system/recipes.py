"""Recipes: the job registry, checking a recipe, and assembling one from setup's answers.

Spec: `source/models-chains-and-projects.md` (`source.recipe.*`, `source.onboard.*`). Read-only:
nothing here writes to a library. The setup window, the Inspector, the command line and MCP all
read the same answers from the engine (four architecture rules: logic in the engine).
"""
from __future__ import annotations

import asyncio
import copy
import logging
from enum import Enum
from pathlib import Path
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator

from fichero_server.actions.registry import ActionContext, ChangeSpec, action, registry, started_by_for
from fichero_server.core.single_flight import single_flight
from fichero_server.api.auth import action_context
from fichero_server.api.routes.auth.accounts import _require_owner_or_bootstrap
from fichero_server.api.library_header import optional_library_path
from fichero_server.llm.local_model_facts import GIB
from fichero_server.api.main import get_library_database, get_library_database_for_write
# Imported, never redefined: one schema component for every route's refusal sentence (#5094).
from fichero_server.api.routes.document.format_import import ErrorDetail as _ErrorDetail
from fichero_server.db import Database
from fichero_server.db.embeddings import search_embedder

from fichero_server.recipes import places
from fichero_server.recipes.assemble import PURPOSE_PARENT, PURPOSE_STEPS, PURPOSES, READING_JOBS, Answers, assemble
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


logger = logging.getLogger(__name__)

#: The jobs that hand a model a page picture to read: its card's page floor applies (`runtime.mlx.fit-estimate`).
READS_A_PICTURE = frozenset({*READING_JOBS, "correct"})

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
    reads_material: bool = Field(default=False, description=(
        "whether the job reads the material into text (a reader's job: the finder's candidates are for it, #5612)"))
    needs_a_model: bool = Field(default=False, description=(
        "whether the job runs a model a person can choose: setup offers the model finder beside its step (#6258)"))


class JobListResponse(BaseModel):
    items: list[JobInfo]
    count: int


@router.get("/jobs", response_model=JobListResponse)
async def list_jobs() -> JobListResponse:
    """Every job a recipe can name, with the plain description setup and the manual show."""
    items = [
        JobInfo(id=j.id, name=j.name, description=j.description, topic=j.topic.id, layer=j.layer,
                takes=sorted(j.takes), gives=sorted(j.gives), compare=j.compare,
                settings=list(j.settings), since=j.since, reads_material=j.id in READING_JOBS,
                needs_a_model=bool(j.needs_a_model))
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
    scripts: list[str] = Field(default_factory=list, description=(
        "ISO 15924 script codes (or a script's English name); at least one, except with the language 'und' (Not sure: the engine "
        "works the script out from the sample pages, `inferred_language`)"))
    materials: list[str] = Field(default_factory=list, description=(
        "handwriting, print, typescript and/or text, any mix; a reading step gets one reader per kind read "
        "(source.onboard.material-any-mix). text is material that is already text (Markdown, plain text, Word, "
        "a PDF with a text layer): a project of text alone gets no reading step "
        "(source.recipe.text-material-is-not-read). Unset: text when every page of the open project's sample "
        "is already text, else handwriting"))
    material: Optional[str] = Field(default=None, description="a single material, as before 2026-10-05")
    jobs: list[str] = Field(default_factory=list, description="jobs ticked on their own, beyond the purposes' "
                            "(GET /api/recipes/jobs)")
    removed_jobs: list[str] = Field(default_factory=list, description=(
        "steps (by job) the person took out of the plan on Ready: left out of the recipe, unless a step left in "
        "needs one (then it stays, with needed_by); listed under removed to be put back "
        "(source.onboard.plan-editable)"))
    directions: dict[str, str] = Field(default_factory=dict, description=(
        "script code -> ltr, rtl, ttb (columns right to left) or ttb-lr; a script left out takes its own "
        "(source.onboard.direction-chosen)"))
    pages: int = Field(default=0, ge=0, description="roughly how many pages")
    period: Optional[str] = Field(default=None, description=(
        "when the material was written: a century or a range of years ('16th century', '1650–1700'), kept as typed "
        "(GET /api/recipes/hands reads it; source.onboard.material.when-written)"))
    place: Optional[str] = Field(default=None, description=(
        "where the material was written, kept as typed (a town, a region or an archive; "
        "source.onboard.material.where-written)"))
    hands: list[str] = Field(default_factory=list, description=(
        "which hand: curated hand ids (GET /api/recipes/hands), anything else typed and kept as typed, or 'not-sure'; "
        "their tags join the reader search (source.onboard.material.which-hand)"))
    cloud_allowed: bool = Field(default=False, description='Whether a step may use a cloud model; false keeps every step on this Mac.')
    mac_memory_gb: Optional[float] = Field(default=None, description="defaults to this machine's memory")
    layers: list[str] = Field(default_factory=list, description="layers added beyond the purposes' "
                              "(source.onboard.add-layer)")
    loose_pages: Optional[bool] = Field(default=None, description=(
        "the material is loose pages (a box or bundle not yet sorted into documents): a recipe that reads them "
        "then finds the documents among them, accepting by itself only the clearest; unset, it is on when the open "
        "project holds a folder of loose page images (finddocs.recipe-step)"))
    faded_pages: Optional[bool] = Field(default=None, description=(
        "the pages are faded: a recipe that lines or reads them first raises their contrast on a new rendition, "
        "keeping the original; unset, it is on when a sample of the open project's pages (up to ten, spread "
        "across them) shows a faded page (source.onboard.auto.prepare-damaged-images)"))
    photographs: Optional[bool] = Field(default=None, description=(
        "the pages are photographs (a book open on a table, two pages to a picture); setup asks, nothing guesses it, "
        "and unset is off: answered yes, a recipe that lines or reads them first splits the pages and prepares the "
        "images (source.onboard.photographed-pages-asked)"))
    job_answers: dict[str, Any] = Field(default_factory=dict, description=(
        "the answers under a purpose (entity_kinds, gazetteer, normalise_how_far): each becomes the setting of the "
        "step it configures (source.onboard.auto.job-answers-read)"))

    @model_validator(mode="after")
    def _scripts_unless_not_sure(self) -> "AssembleRequest":
        if not self.scripts and self.languages != ["und"]:
            raise ValueError("scripts: give at least one script, or say the language is 'und' (Not sure) and it is worked out from the pages")
        return self


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
    source: Literal["shipped", "installed", "kraken-repository", "hugging-face", "remote"] = Field(
        default="shipped", description="where the card came from: the shipped seed, an installed model's own "
        "metadata, Kraken's model repository, a Hugging Face search (GET /api/recipes/candidates) or a cloud provider "
        "row in Settings (remote)")


class NearestReader(BaseModel):
    """A refused reader close to fitting a step that has none (`source.onboard.nothing-fits-names-nearest`)."""

    card: str = Field(description="its card id: for the Inspector, never shown in setup's sentence")
    name: str = Field(description="its card's name, as people read it")
    why: str = Field(description="how near it is, in words: another material, a related script, or the language")


class RefusedCard(BaseModel):
    card: str
    why: str = Field(description="the rules' first reason it cannot do the step")


class StepProblem(BaseModel):
    """Why a step has no model, once, in words a historian reads (`source.onboard.says-no-model`)."""

    kind: str = Field(description="no-model-for-job, no-model-for-script, no-model-for-language, "
                      "no-reader-for-material, licence-not-accepted, cloud-not-allowed or not-enough-memory")
    sentence: str = Field(description="one plain sentence; never a model's id, pin or repository")
    fix: str = Field(description="the fix setup offers as its button: download, choose-cloud, choose-model, "
                     "allow-cloud or accept-licence")
    fixes: list[str] = Field(description="every fix that applies, `fix` first")
    detail: str = Field(description="the rules' own reason, short (how many cards were refused, and why): for "
                        "the Inspector and the log")
    nearest: list[NearestReader] = Field(default_factory=list, description=(
        "up to three refused readers closest to fitting, the ones the sentence names "
        "(source.onboard.nothing-fits-names-nearest)"))
    refused: list[RefusedCard] = Field(default_factory=list, description="every card refused for the step, and why")
    licence: Optional[dict[str, str]] = Field(default=None, description=(
        "for licence-not-accepted: the card, the licence's name and the words the Review the licence button shows "
        "(source.onboard.every-setup-button-acts-or-says-why)"))


class StepReader(BaseModel):
    """The reader proposed for one kind of material (`source.onboard.material-any-mix`)."""

    material: str
    model: Optional[dict[str, Any]] = None
    card: Optional[RecipeCard] = None
    runs_on: Optional[str] = None
    reasons: list[str] = Field(default_factory=list)
    sentence: Optional[str] = Field(default=None, description=(
        "who this extra reader is, in a sentence, as the app and Activity show it: 'Also reads print pages with Apple Vision'"))
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
    needed_by: Optional[list[str]] = Field(default=None, description=(
        "the later steps (by job) that need what this one gives: it cannot be taken out of the plan while they "
        "stay (source.onboard.plan-editable)"))
    run_titles: Optional[list[str]] = Field(default=None, description=(
        "the Normalise step's runs by title, one for each reading level asked and one for a translation, in the "
        "order Start makes them (#5795); null for every other step"))
    built_in: bool = Field(default=False, description=(
        "Fichero's own algorithm, with no model to choose (Find where the readers disagree, #5812): the row never "
        "says it has no model, and Remove from Plan always works"))
    compares: Optional[list[str]] = Field(default=None, description=(
        "a built-in comparison's readers, by name, when the plan has two or more"))
    needs: Optional[str] = Field(default=None, description=(
        "what a built-in step waits for, in words (\"needs a second reader: tick one in Read\"); never a block"))


class AutomaticStep(BaseModel):
    """A step the purpose (or an added layer) turns on by itself (`source.recipe.steps-name-layers`)."""

    id: str
    layer: str
    uses_cloud: bool = Field(description="whether the step may use a cloud model")


class TakenOutStep(BaseModel):
    """A step the person took out of the plan on Ready (`answers.removed_jobs`), offered to be put back."""

    job: str
    title: str


class ByHandJob(BaseModel):
    """A job the answers bring that Start cannot run by itself: never a step, said with why and the fix."""

    job: str
    title: str
    why: str
    fix: str = Field(description="what does it by hand instead, in words")


class LeftOffStep(BaseModel):
    """A step left off by default (#5677): its job, its title, and one line saying why and what it would cost."""

    job: str
    title: str
    sentence: str
    offered: Optional[dict[str, Any]] = Field(default=None, description=(
        "Correct offered at Ready (ruled Q3 2026-10-17, #5677): a cloud corrector whose provider has a key set here, "
        "`card`, `runs_on` (the provider), `pages` and `cost_usd` for them; never turned on by itself. Null: none"))


class RecipeChange(BaseModel):
    """One step a fresh assembly would add, take out or run differently from the project's saved recipe."""

    step: str
    kind: Literal["added", "removed", "changed"]
    words: str = Field(description="the change in a sentence: 'Work out dates would be added'")
    was: Optional[dict[str, Any]] = Field(default=None, description="the saved step's model")
    now: Optional[dict[str, Any]] = Field(default=None, description="the fresh step's model")


class CloudOffer(BaseModel):
    """What one step would send to a cloud model, for the egress question (`source.onboard.egress-asked-once`)."""

    job: str
    title: str
    sends: str = Field(description="what would be sent: the page pictures, or the text of the pages")
    to: str = Field(description="the provider that would receive it")
    pages: Optional[int] = Field(default=None, description="how many pages; null while they are uncounted")
    cost_usd: Optional[float] = Field(default=None, description="the estimate; null when it cannot be worked out")
    sentence: str = Field(description="the above in one sentence, as setup shows it under the question")


class InferredLanguage(BaseModel):
    """What "Not sure" was worked out to from the sample pages (`source.onboard.project.about-material`): the person confirms or changes it."""

    code: Optional[str] = Field(default=None, description="the language tag worked out; null when the pages did not say")
    name: Optional[str] = Field(default=None, description="its name, for the sentence")
    script: Optional[str] = Field(default=None, description="the script code worked out (ISO 15924); null when the pages did not say")
    from_: str = Field(default="pages", alias="from", description="where it was worked out from: pages")
    sentence: str = Field(description="what the stage pages say: 'Language worked out from your pages: Spanish ... Change it if that is wrong.'")

    model_config = ConfigDict(populate_by_name=True)


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
    automatic: list[AutomaticStep] = Field(default_factory=list, description=(
        "the steps the purpose or an added layer turns on by itself, with their layer and whether each may use the "
        "cloud; worked out from the answers, never written by hand (source.recipe.steps-name-layers). A snapshot of the "
        "assembly it came from: saved with the recipe, and nothing compares a saved recipe with a fresh assembly"))
    changes: list[RecipeChange] = Field(default_factory=list, description=(
        "for an open project with a saved recipe: what this assembly would change in it, step by step; nothing is written "
        "(source.onboard.regen-shows-diff)"))
    inferred_language: Optional[InferredLanguage] = Field(default=None, description=(
        "set when the answers said 'Not sure' (languages ['und'], no scripts): the language and script worked out from the sample "
        "pages, with the sentence the stage pages show; null otherwise"))
    gaps: list[str]
    by_hand: list[ByHandJob] = Field(default_factory=list, description=(
        "jobs the answers bring that Start cannot run by itself, so never steps; each with why and the tool that "
        "does it by hand (source.onboard.auto.every-proposed-step-runs)"))
    left_off: list[LeftOffStep] = Field(default_factory=list, description=(
        "steps a purpose brings that are off until turned on, each with why and what turning it on would cost "
        "(Correct with no corrector at hand, #5677)"))
    removed: list[TakenOutStep] = Field(default_factory=list, description=(
        "steps the answers' removed_jobs took out of the plan, in step order, to be put back on Ready "
        "(source.onboard.plan-editable)"))
    cloud_options: list[str] = Field(
        default_factory=list,
        description="jobs a cloud model would also fit if pages could leave this Mac; "
        "setup asks the egress question only when this is not empty",
    )
    cloud_offer: list["CloudOffer"] = Field(
        default_factory=list,
        description="per job in cloud_options: what setup shows under the egress question",
    )
    problems: list[str] = Field(description="what the recipe check finds (empty when it can run)")
    overrides: Optional[list[dict[str, Any]]] = Field(default=None, description=(
        "the open project's saved overrides (Use This, for the project or a folder), kept so a recipe proposed "
        "again and saved keeps them; a project-scope one has already set its step's reader"))
    already_text: Optional[str] = Field(default=None, description=(
        "set when the material is all already text: what Ready says, that there is nothing to read and where the "
        "plan starts (source.recipe.text-material-is-not-read)"))


def _hf_token_set() -> bool:
    from fichero_server.llm import get_api_key

    return bool(get_api_key("huggingface"))


def _cluster_names(request: Request) -> list[str]:
    """The clusters set up on this Mac, by name (#5769); none when the app's settings cannot be read, and none for a
    caller who is not the owner: every /api/hpc route is owner-only (review 85, review 124)."""
    from fichero_server.api.routes.ai.hpc import _load_clusters
    from fichero_server.api.routes.auth.accounts import _require_owner_or_bootstrap
    from fichero_server.db.app import get_app_db

    try:
        _require_owner_or_bootstrap(request)
    except HTTPException:
        return []
    try:
        return sorted(str(c.get("name") or c.get("cluster_id") or "a cluster") for c in _load_clusters(get_app_db()).values())
    except Exception:  # noqa: BLE001 -- no clusters to offer, never a failed plan
        return []


def _this_machine_memory_gb() -> float:
    from fichero_server.recipes.train_offers import this_mac_memory_gb

    return this_mac_memory_gb()


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
    parent: Optional[str] = Field(default=None, description=(
        "the purpose it is shown under, as one of that purpose's options (Search under Transcribe; Entities and "
        "Statements under Knowledge graph); null for a purpose of its own. Still ticked on its own "
        "(source.onboard.purposes-grouped)"))


class PurposeListResponse(BaseModel):
    items: list[PurposeInfo]
    count: int


class StageOption(BaseModel):
    id: str
    title: str


class StageQuestion(BaseModel):
    key: str = Field(description="its answer's key in `answers.job_answers`")
    ask: str
    kind: Literal["one", "many", "yes-no", "text", "language"]  # language: any BCP 47 tag, chosen by search
    options: list[StageOption] = Field(default_factory=list)
    default: Any = None
    answer: Any = Field(default=None, description="this project's answer, else the default")
    read_by_a_step: bool = Field(description="true: a step reads it today; false: kept with the answers")
    open_ended: bool = Field(default=False, description="a question that names kinds: every kind by default (an empty answer), "
                       "the person can type their own, and `options` stay empty (#5805)")
    suggestions: list[str] = Field(default_factory=list, description="for an open question: only the kinds a sample try "
                                   "found; empty until a try returns them")


class StageNeed(BaseModel):
    stage: str
    why: str = Field(description="in words: 'Dates & Times needs Names'")


class ExampleCredit(BaseModel):
    """Where a borrowed example comes from, with both links (#5803, `source.onboard.credits.link-source-and-licence`)."""

    title: str
    short_credit: str = Field(description="the credit line shown under the example")
    licence: str
    source_url: str = Field(description="the item's own page")
    licence_url: str = Field(description="the licence's deed")


class SetupStage(BaseModel):
    """One stage of Set Up, one page each (section 7c, #5668)."""

    id: str
    title: str
    sentence: str = Field(description="what it does, in one sentence")
    example: str
    example_credit: ExampleCredit = Field(description="the shipped example's credit, both links (#5803)")
    example_from_samples: Optional[str] = Field(default=None, description="an example from the person's sample pages, "
                                                "once a try found one (Passages)")
    jobs: list[str] = Field(description="the registry jobs it carries, in step order")
    on: bool = Field(description="whether this project's recipe has any of its jobs")
    jobs_in_recipe: list[str]
    questions: list[StageQuestion]
    needs: list[StageNeed] = Field(description="the stages it needs, ticked with it")
    sampleable: bool = Field(description="it can be tried on the sample pages before Start")
    tried_by: Literal["bake-off", "workflow"]
    not_tried: Optional[str] = Field(default=None, description=(
        "when it cannot be tried on the sample pages yet, one plain sentence saying so (`source.try.every-job`); "
        "null when it can"))


class MoneyAndPlace(BaseModel):
    """The three ruled money-and-place settings as the engine holds them (#5769), for the setup screen to show; this
    month's spend against the cap is on the Start plan (`hf_spend`)."""

    hf_spend_cap_usd: float = Field(description="the monthly Hugging Face cap (`answers.hf_spend_cap_usd`); $0 offers "
                                    "only")
    copies_may_stay_on_cluster: bool = Field(description="whether working copies stay on a cluster for re-runs, as it "
                                             "stands: the person's answer, else what they said about pages leaving")
    copies_follow_pages_may_leave: bool = Field(description="true while the person has not answered the copies "
                                                "question, so its value follows pages-may-leave")
    clusters: list[str] = Field(description="the clusters set up here, by name: the copies question and the cluster "
                                "offer apply only where there is one")


class SetupStageList(BaseModel):
    items: list[SetupStage]
    count: int
    money_and_place: Optional[MoneyAndPlace] = None


@router.get("/stages", response_model=SetupStageList)
async def list_stages(request: Request) -> SetupStageList:
    """The eleven stages of Set Up in order (section 7c, `source.onboard.stages.stages-list-from-the-engine`): each
    with its jobs, its own questions (this project's answer, else the default), whether this project's recipe has
    it on, the stages it needs and why, and whether it can be tried on the sample pages. The app works none of it
    out. Without an open project every stage is off and every answer its default."""
    from fichero_server.recipes.stages import listing

    library = _optional_library(request)
    setup = read_project_setup(library) if library else {"recipe": None, "answers": None}
    from fichero_server.recipes import samples

    tried = samples.stored_results(library, setup["recipe"]) if library else {}
    items = [SetupStage(**s) for s in listing(setup["recipe"], setup["answers"], tried)]
    return SetupStageList(items=items, count=len(items),
                          money_and_place=_money_and_place(setup["answers"] or {}, _cluster_names(request)))


def _where_facts(request: Request) -> tuple[float, bool, list[str]]:
    """(this Mac's memory in GB, whether a Hugging Face account is set up, the clusters set up here this caller may see),
    for the places each candidate lists (#5976). Never the network."""
    from fichero_server.recipes.discovery import remote_compute
    from fichero_server.recipes.train_offers import this_mac_memory_gb

    mac = this_mac_memory_gb()
    return mac, bool(remote_compute(price=False)["available"]), _cluster_names(request)


def _lines_known(db: Any, workflows: list[dict[str, Any]], page_ids: list[str]) -> dict[str, Any] | None:
    """What the project already holds of Kraken's lines, for pricing a run that sends only the unsure ones (variant A);
    None when no run has a bar, so no plan pays for the scan."""
    from fichero_server.recipes.done import kraken_lines_known
    from fichero_server.recipes.start import certainty_bar

    has_bar = any(certainty_bar(w) is not None for w in workflows if w.get("job") == "correct")
    return kraken_lines_known(db, page_ids) if has_bar else None


def _hf_spent(db: Any, answers: dict[str, Any] | None) -> float:
    """This month's Hugging Face spend, at most (`source.onboard.spend-cap`): what the plan checks a chosen Hugging Face
    placement against the cap."""
    from fichero_server.recipes.answers import spend_cap
    from fichero_server.recipes.train_offers import spend_this_month

    return float(spend_this_month(db, cap=spend_cap(answers))["spent_at_most_usd"])


def _bound_cluster(answers: dict[str, Any] | None, clusters: list[str] | tuple[str, ...]) -> str | None:
    """The cluster the project binds its cluster steps to (`answers.cluster`, by the name Set Up shows), as its id;
    None unless it is one of `clusters`, those set up here that this caller may see (owner-only, review 124)."""
    from fichero_server.recipes.answers import CLUSTER

    name = (answers or {}).get(CLUSTER)
    if not name or name not in clusters:
        return None
    from fichero_server.api.routes.ai.hpc import _load_clusters
    from fichero_server.db.app import get_app_db

    try:
        return next((str(cid) for cid, c in _load_clusters(get_app_db()).items()
                     if str(c.get("name") or c.get("cluster_id") or "a cluster") == name), None)
    except Exception:  # noqa: BLE001 -- the settings cannot be read: no cluster, never a failed plan
        return None


def _money_and_place(answers: dict[str, Any], clusters: list[str]) -> MoneyAndPlace:
    from fichero_server.recipes.answers import COPIES_STAY, copies_may_stay, spend_cap

    return MoneyAndPlace(hf_spend_cap_usd=spend_cap(answers), copies_may_stay_on_cluster=copies_may_stay(answers),
                         copies_follow_pages_may_leave=not isinstance(answers.get(COPIES_STAY), bool),
                         clusters=clusters)


class SamplePage(BaseModel):
    id: str
    name: str
    why: str = Field(description="why it is a sample: your first page, the largest image, chosen by you…")
    yours: bool = Field(default=True, description="a page of this project, marked as the person's own: never the shipped "
                        "example image (#5808)")
    thumbnail: bool = Field(default=False, description="whether the page's thumbnail is made yet "
                            "(`GET /api/storage/thumbnail/{id}`), so the stage page can draw it (#5808)")


class SamplePages(BaseModel):
    chosen_by: Literal["fichero", "you"]
    pages: list[SamplePage]


class ChooseSamples(BaseModel):
    ids: list[str] = Field(default_factory=list, description="the pages chosen; empty: back to Fichero's proposal")


class TryStageRequest(BaseModel):
    page_ids: list[str] = Field(default_factory=list, description="the pages to try it on; empty: the samples")
    cost_ok: bool = Field(default=False, description="the person's yes to a cost the try said first (cloud steps)")
    candidates: list[str] = Field(default_factory=list, description=(
        "the card ids to compare side by side on these pages (source.onboard.stages.compares-candidates); empty: "
        "the stage's step's own model and the per-step finder's next ones, up to three"))


class BakeoffRecommendation(BaseModel):
    """What Set Up recommends from the measured rows (#5922): the reader that reads best by more than the project's
    noise band, or a local or cheaper one within the band of the best, with the reason in words."""

    card: str
    name: str
    cer: float
    local: bool
    runs_on: Optional[str] = None
    cost_per_page_usd: Optional[float] = Field(default=None, description="none when the price is not known")
    cost_set_usd: Optional[float] = Field(default=None, description="for the project's whole page count")
    within_noise_band_of: Optional[str] = Field(default=None, description="the best reader's card, when this one is "
                                                "recommended because it reads within the band of it")
    sentence: str


class TryCost(BaseModel):
    """A candidate's cost on the Try's pages (#5922). `measured` is the contract; `why` is words for a person."""

    model_config = ConfigDict(populate_by_name=True)

    value: Optional[float] = Field(default=None, description="US dollars on the Try's pages; none when not known")
    basis: Literal["measured", "estimate", "upper bound", "unknown"] = Field(description=(
        "measured: the provider's own usage (or free, on this Mac); estimate: the price list; upper bound: the most it "
        "can cost (variant A re-reads only the unsure lines, so it costs less); unknown: no price"))
    measured: bool = Field(default=False, description="true when `value` is what the run really cost")
    why: Optional[str] = Field(default=None, description="when `measured` is false for a run that called a model: why")
    source: Optional[str] = Field(default=None, alias="from", description="where the figure comes from, in words")

    @model_validator(mode="before")
    @classmethod
    def _old_results_have_no_flag(cls, data: Any) -> Any:
        """A result stored before the flag existed: it was measured when its basis says so (review 632)."""
        if isinstance(data, dict) and "measured" not in data:
            return {**data, "measured": data.get("basis") == "measured"}
        return data


class TryCandidate(BaseModel):
    """One column of a Try (the bake-off row's fields; the rest pass through untyped)."""

    model_config = ConfigDict(extra="allow")

    card: str
    name: Optional[str] = None
    runs_on: Optional[str] = None
    local: Optional[bool] = None
    state: Optional[str] = None
    cer: Optional[float] = None
    cost_usd: Optional[TryCost] = None


class StageTryResult(BaseModel):
    """A stage's sample result as its try left it; the per-page pictures and the like pass through untyped."""

    model_config = ConfigDict(extra="allow")

    state: str = Field(description="waiting, running, done or failed")
    stage: Optional[str] = None
    pages: list[str] = Field(default_factory=list)
    how: Optional[str] = None
    error: Optional[str] = None
    job_id: Optional[str] = None
    bakeoff: Optional[str] = None
    candidates: list[TryCandidate] = Field(default_factory=list)
    left_out: Optional[str] = Field(default=None, description=(
        "the sentence naming a frontier reader the Try's limit of three left out"))
    recommendation: Optional[BakeoffRecommendation] = Field(default=None, description=(
        "once the Try has finished: what Set Up recommends, ranked by what each candidate really cost"))


@router.get("/samples", response_model=SamplePages)
async def get_samples(stage: Optional[str] = None, db: Database = Depends(get_library_database)) -> SamplePages:
    """The sample pages every stage page tries itself on (section 7c, `source.onboard.stages.samples-proposed`): the
    person's choice, else 3 to 5 proposed across the material (first, last, the largest and smallest images, then
    evenly spaced), each with why. With `stage=organise`, the run of up to 12 consecutive pages of one folder that
    Organise is tried on (`source.onboard.stages.organise-tried-on-a-run`)."""
    from fichero_server.recipes import samples

    return SamplePages(**await asyncio.to_thread(samples.chosen, db, stage))


@router.put("/samples", response_model=SamplePages)
async def choose_samples(body: ChooseSamples, db: Database = Depends(get_library_database_for_write)) -> SamplePages:
    """Choose the sample pages by hand (kept beside the setup, for every stage); none: back to the proposal."""
    from fichero_server.recipes import samples

    try:
        return SamplePages(**await asyncio.to_thread(samples.choose, db, body.ids))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/stages/{stage}/try", response_model=StageTryResult)
async def try_stage(stage: str, body: Optional[TryStageRequest] = None,
                    db: Database = Depends(get_library_database_for_write),
                    ctx: ActionContext = Depends(action_context)) -> dict[str, Any]:
    """Try a stage on the sample pages before Start (section 7c, `source.onboard.stages.sample-run-reuses`), comparing
    2 or 3 of its step's candidates side by side (`source.onboard.stages.compares-candidates`): `candidates`, else the
    step's own model and the finder's next ones, each running the stage's own steps on its own copy of the samples
    (one `try-a-stage` job in Activity); the answer's `candidates` are the columns (the bake-off row's fields, each
    with its `per_page`, `names` and `measures`). Read and Find Lines start the bake-off instead (its evaluation job)
    when no candidates are named and the samples hold its corrected lines. The result is the stage's, kept beside the setup
    and replaced by the next try, never the project's work. A stage whose steps use the cloud says its cost and
    is refused (402) without `cost_ok`; a stage that is off, cannot be tried, or cannot run says why (422)."""
    from fichero_server.recipes import samples

    body = body or TryStageRequest()
    setup = read_project_setup(_library(db))
    try:
        return await asyncio.to_thread(
            samples.start_try, db, stage, setup, page_ids=body.page_ids or None, cost_ok=body.cost_ok,
            started_by=started_by_for(ctx), candidates=body.candidates or None,
            run_evaluation=lambda params: registry.invoke(db, "evaluation.run", params, ctx).result["job_id"])
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/stages/{stage}/try", response_model=StageTryResult)
async def stage_try_result(stage: str, db: Database = Depends(get_library_database)) -> dict[str, Any]:
    """The stage's sample result, as its last try left it (the bake-off's table for Read and Find Lines); 404 when
    it has not been tried, or is no longer chosen (a stage unticked clears it)."""
    from fichero_server.recipes import samples

    result = await asyncio.to_thread(samples.read_result, db, stage, read_project_setup(_library(db))["recipe"])
    if result is None:
        raise HTTPException(status_code=404, detail=f"{stage} has no sample result")
    return result


class HandOption(BaseModel):
    id: str
    title: str
    script: str
    centuries: str = Field(description="when it was written, in words: '15th–16th century'")
    tags: list[str] = Field(description="the Hugging Face tags readers made for it carry")
    looks: str = Field(description="what it looks like, in a few words, until each hand has its picture")


class HandList(BaseModel):
    items: list[HandOption]
    period_years: Optional[list[int]] = Field(default=None, description="the years the period answer means, when read")
    not_sure: str = Field(default="not-sure", description="the answer 'Not sure'")


def _ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


@router.get("/hands", response_model=HandList)
async def list_hands(request: Request, script: str = Query("Latn", description="ISO 15924 script code"),
                     period: Optional[str] = Query(None, description="'16th century', '1650–1700' or a year"),
                     languages: Optional[str] = Query(None, description=(
                         "the project's languages, comma-separated; a hand particular to others is left out"))
                     ) -> HandList:
    """Which hand: the curated hands for a script, those written in the period's centuries when it is read, each with
    its Hugging Face tags and what it looks like (section 7c, `source.onboard.material.which-hand`). Anything else can
    be typed and is kept as typed; 'not-sure' is an answer."""
    from fichero_server.recipes.hands import hands_for, period_years

    # With none asked, the open project's own answers (#5688): its period and languages as saved.
    library = _optional_library(request)
    saved = (read_project_setup(library)["answers"] or {}) if library else {}
    period = period or saved.get("period")
    asked = [t for t in (languages or "").split(",") if t.strip()] or list(saved.get("languages") or [])
    years = period_years(period)
    items = [HandOption(id=h.id, title=h.title, script=h.script, tags=list(h.tags), looks=h.looks,
                        centuries=(f"{_ordinal(h.from_century)} century" if h.from_century == h.to_century
                                   else f"{_ordinal(h.from_century)}–{_ordinal(h.to_century)} century"))
             for h in hands_for(script, period, asked)]
    return HandList(items=items, period_years=list(years) if years else None)


@router.get("/purposes", response_model=PurposeListResponse)
async def list_purposes() -> PurposeListResponse:
    """The purposes setup offers as checkboxes, in order, each with its label, whether it runs by
    itself, the jobs it proposes and the purpose it is listed under (`source.onboard.purpose-first`,
    `source.onboard.purposes-grouped`)."""
    from fichero_server.recipes.jobs import get_job

    items = [
        PurposeInfo(id=pid, title=title, description=desc, runs_by_itself=bool(PURPOSE_STEPS[pid]),
                    jobs=[PurposeJob(id=j, title=get_job(j).name) for j in PURPOSE_STEPS[pid]],
                    parent=PURPOSE_PARENT.get(pid))
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
    script: Optional[str] = Field(default=None, description=(
        "ISO 15924 code of the script the language is usually written in (Unicode CLDR likely subtags), which "
        "setup proposes when the language is chosen and the person may change; null when none is on record "
        "(source.onboard.script-from-language)"))
    script_name: Optional[str] = Field(default=None, description="that script's English name (ISO 15924)")


class LanguageMatchList(BaseModel):
    items: list[LanguageMatch]
    count: int


@router.get("/languages", response_model=LanguageMatchList)
async def search_languages(q: str = "", limit: int = 20) -> LanguageMatchList:
    """Search ISO 639-3 and Glottolog languages and dialects by name, tag or glottocode
    (`source.onboard.widget-and-search`)."""
    from fichero_server.recipes.names import script_name
    from fichero_server.recipes.names import search_languages as find

    items = [LanguageMatch(**row, script_name=script_name(row["script"]) if row.get("script") else None)
             for row in find(q, max(1, min(limit, 100)))]
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
    audit_id: Optional[str] = Field(default=None, description="the audit row of a choice just made; Undo reverses it")


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
async def derived_facts(
    scripts: str = "",
    period: str = "",
    app_db=Depends(_app_database),
    library_path: Optional[str] = Depends(optional_library_path),
) -> DerivedFacts:
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
    # The period and a person's font choice come from the open project's saved setup (#5438).
    saved = (read_project_setup(Path(library_path)).get("answers") or {}) if library_path else {}
    when = period or str(saved.get("period") or "")
    chosen = saved.get("fonts") or {}
    clusters = sorted(c.get("name") or cid for cid, c in _load_clusters(app_db).items())
    return DerivedFacts(
        scripts=[ScriptFacts(**derived.script_facts(c, when, chosen.get(c))) for c in codes],
        mac=MacFacts(**derived.this_mac()), keys=keys,
        targets=[PlaceToRun(**t) for t in derived.targets(keys, clusters)],
    )


class FontChoice(BaseModel):
    script: str = Field(description="ISO 15924 code of the script the font draws")
    font: Optional[str] = Field(default=None, description="a bundled family; null returns to the derived font")


@router.put("/font", response_model=ScriptFacts)
async def choose_font(
    body: FontChoice,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> ScriptFacts:
    """Remember a pane's font choice for a script in this library's setup answers (`answers.fonts`),
    or clear it, through `project.save_setup` (audited, undoable). Transcription text is then drawn in it
    (`layers.text.font-from-script-and-period`)."""
    from fichero_server.recipes import derived

    problem = derived.font_choice_problem(body.font)
    if problem:
        raise HTTPException(status_code=422, detail=problem)
    if derived.unknown_scripts([body.script]):
        raise HTTPException(status_code=422, detail=f"not an ISO 15924 script code: {body.script}")
    answers = dict(read_project_setup(_library(db)).get("answers") or {})
    fonts = dict(answers.get("fonts") or {})
    if body.font:
        fonts[body.script] = body.font
    else:
        fonts.pop(body.script, None)
    if fonts:
        answers["fonts"] = fonts
    else:
        answers.pop("fonts", None)
    try:
        done = registry.invoke(db, "project.save_setup", {"answers": normalise_answers(answers, strict=True)}, ctx)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    facts = derived.script_facts(body.script, str(answers.get("period") or ""), fonts.get(body.script))
    return ScriptFacts(**facts, audit_id=done.audit_id)


@router.get("/scripts", response_model=NamedCodeList)
async def search_scripts(q: str = "", limit: int = 20) -> NamedCodeList:
    """Search ISO 15924 scripts by name or code (`source.onboard.widget-and-search`)."""
    from fichero_server.recipes.names import search_scripts as find

    items = [NamedCode(**row) for row in find(q, max(1, min(limit, 100)))]
    return NamedCodeList(items=items, count=len(items))


def normalise_answers(answers: Any, *, strict: bool) -> Any:
    from fichero_server.recipes.answers import normalise

    return normalise(answers, strict=strict)


def _assemble(answers: dict[str, Any], library: Optional[Path] = None, *, overrides: Optional[list[dict[str, Any]]] = None
              ) -> dict[str, Any]:
    """The rules' recipe for setup's answers (as sent to `/assemble`, or as saved on the project).
    A language or script given as a word is resolved to its tag first, or refused (ValueError, in
    words): the rules only ever see tags (`source.onboard.language-stored-as-tag`).

    For a project with a saved recipe, its overrides come with the recipe and each project-scope one
    sets its step's reader (`bakeoff.apply_project_overrides`, the path Use This takes), so proposing
    the recipe again never undoes a reader the person chose; folder overrides stay overrides."""
    from fichero_server.db.manager import db_manager
    from fichero_server.recipes import language_guess

    if answers.get("loose_pages") is None and library is not None:
        # Default on for a project that holds a folder of loose page images (§7b, "Everything automatic after
        # Start": a box is organised as a stage of the run); an answer of False turns it off.
        answers = {**answers, "loose_pages": _holds_loose_pages(library)}
    if answers.get("faded_pages") is None and library is not None:
        # Measured on the project's sample: a faded page there proposes preparing the images (#5580).
        from fichero_server.db.manager import db_manager
        from fichero_server.recipes.prepare import sample_shows_faded

        answers = {**answers, "faded_pages": sample_shows_faded(db_manager.get_database(str(library)))}
    if not answers.get("materials") and not answers.get("material") and library is not None:
        # Unset: text when every page of the sample is already text (a note, or a PDF page with a text layer, #5553).
        from fichero_server.db.manager import db_manager
        from fichero_server.recipes.prepare import sample_is_text

        if sample_is_text(db_manager.get_database(str(library))):
            answers = {**answers, "materials": ["text"]}
    inferred = None
    if language_guess.unsure(normalise_answers(answers, strict=True)):
        # "Not sure" (`und`, no script): worked out from the sample pages, said on the recipe; the rules see what was found.
        inferred = language_guess.infer(db_manager.get_database(str(library)), library) if library is not None else None
        if inferred is not None and inferred["code"]:
            answers = {**answers, "languages": [inferred["code"]], "scripts": [inferred["script"]] if inferred["script"] else []}
    a = _answers(answers)
    if library is not None:
        from dataclasses import replace

        from fichero_server.recipes.project import read_noise_band

        band = read_noise_band(library)
        if band["measured"]:  # measured readers tie inside the project's own band (#4950, #5692)
            a = replace(a, noise_band=band["value"])
    from fichero_server.recipes.discovery import other_text_cards

    recipe = assemble(a, known_cards(a), offered=_cloud_correctors(a.cloud_keys), readers=_readers_with_a_row(),
                      cloud_text=[c for c in other_text_cards() if str(c.runs_on).startswith("cloud:")])
    if inferred is not None:
        recipe["inferred_language"] = inferred
    saved = (read_project_setup(library)["recipe"] or {}) if library is not None else {}
    kept = list(overrides) if overrides is not None else list(saved.get("overrides") or [])  # `overrides`: the choices to keep
    # A choice for a step the person has since un-ticked goes with the step: kept, it named a step this recipe no longer
    # has and the check refused the whole plan, so Start could not run (owner 2026-10-24). A page reader adds the page
    # step instead (#6259). A removed-step record stays.
    from fichero_server.recipes.recipe import fit_overrides

    recipe["overrides"] = kept
    fit_overrides(recipe)
    kept = recipe.pop("overrides")
    if kept:
        from fichero_server.recipes.bakeoff import apply_project_overrides

        recipe["overrides"] = kept
        # Every card Fichero keeps, not only those the finder lists for these answers: a reader chosen for other
        # languages is still the person's choice (#5660 item 8).
        apply_project_overrides(recipe, [*known_cards(a, include_not_built=True),
                                         *known_cards(None, include_not_built=True)])
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


def _providers_with_keys() -> list[str]:
    from fichero_server.recipes.derived import _providers_with_keys as keyed

    return keyed()


def _readers_with_a_row() -> list[Any]:
    """The person's cloud vision readers whose provider has a row in Settings › AI: what the cloud question counts besides the
    text models. The Claude card that only says to add the key first is not one (nothing could be sent to it)."""
    from fichero_server.recipes.discovery import remote_reader_cards

    return [c for c in remote_reader_cards() if not str(c.id).endswith("@settings")]


def _cloud_correctors(keys: tuple[str, ...] | list[str]) -> list[Any]:
    """The person's cloud vision readers whose provider has a key here, as correctors priced per page from the price
    list (#5677): what Correct is offered with at Ready, never the rules' choice. A reader with no known price is
    left out: the offer states its cost. ponytail: a vision reader is assumed to correct; a card of its own when not."""
    from dataclasses import replace

    from fichero_server.recipes.bakeoff import cloud_readers
    from fichero_server.recipes.routes import _cloud_cost

    out = []
    for card in cloud_readers():
        if not card.runs_here or card.runs_on.split(":", 1)[-1] not in keys:
            continue
        price = _cloud_cost(f"{card.pin['cloud']}/{card.pin['model']}", 1)
        if price:
            out.append(replace(card, jobs=card.jobs | {"correct"}, cost_per_page=price))
    return out


def _answers(answers: dict[str, Any]) -> Answers:
    """Setup's answers as the rules read them (the one place they are turned into `Answers`)."""

    a = normalise_answers(answers, strict=True)
    return Answers(
        purposes=tuple(a["purposes"]), languages=frozenset(t for t in a.get("languages") or () if t != "und"),  # "Not sure" is no language to the rules
        scripts=frozenset(a.get("scripts") or ()), materials=tuple(a["materials"]),
        jobs=tuple(a.get("jobs") or ()), removed_jobs=tuple(a.get("removed_jobs") or ()),
        pages=a.get("pages") or 0, cloud_allowed=places.may_leave_to(a, "cloud"),
        mac_memory_gb=a.get("mac_memory_gb") or _this_machine_memory_gb(),
        layers=frozenset(a.get("layers") or ()), loose_pages=bool(a.get("loose_pages")),
        faded_pages=bool(a.get("faded_pages")), photographs=bool(a.get("photographs")),
        job_answers=dict(a.get("job_answers") or {}), period=str(a.get("period") or ""),
        search_embedder=search_embedder(), cloud_keys=tuple(_providers_with_keys()),
    )


#: A route that takes its question as a body but writes nothing: its generated MCP tool says it reads
#: (`openapi.mcp.reads-say-so`, #5584).
READS = {"x-fichero-reads": True}


def _run_titles(step: dict[str, Any]) -> dict[str, Any]:
    from fichero_server.recipes.answers import normalise_run_titles

    if step.get("job") != "translate-transliterate-normalise":
        return {}
    return {"run_titles": normalise_run_titles((step.get("settings") or {}).get("target"))}


#: Assemble's refusal for an open project with nothing in it (#5813, ruled 2026-10-19): the plan follows from material.
NO_MATERIAL_TO_PLAN = ("This project has no material yet: add your pages in Set Up › Your Material, and the plan "
                       "follows from them.")


def _without_material(http: Request) -> bool:
    """Whether the project the caller names has no material (no page, no file); False with no project named."""
    from fichero_server.recipes.start import count_pages

    path = optional_library_path(http)
    return bool(path) and count_pages(get_library_database(http, path)) == 0


@router.post("/assemble", response_model=AssembledRecipe, openapi_extra=READS, responses={422: {
    "model": _ErrorDetail,
    "description": ("Refused, in one sentence: the named project has no material yet (`NO_MATERIAL_TO_PLAN`), or a "
                    "language, script, purpose, material, job or direction Fichero does not know.")}})
async def assemble_recipe(
    http: Request, request: AssembleRequest, library: Optional[Path] = Depends(_optional_library),
) -> AssembledRecipe:
    """The recipe the rules give for these answers, each choice with its reasons and each gap named
    once as a structured problem (`source.onboard.deterministic-recipe`, `source.onboard.says-no-model`).
    For an open project with a saved recipe, its overrides are kept and a project-scope one (Use This)
    sets its step's reader. Proposes; writes nothing. Refused with 422, in words, for a language,
    script, purpose, material, job or direction Fichero does not know; and for a named project with no material yet
    (#5813)."""
    if library is not None and _without_material(http):
        raise HTTPException(status_code=422, detail=NO_MATERIAL_TO_PLAN)
    try:
        recipe = await asyncio.to_thread(_assemble, request.model_dump(), library)  # "Not sure" runs a quick read: off the loop
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    problems = [] if recipe["gaps"] else check_recipe(recipe)
    return AssembledRecipe(
        fichero_recipe=recipe["fichero_recipe"], version=recipe["version"], suits=recipe["suits"],
        id=recipe["id"], title=recipe["title"], purposes=recipe["purposes"],
        steps=[RecipeStep(**s, **_run_titles(s)) for s in recipe["steps"]], automatic=recipe.get("automatic") or [],
        gaps=recipe["gaps"], by_hand=recipe.get("by_hand") or [],
        removed=recipe.get("removed") or [], left_off=recipe.get("left_off") or [],
        cloud_options=recipe["cloud_options"], cloud_offer=[CloudOffer(**o) for o in recipe.get("cloud_offer") or []], problems=problems, overrides=recipe.get("overrides"),
        already_text=recipe.get("already_text"), changes=_changes(library, recipe),
        inferred_language=recipe.get("inferred_language"),
    )


def _changes(library: Optional[Path], fresh: dict) -> list[RecipeChange]:
    """What the fresh assembly would change in the open project's saved recipe (none when there is no project, or no
    saved recipe: then everything is new and nothing is a change)."""
    from fichero_server.recipes.diff import diff_recipes

    saved = read_project_setup(library)["recipe"] if library else None
    return [RecipeChange(**c) for c in diff_recipes(saved, fresh)] if saved else []


class CheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recipe: dict[str, Any] = Field(description='The recipe to check, as GET /api/recipes/project returns it.')


class CheckResponse(BaseModel):
    problems: list[str]


@router.post("/check", response_model=CheckResponse)
async def check(request: CheckRequest) -> CheckResponse:
    """Every reason a recipe cannot run as it stands, step by step (`source.recipe.*`)."""
    return CheckResponse(problems=check_recipe(request.recipe))


# =============================================================================
# Finding models beyond the shipped cards (#5519): the candidates the rules see, and where they came from.
# =============================================================================

CardSource = Literal["shipped", "installed", "kraken-repository", "hugging-face", "remote", "remote-endpoints",
                     "remote-compute", "transkribus", "htr-united", "nothing-found"]


class CandidateSource(BaseModel):
    source: CardSource
    state: Literal["read", "searched", "searching", "cached", "not-searched", "offline", "failed"] = Field(
        description=(
            "read: on this Mac; searched: fetched by the search job; searching: the search job is running (the "
            "count is what was kept before); cached: from the last fetch; not-searched: online was not asked (or "
            "no project is open to run the search); offline: this engine works offline (local-only); failed: the "
            "fetch failed (detail says why)"))
    count: int
    left_out: int = Field(default=0, description="Hugging Face builds the search left out as not readers (chat "
                          "models), never listed (#5594)")
    detail: str


class SearchJob(BaseModel):
    """The online search as an Activity job (#5594, `source.find.online-search-is-a-job`)."""

    id: str
    state: str = Field(description="waiting, running, done or failed, as Activity shows it")
    reason: Optional[str] = Field(default=None, description="what it is doing, or why it failed, in words")


class CandidatePlace(str, Enum):
    """Where a model runs (`llm.places`): the places the AI settings use."""

    this_mac = "this_mac"
    own_machine = "own_machine"
    provider = "provider"


class CandidateDownload(BaseModel):
    """The action that downloads a candidate's model (as `StartDownload.action`/`params`)."""

    runtime: str = Field(description="mlx or spacy")
    model: str = Field(description="the model's id in that runtime")
    action: str = Field(description="the action to invoke (model.download, a download-model job on the network lane)")
    params: dict[str, Any]
    downloading: bool = Field(default=False, description="a download-model job is already fetching it (#5791)")
    job_id: Optional[str] = Field(default=None, description="that job, as Activity lists it, while downloading (#5791)")
    progress: Optional[str] = Field(default=None, description="how far it has got, as the job last said it (#5791)")


class CandidateAvailability(str, Enum):
    """Where a candidate stands for this Mac (#5660 item 3), one of: it ships with Fichero, it is on this Mac, it can
    be downloaded, it runs elsewhere (a provider, a machine of the person's own), or Fichero cannot run it yet."""

    ships = "ships"
    installed = "installed"
    download = "download"
    elsewhere = "elsewhere"
    not_here = "not_here"


class ModelFit(BaseModel):
    """Whether an MLX model fits this Mac to read with, before anything is downloaded or loaded (#5641,
    `runtime.mlx.fit-estimate`): the same rule the load applies."""

    word: Literal["fits", "tight", "won't fit"]
    reason: str = Field(description="one line: what it needs (weights, KV cache, context) against this Mac")
    smaller: Optional[str] = Field(default=None, description=(
        "a smaller build of the same model that fits, when this one won't (`runtime.mlx.offer-a-way-to-fit`)"))


def _mlx_model_of(card: Any) -> Any:
    """The MLX model a card names, as the fit estimate reads it: the catalogue's spec, a model trained or found in
    the store (never the Hub), else its stated download size; None for a card that is not an MLX model or states
    no size."""
    from types import SimpleNamespace

    from fichero_server.llm.mlx_model_store import MANAGED_MLX_MODELS, get_mlx_model_store

    if not str(card.id).startswith("mlx:"):
        return None
    repo = str((card.pin or {}).get("hf") or "")
    for spec in MANAGED_MLX_MODELS.values():
        if spec.repo_id == repo:
            return spec
    store = get_mlx_model_store()
    try:
        if store.trained_card(repo) is not None:
            return store.spec(repo)
        found = store.found_spec(repo)
    except Exception:  # noqa: BLE001 - a store that cannot be read gives no fit, never a failed listing
        found = None
    if found is not None:
        return found
    if not card.size_gb:
        return None
    return SimpleNamespace(repo_id=repo, display_name=card.note.strip().rstrip(".") or repo,
                           download_size_bytes=int(card.size_gb * GIB), kv_bytes_per_token=None)


class PlaceOption(BaseModel):
    place: str = Field(description="this-mac, hf-jobs, cluster or provider")
    name: str = Field(description="this Mac, Hugging Face Jobs, the cluster's name, or the provider")
    can: bool
    needs: str = ""
    why: str = Field(default="", description="why it cannot run there, in words")
    blocked: str = Field(default="", description="why the app cannot send there yet, though the model could run there")


class ModelCandidate(BaseModel):
    """One reader candidate as a card: where it came from, why it is offered, what it states, and what
    the rules make of it for the project's scripts, languages and material."""

    id: str = Field(description="<runtime>:<source>@<version>")
    name: str
    tier: Optional[str] = Field(default=None, description="a reading candidate's tier: cloud, specialist, small-vlm or general (source.recipe.reader-tiers); null for another job")
    tier_words: Optional[str] = Field(default=None, description="the tier in words for a row: Specialist line reader, Small vision model on this Mac, General model")
    short_name: str = Field(default="", description="the name a model row shows, short enough to read in a row; the whole `name` is the hover text (source.find.model-row-words)")
    source: CardSource
    offered_because: str = Field(description="why discovery offers it, in words")
    pin: dict[str, Any]
    jobs: list[str]
    scripts: Optional[list[str]] = Field(default=None, description="ISO 15924 codes its card states; null: unstated")
    languages: Optional[list[str]] = Field(default=None, description="BCP 47 tags its card states; null: unstated")
    licence: str = ""
    open_licence: bool
    size_gb: Optional[float] = Field(default=None, description="its download size; null: not stated (#5594)")
    memory_gb: Optional[float] = Field(default=None, description="the memory it needs; null: not stated")
    size: str = Field(description="its size in words: '1.2 GB', or 'size not stated' (never 0.0 GB, #5594)")
    cer_published: Optional[float] = Field(default=None, description="a published CER the rules rank on (only "
                                            "where the record names the project's languages)")
    cer_measured_here: Optional[float] = None
    measured: str = Field(description="what is measured on this project, or that it is unmeasured until a "
                          "bake-off measures it")
    in_recipe_rules: bool = Field(description="whether the rules choose from it: true for every candidate since "
                                  "a found Hugging Face reader downloads like a catalogue model (#5593)")
    rule_rank: Optional[int] = Field(default=None, description="its place by the rules' fixed order among the "
                                     "candidates they keep; null when refused or not in the rules")
    refused: Optional[str] = Field(default=None, description="the rules' first reason it cannot do the job here")
    needs_permission: bool = Field(default=False, description="a cloud reader the project may not use until the person has said pages may leave this Mac: shown greyed, \"needs permission\" (`source.onboard.pages-may-leave`, #5768)")
    installed: Optional[bool] = Field(default=None, description=(
        "whether its model is already on this Mac (an MLX model in the store, a spaCy pipeline, a bundled Kraken "
        "model); null where nothing is downloaded first (a Kraken reader the run fetches, a cloud model) (#5612)"))
    download: Optional[CandidateDownload] = Field(default=None, description=(
        "the action that downloads its model, as the Start plan's downloads name it; null when there is nothing "
        "to download first (#5612)"))
    places: list["PlaceOption"] = Field(default_factory=list, description=(
        "every place it can run, this Mac, Hugging Face Jobs and each cluster set up here, with what it needs there and, "
        "where it cannot, why in words; `blocked` is set where the model could run but the app cannot send there yet "
        "(#5976, #5238)"))
    runs_where: CandidatePlace = Field(description=(
        "where it runs: this Mac, a machine of the person's own, or the provider that runs it (llm.places, #5612)"))
    availability: CandidateAvailability = Field(description=(
        "ships with Fichero, installed on this Mac, can be downloaded, runs elsewhere, or not runnable here (#5660)"))
    availability_words: str = Field(description=(
        "the same, in one short phrase with its size: 'Available', 'Downloaded (16 MB)', 'Download "
        "(2.3 GB)', 'Runs at openai', 'Fichero cannot run it yet (…)'"))
    fit: Optional[ModelFit] = Field(default=None, description=(
        "for an MLX model: whether it fits this Mac to read with ('fits', 'tight', 'won't fit') and why, by the rule "
        "the load applies (#5641); null for any other model"))
    compared_by_default: bool = Field(default=False, description="with `step`: Compare on These Pages runs it when "
                                      "none is ticked (the step's own model and the next runnable ones), so the "
                                      "page can name them before it runs (#5808)")
    link: Optional[str] = Field(default=None, description="the page of its model (Hugging Face, Zenodo's DOI); null "
                                "where it has none (#5808)")
    other_period: bool = Field(default=False, description="made for another period than the project's "
                               "(`answers.period`): the app lists it under 'Other periods', not beside the fitting "
                               "ones (#5808)")
    chosen: bool = Field(default=False, description=(
        "with `step`: this is the step's reader now (the person's choice, or the rules' when none was made); "
        "listed first (#5660 item 8)"))
    default_pick: bool = Field(default=False, description=(
        "with `chosen`: no reader is saved for the step, and this is the top-ranked model that runs here at no cost, shown as "
        "chosen by default; Use for This Step still saves it (`source.find.free-local-model-is-the-default-pick`)"))


class HtrUnitedLicence(BaseModel):
    name: str = ""
    url: str = ""


class HtrUnitedDataset(BaseModel):
    """One HTR-United ground-truth dataset and what it may be used as (#5571)."""

    title: str
    url: str
    description: str
    languages: list[str]
    scripts: list[str]
    handwriting: bool
    format: str
    licence: HtrUnitedLicence
    lines: Optional[int] = None
    pages: Optional[int] = None
    as_: list[str] = Field(alias="as", description="test-set and training when the licence is open; empty until "
                           "the licence is accepted")
    accept: Optional[str] = Field(default=None, description="what to accept first; null when the licence is open")
    importable: bool = Field(description="whether Fichero can import its format (PAGE or ALTO)")

    model_config = {"populate_by_name": True}


class HtrUnitedDatasets(BaseModel):
    fetched_at: Optional[str] = Field(default=None, description="when the catalogue was kept; null when never")
    datasets: list[HtrUnitedDataset]


class ModelCandidateList(BaseModel):
    job: str
    items: list[ModelCandidate]
    count: int
    sources: list[CandidateSource]
    search_job: Optional[SearchJob] = Field(default=None, description=(
        "with online=true: the open project's search job (`find-models`, on the network lane): the call answers "
        "at once with what is kept, and a later call, once the job is done, lists what it found (#5594)"))


def _search_job(request: Request, library_path: str, languages: frozenset[str], job: str) -> dict[str, Any]:
    from fichero_server.api.main import _get_library_database_for_access
    from fichero_server.recipes.discovery import search

    return search(_get_library_database_for_access(request, library_path, write=False), languages, job)


def _step_for_job(request: Request, library_path: str, job: str) -> Optional[str]:
    """The open project's first step of this job, or None."""
    from fichero_server.api.main import _get_library_database_for_access

    db = _get_library_database_for_access(request, library_path, write=False)
    recipe = read_project_setup(_library(db))["recipe"] or {}
    return next((str(s.get("id")) for s in recipe.get("steps") or [] if s.get("job") == job), None)


def _step_context(request: Request, library_path: Optional[str], step: Optional[str], job: str) -> int:
    """The context a step's model reads with (#5641): its settings' `max_tokens` where it sets one, a line's for a
    line reader, else the default."""
    from fichero_server.llm.local_inference import step_context_tokens

    settings: dict[str, Any] = {}
    if step and library_path:
        from fichero_server.api.main import _get_library_database_for_access

        db = _get_library_database_for_access(request, library_path, write=False)
        recipe = read_project_setup(_library(db))["recipe"] or {}
        found = next((s for s in recipe.get("steps") or [] if s.get("id") == step), None) or {}
        settings = found.get("settings") if isinstance(found.get("settings"), dict) else {}
    return step_context_tokens(max_tokens=settings.get("max_tokens"), lines=1 if job == "read-a-line" else None)


def _step_reader(request: Request, library_path: Optional[str], step: str) -> Optional[str]:
    """The card id of the open project's step's reader now (its project-scope override, else the rules' choice)."""
    if not library_path:
        return None
    from fichero_server.api.main import _get_library_database_for_access

    db = _get_library_database_for_access(request, library_path, write=False)
    recipe = read_project_setup(_library(db))["recipe"] or {}
    for override in recipe.get("overrides") or []:
        if override.get("step") == step and override.get("scope") == "project" and override.get("card"):
            return str(override["card"])
    found = next((s for s in recipe.get("steps") or [] if s.get("id") == step), None)
    card = (found or {}).get("card")
    return str(card["id"]) if isinstance(card, dict) and card.get("id") else None


@router.get("/htr-united", response_model=HtrUnitedDatasets)
async def htr_united_datasets(languages: str, scripts: str = "") -> HtrUnitedDatasets:
    """HTR-United's ground-truth datasets kept for these languages and scripts, each with what it may be used as
    (a bake-off test set, training data) and the licence to accept first (#5571). Never the network: the search job
    keeps the catalogue."""
    from fichero_server.recipes import htr_united
    from fichero_server.recipes.names import resolve_language, resolve_script

    try:
        script_codes = frozenset(resolve_script(s) for s in scripts.split(",") if s.strip())
        tags = frozenset(resolve_language(t) for t in languages.split(",") if t.strip())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    kept = htr_united.cached()
    found = htr_united.matching(kept["records"], languages=tags, scripts=script_codes) if kept else []
    return HtrUnitedDatasets(fetched_at=kept["fetched_at"] if kept else None, datasets=htr_united.offered(found))


def _compared_by_default(library_path: str, step_id: str) -> set[str]:
    """The cards Compare on These Pages runs for this step when none is ticked: the engine's own choice, so the
    page names them before the run (#5808). Empty where the project has no saved answers or the step is not in it."""
    from fichero_server.recipes import samples

    setup = read_project_setup(Path(library_path))
    step = next((s for s in (setup["recipe"] or {}).get("steps") or [] if s.get("id") == step_id), None)
    if step is None or not setup["answers"]:
        return set()
    try:
        return {c.id for c in samples._cards_for(setup, step, None)}
    except ValueError:  # answers the rules do not read (an old project): nothing is named as the default
        return set()


@router.get("/candidates", response_model=ModelCandidateList)
async def model_candidates(
    request: Request,
    scripts: str, languages: str = "", material: str = "handwriting", job: str = "read-a-line",
    online: bool = False, cloud_allowed: bool = False, mac_memory_gb: Optional[float] = None,
    step: Optional[str] = None,
    period: Optional[str] = None,
    worth_only: bool = False,
    library_path: Optional[str] = Depends(optional_library_path),
) -> ModelCandidateList:
    """Every candidate for a step's job (a reader's by default; any job a card can name, #5619) for these scripts
    and languages (comma-separated codes or names), from the shipped cards, the models on this Mac (and the
    person's own Ollama and LM Studio servers), Kraken's model repository and Hugging Face, each as a
    card saying where it came from and why it is offered, ranked by the rules' fixed order (#5519,
    `source.find.by-need`). The network is never reached inside this call: with `online=true` the search is
    the open project's Activity job (`search_job`, #5594), and this call answers at once with what the earlier
    searches kept; a later call lists what the job found. Never searched when this engine works offline. The
    search is the step's own (#5668): readers for a reading job, and for another job Hugging Face by that job's
    pipeline and Hub tags (`STEP_SEARCHES`); a job with no search of its own says so. With `step` (a step of the open project's recipe), the
    step's reader now is marked `chosen` and listed first, the person's choice included when the finder would not
    list it for these answers (#5660 item 8). Each candidate says plainly whether it ships with Fichero, is on this
    Mac or can be downloaded, with its size (`availability`). With `period` ("16th century", "1650–1700"), a reader
    made for it ranks first (#5683). For `read-a-line`, the page readers (Apple Vision, a vision model) are listed
    too, the person's to choose with no rule rank: a line step reads Kraken's lines with them, as the bake-off
    counts them. Refused (422), in words, for an unknown script, language, material or job."""
    from starlette.concurrency import run_in_threadpool

    from fichero_server.recipes.assemble import (
        READ_MATERIALS, READING_JOBS, _refusal, lists_project_languages, needs_permission, rank_key)
    from fichero_server.recipes.assemble import other_period
    from fichero_server.recipes.discovery import (
        NO_PROJECT,
        TIER_WORDS,
        candidate_availability,
        reader_tier,
        short_name,
        model_link,
        step_candidates,
        candidate_download,
        candidate_installed,
        candidate_place,
        STEP_SEARCHES,
        discover,
        egress_allowed,
        size_words,
    )
    from fichero_server.recipes.names import resolve_language, resolve_script

    from fichero_server.recipes.jobs import get_job

    if get_job(job) is None:
        raise HTTPException(status_code=422, detail=f"{job!r} is not a job Fichero knows")
    if job not in READING_JOBS and job not in STEP_SEARCHES:
        # The finder answers for any step's job (#5619, `source.find.choose-a-model-opens-the-finder`); a job with
        # no search of its own (#5668) is not searched, and the sources say so.
        online = False
    if material not in READ_MATERIALS:
        raise HTTPException(status_code=422, detail=f"material must be one of {', '.join(READ_MATERIALS)}")
    try:
        script_codes = frozenset(resolve_script(s) for s in scripts.split(",") if s.strip())
        tags = frozenset(resolve_language(t) for t in languages.split(",") if t.strip())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not script_codes:
        raise HTTPException(status_code=422, detail="name at least one script")
    # The open project's own yes counts too (`places.may_leave_to`): the app need not repeat it, so a cloud reader is not
    # said to need permission the project already gave (owner 2026-10-23, the step menu's Allow Cloud).
    saved = (read_project_setup(Path(library_path)).get("answers") or {}) if library_path else {}
    a = Answers(purposes=("transcribe",), languages=tags, scripts=script_codes, materials=(material,),
                cloud_allowed=(cloud_allowed and places.allows("cloud")) or places.may_leave_to(saved, "cloud"), mac_memory_gb=mac_memory_gb or _this_machine_memory_gb(),
                search_embedder=search_embedder(library_path or None), period=period or "")
    search = None
    if online and egress_allowed() and library_path:
        search = await run_in_threadpool(_search_job, request, library_path, tags, job)
    not_searched = None if library_path else NO_PROJECT
    cards, sources = await run_in_threadpool(
        discover, a, online=online, search=search, not_searched=not_searched, job=job)
    if step is None and library_path:
        # No step named: the open project's step for this job is the one whose model is `chosen` (#5688).
        step = await run_in_threadpool(_step_for_job, request, library_path, job)
    chosen_id = await run_in_threadpool(_step_reader, request, library_path, step) if step else None
    # The one list Compare reads too (#5808); the step's own card keeps its place against a twin at another revision.
    cards = step_candidates(cards, job, frozenset({chosen_id} if chosen_id else ()))
    if chosen_id and chosen_id not in {c.id for c in cards}:
        from fichero_server.recipes.discovery import known_cards

        # Only a model that does the step's job: a cloud model added by hand is not a line finder (#5838).
        cards += [c for c in known_cards(None, include_not_built=True) if c.id == chosen_id and job in c.jobs][:1]
    # Filtered to the project (owner 2026-10-23): a model refused for the script or the language is not listed at all, so
    # a Chinese reader shows only for Chinese. One for another material stays, ranked last: the finder asks with one
    # material where a project may have several. The step's own model stays, said as refused.
    if worth_only:
        cards = for_the_project(cards, job, a, material, chosen_id)
    kept = sorted((c for c in cards if c.runs_here and not c.offered_only and _refusal(job, c, a, material) is None),
                  key=lambda c: rank_key(job, c, material, a))
    rank = {c.id: i for i, c in enumerate(kept, 1)}
    # No reader chosen for the step (nothing saved yet, or the project's recipe has no such step): the top-ranked model that runs
    # on this Mac at no cost (a download is free: the plan offers it) is already the pick, not waiting for a click (`source.find.free-local-model-is-the-default-pick`).
    # A person's own choice, and the recipe's, win: they are `chosen_id`.
    pick = chosen_id
    if pick is None and kept:
        top = kept[0]
        # And one whose card lists the project's languages, or none: never an Arabic reader for a Spanish project (#6120).
        if top.local and not needs_permission(top, a) and lists_project_languages(top, a):
            pick = top.id

    def refused(c: Any) -> Optional[str]:
        if c.id in rank:
            return None
        made_for = _refusal(job, c, a, material)
        if made_for is not None and made_for[0] == "no-reader-for-material":
            return made_for[1]  # a print reader says it is for print, before it says it cannot run here
        if not c.runs_here:
            return f"Fichero cannot run it yet: {c.cannot_run_because or 'not in this build'}"
        if c.offered_only:
            # Yours to choose, never the rules': no rank, and refused only where it could not do the job here.
            return (_refusal(job, c, a, material) or (None, None))[1]
        return (_refusal(job, c, a, material) or (None, None))[1]

    from fichero_server.llm.local_inference import fit_estimate
    from fichero_server.llm.mlx_model_store import MANAGED_MLX_MODELS

    models = {c.id: _mlx_model_of(c) for c in cards}
    catalogue = [*MANAGED_MLX_MODELS.values(), *(m for m in models.values() if m is not None)]
    physical = int((mac_memory_gb or _this_machine_memory_gb()) * GIB)
    context = await run_in_threadpool(_step_context, request, library_path, step, job)

    def fit(c: Any) -> Optional[ModelFit]:
        model = models.get(c.id)
        if model is None:
            return None
        made = fit_estimate(model, context, physical_memory=physical, catalog=catalogue,
                            reads_pages=job in READS_A_PICTURE)  # the page floor is a refusal for a reader, as in runs_here
        return ModelFit(word=made.word, reason=made.reason, smaller=made.smaller)

    def measured(c: Any) -> str:
        if c.cer_measured_here is not None:
            return f"CER {c.cer_measured_here * 100:.1f}% on your pages"
        return "unmeasured on your pages until a bake-off measures it"

    # Each download under way carries its Activity job and progress, so the sheet shows it under way (#5791).
    downloads = {c.id: candidate_download(c) if c.runs_here else None for c in cards}
    if library_path:
        from fichero_server.recipes.start import mark_downloads_under_way

        mark_downloads_under_way(get_library_database(request, library_path), [d for d in downloads.values() if d])

    def availability_words(c: Any) -> str:
        said = candidate_availability(c)[1]
        d = downloads.get(c.id)
        return f"Downloading{': ' + d['progress'] if d.get('progress') else ''}" if d and d.get("downloading") else said

    compared = await run_in_threadpool(_compared_by_default, library_path, step) if library_path and step else set()
    from fichero_server.recipes.where_it_runs import places_it_can_run

    mac_gb, hf_ready, cluster_names = await run_in_threadpool(_where_facts, request)
    items = [ModelCandidate(
        id=c.id, name=c.note.strip().rstrip(".") or c.id, tier=reader_tier(c, job),
        tier_words=TIER_WORDS.get(reader_tier(c, job) or ""), short_name=short_name(c), source=c.source,
        offered_because=c.offered_because or "a card that ships with Fichero", pin=dict(c.pin),
        jobs=sorted(c.jobs), scripts=sorted(c.scripts) if c.scripts is not None else None,
        languages=sorted(c.languages) if c.languages is not None else None, licence=c.licence,
        open_licence=c.open_licence, size_gb=c.size_gb or None,
        memory_gb=None if not c.memory_gb and c.source == "hugging-face" else c.memory_gb,
        size=size_words(c.size_gb), cer_published=c.cer_published,
        cer_measured_here=c.cer_measured_here, measured=measured(c), in_recipe_rules=not c.offered_only,
        rule_rank=rank.get(c.id), refused=refused(c), needs_permission=needs_permission(c, a),
        installed=candidate_installed(c), download=downloads[c.id],
        places=[PlaceOption(**o) for o in places_it_can_run(c, this_mac_gb=mac_gb, hf_ready=hf_ready, clusters=cluster_names)],
        runs_where=candidate_place(c), availability=candidate_availability(c)[0],
        availability_words=availability_words(c), chosen=c.id == pick, default_pick=chosen_id is None and c.id == pick, fit=fit(c),
        link=model_link(c), other_period=other_period(c, a), compared_by_default=c.id in compared,
    ) for c in sorted(cards, key=lambda c: (c.id != pick, _offered_order(c)[0] != 0, rank.get(c.id, len(rank) + 1), _offered_order(c), c.id))]
    if worth_only:  # the finder's list (owner 2026-10-23); without it every candidate, as Compare and the tests read it
        items = worth_listing(items)
    return ModelCandidateList(
        job=job, items=items, count=len(items), sources=[CandidateSource(**s) for s in sources],
        search_job=SearchJob(id=search["id"], state=search["state"], reason=search.get("reason"))
        if search else None)


#: The refusals that mean a model is not for this project's pages, so the finder leaves it out.
_OFF_PROJECT = frozenset({"no-model-for-script", "no-model-for-language"})


#: How many of a tier the finder lists (owner 2026-10-23: the top few, not hundreds), in rank order.
PER_TIER = 5


def _worth(c: "ModelCandidate") -> bool:
    """Whether a row has something to press (owner 2026-10-23: only what is worth using is listed): the step's own model,
    one a press uses (a licence to accept included) or downloads, a cloud reader waiting on the project's permission, or
    one that needs a key in Settings › AI."""
    cannot = c.availability == CandidateAvailability.not_here
    uses = not c.needs_permission and not cannot and (c.refused is None or "licence" in c.refused)
    downloads = not c.needs_permission and (uses or c.availability == CandidateAvailability.elsewhere)
    asks_settings = cannot and "Settings › AI" in (c.availability_words or "")
    return bool(c.chosen) or uses or downloads or bool(c.needs_permission) or asks_settings


def worth_listing(items: list["ModelCandidate"], per_tier: int = PER_TIER) -> list["ModelCandidate"]:
    """The rows worth listing, at most `per_tier` of each tier in the order given; the step's own model and one measured
    on the person's pages always stay, and do not count against their tier. ponytail: a fixed cap; a Show All is the
    upgrade if a person needs the rest."""
    seen: dict[str | None, int] = {}
    out = []
    for c in items:
        if c.chosen or c.cer_measured_here is not None:
            out.append(c)
        elif _worth(c) and seen.get(c.tier, 0) < per_tier:
            seen[c.tier] = seen.get(c.tier, 0) + 1
            out.append(c)
    return out


def for_the_project(cards: list[Any], job: str, a: Any, material: str, chosen_id: str | None) -> list[Any]:
    """The cards for the project: none refused for its script or language (`_OFF_PROJECT`), and none whose card names
    languages that share none with the project's (the rules do not refuse a reader for its language, so a German reader
    was listed for Spanish pages). A card naming no language stays. The step's own card always stays."""
    from fichero_server.recipes.assemble import _refusal

    def fits(c: Any) -> bool:
        if (_refusal(job, c, a, material) or ("",))[0] in _OFF_PROJECT:
            return False
        return c.languages is None or not a.languages or bool(c.languages & a.languages)

    return [c for c in cards if c.id == chosen_id or fits(c)]


def _offered_order(card: Any) -> tuple[int, int, str]:
    """The person's cloud models top the list, likely the best readers (owner 2026-10-23), in their frontier family's
    expected order (`frontier_rank`), then by provider; then the rest."""
    from fichero_server.recipes.discovery import frontier_rank

    runs_on = str(card.runs_on)
    return (0, frontier_rank(card), runs_on.split(":", 1)[1]) if runs_on.startswith("cloud:") else (1, 0, "")


# =============================================================================
# A project's saved setup (#4951): the answers and the recipe, as files in the project folder.
# =============================================================================


class ProjectSetup(BaseModel):
    """Setup's answers and the project's recipe; each null when the project has none
    (`source.project.has-settings`). Saving is not Start: nothing runs."""

    model_config = ConfigDict(extra="forbid")
    answers: Optional[dict[str, Any]] = Field(default=None, description="Setup's answers (purposes, languages, scripts, materials, directions as {script: direction}); null clears them.")
    recipe: Optional[dict[str, Any]] = Field(default=None, description="The project's recipe, as POST /api/recipes/assemble returns it; null clears it.")


class RedoStep(BaseModel):
    steps: list[str] = Field(description="the step ids, Start's `redo` for this run")
    name: str = Field(description="the run's name, as the menu shows it")


class ProjectSetupView(ProjectSetup):
    """`GET /api/recipes/project`'s answer: the setup and, beside the answers, what the project inherits."""

    cloud_inherited: bool = Field(default=False, description=(
        "True when the project has not answered the cloud question and the app allows a cloud AI service, so pages may go there "
        "by inheritance; never in `answers` and never saved (`source.onboard.new-project-inherits-the-cloud-setting`)"))
    redo_steps: list[RedoStep] = Field(default_factory=list, description=(
        "after the first yes, the recipe's steps a folder can run again, each as Start takes it back in `redo`, with its "
        "name; read with the setup, so the folder menu needs no Start plan (`source.recipe.step-rerun-on-folder`, #6170)"))


def _library(db: Database) -> Path:
    return Path(db.path).parent


class PlacesSetting(BaseModel):
    """Where models may run, app-wide (`source.onboard.first-launch-three-screens`, #5828)."""
    places: list[str] = Field(description="The allowed places, from this-mac, another-mac, cloud, acenet, huggingface; "
                                          "this Mac is always one.")


class PlacesView(PlacesSetting):
    answered: bool = Field(description="False until the person answers in Set Up Fichero; while false, no cap applies, "
                                       "and places shows this Mac only.")
    memory_gb: float = Field(description="This Mac's memory, worked out by the engine.")
    this_mac: str = Field(description="What this Mac can run, in a sentence, from its real memory.")


def _places_view() -> PlacesView:
    gb = _this_machine_memory_gb()
    said = places.get_places()
    return PlacesView(places=said or list(places.DEFAULT), answered=said is not None, memory_gb=round(gb, 1),
                      this_mac=places.this_mac_line(gb))


@router.get("/places", response_model=PlacesView)
async def get_places() -> PlacesView:
    """Where models may run, and this Mac's line (its memory and what it can run)."""
    return _places_view()


@router.put("/places", response_model=PlacesView, responses={422: {"model": _ErrorDetail,
            "description": "A place Fichero does not know."}})
async def put_places(body: PlacesSetting, request: Request) -> PlacesView:
    """Allow these places, with no project open (the setting is the app's, so is its audit row). Every project is
    capped by them: stricter, never looser. Owner only: it decides where every project's pages may go."""
    _require_owner_or_bootstrap(request)
    unknown = [p for p in body.places if p not in places.PLACES]
    if unknown:
        raise HTTPException(status_code=422, detail=f"Fichero does not know the place {unknown[0]!r}.")
    before = places.get_places() or list(places.DEFAULT)
    kept = list(places.normalise(body.places))
    from fichero_server.api.routes.auth.accounts import _current_session_user
    from fichero_server.db.app import get_app_db
    from fichero_server.models import ActionAudit

    # The chain's actor format, as accounts writes it: "bootstrap", or "user:<id>".
    user = _current_session_user(request)
    actor = "bootstrap" if getattr(request.state, "bootstrap_auth", False) else f"user:{user.id}" if user else "system"
    app_db = get_app_db()
    # Audited first: if the audit cannot be written the setting is not changed.
    app_db.save_chained_account_audit(ActionAudit(
        action_name="recipes.set_places", actor=actor,
        target_ids=[], params=body.model_dump(), before={"places": before}, after={"places": kept}))
    places.set_places(kept)
    return _places_view()


def _whole_setup(setup: dict) -> ProjectSetup:
    """A project's setup as every route returns it. A recipe stored from the rules alone has no check result, and the
    contract's AssembledRecipe requires `gaps` and `problems`: without them the app cannot read the setup back, nor the
    recipe a change like Use This hands it (it then kept its stale copy and saved that over the choice)."""
    recipe = setup.get("recipe")
    if isinstance(recipe, dict) and "problems" not in recipe:
        recipe = {**recipe, "gaps": recipe.get("gaps") or []}
        recipe["problems"] = [] if recipe["gaps"] else check_recipe(recipe)
        setup = {**setup, "recipe": recipe}
    return ProjectSetup(**{k: v for k, v in setup.items() if k != "cloud_inherited"})


@router.get("/project", response_model=ProjectSetupView)
async def get_project_setup(db: Database = Depends(get_library_database)) -> ProjectSetupView:
    """The open project's saved setup answers and recipe, and whether it inherits the app's cloud setting."""
    return await asyncio.to_thread(_project_setup_view, db)  # off the loop (#6178): the redo steps are a Start plan


def _project_setup_view(db: Database) -> ProjectSetupView:
    from fichero_server.recipes.project import read_start
    from fichero_server.recipes.start import plan_start

    library = _library(db)
    setup = read_project_setup(library)
    redo = []
    if read_start(library) and setup["recipe"]:  # the started recipe's workflow runs, planned without the pages (cheap)
        planned = plan_start(setup["recipe"], stays_local=not places.may_leave_to(setup["answers"], "cloud"))
        redo = [RedoStep(steps=w["steps"], name=w.get("workflow") or ", ".join(w["steps"])) for w in planned["workflows"]]
    return ProjectSetupView(**_whole_setup(setup).model_dump(), cloud_inherited=bool(setup.get("cloud_inherited")),
                            redo_steps=redo)


class ReviewInstruction(BaseModel):
    lens: str = Field(description="the pass's lens: abbreviations, orthography or names-and-dates")
    default: str = Field(description="the instructions built from the project's language, script and date")
    text: str = Field(description="what the pass is sent: the project's edit, else the default")
    edited: bool = Field(description="whether the project edited this pass's instructions")
    profile: str = Field(description="the sentence saying which profile the default was built from")


class ReviewInstructions(BaseModel):
    passes: list[ReviewInstruction]


@router.get("/project/review-instructions", response_model=ReviewInstructions)
async def get_review_instructions(db: Database = Depends(get_library_database)) -> ReviewInstructions:
    """Each review pass's instructions, the default built from the project's setup and the project's edit if it has one
    (`source.job.review-instructions-are-editable`, #6128). Saved as `job_answers.review_instructions`."""
    from fichero_server.recipes.review_profiles import lens_ids, review_prompt

    answers = read_project_setup(_library(db))["answers"]
    edits = ((answers or {}).get("job_answers") or {}).get("review_instructions") or {}
    out = []
    for lens in lens_ids():
        default, said = review_prompt(lens, answers)
        edited = bool((edits.get(lens) or "").strip())
        out.append(ReviewInstruction(lens=lens, default=default, text=edits[lens] if edited else default,
                                     edited=edited, profile=said))
    return ReviewInstructions(passes=out)


@router.put("/project", response_model=ProjectSetup)
async def save_project_setup(
    request: ProjectSetup,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> ProjectSetup:
    """Save the project's setup answers and recipe (audited, undoable). Only the parts sent change:
    a part left out (`answers` or `recipe`) is kept as it was, and a part sent as null is removed,
    except a recipe the project already has saved, which a null recipe never clears (a client whose assemble failed has no
    recipe in hand and must not wipe the saved one and the person's step choices; the kept recipe is logged)
    (`source.project.setup-saves-what-is-sent`). The answers are saved in today's shape: `purposes`
    and `materials` as lists, languages as tags and scripts as codes (a word is resolved to its tag,
    or refused), and one direction per script. Refused with 422 when either holds code or
    credentials, or an answer Fichero does not know. Answers saved alone to a project with no recipe yet
    also store the recipe the rules assemble from them (#5747); a recipe already stored is kept."""
    try:
        params = request.model_dump(mode="json", exclude_unset=True)
        if "recipe" in params and params["recipe"] is None and read_project_setup(_library(db)).get("recipe"):
            # The backstop for every client (Set Up and first-run Continue after a failed assemble have no recipe in hand):
            # a null never wipes a saved recipe and the person's step choices in it (## 923, ## 924).
            logger.warning("project setup saved with recipe: null; keeping the project's saved recipe")
            del params["recipe"]
        if "answers" in params:
            params["answers"] = normalise_answers(params["answers"], strict=True)
            if params["answers"] and "recipe" not in params:
                # Answers alone to a project with no recipe yet: Start needs one, so the rules assemble it (#5747).
                # A recipe already stored is kept: the person's own choices of model stay.
                library = _library(db)
                if read_project_setup(library).get("recipe") is None:
                    params["recipe"] = await asyncio.to_thread(_assemble, params["answers"], library)
        if params.get("recipe"):
            # A Use This made since the app loaded this recipe is kept, an override a PUT adds is dropped (an undo goes through the action)
            from fichero_server.recipes import bakeoff

            from fichero_server.recipes.recipe import fit_overrides

            from fichero_server.recipes.recipe import PAGE_STEP

            stored = read_project_setup(_library(db)).get("recipe")
            kept = bakeoff.keep_saved_overrides(stored, params["recipe"])
            had = {s.get("id") for s in (stored or {}).get("steps") or [] if s.get("job") == PAGE_STEP}
            unticked = had - {s.get("id") for s in kept.get("steps") or []}
            if unticked:  # the person un-ticked Read the whole page: its reader goes with it, never adds it back (2026-10-24)
                kept["overrides"] = [o for o in kept["overrides"] if o.get("step") not in unticked]
                logger.info("Read the whole page was un-ticked; its page reader's choice went with it")
            fit_overrides(kept)  # a saved choice for a step the sent recipe lacks: the page step added, any other dropped (#6259)
            bakeoff.apply_project_overrides(kept, list(known_cards(include_not_built=True)))
        result = registry.invoke(db, "project.save_setup", params, ctx)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _search_when_known(db, (result.result or {}).get("answers"))
    return _whole_setup(result.result)


def _search_when_known(db: Database, answers: Optional[dict]) -> None:
    """The model search starts by itself once Set Up knows the script and the language (`source.onboard.search-triggered`):
    the person presses nothing. Only the reader search by languages (the step searches wait for their page); it is the
    project's own Activity job, never run offline, and it never fails the save."""
    from fichero_server.recipes import discovery

    languages = frozenset((answers or {}).get("languages") or ())
    if not languages or not (answers or {}).get("scripts") or not discovery.egress_allowed():
        return
    try:
        discovery.search(db, languages, by_itself=True)
        discovery.SEARCH_FAILURES.pop(discovery._languages_key(languages), None)  # queued: an old failure is stale
    except Exception as exc:  # noqa: BLE001 -- a search that cannot be queued never fails the save; the finder says so
        discovery.SEARCH_FAILURES[discovery._languages_key(languages)] = f"{type(exc).__name__}: {exc}"
        logger.warning("the automatic model search could not be queued", exc_info=True)


def _setup_to_restore(before: dict | None) -> dict:
    """The setup an undo puts back. The before-state came from read_project_setup, which reports the response-only
    cloud_inherited beside the answers (## 1101); ProjectSetup forbids it, so the replay drops it, for audit rows
    already saved with it too."""
    return {k: v for k, v in (before or {}).items() if k != "cloud_inherited"} or {"answers": None, "recipe": None}


def _invert_save_setup(before: dict | None, after: dict | None, ctx: ActionContext):
    return ("project.save_setup", _setup_to_restore(before))


@action("project.save_setup", ProjectSetup, domains=["project"], undoable=True,
        invert=_invert_save_setup)
def _action_save_setup(db: Database, params: ProjectSetup, ctx: ActionContext) -> tuple[dict, ChangeSpec]:
    library = _library(db)
    before = read_project_setup(library)
    # A part left out is kept; a part sent as null is removed (#5584).
    sent = params.model_fields_set
    recipe = params.recipe if "recipe" in sent else before.get("recipe")
    if recipe and before.get("recipe"):
        from fichero_server.recipes.bakeoff import drop_readers_of_changed_models

        recipe = drop_readers_of_changed_models(before["recipe"], recipe)
    write_project_setup(library, params.answers if "answers" in sent else before.get("answers"), recipe)
    after = read_project_setup(library)
    return after, ChangeSpec(domains=["project"], target_ids=[], before=before, after=after,
                             emit_type="project.setup_saved")


class CloudCapChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cap_usd: Optional[float] = Field(default=None, ge=0, description=(
        "the most the project's cloud calls may cost a month, in US$ (0 is a cap); left out: unchanged"))
    project_cap_usd: Optional[float] = Field(default=None, ge=0, description=(
        "the most the project may spend on cloud calls in all, across months (`answers.cloud_project_cap_usd`); "
        "left out: unchanged"))
    clear_project_cap: bool = Field(default=False, description="remove the project's total cap (no such limit)")

    @model_validator(mode="after")
    def _says_something(self) -> "CloudCapChange":
        if self.cap_usd is None and self.project_cap_usd is None and not self.clear_project_cap:
            raise ValueError("send the monthly cap, the project cap, or clear_project_cap")
        if self.project_cap_usd is not None and self.clear_project_cap:
            raise ValueError("a project cap is set or cleared, not both")
        return self


class CloudCapChanged(BaseModel):
    cap_usd: float = Field(description="the project's monthly cloud cap now")
    project_cap_usd: Optional[float] = Field(default=None, description="the project's total cloud cap now; null: none")
    audit_id: str = Field(description="the audit row of the change; Undo reverses it")


@router.put("/project/cloud-cap", response_model=CloudCapChanged, responses={422: {"model": _ErrorDetail,
                    "description": "the cap is refused, in one sentence"}})
async def change_cloud_cap(
    request: CloudCapChange,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> CloudCapChanged:
    """Set the project's monthly cloud cap (`answers.cloud_spend_cap_usd`) and/or its total cap
    (`answers.cloud_project_cap_usd`), and nothing else in its setup: Set Up's "Raise the cap to N" (#6295). One
    `project.save_setup`, so audited and undoable as one step; the answer names the audit row."""
    from fichero_server.llm import spend

    answers = dict(read_project_setup(_library(db)).get("answers") or {})
    if request.cap_usd is not None:
        answers[spend.CAP_KEY] = request.cap_usd
    if request.project_cap_usd is not None:
        answers[spend.PROJECT_CAP_KEY] = request.project_cap_usd
    if request.clear_project_cap:
        answers.pop(spend.PROJECT_CAP_KEY, None)
    try:
        done = registry.invoke(db, "project.save_setup", {"answers": normalise_answers(answers, strict=True)}, ctx)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return CloudCapChanged(cap_usd=spend.cap_usd(str(_library(db))) or 0.0, project_cap_usd=spend.project_cap_usd(str(_library(db))),
                           audit_id=done.audit_id)


class AllowCloudResult(BaseModel):
    project: str = Field(description="the project (its library folder's name) whose pages may now go to a cloud model")
    cloud_allowed: bool


@router.post("/project/allow-cloud", response_model=AllowCloudResult)
async def allow_cloud(
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> AllowCloudResult:
    """The one click on a refused cloud call (`ai.where.one-egress-gate`, #5368): say yes, for this project, to cloud
    models. An audited action (who, when, which project), undoable, and reversible in Set Up (the same `cloud_allowed`
    answer). Nothing else in the project's setup changes."""
    result = registry.invoke(db, "project.allow_cloud", {}, ctx)
    return AllowCloudResult(**result.result)


class AllowCloudParams(BaseModel):
    restore: Optional[dict] = Field(default=None, description="an undo restores the setup as it was")


def _invert_allow_cloud(before: dict | None, after: dict | None, ctx: ActionContext):
    return ("project.save_setup", _setup_to_restore(before))


@action("project.allow_cloud", AllowCloudParams, domains=["project"], undoable=True, invert=_invert_allow_cloud)
def _action_allow_cloud(db: Database, params: AllowCloudParams, ctx: ActionContext) -> tuple[dict, ChangeSpec]:
    library = _library(db)
    before = read_project_setup(library)
    answers = dict(before.get("answers") or {})
    answers["cloud_allowed"] = True
    write_project_setup(library, answers, before.get("recipe"))
    after = read_project_setup(library)
    return ({"project": library.stem, "cloud_allowed": True},
            ChangeSpec(domains=["project"], target_ids=[], before=before, after=after, emit_type="project.setup_saved"))


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


class StartLensCost(BaseModel):
    lens: str
    on: bool
    cost_per_page_usd: Optional[float] = Field(description="one call a page: 0 on this Mac; null when unpriced")


class StartEstimateRun(BaseModel):
    workflow: str
    steps: list[str]
    where: str
    pages: int
    cost_usd: Optional[float] = Field(description="0 on this Mac; null when the model has no price")
    basis: str = Field(default="unpriced", description=(
        "how cost_usd is known: `free on this Mac`, `the model's listed rate`, `the batch price, answered within a "
        "day` (a step sent as one provider batch, #5940), or `unpriced` (a cluster or other "
        "place, or a model with no price): never a $0 for what is not known (#5590)"))
    memory: Optional[str] = Field(default=None, description=(
        "a run on this Mac's model server: the model's memory need, how many pages at once it reads on this Mac, "
        "and the peak that comes to (#5537); null for any other run"))
    calls_per_page: Optional[int] = Field(default=1, description=(
        "model calls each page takes: the review makes one for each pass it runs, one a lens on (#5723); any other "
        "run, one; null when a review's passes cannot be counted, and then `cost_usd` is null too, never $0"))
    certainty_bar: Optional[float] = Field(default=None, description=(
        "Kraken, then a model for the unsure lines (`source.recipe.kraken-then-cloud-unsure-lines`): the bar X, below "
        "which Kraken's lines go to the model; null for any other run"))
    lines_to_send: Optional[int] = Field(default=None, description=(
        "with a bar: how many lines the model will be sent, the figure `cost_usd` is priced from; null for any other run"))
    lines_to_send_kind: Optional[str] = Field(default=None, description=(
        "how known `lines_to_send` is: `exact` (every page has its lines and each line its certainty), `at-most` (every "
        "page has its lines; how many are under the bar is not yet known) or `estimate` (some pages have no lines yet: "
        "an assumed number a page)"))
    lines_basis: Optional[str] = Field(default=None, description="with a bar: that figure in words, assumption included")
    lenses: list[StartLensCost] = Field(default_factory=list, description=(
        "the review's lenses, on or off, each with what it costs a page, so turning one on or off is priced before "
        "Start (#5723); empty for any other run"))


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
    folder_id: Optional[str] = Field(default=None, description=(
        "the folder that Start ran on; null: the whole project (source.recipe.folder-scoped-start)"))


class StartReader(BaseModel):
    """The shipped workflow and model that read one kind of page (#5578)."""

    workflow: str
    workflow_id: str
    provider_override: Optional[str] = None
    model_override: Optional[str] = None


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
    how: Optional[str] = Field(default=None, description=(
        "how the step works, in the engine's words, for a step that runs no model (Work out dates); the app shows "
        "it as given (`source.onboard.setup-says-what-is-happening`, #5791)"))
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
    readers: Optional[dict[str, StartReader]] = Field(default=None, description=(
        "a reading card's reader per kind of page (handwriting, print, typescript; #5578): a page sorted as that "
        "kind is read by it, any other page by this card's own model"))


class StartInstead(BaseModel):
    """An installed model the plan offers instead of a download (#5583)."""

    card: str = Field(description="its card id, to send to use-instead")
    model: str = Field(description="its id in this Mac's model store")
    name: str = Field(description="its name, as people read it")
    licence: str = Field("", description="its licence when it is not open (choosing it accepts that); empty when open")


class StartPlaceInstead(BaseModel):
    """The same model at another place that costs nothing, offered for a model this Mac cannot run (#5592)."""

    provider: str = Field(description="the place's provider row id, to send to use-instead")
    provider_name: str = Field(description="the place's name, as people read it")
    provider_type: str = Field(description="the place's provider type")
    place: str = Field(description="where the place keeps the pages: own_machine or provider (llm/places.py)")
    model: str = Field(description="the model's id at the place")
    name: str = Field(description="its name, as people read it")
    free: bool = Field(description="always True: only a free place is offered, the person's own machine or one the "
                       "price list says costs nothing (ai.where.fallback-free-and-asked)")


class StartElsewhere(BaseModel):
    """A model a step is pinned to that this Mac cannot run, and the free places offered instead (#5592)."""

    runtime: str
    model: str
    name: str
    steps: list[str]
    why: str = Field(description="why this Mac cannot run it")
    said: str = Field(description="what its refusal adds: the free place offered, or why none is")
    instead: list[StartPlaceInstead] = Field(default_factory=list, description=(
        "the same model at places that cost nothing, each used only when the person presses it "
        "(POST /api/recipes/project/start/use-instead with `provider`); a paid place is never offered"))


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
    downloading: bool = Field(default=False, description=(
        "a download-model job is already fetching it: Start is not refused for it, and its steps wait for it to "
        "land (#5660)"))
    progress: Optional[str] = Field(default=None, description="how far the download has got, as its job last said it")
    job_id: Optional[str] = Field(default=None, description="the download-model job fetching it, while downloading")
    sentence: Optional[str] = Field(default=None, description=(
        "the download in words: 'Downloading X: 1.2 GB of 5.6 GB; its steps wait for it.', or 'X is not on this Mac "
        "yet (60 MB): Start downloads it, and its steps wait for it.'; shown as given (#5791)"))


class StartDownloadItem(BaseModel):
    name: str = Field(description="the model as people read it")
    size_mb: Optional[int] = Field(default=None, description="its download size; null when not stated")
    steps: list[str]


class StartDownloads(BaseModel):
    """What pressing Start will fetch before its steps run (#5664), for Ready's one line."""

    items: list[StartDownloadItem]
    total_mb: int
    total_known: bool = Field(description="false when a size is not stated: the total is then a lower bound")
    sentence: str = Field(description="e.g. 'Start downloads Qwen2.5-VL 7B (5.7 GB) and the Kraken reader PP-OCRv6 "
                          "(60 MB): 5.8 GB in all.'")


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


class TrainTarget(BaseModel):
    """A place a way of training runs, and the audited action that starts it there (#5660 item 9)."""

    place: str = Field(description=(
        "this-mac, huggingface-jobs, or cluster (a cluster set up here, the free alternative offered beside Hugging "
        "Face; no start action yet)"))
    name: str
    starts: Optional[str] = Field(default=None, description=(
        "the action that starts it, e.g. training.start_here; null for a cluster, offered with its first-run steps"))
    params: Optional[dict[str, Any]] = Field(default=None, description=(
        "what to send with `starts`, as-is (the scope and, for a distillation, the teacher); null: the engine cannot "
        "fill it yet, e.g. no reader has read this project's lines. On Hugging Face Jobs the person's yes for "
        "pages to leave (`pages_may_leave`) is asked at start, never sent here"))
    held: Optional[str] = Field(default=None, description=(
        "why this place stays an offer, never started by itself: a $0 Hugging Face spend cap (#5769)"))
    first_run: Optional[list[str]] = Field(default=None, description=(
        "a cluster's attended first run, step by step (`source.onboard.cluster-offer`, #5769)"))


class TrainWay(BaseModel):
    """One way to train for a step: a fine-tune or a distillation, and where it can run."""

    method: str = Field(description="kraken, mlx-vision-lora, yolo or spacy-ner")
    how: str = Field(description="fine-tune or distil")
    says: str
    targets: list[TrainTarget]
    available: bool = Field(description="false: not available yet (no trainer, or nowhere this project allows)")
    why: Optional[str] = Field(default=None, description="why it is not available, in words")


class TrainAhead(BaseModel):
    """One sentence on a trainable step that is not ready: how many corrected lines training needs (`source.onboard.train-path`)."""

    step: str
    job: str
    sentence: str


class TrainOffer(BaseModel):
    """'Train a model of your own for this step' for one trainable step, offered later, never run at Start."""

    step: str
    job: str
    title: str
    ways: list[TrainWay]
    readiness: dict[str, Any] = Field(description=(
        "whether the project has enough corrected material: counts, how many more lines and pages, and the "
        "sentence that says so (the bake-off's one count, at the train step's threshold)"))
    setting: dict[str, str] = Field(description=(
        "how training happens in this project (the onboarding setting `answers.training`, or the machine's default): "
        "`mode` here, huggingface or offered, and `why`"))
    does: str = Field(description="what the setting does once the corrected lines reach the threshold, in a sentence")
    noise_band: Optional[dict[str, Any]] = Field(default=None, description=(
        "the project's noise band (#5692): `value`, the CER difference a trained model must beat its base by; "
        "`measured`, whether this project's pages measured it (CER spread over 3 held-out splits) or it is the ruled "
        "0.5 CER points; `basis` in words"))


class BakeoffOffer(BaseModel):
    """The bake-off offered on the Start plan: its cost said first, then whether the project can run it now."""

    sentence: str = Field(description="what the comparison costs, first")
    run_cost_usd: float
    pages: int = Field(description="the corrected sample pages it would read")
    ready: bool = Field(description="false until the project holds enough corrected lines")
    readiness_sentence: Optional[str] = Field(default=None, description="when not ready, what to correct")


class HfSpend(BaseModel):
    """This month's Hugging Face spend against the project's cap (`source.onboard.spend-cap`, #5769)."""

    cap_usd: float = Field(description="the project's monthly cap (`answers.hf_spend_cap_usd`); $0 offers only")
    spent_at_most_usd: float = Field(description=(
        "this calendar month's Jobs at their most: each one's hardware price an hour times its time limit"))
    jobs: int = Field(description="the Jobs sent to Hugging Face this month (training and reading at scale)")
    unpriced: int = Field(description="of them, the Jobs with no listed price: not counted in the spend, said so")
    month: str = Field(description="the month, YYYY-MM (UTC)")
    sentence: str


class CloudCapLine(BaseModel):
    """The project's cloud spend cap against this run's estimate (`ai.where.cloud-spend-cap`, #5943, #5987)."""

    cap_usd: float = Field(description="the project's cloud spending cap for a month (`answers.cloud_spend_cap_usd`), US$10 unless set")
    spent_usd: float = Field(description="what its cloud calls have cost this (UTC) month, assumed prices included")
    remaining_usd: float = Field(description="what the cap leaves this month")
    estimate_usd: Optional[float] = Field(default=None, description="this run's estimated cloud cost; null when a model has no listed price")
    over: bool = Field(description="the estimate is more than the cap leaves: Start asks first")
    over_month: bool = Field(default=False, description="the estimate is more than the monthly cap leaves")
    over_project: bool = Field(default=False, description="the estimate is more than the project's total cap leaves")
    needed_cap_usd: Optional[float] = Field(default=None, description=(
        "when `over_month`: the monthly cap under which this run's estimate fits (what is booked this month plus the estimate, "
        "to the cent, no margin); Set Up offers it as \"Raise the cap to N\" (#6295); null otherwise"))
    project_cap_usd: Optional[float] = Field(default=None, description=(
        "the most the project may spend on cloud calls in all (`answers.cloud_project_cap_usd`); null: no such limit"))
    project_spent_usd: float = Field(default=0.0, description="what its cloud calls have cost in all, across months")
    project_remaining_usd: Optional[float] = Field(default=None, description=(
        "what the project's total cap leaves, `project_cap_usd` less `project_spent_usd`, not below 0; null: no total cap"))
    refusal: Optional[str] = Field(default=None, description=(
        "when `over`: the sentence this cap adds to the plan's `refusals`, exactly, so a client can tell which refusal is the cap's "
        "without reading its words; null otherwise"))
    needed_project_cap_usd: Optional[float] = Field(default=None, description=(
        "when `over_project`: the project cap under which this run's estimate fits (spent in all plus the estimate, to the cent)"))
    pages: int = Field(default=0, description="the pages the estimate is for")
    fewer_pages: Optional[int] = Field(default=None, description=(
        "when `over`: how many of the project's first pages, in Finder order, fit what the caps leave at this run's per-page "
        "estimate; null when none fit or the run is not over"))
    unpriced_models: list[str] = Field(default_factory=list, description=(
        "`provider/model` of cloud models in this plan with no listed price that the project has not accepted: listed apart, "
        "counted at an assumed price per call; pressing Start accepts them (`cloud.accept_unpriced`), never a refusal (#6259)"))
    note: Optional[str] = Field(default=None, description=(
        "one sentence naming the unpriced models and the assumed price per call they are counted at; null when there are none"))
    unpriced: bool = Field(description="the estimate is unknown (a cloud model with no listed price): asked about, never $0")
    assumed_calls: int = Field(default=0, description="calls this month booked at the assumed price of a model with no listed price")
    assumed_usd: float = Field(default=0.0, description="what those calls were booked at: counted against the cap, listed apart")


class BuiltInStep(BaseModel):
    """A step that is built in: it runs nothing and needs nothing (#5816)."""

    step: str
    sentence: str = Field(description="why it runs nothing, in the engine's words: it is part of the plan, not a problem")


class StepNeed(BaseModel):
    """What a step candidate needs before it can run, in words, with the kind an app can act on."""

    kind: Literal["permission", "key", "download", "price"] = Field(description=(
        "permission: pages may not leave this Mac yet; key: the provider has no key; download: the model is not on this Mac; "
        "price: a cloud model with no listed price (accepted at Start)"))
    words: str


class StepCandidate(BaseModel):
    """One way to do a step, as the plan lists it (`source.onboard.step-candidates-on-the-plan`): the Try's shapes, reused."""

    card: str = Field(description="the card id, as POST /api/recipes/project/steps/use-candidate takes it")
    name: str
    how: Literal["kraken", "kraken-then-cloud-corrects", "cloud-reads-kraken-lines", "local-model", "cloud-model"]
    runs_on: str = Field(description="this-mac, cluster or cloud:<provider>")
    local: bool
    picked: bool = Field(description="the one the step uses now, Set Up's pick or the person's choice")
    recommended: bool = Field(description="the one Set Up picks by the rules")
    available: bool = Field(description="false while `needs` is not empty; listed greyed, never hidden")
    needs: list[StepNeed] = Field(default_factory=list)
    places: list[PlaceOption] = Field(default_factory=list, description="every place it can run, as the finder lists them")
    cost_usd: Optional[TryCost] = Field(default=None, description="its cost for the whole set before Start; null until priced")
    measured: str = Field(description="what is measured on this project's pages, or that it is not yet")


class StepTurnOn(BaseModel):
    """How to bring a step into the plan: Set Up's own answer, nothing new to send (PUT /api/recipes/project with the answer)."""

    answer: str = Field(description="the job answer to set")
    value: Any
    words: str


class StepChoice(BaseModel):
    """A step of the plan that has a choice of model."""

    step: str = Field(description="the recipe step's id")
    job: str
    name: str = Field(description="the stage in words")
    picked: Optional[str] = Field(default=None, description="the card the step uses now")
    chosen_by: Literal["setup", "person"] = Field(description=(
        "setup: Set Up's pick stands; person: they chose another (POST .../steps/use-setup-pick takes it back)"))
    in_plan: bool = Field(default=True, description=(
        "false for a step the recipe does not have yet but that is listed so it can be found: Correct beside a Kraken reader; "
        "`turn_on` says how to bring it in"))
    wording: Optional[str] = Field(default=None, description="the sentence to show for the step when it is not a plain model choice")
    certainty_bar: Optional[float] = Field(default=None, description=(
        "Correct beside a Kraken reader: Set Up's certainty-bar answer, the lines under it are the ones corrected; null: no bar chosen"))
    turn_on: Optional[StepTurnOn] = None
    candidates: list[StepCandidate]


class StartPlan(BaseModel):
    """What pressing Start would run, on how many pages, and every reason it cannot yet."""

    started: Optional[StartRecord] = Field(default=None, description="the first yes, once given")
    runs: list[StartRun] = Field(description="what Start runs, in order")
    workflows: list[StartWorkflow]
    skipped: list[SkippedStep] = Field(description="steps Start skips, each with why; the others still run")
    built_in: list[BuiltInStep] = Field(default_factory=list, description=(
        "steps that run nothing on purpose, each with the engine's sentence: shown as built in, never as a problem "
        "(#5816)"))
    offered: list[str] = Field(description="steps offered later (training), never run at Start")
    left_off: list[str] = Field(default_factory=list, description=(
        "steps the recipe left off until turned on, one line each with what turning it on would cost (#5677)"))
    train_offers: list[TrainOffer] = Field(default_factory=list, description=(
        "for each step a model can be trained for, how to train it on the corrected pages and where; offered "
        "later, never run at Start (#5660 item 9)"))
    train_ahead: list[TrainAhead] = Field(default_factory=list, description=(
        "for each trainable step not ready yet, one sentence saying how many corrected lines training a model of "
        "your own will need and how many the project has; not an offer (`source.onboard.train-path`)"))
    hf_spend: Optional[HfSpend] = Field(default=None, description=(
        "this month's Hugging Face spend against the project's cap (#5769); null for a plan with no project setup"))
    cloud_cap: Optional[CloudCapLine] = Field(default=None, description=(
        "the project's cloud spending cap against this run's estimate (#5987); Start is refused while the estimate is over it"))
    bakeoff_offer: Optional[BakeoffOffer] = Field(default=None, description=(
        "a comparison of readers on the sample, offered with its cost first and never run by Start; null when the "
        "recipe has no reading step (#5660 item 7)"))
    step_choices: list[StepChoice] = Field(default_factory=list, description=(
        "for each step that has a choice of model, its candidates (local and cloud, with what each needs and costs) and "
        "which one is used: the step menu's data; choosing is POST /api/recipes/project/steps/use-candidate, taking it "
        "back POST /api/recipes/project/steps/use-setup-pick (`source.onboard.step-candidates-on-the-plan`)"))
    refusals: list[str] = Field(description="Start is refused while this is not empty")
    notes: list[str] = Field(default_factory=list, description=(
        "what Start changed in the saved recipe to fit the person's kept choices, one sentence each: a page reader adds the "
        "Read the whole page step, a choice for a step the recipe no longer has is dropped; never a refusal (#6259)"))
    waiting: list[str] = Field(default_factory=list, description=(
        "steps that wait for a model already downloading, in words; Start is not refused for them, and they run "
        "when it lands (#5660)"))
    downloads: list[StartDownload] = Field(default_factory=list, description=(
        "models the steps are pinned to that are not on this Mac; Start downloads each itself and its steps wait "
        "for it (#5664)"))
    start_downloads: Optional[StartDownloads] = Field(default=None, description=(
        "what Start will fetch, by name and size, with the total and one sentence; null when nothing (#5664)"))
    elsewhere: list[StartElsewhere] = Field(default_factory=list, description=(
        "models the steps are pinned to that this Mac cannot run, each with the free places offered instead, "
        "never used without the person's press (ai.where.fallback-free-and-asked)"))
    fallbacks: list[dict[str, Any]] = Field(default_factory=list, description=(
        "steps that run the next candidate in their chain because the first cannot (a missing key), each saying which "
        "and why (`used` true), or offered and not used (`used` false) when it would send pages to another provider: "
        "never a silent substitute (`source.recipe.candidates-fallback-chain`)"))
    estimate: StartEstimate
    in_icloud: Optional[dict[str, Any]] = Field(default=None, description=(
        "pages whose linked originals are in iCloud and not on this Mac, with the offer to copy them into the project "
        "first (`offer`, the action `document.copy_into_project` and its `params`); null when none. Shaped as GET "
        "/api/documents/in-icloud answers (#5669)"))
    proposed: Optional[ProposedJobs] = Field(default=None, description=(
        "jobs proposed for the material already in the project by a layer added later; once the project has "
        "started, the plan is these alone (source.onboard.add-layer)"))
    addable: list[str] = Field(default_factory=list, description=(
        "layers this project can add now: the addable ones less those it has and those its purpose brings "
        "(source.onboard.add-layer)"))
    folder_id: Optional[str] = Field(default=None, description=(
        "the folder the plan and its estimate cover, its folders inside it included; null: the whole project "
        "(source.recipe.folder-scoped-start)"))


def _offered_cards(a: Optional[Answers]) -> list[Any]:
    """Every card a step's menu can list and `use-candidate` can take: the rules' cards, the text models the finder offers beyond
    them, the person's cloud vision readers and the keyed cloud correctors. ONE list, so a candidate the plan lists can be chosen."""
    from dataclasses import replace

    from fichero_server.recipes.discovery import other_text_cards, remote_reader_cards

    # a cloud vision reader corrects too (ponytail: assumed, as `_cloud_correctors` does), so a keyed reader with no listed price
    # stays on Correct's menu after Correct is turned on; the priced corrector of the same id comes first
    correctors = _cloud_correctors(a.cloud_keys if a else ())
    seen = {c.id for c in correctors}
    readers = [replace(c, jobs=c.jobs | {"correct"}) if c.jobs & {"read-a-line", "read-a-page"} else c
               for c in remote_reader_cards() if c.id not in seen]
    # A text model rewrites a reading too (#6089, #6090): every text model the finder knows, installed MLX, Apple Intelligence and the
    # person's cloud models alike, is a candidate for Correct and for Translate, not only the frontier providers' (their cards
    # already say so) and the seed's one Qwen. Offered, never chosen by the rules: these jobs are added only here, on the menu.
    text = (*known_cards(a), *(c for c in other_text_cards() if c.runs_here or str(c.runs_on).startswith("cloud:")))
    return [*(_also_rewrites(c) for c in text), *correctors, *readers]


def _also_rewrites(card: Any) -> Any:
    """A GENERATIVE text model (an MLX or served LLM, Apple Intelligence, a cloud chat model) also corrects and translates, for the
    step menus. Not spaCy, whose pipelines only tag names, nor the parser's statements: they are told apart by the job only a
    generative model does (`split-into-entries`) beside `find-statements`, which a model that writes text carries and the parser's
    subject-verb-object cards do not."""
    from dataclasses import replace

    if {"split-into-entries", "find-statements"} <= card.jobs and not card.jobs & {"read-a-line", "read-a-page"}:
        return replace(card, jobs=card.jobs | {"correct", "translate-transliterate-normalise"})
    return card


def _step_choices_of(setup: dict[str, Any], *, may_leave: bool, pages: Optional[int] = None,
                     clusters: list[str] | tuple[str, ...] = ()) -> list[dict[str, Any]]:
    """The plan's per-step candidates over every card the finder knows, local and cloud (`recipes/step_choices.py`). A project
    whose answers cannot be read has none (the plan says why elsewhere)."""
    from fichero_server.recipes.step_choices import step_choices

    if not setup["recipe"]:
        return []
    try:
        a = _answers(setup["answers"]) if setup["answers"] else None
    except ValueError:
        return []
    from fichero_server.recipes.discovery import remote_compute
    from fichero_server.recipes.train_offers import this_mac_memory_gb
    from fichero_server.recipes.where_it_runs import places_it_can_run

    mac_gb, hf_ready = this_mac_memory_gb(), bool(remote_compute(price=False)["available"])  # never the network
    return step_choices(setup["recipe"], setup["answers"], _offered_cards(a), may_leave=may_leave, pages=pages,
                        places_of=lambda c: places_it_can_run(c, this_mac_gb=mac_gb, hf_ready=hf_ready, clusters=clusters))


def _catalogue_runs(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The plan's Catalogue runs, priced by `estimate` (one call a folder, before Start)."""
    return [r for r in runs if r.get("card") == "catalogue"]


def _folders_covering(db: Database, page_ids: list[str]) -> int:
    """How many folders a Catalogue run over these pages describes (each folder above them, once; those already described are not priced)."""
    from fichero_server.recipes.catalogue_step import folders_to_describe

    return len(folders_to_describe(db, page_ids)[0]) if page_ids else 0


def _reader_notes(runs: list[dict[str, Any]]) -> list[str]:
    """Where a step's per-kind readers differ from the step's own model, said in words: no refusal, no silent switch (#6269)."""
    out = []
    for run in runs:
        for kind, reader in (run.get("readers") or {}).items():
            if reader.get("model_override") != run.get("model_override"):
                out.append(f"{kind} pages are read by {reader.get('note') or reader.get('model_override')}, not the step's "
                           f"{run.get('model_override') or 'default model'} ({', '.join(run.get('steps') or [])})")
    return out


def _only_if_set(**named: Any) -> dict[str, Any]:
    """The keyword arguments that were given: `_start_plan` is called with `first_pages` only for a first-pages run."""
    return {key: value for key, value in named.items() if value is not None}


def _estimate_on(db: Database, plan: dict[str, Any], pages: dict[str, Any], within: set[str] | None, memo: dict) -> dict[str, Any]:
    """The plan's estimate over `pages` (`done.material` of `within`): each run priced on the pages it has still to do, the
    review passes on their lines, the Catalogue step on its folders. The one pricing Start's plan and "run fewer pages" share."""
    from fichero_server.recipes.done import todo_counts
    from fichero_server.recipes.start import estimate

    return estimate(plan["workflows"], pages["pages"], _lines_known(db, plan["workflows"], pages["ids"]),
                    catalogue=_catalogue_runs(plan["runs"]), folders=_folders_covering(db, pages["ids"]),
                    todo=todo_counts(db, plan, within, memo=memo))


def _first_pages_that_fit(db: Database, plan: dict[str, Any], line: dict[str, Any], pages: int) -> Optional[int]:
    """The most first pages (Finder order) whose own estimate, priced as the plan prices it (only what each step has still to
    do, review passes by their lines), fits what the caps leave; None when not even one page does. Found by halving, since the
    price only grows with the pages; the price is the plan's best estimate, no margin (#6295)."""
    from fichero_server.recipes.done import material

    left = [line["remaining_usd"]]
    if line["project_remaining_usd"] is not None:
        left.append(line["project_remaining_usd"])
    room = min(left)
    first = _first_pages(db, pages)

    def fits(count: int) -> bool:
        within = set(first[:count])
        cost = _estimate_on(db, plan, material(db, within), within, {})["total_cost_usd"]
        return cost is not None and cost <= room + 1e-9

    low, high = 0, len(first) - 1  # `low` fits (no page costs nothing); the whole run does not
    while low < high:
        middle = (low + high + 1) // 2
        low, high = (middle, high) if fits(middle) else (low, middle - 1)
    return low or None


def _first_pages(db: Database, count: int) -> list[str]:
    """The first `count` pages of the project in Finder order (the order a run reads them in, #5849): what "run fewer pages"
    runs (#6295)."""
    from fichero_server.recipes.done import pages_for

    return pages_for(db, {}, None)[:count]


def _start_plan(db: Database, folder_id: Optional[str] = None, *, clusters: list[str] | tuple[str, ...] = (),
                first_pages: Optional[int] = None) -> dict[str, Any]:
    """The Start plan, over the whole project or one folder's live pages (`source.recipe.folder-scoped-start`).
    LookupError for a folder not in the project."""
    from fichero_server.recipes import runner
    from fichero_server.recipes.done import annotate, material
    from fichero_server.recipes.layers import addable_now, explain
    from fichero_server.recipes.project import read_proposed, read_start
    from fichero_server.recipes.answers import spend_cap
    from fichero_server.recipes.start import place_runs, plan_start
    from fichero_server.recipes.train_offers import counted, offered, train_ahead, train_offers

    library = _library(db)
    setup = read_project_setup(library)
    started, proposal = read_start(library), read_proposed(library)
    # A project keeps its pages on this Mac unless setup's answer said otherwise.
    stays_local = not places.may_leave_to(setup["answers"], "cloud")
    # Steps the last run did not finish stay in the plan, to run again (#5498).
    unfinished = runner.unfinished_steps(db) if started else {}
    # Before the first yes Start runs the whole recipe, the added layer with it; after it, only what an
    # added layer proposes for the material already there, and what did not finish.
    only = set(proposal["steps"]) | set(unfinished) if started and proposal else None
    from fichero_server.recipes.recipe import fit_overrides

    notes = fit_overrides(setup["recipe"]) if setup["recipe"] else []  # a kept choice never refuses Start (#6259)
    plan = plan_start(setup["recipe"], stays_local=stays_local, only=only,
                      job_answers=(setup["answers"] or {}).get("job_answers"), db=db)
    if first_pages is not None and folder_id:
        raise LookupError("Start takes a folder or the first pages, not both")
    within = runner.folder_scope(db, folder_id) if folder_id else set(_first_pages(db, first_pages)) if first_pages else None
    pages = material(db, within)
    memo: dict = {}  # what each step has done on each page, asked once for the estimate and the notes
    plan["estimate"] = _estimate_on(db, plan, pages, within, memo)
    plan["estimate"]["counted"] = pages["sentence"]
    place_runs(plan["runs"], pages["pages"], cloud_allowed=places.may_leave_to(setup["answers"], "acenet"),
               bound_cluster=_bound_cluster(setup["answers"], clusters),
               hf_allowed=places.may_leave_to(setup["answers"], "huggingface"),
               hf_cap_usd=spend_cap(setup["answers"]), hf_spent_usd=_hf_spent(db, setup["answers"]))
    # Pages whose originals are in iCloud, not on this Mac: warned of, with the offer to copy them in (#5669).
    from fichero_server.importers.keep_a_copy import summary as in_icloud

    plan["in_icloud"] = in_icloud(db, within, of=pages["pages"])
    if plan["in_icloud"] and not plan["in_icloud"]["room"]:
        plan["refusals"] = [*plan["refusals"], plan["in_icloud"]["refusal"]]
    plan["started"] = started
    plan["proposed"] = explain(setup["recipe"], proposal)
    plan["addable"] = addable_now(setup["answers"] or {})
    plan["left_off"] = [o["sentence"] for o in (setup["recipe"] or {}).get("left_off") or [] if o.get("sentence")]
    plan["folder_id"] = folder_id
    plan["notes"] = [*notes, *_reader_notes(plan["workflows"])]
    from fichero_server.recipes.train_offers import training_setting, training_stays_local

    from fichero_server.recipes.answers import spend_cap
    from fichero_server.recipes.project import read_noise_band

    cap = spend_cap(setup["answers"])
    # Training has its own place check (Hugging Face Jobs), the one auto-start uses too (#5841).
    train_local, train_why = training_stays_local(setup["answers"])
    setting = training_setting((setup["answers"] or {}).get("training"), mac_memory_gb=_this_machine_memory_gb(),
                               hf_configured=_hf_token_set(), stays_local=train_local, spend_cap=cap)
    from fichero_server.recipes.train_offers import held_after_failure

    held = held_after_failure(db) if setting["mode"] == "here" else None
    if held:  # the last training here failed: said on the plan, where the person looks (#5440)
        setting = {**setting, "why": held}
    every_offer = train_offers(setup["recipe"], counted(db), stays_local=train_local, setting=setting,
                               spend_cap=cap, clusters=clusters, noise_band=read_noise_band(library), stays_why=train_why)
    plan["train_offers"] = offered(every_offer)
    plan["train_ahead"] = train_ahead(every_offer)
    from fichero_server.recipes.train_offers import spend_this_month

    plan["hf_spend"] = spend_this_month(db, cap=cap)
    from fichero_server.llm import spend as cloud_spend

    cloud_models = [(str(w.get("provider_override") or ""), str(w.get("model_override") or ""))
                    for w in plan["workflows"] if str(w.get("runs_on")).startswith("cloud") and w.get("model_override")]
    plan["cloud_cap"] = cloud_spend.plan_line(str(library), estimate_usd=plan["estimate"].get("total_cost_usd"),
                                              cloud_models=cloud_models, pages=plan["estimate"]["pages"])
    if plan["cloud_cap"]["over"] and not folder_id:
        plan["cloud_cap"]["fewer_pages"] = _first_pages_that_fit(db, plan, plan["cloud_cap"], plan["estimate"]["pages"])
    _cap_refusals(plan)
    plan["step_choices"] = _step_choices_of(setup, may_leave=places.may_leave_to(setup["answers"], "cloud"),
                                            pages=plan["estimate"].get("pages"), clusters=clusters)
    plan["bakeoff_offer"] = _bakeoff_offer(db, setup, pages["pages"])
    if within is not None and not pages["pages"]:
        plan["refusals"] = [*plan["refusals"], "the folder has no pages to run on"]
    elif within is None and not pages["pages"]:
        # Nothing to run on: said, not run (seen 2026-10-11, a Start whose material never arrived ran every step
        # on nothing and failed each, "not run on 1 of 0 folders").
        plan["refusals"] = [*plan["refusals"], NO_MATERIAL]
    annotate(db, plan, unfinished, within, memo=memo)
    return plan


def _as_started(db: Database, plan: dict[str, Any], first_pages: Optional[int] = None) -> dict[str, Any]:
    """The plan as Start started it (#5498): its runs, workflows and skipped steps are the queued run's, so the
    response's `started.workflows` and `runs` name the same thing, never the plan for next time."""
    from fichero_server.recipes import runner
    from fichero_server.recipes.done import annotate
    from fichero_server.recipes.start import estimate

    job_id = (plan.get("started") or {}).get("job_id")
    if not job_id:
        return plan
    started = runner.started_plan(db, job_id)
    # The menus are for choosing before Start; the run has begun, and on a big catalogue of models they made this answer
    # grow past what an agent's tool result holds (73 KB in a full run, #5707).
    plan["step_choices"] = []
    plan["runs"], plan["skipped"] = started["runs"], started["skipped"]
    plan["workflows"] = [r for r in plan["runs"] if r["card"] == "workflow"]
    counted = plan["estimate"].get("counted")
    within = (runner.folder_scope(db, plan["folder_id"]) if plan.get("folder_id")
              else set(_first_pages(db, first_pages)) if first_pages else None)  # the run's own pages (#6295)
    from fichero_server.recipes.done import material, todo_counts

    memo: dict = {}
    plan["estimate"] = {**estimate(plan["workflows"], plan["estimate"]["pages"], catalogue=_catalogue_runs(plan["runs"]),
                                   folders=_folders_covering(db, material(db, within)["ids"]),
                                   todo=todo_counts(db, plan, within, set(started["redo"]), memo=memo)), "counted": counted}
    return annotate(db, plan, within=within, redo=set(started["redo"]), memo=memo)  # its notes say what it redoes (#5689)


_OFFER_SECONDS = 5.0
_offers: dict[tuple, tuple[float, dict | None]] = {}


def _bakeoff_offer(db: Database, setup: dict, volume: int) -> dict | None:
    """`_compute_bakeoff_offer`, kept five seconds: it scans every pass of the project, and the Start sheet polls
    the plan. ponytail: a timed keep, not a change token (none exists); a correction shows within five seconds."""
    import json
    import time

    key = (id(db), json.dumps(setup["answers"], sort_keys=True, default=str), volume)
    kept = _offers.get(key)
    if kept and time.monotonic() - kept[0] < _OFFER_SECONDS:
        return kept[1]
    if len(_offers) > 32:
        _offers.clear()
    offer = _compute_bakeoff_offer(db, setup, volume)
    _offers[key] = (time.monotonic(), offer)
    return offer


def _compute_bakeoff_offer(db: Database, setup: dict, volume: int) -> dict | None:
    """The comparison of readers, offered on the plan with its cost first (`reader-measured-before-bulk`): only for a
    recipe that has a reading step and answers; Start never runs it."""
    answers = setup["answers"]
    if not answers or not any(s.get("job") == "read-a-line" for s in (setup["recipe"] or {}).get("steps") or []):
        return None
    bakeoff = _bakeoff()
    a = _answers(answers)
    run = bakeoff.next_run(db, a, known_cards(a, include_not_built=True), volume=a.pages or volume)
    ready = bakeoff.readiness(*[bakeoff.ground_truth(db, None)[0], bakeoff.unmarked_import_pages(db)])
    return {"sentence": run["sentence"], "run_cost_usd": run["run_cost_usd"], "pages": run["pages"],
            "ready": ready["ready"], "readiness_sentence": ready.get("sentence")}


@router.get("/project/start", response_model=StartPlan,
            openapi_extra={"x-fichero-agent-defaults": {"summary": True}})
async def get_start_plan(
    http: Request,
    folder_id: Optional[str] = Query(default=None, description=(
        "plan Start on this folder alone: its live pages, its folders inside it included "
        "(source.recipe.folder-scoped-start); omit for the whole project")),
    first_pages: Optional[int] = Query(default=None, ge=1, description=(
        "plan Start on the first N pages of the project in Finder order (\"run fewer pages\", #6295); never with `folder_id`")),
    summary: bool = Query(False, description=(
        "a lean answer for an agent: each step's candidates are its picked and recommended ones (else its first), "
        "not the whole menu, which grows with the models this Mac has; the whole plan is this GET without it "
        "(openapi.mcp.answers-fit-an-agent)")),
    db: Database = Depends(get_library_database),
) -> StartPlan:
    """What Start would run on this project, or on one folder of it, with the estimate, before anything runs
    (`source.onboard.estimate-before-start`). 422 for a folder not in the project."""
    try:
        # Off the loop: the plan reads every page's lines (variant A's price) and waits on the database's gate.
        plan = await asyncio.to_thread(lambda: _start_plan(db, folder_id, clusters=_cluster_names(http), **_only_if_set(first_pages=first_pages)))
    except LookupError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if summary:
        for step in plan.get("step_choices") or []:
            cands = step.get("candidates") or []
            step["candidates"] = [c for c in cands if c.get("picked") or c.get("recommended")] or cands[:1]
    return StartPlan(**plan)


class StartParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    withdraw: bool = Field(default=False, description="take the first yes back (undo)")
    redo: list[str] = Field(default_factory=list, description="step ids to run again on pages that already have "
                            "their output (`source.recipe.done-is-not-redone`)")
    folder_id: Optional[str] = Field(default=None, description="run on this folder alone "
                                     "(`source.recipe.folder-scoped-start`); null: the whole project")
    documents: Optional[list[str]] = Field(default=None, description="run on these pages alone, as a run's `missed` "
                                           "names them (#6170); never with `folder_id`")
    clusters: list[str] = Field(default_factory=list, description="the clusters set up here that the person pressing "
                                "Start may use, by name (the route's own, owner-only): the project's cluster binds "
                                "only to one of them")
    first_pages: Optional[int] = Field(default=None, ge=1, description="run on the first N pages of the project in "
                                       "Finder order alone (#6295); never with `folder_id` or `documents`")


class StartRequest(BaseModel):
    """What the person asks of Start, beyond the yes."""

    model_config = ConfigDict(extra="forbid")
    redo: list[str] = Field(default_factory=list, description="step ids to run again on pages that already have "
                            "their output; the others run only on pages that do not")
    folder_id: Optional[str] = Field(default=None, description=(
        "run the whole recipe on this folder alone: its live pages, its folders inside it included "
        "(source.recipe.folder-scoped-start); null: the whole project"))
    documents: Optional[list[str]] = Field(default=None, description=(
        "run the recipe on these pages alone, as a finished run's `missed.documents` names them "
        "(source.recipe.run-again-on-what-was-missed, #6170); never with `folder_id`"))
    first_pages: Optional[int] = Field(default=None, ge=1, description=(
        "run the recipe on the first N pages of the project in Finder order alone (\"run fewer pages\", #6295); "
        "never with `folder_id` or `documents`"))
    accept_unpriced: list[str] = Field(default_factory=list, description=(
        "cloud models with no listed price, as `provider/model` (the plan's `cloud_cap.unpriced_models`) the person accepts running: "
        "counted at an assumed price and listed apart, and recorded in the project by the one accept action "
        "(`ai.where.accept-unpriced-cloud-model`)"))


def _cap_refusals(plan: dict) -> None:
    """The cap's one refusal: an estimate over what the cap leaves, asked before the run, not after the money is gone (#5987).
    A model with no listed price never refuses (#6259): the cap line lists it apart at the assumed price, and Start is the yes."""
    line = plan["cloud_cap"]
    if not line["over"]:
        return
    said = [f"This run is estimated at US${line['estimate_usd']:,.2f} of cloud spending"]
    if line["over_month"]:
        said.append(f"more than the US${line['remaining_usd']:,.2f} your project's monthly cap leaves this month "
                    f"(cap US${line['cap_usd']:,.2f} a month). Raise the monthly cap to US${line['needed_cap_usd']:,.2f}")
    if line["over_project"]:
        said.append(f"more than the US${line['project_remaining_usd']:,.2f} your project's total cap leaves (cap US${line['project_cap_usd']:,.2f} "
                    f"in all). Raise the project cap to US${line['needed_project_cap_usd']:,.2f}")
    fewer = f", or run the first {line['fewer_pages']} pages" if line.get("fewer_pages") else ", or run fewer pages"
    line["refusal"] = ", ".join(said[:1]) + ": " + "; and ".join(said[1:]) + f"{fewer}, or choose a cheaper model."
    plan["refusals"] = [*plan["refusals"], line["refusal"]]


#: Start's refusal for a project with nothing in it, declared as its 422 sentence (#5813, ruled 2026-10-19).
NO_MATERIAL = "This project has no material yet: add your pages in Set Up › Your Material, then press Start."


def _accept_asked(db: Database, accepted: list[str], folder_id: Optional[str], clusters: list[str], ctx: ActionContext) -> None:
    """Start's yes to the cloud models with no listed price it names: the ones sent (`StartRequest.accept_unpriced`), else
    every one the plan lists, since pressing Start is the yes (#6259), taken before Start's own action so it outlives a refused Start
    (`ai.where.accept-unpriced-cloud-model`). Each by `cloud.accept_unpriced`, the one accept action.
    Only a model the plan names can be accepted here."""
    try:
        plan = _start_plan(db, folder_id, clusters=clusters)
    except LookupError as exc:  # a folder not in the project
        raise ValueError(str(exc)) from exc
    asked = set(plan["cloud_cap"]["unpriced_models"]) if plan.get("cloud_cap") else set()
    unknown = [m for m in accepted if m not in asked]
    if unknown:  # a request naming a model the plan never asked about is wrong whether or not Start is refused
        raise ValueError(f"Start did not ask about {', '.join(unknown)}: only the cloud models it names can be accepted.")
    for key in accepted or sorted(asked):
        provider, _, model = key.partition("/")
        registry.invoke(db, "cloud.accept_unpriced", {"provider": provider, "model": model}, ctx)


@router.post("/project/start", response_model=StartPlan, responses={422: {
    "model": _ErrorDetail,
    "description": ("Start is refused, in one sentence: the project has no material yet (`NO_MATERIAL`), a folder "
                    "not in the project or with no pages, or the plan's refusals (a recipe that fails the check, "
                    "nothing to run).")}})
async def start_project(
    http: Request,
    request: Optional[StartRequest] = None,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> StartPlan:
    """The first yes: record that the person pressed Start, on which recipe version (audited,
    undoable), and run the recipe over the project's material as one `run-a-recipe` job
    (`source.recipe.start-runs-the-steps`): its runnable steps in order, the skipped ones named with why.
    Refused with 422 while the plan has refusals (a recipe that fails the check, or nothing to run).
    With `folder_id`, the run covers that folder's live pages alone, and a folder not in the project, or one
    with no pages, is refused with 422 (`source.recipe.folder-scoped-start`).
    The response is the plan as started: its `runs` and `workflows` are the run's, as `started.workflows` is."""
    folder_id = request.folder_id if request else None
    try:
        # The yes to a cloud model with no price is its own audited action, taken BEFORE Start's: inside Start's
        # transaction a refused Start would roll the audit row back and leave the acceptance kept without it.
        clusters = _cluster_names(http)

        if request and request.documents is not None and folder_id:  # said first: the accept's plan would call the folder unknown
            raise ValueError("Start takes a folder or some pages, not both")
        if request and request.first_pages and (folder_id or request.documents is not None):
            raise ValueError("Start takes the first pages, a folder, or some pages: one of them")

        def accept_then_start() -> None:  # the accept builds the Start plan: off the loop with the start (#6178)
            _accept_asked(db, request.accept_unpriced if request else [], folder_id, clusters, ctx)
            registry.invoke(db, "project.start", {"redo": request.redo if request else [], "folder_id": folder_id,
                                                  "documents": request.documents if request else None,
                                                  "first_pages": request.first_pages if request else None,
                                                  "clusters": clusters}, ctx)

        await asyncio.to_thread(accept_then_start)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    clusters = _cluster_names(http)
    first = request.first_pages if request else None  # the answer describes the run queued, not the whole project (#6295)
    return StartPlan(**await asyncio.to_thread(lambda: _as_started(
        db, _start_plan(db, folder_id, clusters=clusters, **_only_if_set(first_pages=first)), first)))


class UseInsteadRequest(BaseModel):
    """Use an installed model instead of downloading the one the plan waits for (#5583), or the same model at a free
    place instead of on this Mac, which cannot run it (#5592). Exactly one of `card` and `provider`."""

    model_config = ConfigDict(extra="forbid")
    model: str = Field(description="the download the plan waits for, as its `downloads` names it (`model`), or the "
                       "model this Mac cannot run, as its `elsewhere` names it")
    card: str = Field("", description="the installed model's card id, as that download's `instead` names it")
    provider: str = Field("", description="the free place's provider row id, as that `elsewhere` entry's `instead` "
                          "names it")


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
    it does not offer instead. With `provider`: every step pinned to the model this Mac cannot run is set to the same
    model at that free place the plan offers (`elsewhere[].instead`), the same way; refused (422) for a place the
    plan does not offer, a paid one included (`ai.where.fallback-free-and-asked`)."""
    from fichero_server.core.timeutil import utc_now_iso
    from fichero_server.recipes.start import use_instead, use_place_instead

    if bool(request.card) == bool(request.provider):
        raise HTTPException(status_code=422, detail="send either an installed model's card or a place's provider")
    library = _library(db)
    setup = read_project_setup(library)
    now = utc_now_iso(timespec="seconds")
    if request.provider:
        try:
            recipe = use_place_instead(setup["recipe"], (await asyncio.to_thread(_start_plan, db))["elsewhere"], request.model,
                                       request.provider, now=now)
            result = registry.invoke(db, "project.save_setup", {"answers": setup["answers"], "recipe": recipe}, ctx)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return _whole_setup(result.result)
    card = next((c for c in known_cards(include_not_built=True) if c.id == request.card), None)
    if card is None:
        raise HTTPException(status_code=422, detail="that model is not one Fichero has a card for")
    try:
        recipe = use_instead(setup["recipe"], (await asyncio.to_thread(_start_plan, db))["downloads"], request.model, card, now=now)
        result = registry.invoke(db, "project.save_setup", {"answers": setup["answers"], "recipe": recipe}, ctx)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _whole_setup(result.result)


class StepPlaceRequest(BaseModel):
    """Where a reading step runs (`source.recipe.step-runs-on-huggingface`, #6173)."""

    model_config = ConfigDict(extra="forbid")
    step: str = Field(description="the recipe step's id (a reading step)")
    place: str = Field(description="`this-mac` or `huggingface-jobs`: the person's choice, kept on the step")


@router.post("/project/steps/place", response_model=ProjectSetup)
async def put_step_on_a_place(
    request: StepPlaceRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> ProjectSetup:
    """Put a reading step on Hugging Face Jobs, or back on this Mac, through `project.save_setup` (audited, undoable)
    (`source.recipe.step-runs-on-huggingface`). Choosing only records where it runs: Start sends pages only with the
    project's yes, the app's Hugging Face place and a monthly cap above $0. Refused (422) for a step the recipe lacks, a
    step that is not a reading, or another place."""
    from fichero_server.recipes.start import set_step_place

    setup = read_project_setup(_library(db))
    try:
        recipe = set_step_place(setup["recipe"], request.step, request.place)
        result = registry.invoke(db, "project.save_setup", {"answers": setup["answers"], "recipe": recipe}, ctx)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _whole_setup(result.result)


class UseCandidateRequest(BaseModel):
    """Set a found candidate as a step's reader (#5612)."""

    model_config = ConfigDict(extra="forbid")
    step: str = Field(description="the recipe step's id")
    card: str = Field(description="the candidate's card id, as GET /api/recipes/candidates lists it (`id`)")


@router.post("/project/steps/use-candidate", response_model=ProjectSetup)
async def use_candidate_for_step(
    request: UseCandidateRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> ProjectSetup:
    """Use this candidate for the step: any model the finder lists (shipped, installed, Kraken's repository or a
    Hugging Face reader an earlier search kept) becomes the step's reader, kept as a project-scope override by the
    path use-instead and Use This take, through `project.save_setup` (audited, undoable) (#5612,
    `source.find.app-card-actions`). A model still to download is then a download the Start plan offers. Refused
    (422) for a card Fichero does not know here, a step the recipe lacks, or a card that does not do its job."""
    from fichero_server.core.timeutil import utc_now_iso
    from fichero_server.recipes.start import use_candidate
    from fichero_server.recipes.step_choices import UNSURE_ID

    library = _library(db)
    setup = read_project_setup(library)
    try:
        a = _answers(setup["answers"]) if setup["answers"] else None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # The rules' cards, and the text models the finder offers a person beyond them (#5660 item 4) that can run.
    # And the keyed cloud correctors: Correct's offer at Ready is taken here (#5677). A text card shares a corrector's
    # id, so the card that does the step's job is the one taken.
    offered = _offered_cards(a)
    if request.card.startswith(UNSURE_ID):
        return await _use_unsure_correction(db, ctx, library, setup, request, offered)
    job = next((s.get("job") for s in (setup["recipe"] or {}).get("steps") or [] if s.get("id") == request.step), None)
    named = [c for c in offered if c.id == request.card]
    card = next((c for c in named if job in c.jobs), named[0] if named else None)
    if card is None:
        raise HTTPException(status_code=422, detail=f"{request.card} is not a model Fichero has found here: list "
                                                    "the candidates (online, to search) and choose one of them")
    try:
        recipe = use_candidate(setup["recipe"], request.step, card, now=utc_now_iso(timespec="seconds"))
        result = registry.invoke(db, "project.save_setup", {"answers": setup["answers"], "recipe": recipe}, ctx)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _whole_setup(result.result)


class UseReadersRequest(BaseModel):
    """Choose the readers Find where the readers disagree compares (#6121)."""

    model_config = ConfigDict(extra="forbid")
    step: str = Field(description="the Find where the readers disagree step's id")
    cards: list[str] = Field(description="two or more different readers' card ids, as GET /api/recipes/candidates lists them (`id`)")


@router.post("/project/steps/use-readers", response_model=ProjectSetup)
async def use_readers_for_step(
    request: UseReadersRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> ProjectSetup:
    """The readers to compare: the person's choice REPLACES the step's reader set (no reader the rules added is compared
    besides; the same model chosen twice counts once), kept as a project-scope override through `project.save_setup`
    (audited, undoable) (`source.disagree.person-chooses-the-readers`, #6121). Refused (422) for a step that is not Find
    where the readers disagree, a card Fichero does not know here or that does not read, or fewer than two different readers."""
    from fichero_server.core.timeutil import utc_now_iso
    from fichero_server.recipes.start import use_readers

    library = _library(db)
    setup = read_project_setup(library)
    try:
        a = _answers(setup["answers"]) if setup["answers"] else None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    offered = _offered_cards(a)
    cards = []
    for card_id in request.cards:
        named = [c for c in offered if c.id == card_id]
        card = next((c for c in named if "read-a-page" in c.jobs or "read-a-line" in c.jobs), named[0] if named else None)
        if card is None:
            raise HTTPException(status_code=422, detail=f"{card_id} is not a model Fichero has found here")
        cards.append(card)
    try:
        recipe = use_readers(setup["recipe"], request.step, cards, now=utc_now_iso(timespec="seconds"))
        result = registry.invoke(db, "project.save_setup", {"answers": setup["answers"], "recipe": recipe}, ctx)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _whole_setup(result.result)


async def _use_unsure_correction(db: Database, ctx: ActionContext, library: Path, setup: dict[str, Any],
                                 request: "UseCandidateRequest", offered: list[Any]) -> ProjectSetup:
    """`corrects-unsure:<cloud card>` on the READ step (`source.recipe.kraken-reads-cloud-corrects-unsure`): Kraken stays the reader and
    Correct is turned on (Set Up's own answer) with that card, which then corrects only the lines under Set Up's certainty bar. One
    saved setup, so one audited, undoable choice; no new request field."""
    from fichero_server.core.timeutil import utc_now_iso
    from fichero_server.recipes.assemble import CORRECT_QUESTION
    from fichero_server.recipes.start import use_candidate
    from fichero_server.recipes.step_choices import (CORRECT_WAS_ON_FIELD, UNSURE_BECAUSE, UNSURE_FIELD, UNSURE_ID, _kraken,
                                                          _person_override)

    recipe = setup["recipe"] or {}
    step = next((st for st in recipe.get("steps") or [] if st.get("id") == request.step), None)
    if step is None or step.get("job") != "read-a-line" or not _kraken(step):
        raise HTTPException(status_code=422, detail="Kraken then a cloud correction is a way to use Kraken's lines: "
                                                    "choose it on the step where Kraken reads")
    wanted = request.card[len(UNSURE_ID):]
    card = next((c for c in offered if c.id == wanted and str(c.runs_on).startswith("cloud:") and "correct" in c.jobs), None)
    if card is None:
        raise HTTPException(status_code=422, detail=f"{wanted} is not a cloud model Fichero has found here to correct with")
    was_on = (setup["answers"].get("job_answers") or {}).get(CORRECT_QUESTION) is True  # the person's own answer, kept on take-back
    answers = {**setup["answers"], "job_answers": {**(setup["answers"].get("job_answers") or {}), CORRECT_QUESTION: True}}
    correct = next((st.get("id") for st in recipe.get("steps") or [] if st.get("job") == "correct"), "correct")
    kept = [copy.deepcopy(o) for o in recipe.get("overrides") or [] if o is not _person_override(recipe, correct)]
    try:
        fresh = await asyncio.to_thread(_assemble, answers, library, overrides=kept)
        fresh["overrides"] = kept
        new_correct = next((st.get("id") for st in fresh.get("steps") or [] if st.get("job") == "correct"), None)
        if new_correct is None:
            raise ValueError("Set Up leaves Correct out for this project, so a model cannot be set to correct")
        fresh = use_candidate(fresh, new_correct, card, now=utc_now_iso(timespec="seconds"), because=UNSURE_BECAUSE,
                             extra={UNSURE_FIELD: True, CORRECT_WAS_ON_FIELD: was_on})
        result = registry.invoke(db, "project.save_setup", {"answers": answers, "recipe": fresh}, ctx)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _whole_setup(result.result)


class UseSetupPickRequest(BaseModel):
    """Take a step back to Set Up's pick."""

    model_config = ConfigDict(extra="forbid")
    step: str = Field(description="the recipe step's id")


@router.post("/project/steps/use-setup-pick", response_model=ProjectSetup)
async def use_setup_pick_for_step(
    request: UseSetupPickRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> ProjectSetup:
    """Take the person's choice for the step back (`source.onboard.step-choice-overrides-the-pick`): the recipe is
    assembled again from the project's answers with that one choice dropped, so Set Up's pick stands for the step; the
    project's other choices stay. Saved through `project.save_setup` (audited, undoable). Refused (422) for a step the
    recipe lacks, or one already on Set Up's pick."""
    from fichero_server.recipes.assemble import CORRECT_QUESTION
    from fichero_server.recipes.step_choices import _person_override, overrides_without, unsure_card, unsure_set_correct_on

    library = _library(db)
    setup = read_project_setup(library)
    answers = setup["answers"]
    try:
        recipe0 = setup["recipe"] or {}
        step = next((st for st in recipe0.get("steps") or [] if st.get("id") == request.step), None)
        if step is not None and step.get("job") == "read-a-line" and unsure_card(recipe0):
            # Taking the read step back drops ITS override too (a cloud reader chosen after the unsure choice goes), and the unsure
            # choice with it: Correct as Set Up had it (its answer off again only when the choice itself turned it on).
            correct = next(st["id"] for st in recipe0["steps"] if st.get("job") == "correct")
            drop = (_person_override(recipe0, correct), _person_override(recipe0, request.step))
            kept = [copy.deepcopy(o) for o in recipe0.get("overrides") or [] if not any(o is d for d in drop)]
            if unsure_set_correct_on(recipe0):
                answers = {**answers, "job_answers": {k: v for k, v in (answers.get("job_answers") or {}).items() if k != CORRECT_QUESTION}}
        else:
            kept = overrides_without(setup["recipe"], request.step)
        recipe = await asyncio.to_thread(_assemble, answers or {}, library, overrides=kept)
        recipe["overrides"] = kept
        result = registry.invoke(db, "project.save_setup", {"answers": answers, "recipe": recipe}, ctx)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _whole_setup(result.result)


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
        if params.documents is not None and params.folder_id:
            raise ValueError("Start takes a folder or some pages, not both")
        if params.first_pages and (params.folder_id or params.documents is not None):
            raise ValueError("Start takes the first pages, a folder, or some pages: one of them")
        if params.documents is not None:
            from fichero_server.recipes.done import pages_for

            # An import run's documents are the imported top-level ones: a PDF or a cut photograph is the
            # project's through its pages (importers/derivatives.py).
            project = set(pages_for(db, {}, None))
            from fichero_server.models import Document

            if any(getattr(d.doc_type, "value", d.doc_type) == "folder"
                   for d in (db.get(Document, i) for i in params.documents) if d):
                raise ValueError("a folder goes in folder_id, not in documents")
            if stray := [d for d in params.documents if d not in project
                         and not set(pages_for(db, {}, [d])) <= project]:
                raise ValueError(f"{len(stray)} of those pages are not in the project")
        try:
            plan = _start_plan(db, params.folder_id, clusters=params.clusters, **_only_if_set(first_pages=params.first_pages))
        except LookupError as exc:  # a folder not in the project
            raise ValueError(str(exc)) from exc
        if NO_MATERIAL in plan["refusals"]:  # said alone: nothing else matters until there is material (#5813)
            raise ValueError(NO_MATERIAL)
        if plan["refusals"]:
            raise ValueError("Start is refused: " + "; ".join(plan["refusals"]))
        from fichero_server.recipes import runner
        from fichero_server.recipes.start import queue_downloads

        recipe = read_project_setup(library)["recipe"] or {}
        runner.register_job_kinds()
        # Start fetches what its steps need (#5664): each download queued now, and the run's steps on it wait.
        queue_downloads(db, plan, started_by=started_by_for(ctx))
        record = {
            "started_at": utc_now_iso(timespec="seconds"),
            "recipe_id": recipe.get("id"),
            "recipe_version": recipe.get("version"),
            "workflows": [w["workflow"] for w in plan["workflows"]],
            "pages": plan["estimate"]["pages"],
            "job_id": runner.enqueue(db, plan, documents=_first_pages(db, params.first_pages) if params.first_pages else params.documents,
                                     first_pages=params.first_pages, started_by=started_by_for(ctx), redo=params.redo,
                                     folder_id=params.folder_id),
            "folder_id": params.folder_id,
        }
        # Start runs what an added layer proposed (source.onboard.add-layer): the proposal is done with.
        from fichero_server.recipes.project import write_proposed

        write_proposed(library, None)
        # Moves Set Up held finish now (#6245), read before the first yes is written.
        from fichero_server.recipes.project import finish_held_moves, holds_moves

        if holds_moves(library):
            finish_held_moves(db)
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
    http: Request,
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
    return StartPlan(**await asyncio.to_thread(_start_plan, db, clusters=_cluster_names(http)))


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


class FolderStepDone(BaseModel):
    steps: list[str]
    done: Optional[int] = Field(default=None, description="its pages done in the folder; null: the step cannot tell")
    of: int = Field(description="the pages it works on in the folder, those left out (blank, a recording) not counted")


class FolderStepsDone(BaseModel):
    folder_id: str
    steps: list[FolderStepDone]


class RecipeRunStatus(BaseModel):
    job_id: str
    state: str
    reason: Optional[str] = None
    documents: Optional[list[str]] = Field(default=None, description="the pages an import brought; none: all")
    folder_id: Optional[str] = Field(default=None, description=(
        "the folder the run covers; null: the whole project, or an import's pages (source.recipe.folder-scoped-start)"))
    folders_done: Optional[int] = Field(default=None, description=(
        "the folders every step has finished on (activity.run.progress-per-folder); null before the run started"))
    folders_total: Optional[int] = Field(default=None, description=(
        "the folders the run goes over, a batch at a time (source.recipe.batch-at-archive-scale); null before "
        "the run started"))
    folder_steps: list[FolderStepsDone] = Field(default_factory=list, description=(
        "each folder the run has counted, with each step's pages done there, current as each step ends on a batch "
        "(activity.run.folder-steps-done); a page in no folder is in none"))
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
    seconds: Optional[float] = Field(default=None, description=(
        "the run's time so far, from its row: ended (or now) less started; null before it started (#6215)"))
    stopped_at_cap: bool = Field(default=False, description=(
        "a step's run was paused at a cloud spend cap and has not gone on (#6295): the app offers the caps' change; `reason` "
        "then carries the cap's words. Resume goes on after the cap is raised"))
    stopped_needs_cap_usd: Optional[float] = Field(default=None, description=(
        "when `stopped_at_cap` at the monthly cap: the monthly cap under which the refused call would have been sent (booked this "
        "month plus the call's worst case, to the cent, no margin); the plan cannot say it, its estimate may fit (#6295)"))
    stopped_needs_project_cap_usd: Optional[float] = Field(default=None, description=(
        "when `stopped_at_cap` at the project's total cap: the total cap under which the refused call would have been sent"))
    pages_at_once: Optional[int] = Field(default=None, description=(
        "how many pages the run reads at once now, from the gate (recipes-run.memory.gate-shown); null when not running"))
    pages_at_once_reason: Optional[str] = Field(default=None, description=(
        "which hold makes it one page at a time, in words shown as sent; null when more than one may go"))
    threads_each: Optional[int] = Field(default=None, description=(
        "the torch threads the pages read on now, as the Kraken seam last set them (the cores the run's priority gives, "
        "split by the pages the plan lets in at once) (recipes-run.memory.threads-fill-the-cores, #6229); null when not running "
        "or no Kraken page is being read"))


class RecipeRuns(BaseModel):
    items: list[RecipeRunStatus]


class AutomaticWork(BaseModel):
    """One kind of work in what runs by itself."""

    job: Optional[str] = Field(description="the job kind (as Activity's rows name it); null for a recipe step skipped")
    name: str = Field(description="the work in words, or the skipped step's id")
    runs: bool = Field(description="whether it runs by itself")
    why: str = Field(description="why it runs or does not, in words, naming the setting that decides it")
    steps: list[str] = Field(default_factory=list, description="the recipe steps it carries out, if any")


class WhatRunsByItself(BaseModel):
    on_add: list[AutomaticWork] = Field(description="what runs on the pages an import brings")
    on_correction: list[AutomaticWork] = Field(description="what runs on a page whose text a person corrects")


@router.get("/project/automatic", response_model=WhatRunsByItself)
async def what_runs_by_itself(db: Database = Depends(get_library_database)) -> WhatRunsByItself:
    """What runs by itself in this project, on an import and on a correction (#5362,
    `activity.auto.what-runs-by-itself`): each kind of work, whether it runs and why, read from the same
    gates the import and the correction use. Reads only."""
    from fichero_server.recipes import runner

    return WhatRunsByItself(**runner.what_runs_by_itself(db))


@router.get("/project/runs", response_model=RecipeRuns)
@single_flight
async def recipe_runs(db: Database = Depends(get_library_database)) -> RecipeRuns:
    """The project's recipe runs, newest first: Start's, and one for each import after it. Each stage that is a
    workflow run carries its run account (pages done, failed and left, time left, what it waits for; #5576)."""
    from fichero_server.recipes import runner
    from fichero_server.recipes.run_view import with_accounts

    # Off the loop (#6178): the runs' rows wait on the transaction gate behind a run's write.
    return RecipeRuns(items=[RecipeRunStatus(**await with_accounts(db, r)) for r in await asyncio.to_thread(runner.runs, db)])


@router.get("/project/runs/{job_id}", response_model=RecipeRunStatus)
@single_flight
async def recipe_run_status(job_id: str, db: Database = Depends(get_library_database)) -> RecipeRunStatus:
    """A started recipe's run: each card's state and its own job (a workflow stage with its run account), the
    steps it skipped with why and their fixes, and what it waits for now (#5576)."""
    from fichero_server.recipes import runner
    from fichero_server.recipes.run_view import with_accounts

    try:
        return RecipeRunStatus(**await with_accounts(db, await asyncio.to_thread(runner.status, db, job_id)))  # off the loop (#6178)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/project/runs/{job_id}/summary", response_model=RecipeRunSummary)
@single_flight
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
    step: Literal["read-a-line", "find-lines"] = Field(default="read-a-line", description=(
        "which step's models to compare: the readers (each scored by CER and WER against the checked text), or the "
        "line finders (each scored by how many checked lines it finds) (#5660 item 7)"))
    named: list[str] = Field(default_factory=list, description=(
        "card ids of readers the person named: each is asked a line, a region and a page at a time (#5722), "
        "whatever its score; the two best also are"))


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
    role: Literal["rule rank", "baseline for print", "contender"] = Field(description=(
        "why it takes part: a contender of its kind (at most two of each: Kraken, Apple Vision, an MLX vision model, a "
        "cloud reader; ruled 2026-10-11, no fixed ranking), or the print baseline. 'rule rank' only in a bake-off "
        "kept from before"))
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
    wer: Optional[float] = Field(default=None, description="a reader's word error rate over the pages it read (#5660)")
    lines_found: Optional[int] = Field(default=None, description="a line finder: the checked lines it found")
    granularity: Optional[Literal["lines", "region", "page"]] = Field(default=None, description=(
        "how a vision model was asked (#5722): a line, a region or the whole page a request; one row for each way it "
        "was asked. None: a reader that reads a line at a time by nature"))
    lines_per_request: Optional[int] = Field(default=None, description="its card's limit on lines in one request")
    lines_checked: Optional[int] = Field(default=None, description="a line finder: the checked lines on the pages")
    extra_lines: Optional[int] = Field(default=None, description="a line finder: its lines that match no checked one")


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
    winner_granularity: Optional[Literal["lines", "region", "page"]] = Field(default=None, description=(
        "how the winner was asked, when it is a vision model (#5722)"))
    no_winner_why: Optional[str] = Field(default=None, description="when the job has finished with no winner, why, in "
                                         "words: only one reader could be compared, or no reader read these pages")
    recommendation: Optional[BakeoffRecommendation] = Field(default=None, description=(
        "Set Up's recommendation from the measured rows, frontier models weighed with the local ones (#5922); none "
        "while scoring or with no winner"))


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


class BakeoffContender(BaseModel):
    """A reader that would take part in a bake-off started now, and what reading the sample would cost."""

    card: str
    name: str = ""
    role: str
    runs_on: str
    local: bool
    not_scored: Optional[str] = Field(default=None, description="why it would be listed but not scored")
    run_cost_usd: Figure = Field(description="reading the sample pages: nothing on this Mac, the price list in the "
                                 "cloud")


class BakeoffNextRun(BaseModel):
    """Who would take part in a bake-off started now and what it would cost, said before it starts (ruled
    2026-10-11): at most two readers of each kind, from what the finder found."""

    candidates: list[BakeoffContender]
    pages: int = Field(description="the sample pages it would read")
    run_cost_usd: float = Field(description="the cloud readers' cost on the sample; 0 when every reader is local")
    granularity_run_cost_usd: float = Field(default=0.0, description=(
        "at most what asking the best readers a line, a region and a page at a time adds (#5722); 0 when free"))
    cost_known: bool = Field(description="false when a cloud reader's price is not known: the total is a lower bound")
    sentence: str


class BakeoffList(BaseModel):
    items: list[BakeoffResult]
    readiness: BakeoffReadiness
    next_run: Optional[BakeoffNextRun] = Field(default=None, description=(
        "who would take part in a bake-off started now and what it would cost; null before setup"))


class BakeoffUseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    card: str = Field(description="the candidate's card id")
    scope: Literal["project", "folder"] = Field(default="project", description='Where the choice applies: the whole project, or one folder.')
    folder_id: Optional[str] = Field(default=None, description="the folder, when the scope is a folder")
    granularity: Optional[Literal["lines", "region", "page"]] = Field(default=None, description=(
        "a vision model measured at several granularities is used at this one (#5722); none: its best row's"))


def _bakeoff() -> Any:
    from fichero_server.recipes import bakeoff  # loaded on first use (#3950)

    return bakeoff


@router.post("/project/bakeoffs", response_model=BakeoffResult, response_model_by_alias=True)
async def start_bakeoff(
    request: Optional[BakeoffStartRequest] = None,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> BakeoffResult:
    """Compare the readers on the project's corrected sample pages: at most two of each kind from what the finder
    found (Kraken, Apple Vision, an MLX vision model from this Mac or Hugging Face, a cloud reader at the person's
    remote endpoints where pages may leave; ruled 2026-10-11, no fixed ranking: the measured best wins; a kind that
    cannot read here is listed with why; `GET` says who and the cost first), and Tesseract for print when it has the
    language,
    each scored by CER and WER by the evaluation job (`evaluation.run`, audited) on the same pages. With
    `step: find-lines`, the line finders instead, each scored by how many checked lines it finds (a
    `compare-line-finders` job). Refused (422) in words, with nothing run, below 100 corrected lines on two pages
    (saying how many more), for a project not set up, or when no candidate can be scored on this Mac."""
    from fichero_server.core.timeutil import utc_now_iso
    from fichero_server.recipes.start import count_pages

    library = _library(db)
    setup = read_project_setup(library)
    if not setup["answers"]:
        raise HTTPException(status_code=422, detail="this project has not been set up: run setup first")
    bakeoff = _bakeoff()
    if request is not None and request.step == "find-lines":
        try:
            record = bakeoff.start_lines(db, library, page_ids=request.page_ids or None,
                                         now=utc_now_iso(timespec="seconds"), started_by=started_by_for(ctx))
            return BakeoffResult(**bakeoff.result(db, library, record["id"]))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        a = _answers(setup["answers"])
        record = bakeoff.start(
            db, library, a, known_cards(a, include_not_built=True), page_ids=request.page_ids if request else None,
            volume=a.pages or count_pages(db), now=utc_now_iso(timespec="seconds"),
            named=request.named if request else None,
            run_evaluation=lambda params: registry.invoke(db, "evaluation.run", params, ctx).result["job_id"])
        return BakeoffResult(**bakeoff.result(db, library, record["id"]))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/project/bakeoffs", response_model=BakeoffList, response_model_by_alias=True)
async def list_bakeoffs(named: list[str] = Query(default_factory=list, description=(
        "card ids of readers the person wants compared: `next_run` counts them in whatever the cap on readers of "
        "a kind (#5718)")), db: Database = Depends(get_library_database)) -> BakeoffList:
    """Every bake-off kept in the project, newest first, each with its table (`source.try.kept-and-rerunnable`),
    and whether the project has enough corrected lines to run one now (`readiness`, counted as a start is)."""
    from fichero_server.recipes.start import count_pages

    bakeoff, library = _bakeoff(), _library(db)
    pages, _ = bakeoff.ground_truth(db, None)
    answers = read_project_setup(library)["answers"]
    next_run = None
    if answers:
        a = _answers(answers)
        next_run = BakeoffNextRun(**bakeoff.next_run(db, a, known_cards(a, include_not_built=True),
                                                    volume=a.pages or count_pages(db), named=named))
    return BakeoffList(items=[BakeoffResult(**bakeoff.result(db, library, r["id"]))
                              for r in bakeoff.list_records(library)],
                       readiness=BakeoffReadiness(**bakeoff.readiness(pages, bakeoff.unmarked_import_pages(db))),
                       next_run=next_run)


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
    bakeoff, library = _bakeoff(), _library(db)
    try:
        table = bakeoff.result(db, library, bakeoff_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    card = next((c for c in known_cards(include_not_built=True) if c.id == request.card), None)
    if card is None:
        raise HTTPException(status_code=422, detail="that reader is not one Fichero has a card for")
    if request.scope == "folder" and request.folder_id:  # a folder override runs on that folder's pages (#6135)
        from fichero_server.recipes.runner import folder_scope

        try:
            folder_scope(db, request.folder_id)
        except LookupError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    setup = read_project_setup(library)
    try:
        recipe = bakeoff.use_this(setup["recipe"], table, card, scope=request.scope, folder_id=request.folder_id,
                                  now=utc_now_iso(timespec="seconds"), granularity=request.granularity)
        result = registry.invoke(db, "project.save_setup", {"answers": setup["answers"], "recipe": recipe}, ctx)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _whole_setup(result.result)


class AcceptUnpricedRequest(BaseModel):
    """One cloud model with no listed price, which this project accepts running (or withdraws that yes)."""

    model_config = ConfigDict(extra="forbid")
    provider: str = Field(min_length=1, description="the provider row id of the cloud model")
    model: str = Field(min_length=1, description="the model id, as the refusal names it")
    withdraw: bool = Field(default=False, description="take the yes back: calls to it are refused again")


class AcceptedUnpriced(BaseModel):
    accepted: list[str] = Field(description="every `provider/model` this project accepts running without a listed price")


def _was_accepted(db: Database, params: AcceptUnpricedRequest, ctx: ActionContext) -> bool:
    from fichero_server.llm import spend

    return spend.model_key(params.provider, params.model) in spend.accepted_models(_library(db))


def _put_accepted_back(db: Database, params: AcceptUnpricedRequest, ctx: ActionContext, was: bool) -> None:
    """The file is written inside the action, before its audit row commits: when the invocation then fails, just THIS key goes
    back to what it was (never the whole list, which would undo a concurrent accept of another model)."""
    from fichero_server.llm import spend

    spend.set_accepted(_library(db), params.provider, params.model, was)


@action("cloud.accept_unpriced", AcceptUnpricedRequest, domains=["project"],
        snapshot=_was_accepted, restore=_put_accepted_back)
def _action_accept_unpriced(db: Database, params: AcceptUnpricedRequest, ctx: ActionContext) -> tuple[dict, ChangeSpec]:
    from fichero_server.llm import spend

    library = _library(db)
    before = spend.accepted_models(library)
    kept = spend.set_accepted(library, params.provider, params.model, not params.withdraw)
    mark = {"provider": params.provider, "model": params.model, "withdraw": params.withdraw}
    return {"accepted": kept}, ChangeSpec(domains=["project"], target_ids=[], before={**mark, "withdraw": not params.withdraw,
                                          "accepted": before}, after={**mark, "accepted": kept}, emit_type="project.cloud_accepted")


@router.post("/cloud/accept-unpriced", response_model=AcceptedUnpriced)
async def accept_unpriced_cloud_model(
    request: AcceptUnpricedRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> AcceptedUnpriced:
    """Accept that this project runs one cloud model with no listed price (or take the yes back): its calls are counted at an
    assumed price and listed apart (`ai.where.accept-unpriced-cloud-model`). The one audited action every refused path names, and the
    one Start's yes uses; kept in the project, keyed by provider and model, not in Set Up's answers."""
    return AcceptedUnpriced(**registry.invoke(db, "cloud.accept_unpriced", request.model_dump(), ctx).result)
