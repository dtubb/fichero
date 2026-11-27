"""The response models of the recipe routes that other models are built from: what a try costs, where a step can run, and the
Start plan (#4951). Moved out of `recipes.py` unchanged so that file stays under its length cap (#6295)."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from fichero_server.recipes.cloud_cap import CloudCapLine
from fichero_server.recipes.run_view import SkippedStep


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


class PlaceOption(BaseModel):
    place: str = Field(description="this-mac, hf-jobs, cluster or provider")
    name: str = Field(description="this Mac, Hugging Face Jobs, the cluster's name, or the provider")
    can: bool
    needs: str = ""
    why: str = Field(default="", description="why it cannot run there, in words")
    blocked: str = Field(default="", description="why the app cannot send there yet, though the model could run there")


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
    seconds: Optional[float] = Field(default=None, description=(
        "how long the run takes on these `pages`: this Mac's median seconds a page for the step's model times the pages "
        "(`recipes-run.timing.plan-says-time-from-measured-pages`); null when the model has no finished page here or the run is in the "
        "cloud, never 0"))
    seconds_basis: Literal["measured", "unknown"] = Field(default="unknown", description="how `seconds` is known")
    seconds_words: Optional[str] = Field(default=None, description="`seconds` and its basis in words; the app words nothing itself")
    basis: str = Field(default="unpriced", description=(
        "how cost_usd is known: `free on this Mac`, `the model's listed rate`, `the batch price, answered within a "
        "day` (a step sent as one provider batch, #5940), or `unpriced` (a cluster or other "
        "place, or a model with no price): never a $0 for what is not known (#5590)"))
    basis_kind: Literal["measured", "assumed", "free", "unpriced"] = Field(default="unpriced", description=(
        "how `cost_usd` is known (`designer.budget.basis-per-step`): `measured` on this project's booked calls, `assumed` from the "
        "model's listed rate and a token assumption, `free` on this Mac, or `unpriced`"))
    basis_words: Optional[str] = Field(default=None, description=(
        'the basis in words: "16 pages × $0.021 a page, measured on 9 pages of this project"; the app words nothing itself'))
    cost_per_page_usd: Optional[float] = Field(default=None, description="`cost_usd` over `pages`; null when unpriced or free")
    measured_pages: Optional[int] = Field(default=None, description="with `measured`: the pages the figure rests on")
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
    from_tries: int = Field(default=0, description="pages whose readings came from a kept try, adopted as Start's first action: \"N pages came from your try\"")
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
