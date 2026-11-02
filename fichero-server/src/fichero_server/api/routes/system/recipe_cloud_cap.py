"""Routes taken out of `recipes.py`, which is over a thousand lines (#6295): the one that changes the project's cloud spend caps in
place (`ai.where.cloud-spend-cap`) and the bake-off's (#4951, `source.try.bakeoff-is-the-same-tool`). Registered under the same
`/api/recipes` prefix and tag, so the contract is as it was. One module, not two: each module is counted by the import budget."""

from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from fichero_server.actions.registry import ActionContext, registry, started_by_for
from fichero_server.api.auth import action_context
from fichero_server.api.main import get_library_database, get_library_database_for_write
from fichero_server.api.routes.document.format_import import ErrorDetail as _ErrorDetail
from fichero_server.api.routes.system.recipes import (
    BakeoffRecommendation, Figure, ProjectSetup, _answers, _bakeoff, _library, _whole_setup, known_cards, normalise_answers,
    read_project_setup)
from fichero_server.db import Database
from fichero_server.recipes.cloud_cap import CloudCapChange, CloudCapChanged

router = APIRouter(prefix="/recipes")


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

    from fichero_server.recipes.project import read_saved_answers  # lazy: it pulls recipes.recipe, jobs and topics into the app import (#5798)

    answers = read_saved_answers(_library(db))
    asked = {key: value for key, value in ((spend.CAP_KEY, request.cap_usd), (spend.PROJECT_CAP_KEY, request.project_cap_usd))
             if value is not None}
    try:
        # Only the caps are checked and written, over the answers as the file holds them: reading them in today's shape and
        # normalising them all wrote the defaults (`purposes: [not-sure]`, `materials: [handwriting]`) into a project that had
        # answered nothing.
        answers.update({key: normalise_answers(asked, strict=True)[key] for key in asked})
        if request.clear_project_cap:
            answers.pop(spend.PROJECT_CAP_KEY, None)
        done = registry.invoke(db, "project.save_setup", {"answers": answers}, ctx)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return CloudCapChanged(cap_usd=spend.cap_usd(str(_library(db))) or 0.0, project_cap_usd=spend.project_cap_usd(str(_library(db))),
                           audit_id=done.audit_id)

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


# =============================================================================
# The questions About the Material asks from the engine's own list (`designer.material.condition-asked`, #6052).
# =============================================================================


class ConditionQuestion(BaseModel):
    id: str
    name: str = Field(description="the condition's name, as the tick box says it")
    help: str = Field(description="what Fichero does about it, in one line")


class HowOption(BaseModel):
    id: str
    name: str
    consequence: str = Field(description="what choosing it means, in one sentence")
    allowed: bool = Field(description="false: shown greyed with the reason, never hidden")
    reason: Optional[str] = None


class HowQuestions(BaseModel):
    places: list[HowOption] = Field(description="Where should the work run? limited to the places Set Up Fichero allows")
    model_kinds: list[HowOption] = Field(description="Which kind of model? `compare` is the default")
    default_model_kind: str
    matters: list[str] = Field(description="What matters most? one of these")
    proposed_card: Optional[str] = Field(default=None, description="the route card (a to d) the answers sent propose; null when they say nothing")


class QuestionList(BaseModel):
    conditions: list[ConditionQuestion] = Field(description="the condition-of-the-pages tick boxes, in the order they are asked; none is ticked by default")
    how: HowQuestions = Field(description="How do you want to run this: the four questions (`designer.how.*`)")


@router.get("/questions", response_model=QuestionList)
async def questions(places: str = "", matters: str = "", pages: int = 0) -> QuestionList:
    """The one list the app asks About the Material and How from. It invents none (`designer.material.condition-asked`,
    `designer.how.*`). `places`, `matters` and `pages` are the answers so far, comma separated: the answer says the card they propose."""
    from fichero_server.recipes import derived, how as how_module, places as app_places  # lazy: the import budget counts a module per route file
    from fichero_server.recipes.condition import CONDITIONS

    allowed = app_places.get_places()
    said = {"places": [p for p in places.split(",") if p], "matters": matters or None}
    return QuestionList(
        conditions=[ConditionQuestion(id=i, name=n, help=h) for i, n, h in CONDITIONS],
        how=HowQuestions(
            places=[HowOption(**o) for o in how_module.offered_places(allowed)],
            model_kinds=[HowOption(**o) for o in how_module.model_kind_options(
                cloud_allowed=app_places.allows("cloud", allowed), memory_gb=derived.this_mac()["memory_gb"])],
            default_model_kind=how_module.DEFAULT_MODEL_KIND, matters=list(how_module.MATTERS),
            proposed_card=how_module.proposed_card(said, pages)))


class WhyOfDefault(BaseModel):
    why: str
    because: str = Field(description="the answers that chose it, e.g. 'faded, this mac'")


class RecipeDefaults(BaseModel):
    steps: list[str]
    prepare: list[str] = Field(description="the Prepare Images operations the answers choose")
    model_kind: str
    review: str = Field(description="off, on or unsure-lines")
    cap: str = Field(description="what the cap is proposed from (none, estimate, ...); a figure is shown, never written")
    rows: list[str] = Field(description="the table rows that chose these defaults")
    why: dict[str, WhyOfDefault] = Field(description="by default: the row's sentence and what chose it; a default with no entry says Fichero's usual default")


@router.get("/defaults", response_model=RecipeDefaults)
async def recipe_defaults(materials: str = "", condition: str = "", places: str = "", matters: str = "", pages: int = 0) -> RecipeDefaults:
    """The defaults the answers so far propose, each saying why (`designer.defaults.table`, `designer.defaults.says-why`). Reads, writes nothing."""
    from fichero_server.recipes import defaults  # lazy: the import budget counts a module per route file

    split = lambda text: [t for t in text.split(",") if t]  # noqa: E731
    got = defaults.resolve({"materials": split(materials), "condition": split(condition),
                            "how": {"places": split(places), "matters": matters or None}}, pages)
    return RecipeDefaults(**got)
